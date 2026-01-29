"""Tests for audio downloader with resume support."""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.patreon.downloader import AudioDownloader, DownloadResult


@pytest.fixture
def temp_download_dir():
    """Create a temporary download directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def downloader(temp_download_dir):
    """Create a downloader instance with temp directory."""
    return AudioDownloader(session_id="test_session", download_dir=temp_download_dir)


@pytest.mark.unit
def test_416_with_matching_file_size_succeeds(downloader, temp_download_dir):
    """Test 416 response with matching Content-Range succeeds."""
    temp_path = Path(temp_download_dir) / "test_episode.tmp"
    file_content = b"complete file content"
    temp_path.write_bytes(file_content)

    mock_response = MagicMock()
    mock_response.status_code = 416
    mock_response.headers = {"Content-Range": f"bytes */{len(file_content)}"}

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download("http://example.com/audio.mp3", "test_episode")

    assert result.success is True
    assert result.file_size == len(file_content)
    final_path = Path(temp_download_dir) / "test_episode.mp3"
    assert final_path.exists()
    assert not temp_path.exists()


@pytest.mark.unit
def test_416_with_mismatched_file_size_raises(downloader, temp_download_dir):
    """Test 416 response with wrong Content-Range raises and deletes temp file."""
    temp_path = Path(temp_download_dir) / "test_episode.tmp"
    file_content = b"incomplete"

    call_count = 0

    def mock_get(url, headers, stream):
        nonlocal call_count
        call_count += 1
        # Recreate temp file on each retry to simulate persistent corrupted file
        temp_path.write_bytes(file_content)
        mock_response = MagicMock()
        mock_response.status_code = 416
        mock_response.headers = {"Content-Range": "bytes */1000"}  # Expected 1000
        return mock_response

    with patch.object(downloader.session, "get", side_effect=mock_get):
        result = downloader.download("http://example.com/audio.mp3", "test_episode")

    # Should fail after retries (default MAX_RETRIES=3)
    assert call_count == 3
    assert result.success is False
    assert "size mismatch" in result.error


@pytest.mark.unit
def test_416_without_content_range_succeeds(downloader, temp_download_dir):
    """Test 416 response without Content-Range header succeeds (backward compatible)."""
    temp_path = Path(temp_download_dir) / "test_episode.tmp"
    file_content = b"some content"
    temp_path.write_bytes(file_content)

    mock_response = MagicMock()
    mock_response.status_code = 416
    mock_response.headers = {}  # No Content-Range header

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download("http://example.com/audio.mp3", "test_episode")

    # Should succeed without validation when no Content-Range
    assert result.success is True
    assert result.file_size == len(file_content)


@pytest.mark.unit
def test_416_with_invalid_content_range_succeeds(downloader, temp_download_dir):
    """Test 416 response with malformed Content-Range header succeeds."""
    temp_path = Path(temp_download_dir) / "test_episode.tmp"
    file_content = b"some content"
    temp_path.write_bytes(file_content)

    mock_response = MagicMock()
    mock_response.status_code = 416
    mock_response.headers = {"Content-Range": "invalid header"}

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download("http://example.com/audio.mp3", "test_episode")

    # Should succeed when Content-Range can't be parsed
    assert result.success is True


@pytest.mark.unit
def test_already_downloaded_returns_success(downloader, temp_download_dir):
    """Test that already downloaded files return success without re-downloading."""
    final_path = Path(temp_download_dir) / "test_episode.mp3"
    file_content = b"already downloaded"
    final_path.write_bytes(file_content)

    result = downloader.download("http://example.com/audio.mp3", "test_episode")

    assert result.success is True
    assert result.file_size == len(file_content)
