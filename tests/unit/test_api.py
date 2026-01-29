import pytest
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

@pytest.mark.unit
def test_health_endpoint(client):
    """Test health endpoint returns ok."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}

@pytest.mark.unit
def test_search_empty_query(client):
    """Test search with empty query returns empty results."""
    response = client.get("/api/search?q=")
    assert response.status_code == 200
    assert response.json == {"results": [], "query": ""}

@pytest.mark.unit
def test_search_no_query_param(client):
    """Test search with no query param returns empty results."""
    response = client.get("/api/search")
    assert response.status_code == 200
    assert response.json == {"results": [], "query": ""}

@pytest.mark.unit
def test_search_with_query(client):
    """Test search with query calls search_items and returns results."""
    mock_results = [{"id": 1, "name": "Test", "description": "Test item"}]

    with patch("app.api.routes.search_items", return_value=mock_results):
        response = client.get("/api/search?q=test")
        assert response.status_code == 200
        assert response.json["query"] == "test"
        assert response.json["results"] == mock_results

@pytest.mark.unit
def test_search_response_format(client):
    """Test search response has correct format."""
    with patch("app.api.routes.search_items", return_value=[]):
        response = client.get("/api/search?q=anything")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "query" in data
        assert isinstance(data["results"], list)

@pytest.mark.unit
def test_context_endpoint_missing_params(client):
    """Test context endpoint requires episode_id and segment_index."""
    response = client.get("/api/transcripts/context")
    assert response.status_code == 400
    assert "error" in response.json

@pytest.mark.unit
def test_context_endpoint_missing_segment_index(client):
    """Test context endpoint requires segment_index."""
    response = client.get("/api/transcripts/context?episode_id=1")
    assert response.status_code == 400
    assert "error" in response.json


@pytest.mark.unit
def test_speakers_endpoint(client):
    """Test speakers endpoint returns list of speakers."""
    mock_rows = [
        {"speaker": "SPEAKER_01", "word_count": 100},
        {"speaker": "SPEAKER_02", "word_count": 50},
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/speakers")
        assert response.status_code == 200
        data = response.json
        assert "speakers" in data
        assert isinstance(data["speakers"], list)


@pytest.mark.unit
def test_search_by_speaker_missing_param(client):
    """Test search by speaker requires speaker param."""
    response = client.get("/api/transcripts/search/speaker?q=test")
    assert response.status_code == 400
    assert "error" in response.json
    assert "speaker" in response.json["error"]


@pytest.mark.unit
def test_search_by_speaker_with_params(client):
    """Test search by speaker with valid params."""
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "Test Episode",
            "patreon_id": "123",
            "published_at": None,
            "youtube_url": None,
            "is_free": True,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search/speaker?speaker=SPEAKER_01&q=test")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "speaker" in data
        assert data["speaker"] == "SPEAKER_01"


@pytest.mark.unit
def test_search_with_date_filter(client):
    """Test search with date_from and date_to filters."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Test Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": "https://youtube.com/watch?v=123",
            "is_free": True,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&date_from=2023-01-01&date_to=2023-12-31")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["date_from"] == "2023-01-01"
        assert data["filters"]["date_to"] == "2023-12-31"


@pytest.mark.unit
def test_search_with_episode_number_filter(client):
    """Test search with episode_number filter."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0042 - Test Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": None,
            "is_free": False,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&episode_number=42")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["episode_number"] == 42


@pytest.mark.unit
def test_search_with_content_type_free(client):
    """Test search with content_type=free filter."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Free Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": "https://youtube.com/watch?v=123",
            "is_free": True,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&content_type=free")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["content_type"] == "free"
        assert data["results"][0]["is_free"] is True


@pytest.mark.unit
def test_search_with_content_type_premium(client):
    """Test search with content_type=premium filter."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Premium Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": None,
            "is_free": False,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&content_type=premium")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["content_type"] == "premium"
        assert data["results"][0]["is_free"] is False


@pytest.mark.unit
def test_search_with_multiple_filters(client):
    """Test search with multiple filters combined."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0042 - Test Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": "https://youtube.com/watch?v=123",
            "is_free": True,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&date_from=2023-01-01&date_to=2023-12-31&episode_number=42&content_type=free")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["date_from"] == "2023-01-01"
        assert data["filters"]["date_to"] == "2023-12-31"
        assert data["filters"]["episode_number"] == 42
        assert data["filters"]["content_type"] == "free"


@pytest.mark.unit
def test_search_with_invalid_content_type_defaults_to_all(client):
    """Test search with invalid content_type defaults to no filter."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Test Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": None,
            "is_free": False,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&content_type=invalid")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        # Invalid content_type should be excluded from filters
        assert "content_type" not in data.get("filters", {})


@pytest.mark.unit
def test_map_speaker_to_name_known_speakers():
    """Test mapping SPEAKER_XX to known host names."""
    from app.api.transcript_routes import map_speaker_to_name

    assert map_speaker_to_name("SPEAKER_00") == "Matt"
    assert map_speaker_to_name("SPEAKER_01") == "Will"
    assert map_speaker_to_name("SPEAKER_02") == "Felix"
    assert map_speaker_to_name("SPEAKER_03") == "Amber"
    assert map_speaker_to_name("SPEAKER_04") == "Virgil"


@pytest.mark.unit
def test_map_speaker_to_name_unknown_speaker():
    """Test that speakers beyond known list keep original ID."""
    from app.api.transcript_routes import map_speaker_to_name

    assert map_speaker_to_name("SPEAKER_05") == "SPEAKER_05"
    assert map_speaker_to_name("SPEAKER_99") == "SPEAKER_99"


@pytest.mark.unit
def test_map_speaker_to_name_non_speaker_format():
    """Test that non-SPEAKER_XX formats are preserved."""
    from app.api.transcript_routes import map_speaker_to_name

    assert map_speaker_to_name("Guest") == "Guest"
    assert map_speaker_to_name("Unknown") == "Unknown"
    assert map_speaker_to_name("speaker_00") == "speaker_00"  # lowercase not matched


@pytest.mark.unit
def test_map_speaker_to_name_none():
    """Test that None input returns None."""
    from app.api.transcript_routes import map_speaker_to_name

    assert map_speaker_to_name(None) is None


@pytest.mark.unit
def test_context_endpoint_maps_speakers(client):
    """Test context endpoint maps speaker IDs to known names."""
    mock_rows = [
        {"word": "hello", "segment_index": 9, "start_time": 1.0, "end_time": 1.5, "speaker": "SPEAKER_00"},
        {"word": "there", "segment_index": 10, "start_time": 1.5, "end_time": 2.0, "speaker": "SPEAKER_00"},
        {"word": "hi", "segment_index": 11, "start_time": 2.0, "end_time": 2.5, "speaker": "SPEAKER_01"},
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/context?episode_id=1&segment_index=10")
        assert response.status_code == 200
        data = response.json

        # center_speaker should be mapped
        assert data["center_speaker"] == "Matt"

        # speaker_turns should have mapped names
        assert len(data["speaker_turns"]) == 2
        assert data["speaker_turns"][0]["speaker"] == "Matt"
        assert data["speaker_turns"][0]["text"] == "hello there"
        assert data["speaker_turns"][1]["speaker"] == "Will"
        assert data["speaker_turns"][1]["text"] == "hi"
