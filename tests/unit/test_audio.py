"""Tests for audio streaming API."""
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    """Create a test client with mocked database."""
    with patch("app.data.database.init_db"):
        from app.api.app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client


@pytest.fixture
def temp_audio_file():
    """Create a temporary audio file for testing."""
    # Create a temp directory and file
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "123456.mp3")
        # Create a fake audio file with some content
        content = b"FAKE_MP3_CONTENT" * 1000  # ~16KB file
        with open(audio_path, "wb") as f:
            f.write(content)
        yield tmpdir, audio_path, content


@pytest.mark.unit
def test_audio_stream_invalid_patreon_id(client):
    """Test audio stream rejects invalid patreon_id format."""
    response = client.get("/api/audio/stream/invalid")
    assert response.status_code == 400


@pytest.mark.unit
def test_audio_stream_non_numeric_rejected(client):
    """Test audio stream rejects non-numeric patreon_id."""
    # Letters should be rejected
    response = client.get("/api/audio/stream/abc123")
    assert response.status_code == 400

    # Special characters should be rejected
    response = client.get("/api/audio/stream/123-456")
    assert response.status_code == 400


@pytest.mark.unit
def test_audio_stream_not_found(client):
    """Test audio stream returns 404 for missing file."""
    with patch("app.api.audio_routes.get_audio_path", return_value=None):
        response = client.get("/api/audio/stream/999999")
        assert response.status_code == 404


@pytest.mark.unit
def test_audio_stream_full_file(client, temp_audio_file):
    """Test audio stream returns full file without Range header."""
    tmpdir, audio_path, content = temp_audio_file

    with patch("app.api.audio_routes.AUDIO_DIR", tmpdir):
        response = client.get("/api/audio/stream/123456")
        assert response.status_code == 200
        assert response.content_type == "audio/mpeg"
        assert response.headers.get("Accept-Ranges") == "bytes"
        assert response.headers.get("Content-Length") == str(len(content))
        assert response.data == content


@pytest.mark.unit
def test_audio_stream_range_request(client, temp_audio_file):
    """Test audio stream handles Range requests for seeking."""
    tmpdir, audio_path, content = temp_audio_file

    with patch("app.api.audio_routes.AUDIO_DIR", tmpdir):
        # Request first 100 bytes
        response = client.get(
            "/api/audio/stream/123456",
            headers={"Range": "bytes=0-99"}
        )
        assert response.status_code == 206
        assert response.content_type == "audio/mpeg"
        assert response.headers.get("Content-Range") == f"bytes 0-99/{len(content)}"
        assert response.headers.get("Content-Length") == "100"
        assert response.data == content[:100]


@pytest.mark.unit
def test_audio_stream_range_from_middle(client, temp_audio_file):
    """Test audio stream handles Range requests from middle of file."""
    tmpdir, audio_path, content = temp_audio_file

    with patch("app.api.audio_routes.AUDIO_DIR", tmpdir):
        # Request bytes 100-199
        response = client.get(
            "/api/audio/stream/123456",
            headers={"Range": "bytes=100-199"}
        )
        assert response.status_code == 206
        assert response.headers.get("Content-Range") == f"bytes 100-199/{len(content)}"
        assert response.data == content[100:200]


@pytest.mark.unit
def test_audio_stream_range_open_end(client, temp_audio_file):
    """Test audio stream handles Range request with open end."""
    tmpdir, audio_path, content = temp_audio_file

    with patch("app.api.audio_routes.AUDIO_DIR", tmpdir):
        # Request from byte 100 to end
        response = client.get(
            "/api/audio/stream/123456",
            headers={"Range": "bytes=100-"}
        )
        assert response.status_code == 206
        expected_length = len(content) - 100
        assert response.headers.get("Content-Length") == str(expected_length)
        assert response.data == content[100:]


@pytest.mark.unit
def test_audio_stream_range_suffix(client, temp_audio_file):
    """Test audio stream handles suffix Range request (last N bytes)."""
    tmpdir, audio_path, content = temp_audio_file

    with patch("app.api.audio_routes.AUDIO_DIR", tmpdir):
        # Request last 50 bytes
        response = client.get(
            "/api/audio/stream/123456",
            headers={"Range": "bytes=-50"}
        )
        assert response.status_code == 206
        assert response.data == content[-50:]


@pytest.mark.unit
def test_audio_stream_invalid_range(client, temp_audio_file):
    """Test audio stream rejects invalid Range requests."""
    tmpdir, audio_path, content = temp_audio_file

    with patch("app.api.audio_routes.AUDIO_DIR", tmpdir):
        # Request beyond file size
        response = client.get(
            "/api/audio/stream/123456",
            headers={"Range": f"bytes={len(content) + 100}-"}
        )
        assert response.status_code == 416


@pytest.mark.unit
def test_audio_info_invalid_patreon_id(client):
    """Test audio info rejects invalid patreon_id format."""
    response = client.get("/api/audio/info/invalid")
    assert response.status_code == 400


@pytest.mark.unit
def test_audio_info_not_available(client):
    """Test audio info returns available=false for missing file."""
    with patch("app.api.audio_routes.get_audio_path", return_value=None):
        response = client.get("/api/audio/info/999999")
        assert response.status_code == 200
        data = response.json
        assert data["patreon_id"] == "999999"
        assert data["available"] is False
        assert "size_bytes" not in data
        assert "stream_url" not in data


@pytest.mark.unit
def test_audio_info_available(client, temp_audio_file):
    """Test audio info returns metadata for available file."""
    tmpdir, audio_path, content = temp_audio_file

    with patch("app.api.audio_routes.AUDIO_DIR", tmpdir):
        response = client.get("/api/audio/info/123456")
        assert response.status_code == 200
        data = response.json
        assert data["patreon_id"] == "123456"
        assert data["available"] is True
        assert data["size_bytes"] == len(content)
        assert data["stream_url"] == "/api/audio/stream/123456"


@pytest.mark.unit
def test_parse_range_header_basic():
    """Test parse_range_header with basic ranges."""
    from app.api.audio_routes import parse_range_header

    # Standard range
    assert parse_range_header("bytes=0-99", 1000) == (0, 99)
    assert parse_range_header("bytes=100-199", 1000) == (100, 199)

    # Open end
    assert parse_range_header("bytes=500-", 1000) == (500, 999)

    # Suffix range
    assert parse_range_header("bytes=-100", 1000) == (900, 999)


@pytest.mark.unit
def test_parse_range_header_invalid():
    """Test parse_range_header with invalid ranges."""
    from app.api.audio_routes import parse_range_header

    # None header
    assert parse_range_header(None, 1000) is None

    # Invalid format
    assert parse_range_header("invalid", 1000) is None

    # Start beyond file size
    assert parse_range_header("bytes=2000-", 1000) is None

    # Start > end
    assert parse_range_header("bytes=500-100", 1000) is None


@pytest.mark.unit
def test_parse_range_header_clamps_end():
    """Test parse_range_header clamps end to file size."""
    from app.api.audio_routes import parse_range_header

    # End beyond file size should be clamped
    assert parse_range_header("bytes=0-5000", 1000) == (0, 999)


@pytest.mark.unit
def test_get_audio_path_exists(temp_audio_file):
    """Test get_audio_path returns path for existing file."""
    tmpdir, audio_path, content = temp_audio_file

    with patch("app.api.audio_routes.AUDIO_DIR", tmpdir):
        from app.api.audio_routes import get_audio_path
        result = get_audio_path("123456")
        assert result == audio_path


@pytest.mark.unit
def test_get_audio_path_not_exists():
    """Test get_audio_path returns None for missing file."""
    from app.api.audio_routes import get_audio_path
    with patch("app.api.audio_routes.AUDIO_DIR", "/nonexistent"):
        result = get_audio_path("999999")
        assert result is None
