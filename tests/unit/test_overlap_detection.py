"""TDD tests for Feature 4: Overlap Detection.

Tests for:
- TranscriptSegment.is_overlap model field
- assign_speakers_to_words() overlap detection logic
- TranscriptStorage.bulk_insert() is_overlap persistence
- TranscriptStorage.update_speaker_labels() is_overlap persistence
- TranscriptStorage.get_episode_paragraphs() has_overlap aggregation
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.db.models import TranscriptSegment
from app.transcription.diarization import SpeakerSegment, assign_speakers_to_words
from app.transcription.storage import TranscriptStorage


# ─── Model tests ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_transcript_segment_is_overlap_defaults_to_false():
    """TranscriptSegment.is_overlap should default to False."""
    seg = TranscriptSegment(
        id=1,
        episode_id=1,
        word="hello",
        start_time=Decimal("0.0"),
        end_time=Decimal("0.5"),
        segment_index=0,
    )
    assert seg.is_overlap is False


@pytest.mark.unit
def test_transcript_segment_is_overlap_can_be_set_true():
    """TranscriptSegment.is_overlap can be set to True."""
    seg = TranscriptSegment(
        id=1,
        episode_id=1,
        word="hello",
        start_time=Decimal("0.0"),
        end_time=Decimal("0.5"),
        segment_index=0,
        is_overlap=True,
    )
    assert seg.is_overlap is True


# ─── Diarization overlap detection tests ──────────────────────────────────────

def _make_word(start, end):
    """Helper: create a MagicMock word with timing and is_overlap attribute."""
    word = MagicMock()
    word.start_time = Decimal(str(start))
    word.end_time = Decimal(str(end))
    word.speaker = None
    word.is_overlap = False
    return word


@pytest.mark.unit
def test_overlap_not_detected_when_no_second_speaker():
    """A word with only one candidate speaker should not be flagged as overlap."""
    speaker_segments = [
        SpeakerSegment(speaker="A", start_time=Decimal("0.0"), end_time=Decimal("2.0")),
    ]
    word = _make_word(0.2, 0.8)
    result = assign_speakers_to_words([word], speaker_segments)
    assert result[0].speaker == "A"
    assert result[0].is_overlap is False


@pytest.mark.unit
def test_overlap_not_detected_when_second_speaker_overlap_too_small():
    """Second speaker overlap < 30% of word duration → not flagged."""
    # Word duration = 1.0s (0.0 → 1.0)
    # Speaker A overlaps 0.8s (80%), Speaker B overlaps 0.2s (20% < 30%) → no flag
    speaker_segments = [
        SpeakerSegment(speaker="A", start_time=Decimal("0.0"), end_time=Decimal("0.8")),
        SpeakerSegment(speaker="B", start_time=Decimal("0.8"), end_time=Decimal("2.0")),
    ]
    word = _make_word(0.0, 1.0)
    result = assign_speakers_to_words([word], speaker_segments)
    assert result[0].speaker == "A"
    assert result[0].is_overlap is False


@pytest.mark.unit
def test_overlap_not_detected_when_second_speaker_not_50pct_of_best():
    """Second speaker overlap < 50% of best overlap → not flagged."""
    # Word duration = 1.0s (0.0 → 1.0)
    # Speaker A overlaps 0.8s, Speaker B overlaps 0.3s (30% of duration ✓, but 37.5% of best < 50%) → no flag
    speaker_segments = [
        SpeakerSegment(speaker="A", start_time=Decimal("0.0"), end_time=Decimal("0.8")),
        SpeakerSegment(speaker="B", start_time=Decimal("0.7"), end_time=Decimal("2.0")),
    ]
    # A overlaps [0.0,0.8] ∩ [0.0,1.0] = 0.8s
    # B overlaps [0.7,1.0] = 0.3s  → 30% duration ✓, but 0.3/0.8 = 37.5% < 50% → no flag
    word = _make_word(0.0, 1.0)
    result = assign_speakers_to_words([word], speaker_segments)
    assert result[0].speaker == "A"
    assert result[0].is_overlap is False


@pytest.mark.unit
def test_overlap_detected_when_both_conditions_met():
    """Second speaker overlap >= 30% word duration AND >= 50% best overlap → flagged."""
    # Word duration = 1.0s (0.0 → 1.0)
    # Speaker A overlaps [0.0, 0.7] = 0.7s (best)
    # Speaker B overlaps [0.5, 1.0] = 0.5s  → 50% duration ✓, 0.5/0.7 = 71.4% >= 50% ✓ → OVERLAP
    speaker_segments = [
        SpeakerSegment(speaker="A", start_time=Decimal("0.0"), end_time=Decimal("0.7")),
        SpeakerSegment(speaker="B", start_time=Decimal("0.5"), end_time=Decimal("2.0")),
    ]
    word = _make_word(0.0, 1.0)
    result = assign_speakers_to_words([word], speaker_segments)
    assert result[0].speaker == "A"
    assert result[0].is_overlap is True


@pytest.mark.unit
def test_overlap_detected_at_exact_30pct_threshold():
    """Second speaker overlap exactly at 30% of word duration → flagged (boundary)."""
    # Word duration = 1.0s (0.0 → 1.0)
    # Speaker A overlaps 0.6s; Speaker B overlaps 0.3s → 30% duration ✓, 0.3/0.6 = 50% ✓ → OVERLAP
    speaker_segments = [
        SpeakerSegment(speaker="A", start_time=Decimal("0.0"), end_time=Decimal("0.6")),
        SpeakerSegment(speaker="B", start_time=Decimal("0.7"), end_time=Decimal("2.0")),
    ]
    # A overlaps [0.0, 0.6] ∩ [0.0, 1.0] = 0.6
    # B overlaps [0.7, 1.0] = 0.3 → 30% ✓, 0.3/0.6 = 50% ✓ → OVERLAP
    word = _make_word(0.0, 1.0)
    result = assign_speakers_to_words([word], speaker_segments)
    assert result[0].speaker == "A"
    assert result[0].is_overlap is True


@pytest.mark.unit
def test_overlap_not_set_when_word_has_no_overlap_candidates():
    """Words with no speaker overlap at all should not have is_overlap set."""
    speaker_segments = [
        SpeakerSegment(speaker="A", start_time=Decimal("3.0"), end_time=Decimal("5.0")),
    ]
    # Word is in gap before speakers start
    word = _make_word(0.0, 1.0)
    word.speaker = None
    result = assign_speakers_to_words([word], speaker_segments)
    assert result[0].is_overlap is False


@pytest.mark.unit
def test_overlap_multiple_words_independent():
    """Overlap detection works independently per word."""
    # SPEAKER_A: 0-2, SPEAKER_B: 1.5-3
    # word1: 0.0-0.5 → only in A (no overlap)
    # word2: 1.0-2.5 → A overlaps 1.0s, B overlaps 1.0s → 40% dur ✓, 100% best ✓ → OVERLAP
    speaker_segments = [
        SpeakerSegment(speaker="A", start_time=Decimal("0.0"), end_time=Decimal("2.0")),
        SpeakerSegment(speaker="B", start_time=Decimal("1.5"), end_time=Decimal("3.0")),
    ]
    word1 = _make_word(0.0, 0.5)
    word2 = _make_word(1.0, 2.5)

    result = assign_speakers_to_words([word1, word2], speaker_segments)
    assert result[0].is_overlap is False
    assert result[1].is_overlap is True


# ─── Storage: bulk_insert is_overlap tests ────────────────────────────────────

@pytest.mark.unit
def test_bulk_insert_includes_is_overlap_false():
    """bulk_insert should include is_overlap=False in the SQL."""
    mock_cursor = MagicMock()
    mock_cursor.mogrify = lambda tmpl, vals: (tmpl % tuple(repr(v) for v in vals)).encode("utf-8")

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = None  # no speaker_id needed

        storage = TranscriptStorage()
        seg = TranscriptSegment(
            id=None,
            episode_id=1,
            word="hello",
            start_time=Decimal("0.0"),
            end_time=Decimal("0.5"),
            segment_index=0,
            speaker=None,
            is_overlap=False,
        )
        storage.bulk_insert([seg])

        # Verify execute was called and includes is_overlap in the INSERT
        assert mock_cursor.execute.called
        sql = mock_cursor.execute.call_args[0][0]
        assert "is_overlap" in sql


@pytest.mark.unit
def test_bulk_insert_includes_is_overlap_true():
    """bulk_insert should persist is_overlap=True for overlapping words."""
    mock_cursor = MagicMock()
    mock_cursor.mogrify = lambda tmpl, vals: (tmpl % tuple(repr(v) for v in vals)).encode("utf-8")

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = None

        storage = TranscriptStorage()
        seg = TranscriptSegment(
            id=None,
            episode_id=1,
            word="hello",
            start_time=Decimal("0.0"),
            end_time=Decimal("0.5"),
            segment_index=0,
            speaker=None,
            is_overlap=True,
        )
        storage.bulk_insert([seg])

        assert mock_cursor.execute.called
        sql = mock_cursor.execute.call_args[0][0]
        assert "is_overlap" in sql


# ─── Storage: update_speaker_labels is_overlap tests ─────────────────────────

@pytest.mark.unit
def test_update_speaker_labels_includes_is_overlap():
    """update_speaker_labels should UPDATE is_overlap column."""
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1
    mock_cursor.fetchone.return_value = None  # no speaker_id

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        storage = TranscriptStorage()
        seg = TranscriptSegment(
            id=42,
            episode_id=1,
            word="test",
            start_time=Decimal("0.0"),
            end_time=Decimal("0.5"),
            segment_index=0,
            speaker=None,
            is_overlap=True,
        )
        storage.update_speaker_labels([seg])

        assert mock_cursor.execute.called
        # Find the UPDATE call (not the speaker resolution SELECT)
        for call in mock_cursor.execute.call_args_list:
            sql = call[0][0]
            if "UPDATE transcript_segments" in sql:
                assert "is_overlap" in sql
                break
        else:
            pytest.fail("No UPDATE transcript_segments call found")


# ─── Storage: get_episode_paragraphs has_overlap aggregation tests ────────────

@pytest.mark.unit
def test_get_episode_paragraphs_has_overlap_false_when_none_overlap():
    """Paragraph has_overlap should be False when no words have is_overlap=True."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        {
            "id": 1, "word": "hello", "start_time": Decimal("0.0"), "end_time": Decimal("0.5"),
            "segment_index": 0, "speaker": "A", "speaker_name": "Alice",
            "speaker_confidence": None, "is_overlap": False,
        },
        {
            "id": 2, "word": "world", "start_time": Decimal("0.5"), "end_time": Decimal("1.0"),
            "segment_index": 1, "speaker": "A", "speaker_name": "Alice",
            "speaker_confidence": None, "is_overlap": False,
        },
    ]

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        storage = TranscriptStorage()
        paragraphs = storage.get_episode_paragraphs(1)

        assert len(paragraphs) == 1
        assert paragraphs[0]["has_overlap"] is False


@pytest.mark.unit
def test_get_episode_paragraphs_has_overlap_true_when_any_word_overlaps():
    """Paragraph has_overlap should be True if any word in it has is_overlap=True."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        {
            "id": 1, "word": "hello", "start_time": Decimal("0.0"), "end_time": Decimal("0.5"),
            "segment_index": 0, "speaker": "A", "speaker_name": "Alice",
            "speaker_confidence": None, "is_overlap": False,
        },
        {
            "id": 2, "word": "world", "start_time": Decimal("0.5"), "end_time": Decimal("1.0"),
            "segment_index": 1, "speaker": "A", "speaker_name": "Alice",
            "speaker_confidence": None, "is_overlap": True,
        },
    ]

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        storage = TranscriptStorage()
        paragraphs = storage.get_episode_paragraphs(1)

        assert len(paragraphs) == 1
        assert paragraphs[0]["has_overlap"] is True


@pytest.mark.unit
def test_get_episode_paragraphs_has_overlap_only_for_affected_paragraph():
    """has_overlap is aggregated per paragraph, not globally."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        # Paragraph 1: speaker A, no overlap
        {
            "id": 1, "word": "hello", "start_time": Decimal("0.0"), "end_time": Decimal("0.5"),
            "segment_index": 0, "speaker": "A", "speaker_name": "Alice",
            "speaker_confidence": None, "is_overlap": False,
        },
        # Paragraph 2: speaker B, has overlap
        {
            "id": 2, "word": "crosstalk", "start_time": Decimal("0.5"), "end_time": Decimal("1.0"),
            "segment_index": 1, "speaker": "B", "speaker_name": "Bob",
            "speaker_confidence": None, "is_overlap": True,
        },
        # Paragraph 3: speaker A again, no overlap
        {
            "id": 3, "word": "ok", "start_time": Decimal("1.0"), "end_time": Decimal("1.5"),
            "segment_index": 2, "speaker": "A", "speaker_name": "Alice",
            "speaker_confidence": None, "is_overlap": False,
        },
    ]

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        storage = TranscriptStorage()
        paragraphs = storage.get_episode_paragraphs(1)

        assert len(paragraphs) == 3
        assert paragraphs[0]["has_overlap"] is False   # Alice paragraph
        assert paragraphs[1]["has_overlap"] is True    # Bob paragraph (overlap)
        assert paragraphs[2]["has_overlap"] is False   # Alice paragraph again
