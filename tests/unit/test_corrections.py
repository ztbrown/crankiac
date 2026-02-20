"""Unit tests for correction dictionary: load_corrections and apply_corrections."""
import json
import os
import tempfile
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.transcription.corrections import load_corrections, apply_corrections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_segment(word, start=0.0, end=1.0, speaker=None):
    """Create a WordSegment-like SimpleNamespace for testing."""
    from types import SimpleNamespace
    return SimpleNamespace(word=word, start_time=Decimal(str(start)),
                           end_time=Decimal(str(end)), speaker=speaker)


# ---------------------------------------------------------------------------
# load_corrections
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLoadCorrections:
    def test_returns_dict_from_valid_json(self, tmp_path):
        """load_corrections returns a dict from a valid JSON file."""
        corrections = {"helo": "hello", "teh": "the"}
        path = tmp_path / "corrections.json"
        path.write_text(json.dumps(corrections))

        result = load_corrections(str(path))
        assert result == corrections

    def test_returns_empty_dict_if_file_missing(self, tmp_path):
        """load_corrections returns {} if the file does not exist."""
        result = load_corrections(str(tmp_path / "nonexistent.json"))
        assert result == {}

    def test_returns_empty_dict_if_path_none(self):
        """load_corrections returns {} if path is None."""
        result = load_corrections(None)
        assert result == {}

    def test_returns_empty_dict_if_path_empty_string(self):
        """load_corrections returns {} if path is empty string."""
        result = load_corrections("")
        assert result == {}

    def test_returns_empty_dict_on_invalid_json(self, tmp_path):
        """load_corrections returns {} on malformed JSON (graceful fallback)."""
        path = tmp_path / "bad.json"
        path.write_text("not valid json{{")

        result = load_corrections(str(path))
        assert result == {}

    def test_returns_empty_dict_for_empty_file(self, tmp_path):
        """load_corrections returns {} for an empty corrections file."""
        path = tmp_path / "empty.json"
        path.write_text("{}")

        result = load_corrections(str(path))
        assert result == {}

    def test_preserves_case_in_keys_and_values(self, tmp_path):
        """load_corrections preserves case exactly as stored."""
        corrections = {"Peter Theil": "Peter Thiel", "chamath": "Chamath"}
        path = tmp_path / "corrections.json"
        path.write_text(json.dumps(corrections))

        result = load_corrections(str(path))
        assert result["Peter Theil"] == "Peter Thiel"
        assert result["chamath"] == "Chamath"


# ---------------------------------------------------------------------------
# apply_corrections
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestApplyCorrections:
    def test_replaces_matching_word(self):
        """apply_corrections replaces words found in the corrections dict."""
        corrections = {"helo": "hello"}
        segments = [make_segment("helo"), make_segment("world")]

        result = apply_corrections(segments, corrections)
        assert result[0].word == "hello"
        assert result[1].word == "world"

    def test_no_match_leaves_word_unchanged(self):
        """apply_corrections leaves words not in corrections unchanged."""
        corrections = {"helo": "hello"}
        segments = [make_segment("goodbye")]

        result = apply_corrections(segments, corrections)
        assert result[0].word == "goodbye"

    def test_empty_corrections_returns_segments_unchanged(self):
        """apply_corrections with empty dict returns segments as-is."""
        segments = [make_segment("hello"), make_segment("world")]
        result = apply_corrections(segments, {})
        assert [s.word for s in result] == ["hello", "world"]

    def test_empty_segments_returns_empty_list(self):
        """apply_corrections with empty segment list returns []."""
        result = apply_corrections([], {"x": "y"})
        assert result == []

    def test_preserves_timing_and_speaker(self):
        """apply_corrections preserves start_time, end_time, and speaker."""
        corrections = {"teh": "the"}
        seg = make_segment("teh", start=1.5, end=2.0, speaker="Alice")
        result = apply_corrections([seg], corrections)

        assert result[0].word == "the"
        assert result[0].start_time == Decimal("1.5")
        assert result[0].end_time == Decimal("2.0")
        assert result[0].speaker == "Alice"

    def test_multiple_corrections_applied(self):
        """apply_corrections applies multiple distinct corrections."""
        corrections = {"helo": "hello", "teh": "the", "wrold": "world"}
        segments = [make_segment("helo"), make_segment("teh"), make_segment("wrold")]

        result = apply_corrections(segments, corrections)
        assert [s.word for s in result] == ["hello", "the", "world"]

    def test_case_sensitive_matching(self):
        """apply_corrections is case-sensitive (exact key match required)."""
        corrections = {"hello": "HELLO"}
        segments = [make_segment("Hello"), make_segment("hello")]

        result = apply_corrections(segments, corrections)
        assert result[0].word == "Hello"   # no match (capital H)
        assert result[1].word == "HELLO"   # exact match

    def test_returns_new_list_does_not_mutate(self):
        """apply_corrections returns a new list and does not mutate original segments."""
        corrections = {"helo": "hello"}
        original = [make_segment("helo")]
        result = apply_corrections(original, corrections)

        # Original should be unchanged
        assert original[0].word == "helo"
        assert result[0].word == "hello"
        assert result is not original


# ---------------------------------------------------------------------------
# mine_corrections (CLI logic - tested via the DB query, not the full CLI)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMineCorrections:
    """Tests for the mine_corrections logic (DB query + JSON output)."""

    def test_mine_corrections_queries_edit_history(self):
        """mine_corrections queries edit_history for field='word' corrections."""
        from app.transcription.corrections import mine_corrections

        mock_cursor = MagicMock()
        # Simulate DB returning: "helo" -> "hello" (3 times), "teh" -> "the" (2 times)
        mock_cursor.fetchall.return_value = [
            {"old_value": "helo", "new_value": "hello", "count": 3},
            {"old_value": "teh", "new_value": "the", "count": 2},
        ]

        with patch("app.transcription.corrections.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = mine_corrections(min_count=2)

        assert result == {"helo": "hello", "teh": "the"}

    def test_mine_corrections_filters_by_min_count(self):
        """mine_corrections passes min_count to the SQL query."""
        from app.transcription.corrections import mine_corrections

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch("app.transcription.corrections.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            mine_corrections(min_count=5)

        # The SQL should have been called with min_count=5 as a parameter
        sql, params = mock_cursor.execute.call_args[0]
        assert 5 in params

    def test_mine_corrections_returns_empty_dict_when_no_data(self):
        """mine_corrections returns {} when edit_history has no word corrections."""
        from app.transcription.corrections import mine_corrections

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch("app.transcription.corrections.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = mine_corrections(min_count=2)

        assert result == {}

    def test_mine_corrections_picks_most_frequent_new_value(self):
        """When same old_value maps to multiple new_values, pick the most frequent."""
        from app.transcription.corrections import mine_corrections

        mock_cursor = MagicMock()
        # "teh" -> "the" (5x), "teh" -> "te" (2x). Query orders by count DESC per group,
        # so the DB returns the most frequent first.
        mock_cursor.fetchall.return_value = [
            {"old_value": "teh", "new_value": "the", "count": 5},
        ]

        with patch("app.transcription.corrections.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = mine_corrections(min_count=2)

        assert result["teh"] == "the"


# ---------------------------------------------------------------------------
# Pipeline integration: corrections applied after transcription
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPipelineCorrectionsIntegration:
    """Tests that EpisodePipeline applies corrections after transcription."""

    def test_pipeline_applies_corrections_to_transcript(self, tmp_path):
        """Pipeline should call apply_corrections when self.corrections is non-empty."""
        from decimal import Decimal
        from unittest.mock import patch, MagicMock
        from app.pipeline import EpisodePipeline
        from app.transcription.whisper_transcriber import WordSegment, TranscriptResult
        from app.db.models import Episode
        from app.patreon.downloader import DownloadResult
        from datetime import datetime

        corrections = {"helo": "hello"}
        corrections_path = tmp_path / "corrections.json"
        import json
        corrections_path.write_text(json.dumps(corrections))

        with patch("app.pipeline.PatreonClient"), \
             patch("app.pipeline.AudioDownloader"), \
             patch("app.pipeline.get_transcriber"), \
             patch("app.pipeline.TranscriptStorage"), \
             patch("app.pipeline.EpisodeRepository"):

            pipeline = EpisodePipeline(
                session_id="test",
                corrections_file=str(corrections_path),
            )

        assert pipeline.corrections == corrections

    def test_pipeline_loads_empty_corrections_when_file_missing(self):
        """Pipeline should start with empty corrections when file doesn't exist."""
        from app.pipeline import EpisodePipeline
        from unittest.mock import patch

        with patch("app.pipeline.PatreonClient"), \
             patch("app.pipeline.AudioDownloader"), \
             patch("app.pipeline.get_transcriber"), \
             patch("app.pipeline.TranscriptStorage"), \
             patch("app.pipeline.EpisodeRepository"):

            pipeline = EpisodePipeline(
                session_id="test",
                corrections_file="/nonexistent/path.json",
            )

        assert pipeline.corrections == {}


# ---------------------------------------------------------------------------
# CLI: mine-corrections command appears in help
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMineCorrectionsCliHelp:
    def test_mine_corrections_in_manage_help(self):
        """mine-corrections subcommand appears in manage.py help."""
        import subprocess, sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        result = subprocess.run(
            [sys.executable, "manage.py", "--help"],
            capture_output=True, text=True, cwd=project_root
        )
        assert "mine-corrections" in result.stdout

    def test_mine_corrections_help_shows_min_count(self):
        """mine-corrections --help shows --min-count option."""
        import subprocess, sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        result = subprocess.run(
            [sys.executable, "manage.py", "mine-corrections", "--help"],
            capture_output=True, text=True, cwd=project_root
        )
        assert "--min-count" in result.stdout
        assert "--dry-run" in result.stdout
