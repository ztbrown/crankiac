import pytest
import tempfile
import os
import threading
import time
from unittest.mock import patch

@pytest.fixture(scope="module")
def app_server():
    """Start the Flask app in a background thread for acceptance tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    with patch("app.config.Config.DATABASE_PATH", db_path):
        with patch("app.config.Config.PORT", 5099):
            from app.api.app import create_app
            app = create_app()

            server_thread = threading.Thread(
                target=lambda: app.run(host="127.0.0.1", port=5099, use_reloader=False)
            )
            server_thread.daemon = True
            server_thread.start()

            # Wait for server to start
            time.sleep(1)

            yield "http://127.0.0.1:5099"

    os.unlink(db_path)

@pytest.mark.acceptance
def test_home_page_loads(app_server):
    """Test that the home page loads successfully."""
    import requests
    response = requests.get(f"{app_server}/")
    assert response.status_code == 200
    assert "Search" in response.text
    assert "search-input" in response.text

@pytest.mark.acceptance
def test_search_flow(app_server):
    """Test the complete search flow via API."""
    import requests

    # Perform a search
    response = requests.get(f"{app_server}/api/search?q=Python")
    assert response.status_code == 200

    data = response.json()
    assert "results" in data
    assert len(data["results"]) > 0
    assert any(r["name"] == "Python" for r in data["results"])

@pytest.mark.acceptance
def test_empty_search_handled(app_server):
    """Test that empty search is handled gracefully."""
    import requests

    response = requests.get(f"{app_server}/api/search?q=")
    assert response.status_code == 200
    assert response.json()["results"] == []

@pytest.mark.acceptance
def test_no_results_search(app_server):
    """Test search with no matching results."""
    import requests

    response = requests.get(f"{app_server}/api/search?q=xyznonexistent")
    assert response.status_code == 200
    assert response.json()["results"] == []

@pytest.mark.acceptance
def test_static_assets_served(app_server):
    """Test that static assets are served correctly."""
    import requests

    # CSS
    css_response = requests.get(f"{app_server}/static/styles.css")
    assert css_response.status_code == 200
    assert "search-box" in css_response.text

    # JavaScript
    js_response = requests.get(f"{app_server}/static/app.js")
    assert js_response.status_code == 200
    assert "performSearch" in js_response.text

@pytest.mark.acceptance
def test_health_check(app_server):
    """Test health check endpoint works."""
    import requests

    response = requests.get(f"{app_server}/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
