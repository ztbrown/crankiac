"""Unit tests for edit history logging in TranscriptStorage."""
import pytest
from unittest.mock import MagicMock, patch, call
from app.transcription.storage import TranscriptStorage


@pytest.mark.unit
class TestLogEdit:
    """Tests for the _log_edit helper method."""

    def test_log_edit_inserts_row(self):
        """_log_edit should insert a row into edit_history."""
        mock_cursor = MagicMock()

        storage = TranscriptStorage()
        storage._log_edit(mock_cursor, episode_id=1, segment_id=42, field='word',
                          old_value='helo', new_value='hello')

        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert 'edit_history' in sql
        assert params == (1, 42, 'word', 'helo', 'hello')

    def test_log_edit_stores_all_fields(self):
        """_log_edit should store episode_id, segment_id, field, old_value, new_value."""
        mock_cursor = MagicMock()

        storage = TranscriptStorage()
        storage._log_edit(mock_cursor, episode_id=5, segment_id=99, field='speaker',
                          old_value='Alice', new_value='Bob')

        _, params = mock_cursor.execute.call_args[0]
        assert params[0] == 5      # episode_id
        assert params[1] == 99     # segment_id
        assert params[2] == 'speaker'
        assert params[3] == 'Alice'
        assert params[4] == 'Bob'

    def test_log_edit_accepts_none_old_value(self):
        """_log_edit should accept None for old_value (insert case)."""
        mock_cursor = MagicMock()

        storage = TranscriptStorage()
        # Should not raise
        storage._log_edit(mock_cursor, episode_id=1, segment_id=1, field='insert',
                          old_value=None, new_value='hello')

        mock_cursor.execute.assert_called_once()

    def test_log_edit_accepts_none_new_value(self):
        """_log_edit should accept None for new_value (delete case)."""
        mock_cursor = MagicMock()

        storage = TranscriptStorage()
        storage._log_edit(mock_cursor, episode_id=1, segment_id=1, field='delete',
                          old_value='goodbye', new_value=None)

        mock_cursor.execute.assert_called_once()


@pytest.mark.unit
class TestUpdateWordTextLogsEdit:
    """Tests that update_word_text logs edits."""

    def _make_cursor(self, old_word='helo'):
        """Create a mock cursor that returns a segment row."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 42, 'word': old_word, 'episode_id': 7
        }
        mock_cursor.rowcount = 1
        return mock_cursor

    def test_update_word_text_logs_edit(self):
        """update_word_text should log an edit with old and new word values."""
        mock_cursor = self._make_cursor(old_word='helo')

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.update_word_text(42, 'hello')

        assert result is True
        # Should have fetched old word and inserted edit_history row
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any('edit_history' in c for c in calls)

    def test_update_word_text_logs_correct_field(self):
        """update_word_text should log field='word'."""
        mock_cursor = self._make_cursor(old_word='teh')

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            storage.update_word_text(42, 'the')

        # Find the edit_history insert call and check field='word'
        for c in mock_cursor.execute.call_args_list:
            sql, params = c[0]
            if 'edit_history' in sql:
                assert params[2] == 'word'
                assert params[3] == 'teh'    # old_value
                assert params[4] == 'the'    # new_value
                break
        else:
            pytest.fail("edit_history insert not found")

    def test_update_word_text_no_log_when_segment_missing(self):
        """update_word_text should not log if segment not found."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.rowcount = 0

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.update_word_text(999, 'hello')

        assert result is False
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert not any('edit_history' in c for c in calls)


@pytest.mark.unit
class TestDeleteSegmentLogsEdit:
    """Tests that delete_segment logs edits."""

    def test_delete_segment_logs_edit(self):
        """delete_segment should log a delete edit with the old word value."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 10, 'word': 'goodbye', 'episode_id': 3
        }
        mock_cursor.rowcount = 1

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.delete_segment(10)

        assert result is True
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any('edit_history' in c for c in calls)

    def test_delete_segment_logs_correct_field(self):
        """delete_segment should log field='delete' with old_value=word, new_value=None."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 10, 'word': 'goodbye', 'episode_id': 3
        }
        mock_cursor.rowcount = 1

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            storage.delete_segment(10)

        for c in mock_cursor.execute.call_args_list:
            sql, params = c[0]
            if 'edit_history' in sql:
                assert params[2] == 'delete'
                assert params[3] == 'goodbye'  # old_value
                assert params[4] is None       # new_value
                break
        else:
            pytest.fail("edit_history insert not found")

    def test_delete_segment_no_log_when_not_found(self):
        """delete_segment should not log if segment not found."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.rowcount = 0

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.delete_segment(999)

        assert result is False
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert not any('edit_history' in c for c in calls)


@pytest.mark.unit
class TestInsertSegmentAfterLogsEdit:
    """Tests that insert_segment_after logs edits."""

    def _make_cursor(self):
        mock_cursor = MagicMock()
        # First fetchone: get reference segment
        # Second fetchone: RETURNING id after insert
        mock_cursor.fetchone.side_effect = [
            {
                'episode_id': 5, 'start_time': '1.0', 'end_time': '2.0',
                'segment_index': 3, 'speaker': 'Alice', 'speaker_id': 1
            },
            {'id': 77}
        ]
        return mock_cursor

    def test_insert_segment_after_logs_edit(self):
        """insert_segment_after should log an insert edit."""
        mock_cursor = self._make_cursor()

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.insert_segment_after(10, 'world')

        assert result == 77
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any('edit_history' in c for c in calls)

    def test_insert_segment_after_logs_correct_field(self):
        """insert_segment_after should log field='insert' with old_value=None, new_value=word."""
        mock_cursor = self._make_cursor()

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            storage.insert_segment_after(10, 'world')

        for c in mock_cursor.execute.call_args_list:
            sql, params = c[0]
            if 'edit_history' in sql:
                assert params[2] == 'insert'
                assert params[3] is None        # old_value
                assert params[4] == 'world'     # new_value
                break
        else:
            pytest.fail("edit_history insert not found")

    def test_insert_segment_after_no_log_when_ref_not_found(self):
        """insert_segment_after should not log if reference segment not found."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.insert_segment_after(999, 'world')

        assert result is None
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert not any('edit_history' in c for c in calls)


@pytest.mark.unit
class TestAssignSpeakerToRangeLogsEdit:
    """Tests that assign_speaker_to_range logs edits for changed segments."""

    def _make_cursor_single(self, segment_id=10, old_speaker_id=1, episode_id=5):
        """Mock cursor for single-segment assignment."""
        mock_cursor = MagicMock()

        call_count = [0]
        def fetchone_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                # Get segment_index for single selection
                return {'segment_index': 3}
            return None

        fetchall_call_count = [0]
        def fetchall_side_effect():
            fetchall_call_count[0] += 1
            if fetchall_call_count[0] == 1:
                # Get old speaker_ids for affected segments
                return [
                    {'id': segment_id, 'speaker_id': old_speaker_id, 'episode_id': episode_id}
                ]
            return []

        mock_cursor.fetchone.side_effect = fetchone_side_effect
        mock_cursor.fetchall.side_effect = fetchall_side_effect
        mock_cursor.rowcount = 1
        return mock_cursor

    def test_assign_speaker_logs_edit_for_each_changed_segment(self):
        """assign_speaker_to_range should log field='speaker' for each changed segment."""
        mock_cursor = self._make_cursor_single(segment_id=10, old_speaker_id=1)

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.assign_speaker_to_range(
                episode_id=5, start_segment_id=10, end_segment_id=10, speaker_id=2
            )

        assert result == 1
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any('edit_history' in c for c in calls)

    def test_assign_speaker_logs_correct_values(self):
        """assign_speaker_to_range should log old speaker_id and new speaker_id."""
        mock_cursor = self._make_cursor_single(segment_id=10, old_speaker_id=1, episode_id=5)

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            storage.assign_speaker_to_range(
                episode_id=5, start_segment_id=10, end_segment_id=10, speaker_id=2
            )

        for c in mock_cursor.execute.call_args_list:
            sql, params = c[0]
            if 'edit_history' in sql:
                assert params[2] == 'speaker'
                assert params[3] == '1'   # old speaker_id as string
                assert params[4] == '2'   # new speaker_id as string
                break
        else:
            pytest.fail("edit_history insert not found")


@pytest.mark.unit
class TestEditParagraph:
    """Tests for edit_paragraph with semantic diff logging."""

    def _make_seg(self, id, word, episode_id=1, segment_index=0,
                  start_time='1.0', end_time='2.0', speaker='Alice', speaker_id=1):
        return {
            'id': id, 'word': word, 'episode_id': episode_id,
            'segment_index': segment_index,
            'start_time': start_time, 'end_time': end_time,
            'speaker': speaker, 'speaker_id': speaker_id,
        }

    def _history_entries(self, mock_cursor):
        """Extract (sql, params) tuples for edit_history inserts."""
        return [
            params
            for c in mock_cursor.execute.call_args_list
            for sql, params in [c[0]]
            if 'edit_history' in sql
        ]

    def _patch_cursor(self, mock_cursor):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=mock_cursor)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    def test_no_change_edit_creates_no_history(self):
        """When new text matches existing words exactly, no edit_history rows are inserted."""
        segs = [
            self._make_seg(1, 'hello', segment_index=0),
            self._make_seg(2, 'world', segment_index=1),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = segs

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.edit_paragraph([1, 2], 'hello world')

        assert result == {'updated': 0, 'inserted': 0, 'deleted': 0}
        assert self._history_entries(mock_cursor) == []

    def test_single_word_correction_logs_word_field(self):
        """Correcting a single misspelled word logs field='word' with old and new values."""
        segs = [self._make_seg(1, 'helo', segment_index=0)]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = segs

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.edit_paragraph([1], 'hello')

        assert result == {'updated': 1, 'inserted': 0, 'deleted': 0}
        entries = self._history_entries(mock_cursor)
        assert len(entries) == 1
        assert entries[0][2] == 'word'
        assert entries[0][3] == 'helo'   # old_value
        assert entries[0][4] == 'hello'  # new_value

    def test_multi_word_to_single_word_replacement(self):
        """Replacing two old words with one logs a word correction and a deletion."""
        segs = [
            self._make_seg(1, 'gonna', segment_index=0),
            self._make_seg(2, 'be', segment_index=1),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = segs

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.edit_paragraph([1, 2], 'will')

        assert result == {'updated': 1, 'inserted': 0, 'deleted': 1}
        entries = self._history_entries(mock_cursor)
        assert len(entries) == 2
        fields = [e[2] for e in entries]
        assert 'word' in fields
        assert 'delete' in fields

        word_entry = next(e for e in entries if e[2] == 'word')
        assert word_entry[3] == 'gonna'  # old_value (joined old segment)
        assert word_entry[4] == 'will'   # new_value

        delete_entry = next(e for e in entries if e[2] == 'delete')
        assert delete_entry[3] == 'be'   # old_value
        assert delete_entry[4] is None   # new_value

    def test_word_insertion_logs_insert_field(self):
        """Inserting a new word between existing words logs field='insert'."""
        segs = [
            self._make_seg(1, 'hello', segment_index=0),
            self._make_seg(2, 'world', segment_index=1),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = segs
        mock_cursor.fetchone.return_value = {'id': 99}

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.edit_paragraph([1, 2], 'hello there world')

        assert result == {'updated': 0, 'inserted': 1, 'deleted': 0}
        entries = self._history_entries(mock_cursor)
        assert len(entries) == 1
        assert entries[0][2] == 'insert'
        assert entries[0][3] is None       # old_value
        assert entries[0][4] == 'there'    # new_value

    def test_word_deletion_logs_delete_field(self):
        """Deleting a word logs field='delete' with the removed word as old_value."""
        segs = [
            self._make_seg(1, 'hello', segment_index=0),
            self._make_seg(2, 'there', segment_index=1),
            self._make_seg(3, 'world', segment_index=2),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = segs

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.edit_paragraph([1, 2, 3], 'hello world')

        assert result == {'updated': 0, 'inserted': 0, 'deleted': 1}
        entries = self._history_entries(mock_cursor)
        assert len(entries) == 1
        assert entries[0][2] == 'delete'
        assert entries[0][3] == 'there'  # old_value
        assert entries[0][4] is None     # new_value

    def test_complex_edit_only_logs_semantic_corrections(self):
        """Equal (unchanged) words produce no edit_history entries; only changed words are logged."""
        segs = [
            self._make_seg(1, 'the', segment_index=0),
            self._make_seg(2, 'quick', segment_index=1),
            self._make_seg(3, 'brown', segment_index=2),
            self._make_seg(4, 'fox', segment_index=3),
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = segs

        with patch('app.transcription.storage.get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            storage = TranscriptStorage()
            result = storage.edit_paragraph([1, 2, 3, 4], 'the slow brown fox')

        assert result == {'updated': 1, 'inserted': 0, 'deleted': 0}
        entries = self._history_entries(mock_cursor)
        # Only the changed word is logged — no positional noise from equal matches
        assert len(entries) == 1
        assert entries[0][2] == 'word'
        assert entries[0][3] == 'quick'  # old_value
        assert entries[0][4] == 'slow'   # new_value
