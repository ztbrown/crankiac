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

@pytest.fixture(scope="function")
def test_db_url():
    """
    Provide DATABASE_URL for PostgreSQL-based tests.

    This fixture requires a test PostgreSQL database to be available.
    Set TEST_DATABASE_URL environment variable or it will use a default test database.
    """
    test_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://localhost:5432/crankiac_test"
    )
    return test_url

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

@pytest.mark.acceptance
@pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None and os.environ.get("DATABASE_URL") is None,
    reason="Requires PostgreSQL database (set TEST_DATABASE_URL or DATABASE_URL)"
)
def test_update_segment_speakers_e2e():
    """
    End-to-end test for updating transcript segment speakers.

    Tests the full stack:
    1. Create episode and transcript segments in database
    2. Update speakers via PATCH endpoint
    3. Verify updates persisted to database
    4. Verify changes retrievable via search API

    Note: This test requires a real PostgreSQL database and Flask server.
    Run with: pytest -m acceptance tests/acceptance/test_e2e.py::test_update_segment_speakers_e2e
    """
    import requests
    from datetime import datetime
    from unittest.mock import patch
    from app.api.app import create_app
    from app.db.connection import get_cursor
    import threading
    import time

    # Use test database if specified, otherwise fall back to DATABASE_URL
    test_db_url = os.environ.get("TEST_DATABASE_URL", os.environ.get("DATABASE_URL"))

    episode_id = None

    # Start Flask server in background with test database
    with patch.dict(os.environ, {"DATABASE_URL": test_db_url}):
        # Create app with test database
        app = create_app()

        # Start server in background thread
        server_thread = threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=5098, use_reloader=False)
        )
        server_thread.daemon = True
        server_thread.start()

        # Wait for server to start
        time.sleep(2)

        server_url = "http://127.0.0.1:5098"

        try:
            # Step 1: Insert test data directly into the database
            # Create test episode
            with get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO episodes (patreon_id, title, published_at, processed, is_free)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    ("test-e2e-speaker-update", "E2E Test Episode", datetime(2023, 6, 15), True, True)
                )
                episode_id = cursor.fetchone()["id"]

                # Create test transcript segments with speakers
                segments_data = [
                    ("Hello", 0.0, 0.5, 0, "SPEAKER_00"),
                    ("world", 0.5, 1.0, 1, "SPEAKER_00"),
                    ("this", 1.0, 1.5, 2, "SPEAKER_01"),
                    ("is", 1.5, 2.0, 3, "SPEAKER_01"),
                    ("a", 2.0, 2.5, 4, "SPEAKER_00"),
                    ("test", 2.5, 3.0, 5, "SPEAKER_00"),
                ]

                for word, start, end, idx, speaker in segments_data:
                    cursor.execute(
                        """
                        INSERT INTO transcript_segments
                        (episode_id, word, start_time, end_time, segment_index, speaker)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (episode_id, word, start, end, idx, speaker)
                    )

            # Get segment IDs for the update
            with get_cursor(commit=False) as cursor:
                cursor.execute(
                    """
                    SELECT id, word, speaker FROM transcript_segments
                    WHERE episode_id = %s
                    ORDER BY segment_index
                    """,
                    (episode_id,)
                )
                segments = cursor.fetchall()

            # Step 2: Update speakers via PATCH endpoint
            # Update first two segments (Hello, world) to Matt
            # Update next two segments (this, is) to Will
            updates = [
                {"id": segments[0]["id"], "speaker": "Matt"},
                {"id": segments[1]["id"], "speaker": "Matt"},
                {"id": segments[2]["id"], "speaker": "Will"},
                {"id": segments[3]["id"], "speaker": "Will"},
            ]

            response = requests.patch(
                f"{server_url}/api/transcripts/segments/speaker",
                json={"updates": updates}
            )

            # Verify the API response
            assert response.status_code == 200
            data = response.json()
            assert data["updated"] == 4, f"Expected 4 updates, got {data['updated']}"
            assert data["requested"] == 4

            # Step 3: Verify updates persisted to database
            with get_cursor(commit=False) as cursor:
                cursor.execute(
                    """
                    SELECT id, word, speaker FROM transcript_segments
                    WHERE episode_id = %s
                    ORDER BY segment_index
                    """,
                    (episode_id,)
                )
                updated_segments = cursor.fetchall()

            # Verify the first 4 segments were updated correctly
            assert updated_segments[0]["word"] == "Hello"
            assert updated_segments[0]["speaker"] == "Matt", \
                f"Expected 'Matt', got '{updated_segments[0]['speaker']}'"
            assert updated_segments[1]["word"] == "world"
            assert updated_segments[1]["speaker"] == "Matt"
            assert updated_segments[2]["word"] == "this"
            assert updated_segments[2]["speaker"] == "Will"
            assert updated_segments[3]["word"] == "is"
            assert updated_segments[3]["speaker"] == "Will"

            # Verify the last 2 segments remain unchanged
            assert updated_segments[4]["speaker"] == "SPEAKER_00"
            assert updated_segments[5]["speaker"] == "SPEAKER_00"

            # Step 4: Verify changes are retrievable via search API
            # Search for word "Hello" and verify speaker is now Matt
            search_response = requests.get(f"{server_url}/api/transcripts/search?q=Hello")
            assert search_response.status_code == 200
            search_data = search_response.json()

            # Find our test episode in results
            test_results = [r for r in search_data["results"] if r["episode_id"] == episode_id]
            assert len(test_results) > 0, "Test episode not found in search results"
            assert test_results[0]["speaker"] == "Matt", \
                f"Expected speaker 'Matt' in search results, got '{test_results[0]['speaker']}'"

            # Search by speaker "Matt" and verify we get the updated segments
            speaker_search_response = requests.get(
                f"{server_url}/api/transcripts/search/speaker?speaker=Matt&q=Hello"
            )
            assert speaker_search_response.status_code == 200
            speaker_data = speaker_search_response.json()
            assert speaker_data["speaker"] == "Matt"

            # Verify our test episode is in the results
            matt_results = [r for r in speaker_data["results"] if r["episode_id"] == episode_id]
            assert len(matt_results) > 0, "Test episode not found in speaker search results"
            assert matt_results[0]["word"] == "Hello"
            assert matt_results[0]["speaker"] == "Matt"

        finally:
            # Clean up test data
            if episode_id is not None:
                with get_cursor() as cursor:
                    cursor.execute("DELETE FROM episodes WHERE id = %s", (episode_id,))
