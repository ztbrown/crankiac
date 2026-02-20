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
