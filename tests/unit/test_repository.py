"""Tests for EpisodeRepository."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from app.db.models import Episode
from app.db.repository import EpisodeRepository


def make_episode(id=1, patreon_id="123", title="Test Episode"):
    return Episode(
        id=id,
        patreon_id=patreon_id,
        title=title,
        audio_url="https://example.com/audio.mp3",
        published_at=datetime(2024, 1, 1),
        duration_seconds=3600,
        processed=False,
    )


class TestGetByEpisodeNumbers:
    """Tests for get_by_episode_numbers method."""

    @pytest.mark.unit
    def test_returns_episodes_matching_episode_numbers(self):
        """Should return episodes whose titles start with the given episode numbers."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "patreon_id": "abc123",
                "title": "1003 - Bored of Peace feat. Derek Davison",
                "audio_url": "https://example.com/1.mp3",
                "published_at": datetime(2024, 1, 1),
                "duration_seconds": 3600,
                "youtube_url": None,
                "youtube_id": None,
                "is_free": False,
                "processed": False,
                "created_at": datetime(2024, 1, 1),
                "updated_at": datetime(2024, 1, 1),
            },
            {
                "id": 2,
                "patreon_id": "def456",
                "title": "1006 - Another Episode",
                "audio_url": "https://example.com/2.mp3",
                "published_at": datetime(2024, 1, 2),
                "duration_seconds": 4200,
                "youtube_url": None,
                "youtube_id": None,
                "is_free": False,
                "processed": False,
                "created_at": datetime(2024, 1, 2),
                "updated_at": datetime(2024, 1, 2),
            },
        ]

        with patch("app.db.repository.get_cursor") as mock_get_cursor:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_cursor)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_get_cursor.return_value = mock_ctx

            repo = EpisodeRepository()
            episodes = repo.get_by_episode_numbers([1003, 1006])

            assert len(episodes) == 2
            assert episodes[0].title == "1003 - Bored of Peace feat. Derek Davison"
            assert episodes[1].title == "1006 - Another Episode"

    @pytest.mark.unit
    def test_returns_empty_list_for_empty_input(self):
        """Should return empty list when no episode numbers provided."""
        repo = EpisodeRepository()
        episodes = repo.get_by_episode_numbers([])
        assert episodes == []

    @pytest.mark.unit
    def test_queries_with_like_patterns(self):
        """Should query with LIKE patterns for episode number prefixes."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch("app.db.repository.get_cursor") as mock_get_cursor:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_cursor)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_get_cursor.return_value = mock_ctx

            repo = EpisodeRepository()
            repo.get_by_episode_numbers([1003, 1006])

            # Verify execute was called with the expected query
            mock_cursor.execute.assert_called_once()
            call_args = mock_cursor.execute.call_args
            query = call_args[0][0]
            params = call_args[0][1]

            # Check that query contains LIKE and OR logic
            assert "LIKE" in query or "title LIKE" in query.upper() or "like" in query.lower()
            # Check that params include the patterns
            assert "1003 -%" in params or "1003 - %" in params or ("1003 -%",) in params or any("1003" in str(p) for p in params)

    @pytest.mark.unit
    def test_handles_single_episode_number(self):
        """Should work with a single episode number."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "patreon_id": "abc123",
                "title": "1003 - Bored of Peace feat. Derek Davison",
                "audio_url": "https://example.com/1.mp3",
                "published_at": datetime(2024, 1, 1),
                "duration_seconds": 3600,
                "youtube_url": None,
                "youtube_id": None,
                "is_free": False,
                "processed": False,
                "created_at": datetime(2024, 1, 1),
                "updated_at": datetime(2024, 1, 1),
            },
        ]

        with patch("app.db.repository.get_cursor") as mock_get_cursor:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_cursor)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_get_cursor.return_value = mock_ctx

            repo = EpisodeRepository()
            episodes = repo.get_by_episode_numbers([1003])

            assert len(episodes) == 1
            assert episodes[0].title == "1003 - Bored of Peace feat. Derek Davison"
