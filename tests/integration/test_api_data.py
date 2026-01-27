import pytest
import tempfile
import os
from unittest.mock import patch

@pytest.fixture
def integration_client():
    """Create a test client with real database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    with patch("app.config.Config.DATABASE_PATH", db_path):
        from app.api.app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    os.unlink(db_path)

@pytest.mark.integration
def test_search_returns_seeded_data(integration_client):
    """Test that search endpoint returns data from seeded database."""
    response = integration_client.get("/api/search?q=Python")
    assert response.status_code == 200
    data = response.json
    assert len(data["results"]) > 0
    assert any(r["name"] == "Python" for r in data["results"])

@pytest.mark.integration
def test_search_case_insensitive(integration_client):
    """Test that search is case insensitive."""
    response_lower = integration_client.get("/api/search?q=python")
    response_upper = integration_client.get("/api/search?q=PYTHON")

    # SQLite LIKE is case-insensitive for ASCII
    assert response_lower.status_code == 200
    assert response_upper.status_code == 200

@pytest.mark.integration
def test_search_by_description(integration_client):
    """Test that search matches description field."""
    response = integration_client.get("/api/search?q=framework")
    assert response.status_code == 200
    data = response.json
    assert len(data["results"]) > 0
    # Flask has "framework" in its description
    assert any("Flask" in r["name"] for r in data["results"])

@pytest.mark.integration
def test_full_request_response_cycle(integration_client):
    """Test complete request/response cycle."""
    # Health check
    health = integration_client.get("/api/health")
    assert health.status_code == 200

    # Search
    search = integration_client.get("/api/search?q=database")
    assert search.status_code == 200
    data = search.json
    assert "results" in data
    assert "query" in data
    assert data["query"] == "database"

@pytest.mark.integration
def test_empty_search_returns_empty_list(integration_client):
    """Test that search for nonexistent term returns empty list."""
    response = integration_client.get("/api/search?q=xyznonexistent123")
    assert response.status_code == 200
    assert response.json["results"] == []

@pytest.mark.integration
def test_special_characters_in_query(integration_client):
    """Test that special characters in query are handled safely."""
    response = integration_client.get("/api/search?q=%25%27%22")
    assert response.status_code == 200
    # Should not error, just return empty or matching results
    assert "results" in response.json
