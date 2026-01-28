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
def test_version_endpoint(client):
    """Test version endpoint returns current version."""
    from app import __version__
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json == {"version": __version__}
    """Test version endpoint returns version info."""
    response = client.get("/api/version")
    assert response.status_code == 200
    data = response.json
    assert "version" in data
    # Version should follow semver format (MAJOR.MINOR.PATCH)
    version = data["version"]
    parts = version.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)

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
def test_on_this_day_endpoint_default_date(client):
    """Test on-this-day endpoint uses current date by default."""
    from datetime import date
    today = date.today()

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchall.return_value = []
        mock_cursor.return_value = mock_ctx

        response = client.get("/api/transcripts/on-this-day")
        assert response.status_code == 200
        data = response.json
        assert data["date"]["month"] == today.month
        assert data["date"]["day"] == today.day
        assert "episodes" in data


@pytest.mark.unit
def test_on_this_day_endpoint_custom_date(client):
    """Test on-this-day endpoint accepts custom month/day."""
    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchall.return_value = []
        mock_cursor.return_value = mock_ctx

        response = client.get("/api/transcripts/on-this-day?month=7&day=4")
        assert response.status_code == 200
        data = response.json
        assert data["date"]["month"] == 7
        assert data["date"]["day"] == 4


@pytest.mark.unit
def test_on_this_day_endpoint_invalid_month(client):
    """Test on-this-day endpoint rejects invalid month."""
    response = client.get("/api/transcripts/on-this-day?month=13")
    assert response.status_code == 400
    assert "month" in response.json["error"]


@pytest.mark.unit
def test_on_this_day_endpoint_invalid_day(client):
    """Test on-this-day endpoint rejects invalid day."""
    response = client.get("/api/transcripts/on-this-day?day=32")
    assert response.status_code == 400
    assert "day" in response.json["error"]


def test_transcript_search_empty_query(client):
    """Test transcript search with empty query returns empty results."""
    response = client.get("/api/transcripts/search?q=")
    assert response.status_code == 200
    assert response.json["results"] == []
    assert response.json["query"] == ""
    assert response.json["total"] == 0


@pytest.mark.unit
def test_transcript_search_response_includes_fuzzy_params(client):
    """Test that transcript search response includes fuzzy parameters."""
    with patch("app.api.transcript_routes.search_fuzzy_word", return_value=([], 0)):
        response = client.get("/api/transcripts/search?q=test")
        assert response.status_code == 200
        data = response.json
        assert "fuzzy" in data
        assert "threshold" in data
        assert data["fuzzy"] is True
        assert data["threshold"] == 0.3


@pytest.mark.unit
def test_transcript_search_fuzzy_disabled(client):
    """Test that fuzzy matching can be disabled."""
    with patch("app.api.transcript_routes.search_single_word", return_value=([], 0)) as mock:
        response = client.get("/api/transcripts/search?q=test&fuzzy=false")
        assert response.status_code == 200
        mock.assert_called_once()
        data = response.json
        assert data["fuzzy"] is False
        assert data["threshold"] is None


@pytest.mark.unit
def test_transcript_search_custom_threshold(client):
    """Test that custom similarity threshold is respected."""
    with patch("app.api.transcript_routes.search_fuzzy_word", return_value=([], 0)):
        response = client.get("/api/transcripts/search?q=test&threshold=0.5")
        assert response.status_code == 200
        data = response.json
        assert data["threshold"] == 0.5


@pytest.mark.unit
def test_transcript_search_threshold_bounds(client):
    """Test that threshold is bounded between 0.1 and 0.9."""
    with patch("app.api.transcript_routes.search_fuzzy_word", return_value=([], 0)):
        # Test lower bound
        response = client.get("/api/transcripts/search?q=test&threshold=0.01")
        assert response.json["threshold"] == 0.1

        # Test upper bound
        response = client.get("/api/transcripts/search?q=test&threshold=0.99")
        assert response.json["threshold"] == 0.9

def test_transcript_search_accepts_filter_params(client):
    """Test transcript search accepts filter parameters without error."""
    with patch("app.api.transcript_routes.search_single_word", return_value=([], 0)):
        response = client.get(
            "/api/transcripts/search?q=test"
            "&fuzzy=false"
            "&date_from=2023-01-01"
            "&date_to=2023-12-31"
            "&episode_number=123"
            "&content_type=free"
        )
        assert response.status_code == 200
        data = response.json
        assert "filters" in data
        assert data["filters"]["date_from"] == "2023-01-01"
        assert data["filters"]["date_to"] == "2023-12-31"
        assert data["filters"]["episode_number"] == 123
        assert data["filters"]["content_type"] == "free"


@pytest.mark.unit
def test_transcript_search_filters_omitted_when_empty(client):
    """Test transcript search omits filters that are not provided."""
    with patch("app.api.transcript_routes.search_single_word", return_value=([], 0)):
        response = client.get("/api/transcripts/search?q=test&fuzzy=false&content_type=all")
        assert response.status_code == 200
        data = response.json
        # Filters should be empty when content_type is 'all' (default)
        assert data["filters"] == {}


@pytest.mark.unit
def test_transcript_search_content_type_premium(client):
    """Test transcript search accepts premium content type filter."""
    with patch("app.api.transcript_routes.search_single_word", return_value=([], 0)):
        response = client.get("/api/transcripts/search?q=test&fuzzy=false&content_type=premium")
        assert response.status_code == 200
        assert response.json["filters"]["content_type"] == "premium"


@pytest.mark.unit
def test_fuzzy_word_search_with_filters(client):
    """Test fuzzy word search passes filters to search function."""
    with patch("app.api.transcript_routes.search_fuzzy_word", return_value=([], 0)) as mock:
        response = client.get(
            "/api/transcripts/search?q=test"
            "&date_from=2023-01-01"
            "&content_type=free"
        )
        assert response.status_code == 200
        # Verify filters were passed to search_fuzzy_word
        mock.assert_called_once()
        call_args = mock.call_args
        filters_arg = call_args[0][4]  # 5th positional arg is filters
        assert filters_arg["date_from"] == "2023-01-01"
        assert filters_arg["content_type"] == "free"


@pytest.mark.unit
def test_fuzzy_phrase_search_with_filters(client):
    """Test fuzzy phrase search passes filters to search function."""
    with patch("app.api.transcript_routes.search_fuzzy_phrase", return_value=([], 0)) as mock:
        response = client.get(
            "/api/transcripts/search?q=hello+world"
            "&episode_number=42"
            "&content_type=premium"
        )
        assert response.status_code == 200
        # Verify filters were passed to search_fuzzy_phrase
        mock.assert_called_once()
        call_args = mock.call_args
        filters_arg = call_args[0][4]  # 5th positional arg is filters
        assert filters_arg["episode_number"] == 42
        assert filters_arg["content_type"] == "premium"


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
