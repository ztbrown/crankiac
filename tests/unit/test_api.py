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
def test_context_endpoint_speaker_turns_include_start_time(client):
    """Test context endpoint includes start_time in speaker_turns."""
    from decimal import Decimal
    mock_segments = [
        {"word": "Hello", "segment_index": 10, "start_time": Decimal("1.5"), "end_time": Decimal("2.0"), "speaker": "SPEAKER_01"},
        {"word": "world", "segment_index": 11, "start_time": Decimal("2.0"), "end_time": Decimal("2.5"), "speaker": "SPEAKER_01"},
        {"word": "Hi", "segment_index": 12, "start_time": Decimal("3.0"), "end_time": Decimal("3.5"), "speaker": "SPEAKER_02"},
        {"word": "there", "segment_index": 13, "start_time": Decimal("3.5"), "end_time": Decimal("4.0"), "speaker": "SPEAKER_02"},
    ]
    mock_mappings = {"SPEAKER_01": "Will", "SPEAKER_02": "Felix"}

    with patch("app.api.transcript_routes.get_speaker_mappings_for_episode") as mock_get_mappings:
        mock_get_mappings.return_value = mock_mappings
        with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
            mock_ctx = MagicMock()
            mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.fetchall.return_value = mock_segments

            response = client.get("/api/transcripts/context?episode_id=1&segment_index=11")
            assert response.status_code == 200
            data = response.json

            assert "speaker_turns" in data
            assert len(data["speaker_turns"]) == 2

            # First turn: Will (mapped from SPEAKER_01) starting at 1.5
            assert data["speaker_turns"][0]["speaker"] == "Will"
            assert data["speaker_turns"][0]["text"] == "Hello world"
            assert data["speaker_turns"][0]["start_time"] == 1.5

            # Second turn: Felix (mapped from SPEAKER_02) starting at 3.0
            assert data["speaker_turns"][1]["speaker"] == "Felix"
            assert data["speaker_turns"][1]["text"] == "Hi there"
            assert data["speaker_turns"][1]["start_time"] == 3.0


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
def test_speaker_mappings_endpoint_missing_episode_id(client):
    """Test speaker-mappings endpoint requires episode_id."""
    response = client.get("/api/transcripts/speaker-mappings")
    assert response.status_code == 400
    assert "error" in response.json
    assert "episode_id" in response.json["error"]


@pytest.mark.unit
def test_speaker_mappings_get_endpoint(client):
    """Test GET speaker-mappings returns mappings for episode."""
    from datetime import datetime
    mock_rows = [
        {
            "id": 1,
            "speaker_label": "SPEAKER_00",
            "speaker_name": "Matt",
            "created_at": datetime(2023, 1, 1),
            "updated_at": datetime(2023, 1, 1)
        },
        {
            "id": 2,
            "speaker_label": "SPEAKER_01",
            "speaker_name": "Will",
            "created_at": datetime(2023, 1, 1),
            "updated_at": datetime(2023, 1, 1)
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/speaker-mappings?episode_id=1")
        assert response.status_code == 200
        data = response.json
        assert "episode_id" in data
        assert data["episode_id"] == 1
        assert "mappings" in data
        assert len(data["mappings"]) == 2


@pytest.mark.unit
def test_speaker_mappings_put_missing_body(client):
    """Test PUT speaker-mappings requires JSON body."""
    response = client.put("/api/transcripts/speaker-mappings")
    # Flask returns 415 when no content-type is provided
    assert response.status_code in (400, 415)


@pytest.mark.unit
def test_speaker_mappings_put_missing_episode_id(client):
    """Test PUT speaker-mappings requires episode_id."""
    response = client.put(
        "/api/transcripts/speaker-mappings",
        json={"mappings": []}
    )
    assert response.status_code == 400
    assert "episode_id" in response.json["error"]


@pytest.mark.unit
def test_speaker_mappings_delete_missing_params(client):
    """Test DELETE speaker-mappings requires episode_id and speaker_label."""
    response = client.delete("/api/transcripts/speaker-mappings")
    assert response.status_code == 400
    assert "episode_id" in response.json["error"]

    response = client.delete("/api/transcripts/speaker-mappings?episode_id=1")
    assert response.status_code == 400
    assert "speaker_label" in response.json["error"]


@pytest.mark.unit
def test_apply_speaker_mapping_function():
    """Test the apply_speaker_mapping helper function."""
    from app.api.transcript_routes import apply_speaker_mapping

    mappings = {"SPEAKER_00": "Matt", "SPEAKER_01": "Will"}

    # Returns mapped name
    assert apply_speaker_mapping("SPEAKER_00", mappings) == "Matt"
    assert apply_speaker_mapping("SPEAKER_01", mappings) == "Will"

    # Returns original if no mapping
    assert apply_speaker_mapping("SPEAKER_02", mappings) == "SPEAKER_02"

    # Returns None for None input
    assert apply_speaker_mapping(None, mappings) is None

    # Works with empty mappings
    assert apply_speaker_mapping("SPEAKER_00", {}) == "SPEAKER_00"
