"""Tests for transcript editor API endpoints."""

import pytest
from app.api.app import create_app
from app.db.connection import get_cursor
from app.transcription.diarization import KNOWN_SPEAKERS


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def test_episode(client):
    """Create a test episode with segments."""
    with get_cursor() as cursor:
        # Create test episode
        cursor.execute(
            """
            INSERT INTO episodes (patreon_id, title, published_at, processed)
            VALUES ('test123', 'Test Episode', '2024-01-01', true)
            RETURNING id
            """
        )
        episode_id = cursor.fetchone()['id']

        # Add some test segments with different speakers
        segments = [
            (episode_id, 'Hello', '0.0', '0.5', 0, 'Matt'),
            (episode_id, 'there', '0.5', '1.0', 1, 'Matt'),
            (episode_id, 'Shane', '1.0', '1.5', 2, 'Shane'),
            (episode_id, 'here', '1.5', '2.0', 3, 'Shane'),
            (episode_id, 'Guest', '2.0', '2.5', 4, 'Alice'),
        ]

        for seg in segments:
            cursor.execute(
                """
                INSERT INTO transcript_segments
                (episode_id, word, start_time, end_time, segment_index, speaker)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                seg
            )

    yield episode_id

    # Cleanup
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM transcript_segments WHERE episode_id = %s", (episode_id,))
        cursor.execute("DELETE FROM episodes WHERE id = %s", (episode_id,))


class TestGetSpeakers:
    """Tests for GET /api/transcripts/episode/<id>/speakers endpoint."""

    def test_get_speakers_list(self, client, test_episode):
        """Test getting speakers list returns known and episode speakers."""
        response = client.get(f'/api/transcripts/episode/{test_episode}/speakers')

        assert response.status_code == 200
        data = response.get_json()

        # Should return known speakers
        assert 'known_speakers' in data
        assert data['known_speakers'] == KNOWN_SPEAKERS

        # Should return distinct speakers from episode
        assert 'episode_speakers' in data
        assert set(data['episode_speakers']) == {'Matt', 'Shane', 'Alice'}

    def test_get_speakers_invalid_episode(self, client):
        """Test getting speakers for non-existent episode returns 404."""
        response = client.get('/api/transcripts/episode/99999/speakers')

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data


class TestUpdateSpeaker:
    """Tests for PATCH /api/transcripts/segments/speaker endpoint."""

    def test_update_speaker_single(self, client, test_episode):
        """Test updating speaker for a single segment."""
        # Get a segment ID
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT id FROM transcript_segments WHERE episode_id = %s LIMIT 1",
                (test_episode,)
            )
            segment_id = cursor.fetchone()['id']

        # Update speaker using correct format
        response = client.patch(
            '/api/transcripts/segments/speaker',
            json={'updates': [{'id': segment_id, 'speaker': 'NewSpeaker'}]}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['updated'] == 1
        assert data['requested'] == 1

        # Verify update in database
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT speaker FROM transcript_segments WHERE id = %s",
                (segment_id,)
            )
            assert cursor.fetchone()['speaker'] == 'NewSpeaker'

    def test_update_speaker_bulk(self, client, test_episode):
        """Test updating speaker for multiple segments."""
        # Get multiple segment IDs
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT id FROM transcript_segments WHERE episode_id = %s LIMIT 3",
                (test_episode,)
            )
            segment_ids = [row['id'] for row in cursor.fetchall()]

        # Update speaker for all using correct format
        updates = [{'id': seg_id, 'speaker': 'BulkSpeaker'} for seg_id in segment_ids]
        response = client.patch(
            '/api/transcripts/segments/speaker',
            json={'updates': updates}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['updated'] == 3
        assert data['requested'] == 3

        # Verify updates in database
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                f"SELECT speaker FROM transcript_segments WHERE id = ANY(%s)",
                (segment_ids,)
            )
            speakers = [row['speaker'] for row in cursor.fetchall()]
            assert all(s == 'BulkSpeaker' for s in speakers)

    def test_update_speaker_validation(self, client):
        """Test that updates array is required and validated."""
        # Missing updates
        response = client.patch(
            '/api/transcripts/segments/speaker',
            json={'speaker': 'Test'}
        )
        assert response.status_code == 400

        # Updates not an array
        response = client.patch(
            '/api/transcripts/segments/speaker',
            json={'updates': 'not an array'}
        )
        assert response.status_code == 400

        # Update missing id
        response = client.patch(
            '/api/transcripts/segments/speaker',
            json={'updates': [{'speaker': 'Test'}]}
        )
        assert response.status_code == 400

        # Update missing speaker
        response = client.patch(
            '/api/transcripts/segments/speaker',
            json={'updates': [{'id': 1}]}
        )
        assert response.status_code == 400

    def test_update_speaker_empty_list(self, client):
        """Test that empty updates array returns error."""
        response = client.patch(
            '/api/transcripts/segments/speaker',
            json={'updates': []}
        )

        # Empty updates array should return 400
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
