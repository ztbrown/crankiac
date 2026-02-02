"""
Integration tests for transcript speaker updates.

These tests verify the full stack (endpoint -> storage -> database) for the
PATCH /api/transcripts/segments/speaker endpoint.
"""
import pytest
import os
from datetime import datetime
from unittest.mock import patch
from decimal import Decimal


@pytest.fixture
def client():
    """Create a test client with real database connection."""
    from app.api.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None and os.environ.get("DATABASE_URL") is None,
    reason="Requires PostgreSQL database (set TEST_DATABASE_URL or DATABASE_URL)"
)
def test_update_segment_speakers_integration(client):
    """
    Integration test for updating transcript segment speakers.

    Tests the full stack without a running server:
    1. Create episode and transcript segments in database
    2. Update speakers via PATCH endpoint using test client
    3. Verify updates persisted to database
    4. Clean up test data
    """
    from app.db.connection import get_cursor

    episode_id = None

    try:
        # Step 1: Create test episode and segments
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO episodes (patreon_id, title, published_at, processed, is_free)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                ("test-integration-001", "Integration Test Episode", datetime(2023, 6, 15), True, True)
            )
            episode_id = cursor.fetchone()["id"]

            # Create test transcript segments with speakers
            segments_data = [
                ("Hello", 0.0, 0.5, 0, "SPEAKER_00"),
                ("world", 0.5, 1.0, 1, "SPEAKER_00"),
                ("this", 1.0, 1.5, 2, "SPEAKER_01"),
                ("is", 1.5, 2.0, 3, "SPEAKER_01"),
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

        # Step 2: Update speakers via API endpoint
        updates = [
            {"id": segments[0]["id"], "speaker": "Matt"},
            {"id": segments[1]["id"], "speaker": "Matt"},
            {"id": segments[2]["id"], "speaker": "Will"},
            {"id": segments[3]["id"], "speaker": "Will"},
        ]

        response = client.patch(
            "/api/transcripts/segments/speaker",
            json={"updates": updates}
        )

        # Verify the API response
        assert response.status_code == 200
        data = response.json
        assert data["updated"] == 4
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

        # Verify all segments were updated correctly
        assert updated_segments[0]["word"] == "Hello"
        assert updated_segments[0]["speaker"] == "Matt"
        assert updated_segments[1]["word"] == "world"
        assert updated_segments[1]["speaker"] == "Matt"
        assert updated_segments[2]["word"] == "this"
        assert updated_segments[2]["speaker"] == "Will"
        assert updated_segments[3]["word"] == "is"
        assert updated_segments[3]["speaker"] == "Will"

    finally:
        # Clean up test data
        if episode_id is not None:
            with get_cursor() as cursor:
                cursor.execute("DELETE FROM episodes WHERE id = %s", (episode_id,))


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None and os.environ.get("DATABASE_URL") is None,
    reason="Requires PostgreSQL database (set TEST_DATABASE_URL or DATABASE_URL)"
)
def test_update_segment_speakers_partial_update(client):
    """
    Test that partial updates work correctly.

    When some segment IDs don't exist, the API should still update the ones that do exist.
    """
    from app.db.connection import get_cursor

    episode_id = None

    try:
        # Create test episode and segments
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO episodes (patreon_id, title, published_at, processed, is_free)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                ("test-partial-001", "Partial Update Test", datetime(2023, 6, 15), True, True)
            )
            episode_id = cursor.fetchone()["id"]

            # Create one test segment
            cursor.execute(
                """
                INSERT INTO transcript_segments
                (episode_id, word, start_time, end_time, segment_index, speaker)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (episode_id, "test", 0.0, 0.5, 0, "SPEAKER_00")
            )
            segment_id = cursor.fetchone()["id"]

        # Try to update one existing and one non-existing segment
        # Use a very large ID that's guaranteed not to exist
        non_existent_id = 999999999
        updates = [
            {"id": segment_id, "speaker": "Matt"},
            {"id": non_existent_id, "speaker": "Will"},  # This ID doesn't exist
        ]

        response = client.patch(
            "/api/transcripts/segments/speaker",
            json={"updates": updates}
        )

        # Verify the API response
        assert response.status_code == 200
        data = response.json
        assert data["updated"] == 1  # Only 1 segment was actually updated
        assert data["requested"] == 2  # 2 were requested

        # Verify the existing segment was updated
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT speaker FROM transcript_segments WHERE id = %s",
                (segment_id,)
            )
            result = cursor.fetchone()
            assert result["speaker"] == "Matt"

    finally:
        # Clean up test data
        if episode_id is not None:
            with get_cursor() as cursor:
                cursor.execute("DELETE FROM episodes WHERE id = %s", (episode_id,))


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None and os.environ.get("DATABASE_URL") is None,
    reason="Requires PostgreSQL database (set TEST_DATABASE_URL or DATABASE_URL)"
)
def test_update_segment_speakers_validation_errors(client):
    """
    Test that validation errors are properly returned.
    """
    # Test missing updates field
    response = client.patch("/api/transcripts/segments/speaker", json={})
    assert response.status_code == 400
    assert "updates" in response.json["error"]

    # Test empty updates array
    response = client.patch("/api/transcripts/segments/speaker", json={"updates": []})
    assert response.status_code == 400
    assert "empty" in response.json["error"]

    # Test invalid id type
    response = client.patch(
        "/api/transcripts/segments/speaker",
        json={"updates": [{"id": "not-an-int", "speaker": "Matt"}]}
    )
    assert response.status_code == 400
    assert "integer" in response.json["error"]

    # Test invalid speaker type
    response = client.patch(
        "/api/transcripts/segments/speaker",
        json={"updates": [{"id": 123, "speaker": 456}]}
    )
    assert response.status_code == 400
    assert "string" in response.json["error"]

    # Test missing speaker field
    response = client.patch(
        "/api/transcripts/segments/speaker",
        json={"updates": [{"id": 123}]}
    )
    assert response.status_code == 400
    assert "speaker" in response.json["error"]
