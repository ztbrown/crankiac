"""Unit tests for LLM transcript corrector (cr-tg32n).

All Anthropic API calls are mocked — no real network calls are made.
"""
import pytest
from unittest.mock import MagicMock, patch, call

from app.transcription.llm_corrector import LLMCorrector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_seg(word, confidence=None, idx=0, seg_id=None, speaker=None):
    """Build a segment dict matching the transcript_segments schema."""
    return {
        "id": seg_id if seg_id is not None else idx,
        "word": word,
        "segment_index": idx,
        "word_confidence": confidence,
        "speaker": speaker,
    }


def _make_cursor_ctx():
    """Return (ctx_manager, cursor_mock) for patching get_cursor."""
    cursor = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cursor)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cursor


# ---------------------------------------------------------------------------
# identify_low_confidence_regions
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIdentifyLowConfidenceRegions:

    def test_empty_segments_returns_empty(self):
        lc = LLMCorrector()
        assert lc.identify_low_confidence_regions([]) == []

    def test_all_high_confidence_returns_empty(self):
        segs = [make_seg(f"w{i}", 0.9, idx=i, seg_id=i) for i in range(5)]
        lc = LLMCorrector(threshold=0.7)
        assert lc.identify_low_confidence_regions(segs) == []

    def test_all_none_confidence_returns_empty(self):
        """Segments with word_confidence=None are treated as high-confidence."""
        segs = [make_seg(f"w{i}", None, idx=i, seg_id=i) for i in range(5)]
        lc = LLMCorrector()
        assert lc.identify_low_confidence_regions(segs) == []

    def test_single_low_conf_word_is_found(self):
        segs = [
            make_seg("hello", 0.9, idx=0, seg_id=0),
            make_seg("choppo", 0.3, idx=1, seg_id=1),
            make_seg("everyone", 0.9, idx=2, seg_id=2),
        ]
        lc = LLMCorrector(threshold=0.7, context_window=0)
        regions = lc.identify_low_confidence_regions(segs)
        assert len(regions) == 1
        assert 1 in regions[0]["flagged"]

    def test_groups_words_within_group_distance(self):
        """Two low-conf words within 15 indices are merged into one group."""
        segs = [make_seg(f"w{i}", 0.3 if i in (5, 15) else 0.9, idx=i, seg_id=i)
                for i in range(30)]
        lc = LLMCorrector(threshold=0.7, context_window=0, group_distance=15)
        regions = lc.identify_low_confidence_regions(segs)
        assert len(regions) == 1
        assert 5 in regions[0]["flagged"]
        assert 15 in regions[0]["flagged"]

    def test_does_not_group_words_beyond_group_distance(self):
        """Two low-conf words 20 apart are split into separate groups."""
        segs = [make_seg(f"w{i}", 0.3 if i in (5, 25) else 0.9, idx=i, seg_id=i)
                for i in range(40)]
        lc = LLMCorrector(threshold=0.7, context_window=0, group_distance=15)
        regions = lc.identify_low_confidence_regions(segs)
        assert len(regions) == 2
        assert 5 in regions[0]["flagged"]
        assert 25 in regions[1]["flagged"]

    def test_expands_region_with_context_window(self):
        """Region start/end expand by context_window words in each direction."""
        segs = [make_seg(f"w{i}", 0.3 if i == 10 else 0.9, idx=i, seg_id=i)
                for i in range(20)]
        lc = LLMCorrector(threshold=0.7, context_window=3, group_distance=15)
        regions = lc.identify_low_confidence_regions(segs)
        assert len(regions) == 1
        assert regions[0]["start"] == 7   # 10 - 3
        assert regions[0]["end"] == 13    # 10 + 3

    def test_context_expansion_clamped_at_segment_bounds(self):
        """Context window does not go below index 0 or above len-1."""
        segs = [make_seg(f"w{i}", 0.3 if i == 0 else 0.9, idx=i, seg_id=i)
                for i in range(5)]
        lc = LLMCorrector(threshold=0.7, context_window=50)
        regions = lc.identify_low_confidence_regions(segs)
        assert regions[0]["start"] == 0
        assert regions[0]["end"] == 4    # clamped to len-1

    def test_overlapping_regions_are_merged(self):
        """Two groups that are distinct but whose expanded windows overlap merge into one."""
        segs = [make_seg(f"w{i}", 0.3 if i in (5, 10) else 0.9, idx=i, seg_id=i)
                for i in range(20)]
        # group_distance=3 keeps them separate; context_window=3 makes windows touch
        lc = LLMCorrector(threshold=0.7, context_window=3, group_distance=3)
        regions = lc.identify_low_confidence_regions(segs)
        assert len(regions) == 1
        assert 5 in regions[0]["flagged"]
        assert 10 in regions[0]["flagged"]

    def test_high_conf_word_between_low_conf_words_does_not_get_flagged(self):
        """Only words below threshold end up in the 'flagged' set."""
        segs = [
            make_seg("a", 0.3, idx=0, seg_id=0),
            make_seg("b", 0.9, idx=1, seg_id=1),  # high-conf — NOT flagged
            make_seg("c", 0.3, idx=2, seg_id=2),
        ]
        lc = LLMCorrector(threshold=0.7, context_window=0, group_distance=5)
        regions = lc.identify_low_confidence_regions(segs)
        assert len(regions) == 1
        assert 0 in regions[0]["flagged"]
        assert 1 not in regions[0]["flagged"]
        assert 2 in regions[0]["flagged"]


# ---------------------------------------------------------------------------
# build_chunks
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildChunks:

    def test_small_region_becomes_single_chunk(self):
        segs = [make_seg(f"w{i}", 0.3 if i == 2 else 0.9, idx=i, seg_id=i)
                for i in range(5)]
        lc = LLMCorrector(threshold=0.7, context_window=0, max_chunk_words=2000)
        regions = lc.identify_low_confidence_regions(segs)
        chunks = lc.build_chunks(segs, regions)
        assert len(chunks) == 1

    def test_flagged_indices_in_chunk_are_relative_to_chunk_start(self):
        """Flagged set uses indices into chunk['segments'], not into the global list."""
        segs = [make_seg(f"w{i}", 0.3 if i == 5 else 0.9, idx=i, seg_id=i)
                for i in range(10)]
        lc = LLMCorrector(threshold=0.7, context_window=2, group_distance=15)
        regions = lc.identify_low_confidence_regions(segs)
        # region starts at max(0, 5-2)=3; flagged global index 5 → local index 2
        chunks = lc.build_chunks(segs, regions)
        assert len(chunks) == 1
        assert 2 in chunks[0]["flagged"]

    def test_oversized_region_splits_at_speaker_boundary(self):
        """A region larger than max_chunk_words is split at speaker changes."""
        segs = []
        for i in range(100):
            speaker = "A" if i < 50 else "B"
            conf = 0.3 if i < 50 else 0.9
            segs.append(make_seg(f"w{i}", conf, idx=i, seg_id=i, speaker=speaker))

        lc = LLMCorrector(threshold=0.7, context_window=0, max_chunk_words=60,
                          group_distance=100)
        regions = lc.identify_low_confidence_regions(segs)
        chunks = lc.build_chunks(segs, regions)
        # Should produce sub-chunks; each must have flagged words
        assert len(chunks) >= 1
        for chunk in chunks:
            assert len(chunk["flagged"]) > 0

    def test_split_chunks_contain_only_flagged_sub_sections(self):
        """Sub-chunks without flagged words are dropped after a speaker split."""
        segs = []
        for i in range(100):
            speaker = "A" if i < 50 else "B"
            # Only speaker A has low-conf words
            conf = 0.3 if (speaker == "A" and i < 50) else 0.9
            segs.append(make_seg(f"w{i}", conf, idx=i, seg_id=i, speaker=speaker))

        lc = LLMCorrector(threshold=0.7, context_window=0, max_chunk_words=60,
                          group_distance=100)
        regions = lc.identify_low_confidence_regions(segs)
        chunks = lc.build_chunks(segs, regions)
        # Speaker B sub-chunks have no flagged words → dropped
        for chunk in chunks:
            assert len(chunk["flagged"]) > 0

    def test_empty_regions_returns_empty_chunks(self):
        segs = [make_seg(f"w{i}", 0.9, idx=i, seg_id=i) for i in range(5)]
        lc = LLMCorrector()
        assert lc.build_chunks(segs, []) == []

    def test_chunk_segments_are_correct_slice(self):
        """The segments in a chunk are the correct slice of the global list."""
        segs = [make_seg(f"w{i}", 0.3 if i == 3 else 0.9, idx=i, seg_id=i)
                for i in range(7)]
        lc = LLMCorrector(threshold=0.7, context_window=1, group_distance=15)
        regions = lc.identify_low_confidence_regions(segs)
        chunks = lc.build_chunks(segs, regions)
        # region: start=2, end=4  → segments w2, w3, w4
        chunk_words = [s["word"] for s in chunks[0]["segments"]]
        assert "w2" in chunk_words
        assert "w3" in chunk_words
        assert "w4" in chunk_words


# ---------------------------------------------------------------------------
# format_chunk
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatChunk:

    def test_plain_words_appear_unmodified(self):
        chunk = {
            "segments": [
                {"id": 1, "word": "hello", "word_confidence": 0.9},
                {"id": 2, "word": "world", "word_confidence": 0.8},
            ],
            "flagged": set(),
        }
        result = LLMCorrector().format_chunk(chunk)
        assert result == "hello world"

    def test_flagged_word_annotated_with_confidence_and_id(self):
        chunk = {
            "segments": [{"id": 42, "word": "choppo", "word_confidence": 0.53}],
            "flagged": {0},
        }
        result = LLMCorrector().format_chunk(chunk)
        assert result == "[?choppo?](0.53)[42]"

    def test_first_word_flagged(self):
        chunk = {
            "segments": [
                {"id": 1, "word": "bad", "word_confidence": 0.2},
                {"id": 2, "word": "good", "word_confidence": 0.9},
            ],
            "flagged": {0},
        }
        result = LLMCorrector().format_chunk(chunk)
        assert result.startswith("[?bad?]")
        assert "good" in result

    def test_last_word_flagged(self):
        chunk = {
            "segments": [
                {"id": 1, "word": "good", "word_confidence": 0.9},
                {"id": 2, "word": "bad", "word_confidence": 0.2},
            ],
            "flagged": {1},
        }
        result = LLMCorrector().format_chunk(chunk)
        assert result.endswith("[?bad?](0.20)[2]")

    def test_none_confidence_renders_as_question_mark(self):
        chunk = {
            "segments": [{"id": 10, "word": "word", "word_confidence": None}],
            "flagged": {0},
        }
        result = LLMCorrector().format_chunk(chunk)
        assert result == "[?word?](?)[10]"

    def test_mixed_flagged_and_plain_words(self):
        chunk = {
            "segments": [
                {"id": 1, "word": "good", "word_confidence": 0.9},
                {"id": 2, "word": "bad",  "word_confidence": 0.3},
                {"id": 3, "word": "also", "word_confidence": 0.9},
            ],
            "flagged": {1},
        }
        result = LLMCorrector().format_chunk(chunk)
        assert result == "good [?bad?](0.30)[2] also"

    def test_multiple_flagged_words_in_sequence(self):
        chunk = {
            "segments": [
                {"id": 1, "word": "a", "word_confidence": 0.1},
                {"id": 2, "word": "b", "word_confidence": 0.2},
            ],
            "flagged": {0, 1},
        }
        result = LLMCorrector().format_chunk(chunk)
        assert "[?a?](0.10)[1]" in result
        assert "[?b?](0.20)[2]" in result


# ---------------------------------------------------------------------------
# call_llm
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCallLLM:

    def _llm_response(self, text):
        resp = MagicMock()
        resp.content = [MagicMock(text=text)]
        return resp

    def _lc_with_mock_client(self, response_text=None, side_effect=None):
        lc = LLMCorrector()
        mock_client = MagicMock()
        if side_effect:
            mock_client.messages.create.side_effect = side_effect
        else:
            mock_client.messages.create.return_value = self._llm_response(response_text)
        lc._client = mock_client
        return lc, mock_client

    def test_returns_corrections_dict_on_valid_json(self):
        lc, _ = self._lc_with_mock_client('{"10": "Chapo"}')
        result = lc.call_llm("some transcript text")
        assert result == {"10": "Chapo"}

    def test_strips_markdown_json_code_fence(self):
        lc, _ = self._lc_with_mock_client('```json\n{"10": "Chapo"}\n```')
        result = lc.call_llm("text")
        assert result == {"10": "Chapo"}

    def test_strips_plain_code_fence(self):
        lc, _ = self._lc_with_mock_client('```\n{"10": "Chapo"}\n```')
        result = lc.call_llm("text")
        assert result == {"10": "Chapo"}

    def test_retries_once_on_invalid_json(self):
        lc, mock_client = self._lc_with_mock_client("not valid json {{{")
        result = lc.call_llm("text")
        assert result == {}
        assert mock_client.messages.create.call_count == 2

    def test_returns_empty_on_persistent_invalid_json(self):
        lc, _ = self._lc_with_mock_client("garbage")
        result = lc.call_llm("text")
        assert result == {}

    def test_returns_empty_on_api_exception(self):
        lc, _ = self._lc_with_mock_client(side_effect=Exception("connection refused"))
        result = lc.call_llm("text")
        assert result == {}

    def test_returns_empty_on_non_dict_json(self):
        """LLM returning a JSON array (not a dict) is rejected."""
        lc, _ = self._lc_with_mock_client('["a", "b"]')
        result = lc.call_llm("text")
        assert result == {}

    def test_returns_empty_dict_when_no_corrections_needed(self):
        lc, _ = self._lc_with_mock_client("{}")
        result = lc.call_llm("all good text")
        assert result == {}


# ---------------------------------------------------------------------------
# apply_corrections
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestApplyCorrections:

    def _chunk(self, segs, flagged_local):
        return {"segments": segs, "flagged": flagged_local}

    def test_applies_correction_and_returns_count(self):
        seg = make_seg("choppo", 0.5, idx=0, seg_id=10)
        chunk = self._chunk([seg], {0})
        ctx, cursor = _make_cursor_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            count = lc.apply_corrections(1, [seg], [chunk], [{"10": "Chapo"}])
        assert count == 1

    def test_update_sets_new_word_and_null_confidence(self):
        seg = make_seg("choppo", 0.5, idx=0, seg_id=10)
        chunk = self._chunk([seg], {0})
        ctx, cursor = _make_cursor_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            lc.apply_corrections(1, [seg], [chunk], [{"10": "Chapo"}])
        update_sql, update_params = cursor.execute.call_args_list[0][0]
        assert "UPDATE transcript_segments" in update_sql
        assert "word_confidence = NULL" in update_sql
        assert update_params == ("Chapo", 10)

    def test_logs_to_edit_history_with_llm_word_field(self):
        seg = make_seg("choppo", 0.5, idx=0, seg_id=10)
        chunk = self._chunk([seg], {0})
        ctx, cursor = _make_cursor_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            lc.apply_corrections(1, [seg], [chunk], [{"10": "Chapo"}])
        insert_sql, insert_params = cursor.execute.call_args_list[1][0]
        assert "edit_history" in insert_sql
        assert insert_params == (1, 10, "llm_word", "choppo", "Chapo")

    def test_rejects_multi_word_replacement(self):
        """Corrections with spaces are rejected (non-1:1 replacements)."""
        seg = make_seg("choppo", 0.5, idx=0, seg_id=10)
        chunk = self._chunk([seg], {0})
        ctx, cursor = _make_cursor_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            count = lc.apply_corrections(1, [seg], [chunk], [{"10": "Chapo Trap"}])
        assert count == 0
        cursor.execute.assert_not_called()

    def test_rejects_correction_to_unmarked_segment(self):
        """LLM trying to fix a segment not in chunk's flagged set is rejected."""
        seg_flagged = make_seg("choppo", 0.5, idx=0, seg_id=10)
        seg_clean   = make_seg("clean",  0.9, idx=1, seg_id=20)
        chunk = self._chunk([seg_flagged, seg_clean], {0})  # only index 0 flagged
        ctx, cursor = _make_cursor_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            count = lc.apply_corrections(
                1, [seg_flagged, seg_clean], [chunk], [{"20": "corrected"}]
            )
        assert count == 0
        cursor.execute.assert_not_called()

    def test_skips_when_corrected_word_equals_original(self):
        """No DB write when the 'correction' is the same as the original."""
        seg = make_seg("hello", 0.5, idx=0, seg_id=10)
        chunk = self._chunk([seg], {0})
        ctx, cursor = _make_cursor_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            count = lc.apply_corrections(1, [seg], [chunk], [{"10": "hello"}])
        assert count == 0
        cursor.execute.assert_not_called()

    def test_empty_corrections_dict_makes_no_db_calls(self):
        seg = make_seg("choppo", 0.5, idx=0, seg_id=10)
        chunk = self._chunk([seg], {0})
        ctx, cursor = _make_cursor_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            count = lc.apply_corrections(1, [seg], [chunk], [{}])
        assert count == 0
        cursor.execute.assert_not_called()

    def test_rejects_non_integer_key(self):
        """Non-integer keys (e.g. string like 'abc') are silently skipped."""
        seg = make_seg("word", 0.5, idx=0, seg_id=10)
        chunk = self._chunk([seg], {0})
        ctx, cursor = _make_cursor_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            count = lc.apply_corrections(1, [seg], [chunk], [{"abc": "word"}])
        assert count == 0
        cursor.execute.assert_not_called()

    def test_multiple_valid_corrections_in_single_chunk(self):
        segs = [
            make_seg("choppo", 0.5, idx=0, seg_id=10),
            make_seg("teh",    0.4, idx=1, seg_id=11),
        ]
        chunk = self._chunk(segs, {0, 1})
        ctx, cursor = _make_cursor_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            count = lc.apply_corrections(
                1, segs, [chunk], [{"10": "Chapo", "11": "the"}]
            )
        assert count == 2
        assert cursor.execute.call_count == 4  # 2 UPDATEs + 2 INSERTs


# ---------------------------------------------------------------------------
# correct_episode
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCorrectEpisode:

    def _claim_ctx(self, episode_id):
        """Cursor that successfully claims the episode advisory lock."""
        ctx, cursor = _make_cursor_ctx()
        cursor.fetchone.return_value = {"id": episode_id}
        return ctx, cursor

    def _not_found_ctx(self):
        """Cursor whose fetchone returns None (already locked or not found)."""
        ctx, cursor = _make_cursor_ctx()
        cursor.fetchone.return_value = None
        return ctx, cursor

    def _segments_ctx(self, segments):
        """Cursor whose fetchall returns the given segment dicts."""
        ctx, cursor = _make_cursor_ctx()
        cursor.fetchall.return_value = segments
        return ctx, cursor

    def test_returns_neg_one_if_episode_already_corrected(self):
        ctx, _ = self._not_found_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            result = lc.correct_episode(99)
        assert result == -1

    def test_returns_zero_if_no_segments(self):
        ctx1, _ = self._claim_ctx(11)
        ctx2, _ = self._segments_ctx([])
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor",
                   side_effect=[ctx1, ctx2]):
            result = lc.correct_episode(11)
        assert result == 0

    def test_no_api_calls_when_all_words_high_confidence(self):
        """If identify_low_confidence_regions returns [], call_llm is never called."""
        segs = [
            {"id": i, "word": f"w{i}", "segment_index": i,
             "word_confidence": 0.95, "speaker": "A"}
            for i in range(5)
        ]
        ctx1, _ = self._claim_ctx(11)
        ctx2, _ = self._segments_ctx(segs)
        lc = LLMCorrector()
        lc._client = MagicMock()  # should never be touched

        with patch("app.transcription.llm_corrector.get_cursor",
                   side_effect=[ctx1, ctx2]):
            result = lc.correct_episode(11)

        assert result == 0
        lc._client.messages.create.assert_not_called()

    def test_correct_episode_calls_llm_and_applies_corrections(self):
        """End-to-end: low-conf segments → call_llm → apply_corrections → count."""
        segs = [
            {"id": 1, "word": "choppo",   "segment_index": 0,
             "word_confidence": 0.3, "speaker": "A"},
            {"id": 2, "word": "everyone", "segment_index": 1,
             "word_confidence": 0.95, "speaker": "A"},
        ]
        ctx1, _ = self._claim_ctx(11)
        ctx2, _ = self._segments_ctx(segs)

        lc = LLMCorrector(threshold=0.7, context_window=0)

        mock_corrections = {"1": "Chapo"}
        with patch("app.transcription.llm_corrector.get_cursor",
                   side_effect=[ctx1, ctx2]):
            with patch.object(lc, "call_llm", return_value=mock_corrections) as mock_llm:
                with patch.object(lc, "apply_corrections", return_value=1) as mock_apply:
                    result = lc.correct_episode(11)

        assert result == 1
        mock_llm.assert_called_once()
        mock_apply.assert_called_once()

    def test_skips_episode_without_word_confidence_returns_zero(self):
        """Episode where all word_confidence is None → no regions → returns 0."""
        segs = [
            {"id": i, "word": f"w{i}", "segment_index": i,
             "word_confidence": None, "speaker": "A"}
            for i in range(5)
        ]
        ctx1, _ = self._claim_ctx(11)
        ctx2, _ = self._segments_ctx(segs)

        lc = LLMCorrector()
        lc._client = MagicMock()

        with patch("app.transcription.llm_corrector.get_cursor",
                   side_effect=[ctx1, ctx2]):
            result = lc.correct_episode(11)

        assert result == 0
        lc._client.messages.create.assert_not_called()

    def test_advisory_lock_update_targets_only_uncorrected_episodes(self):
        """The UPDATE SQL must include WHERE llm_corrected = FALSE."""
        ctx, cursor = self._not_found_ctx()
        lc = LLMCorrector()
        with patch("app.transcription.llm_corrector.get_cursor", return_value=ctx):
            lc.correct_episode(11)
        update_sql = cursor.execute.call_args[0][0]
        assert "llm_corrected = FALSE" in update_sql
        assert "llm_corrected = TRUE" in update_sql
