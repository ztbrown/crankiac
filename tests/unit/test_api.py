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
