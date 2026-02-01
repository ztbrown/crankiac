"""Unit tests for TranscriptStorage class."""
import pytest
from unittest.mock import MagicMock, patch, call
from app.transcription.storage import TranscriptStorage, BATCH_SIZE


@pytest.mark.unit
def test_update_speakers_by_ids_empty_list():
    """Test update_speakers_by_ids with empty segment_ids list."""
    storage = TranscriptStorage()
    result = storage.update_speakers_by_ids([], "Speaker 1")
    assert result == 0


@pytest.mark.unit
def test_update_speakers_by_ids_single_segment():
    """Test update_speakers_by_ids with a single segment."""
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        storage = TranscriptStorage()
        result = storage.update_speakers_by_ids([123], "Speaker 1")

        assert result == 1
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0]
        assert "UPDATE transcript_segments SET speaker = %s WHERE id IN (%s)" in call_args[0]
        assert call_args[1] == ["Speaker 1", 123]


@pytest.mark.unit
def test_update_speakers_by_ids_multiple_segments():
    """Test update_speakers_by_ids with multiple segments."""
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 3

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        storage = TranscriptStorage()
        segment_ids = [100, 101, 102]
        result = storage.update_speakers_by_ids(segment_ids, "Speaker 2")

        assert result == 3
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0]
        assert "UPDATE transcript_segments SET speaker = %s WHERE id IN (%s,%s,%s)" in call_args[0]
        assert call_args[1] == ["Speaker 2", 100, 101, 102]


@pytest.mark.unit
def test_update_speakers_by_ids_batching():
    """Test update_speakers_by_ids handles batching correctly for large lists."""
    mock_cursor = MagicMock()
    mock_cursor.rowcount = BATCH_SIZE  # Each batch updates BATCH_SIZE rows

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        storage = TranscriptStorage()
        # Create a list larger than BATCH_SIZE
        segment_ids = list(range(1, BATCH_SIZE + 500))
        result = storage.update_speakers_by_ids(segment_ids, "Speaker 3")

        # Should make 2 batches: one with BATCH_SIZE items, one with 499 items
        assert mock_cursor.execute.call_count == 2
        assert result == BATCH_SIZE * 2  # Total rowcount from both batches


@pytest.mark.unit
def test_update_speakers_by_ids_partial_updates():
    """Test update_speakers_by_ids when some segments don't exist."""
    mock_cursor = MagicMock()
    # Only 2 out of 5 segments exist
    mock_cursor.rowcount = 2

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        storage = TranscriptStorage()
        segment_ids = [1, 2, 3, 4, 5]
        result = storage.update_speakers_by_ids(segment_ids, "Speaker 4")

        assert result == 2  # Only segments that existed were updated


@pytest.mark.unit
def test_update_speakers_by_ids_speaker_name_formats():
    """Test update_speakers_by_ids with different speaker name formats."""
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1

    with patch("app.transcription.storage.get_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        storage = TranscriptStorage()

        # Test various speaker name formats
        test_cases = [
            "Speaker 1",
            "SPEAKER_0",
            "Unknown",
            "John Doe",
            "",  # Empty string
        ]

        for speaker_name in test_cases:
            mock_cursor.reset_mock()
            result = storage.update_speakers_by_ids([100], speaker_name)
            assert result == 1
            call_args = mock_cursor.execute.call_args[0]
            assert call_args[1][0] == speaker_name
