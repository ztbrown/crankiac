"""Tests for YouTube client and matching logic."""
import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from app.youtube.client import (
    YouTubeClient,
    YouTubeVideo,
    normalize_title,
    extract_episode_number,
    match_episode_to_video,
    is_free_monday_episode,
    save_videos_to_json,
    load_videos_from_json,
    _parse_duration,
)


class TestNormalizeTitle:
    def test_removes_episode_number_patterns(self):
        assert "test" in normalize_title("Episode 123: Test")
        assert "test" in normalize_title("Ep. 456 - Test")
        assert "test" in normalize_title("#789 Test")
        assert "123" not in normalize_title("Episode 123: Test")

    def test_removes_common_suffixes(self):
        assert "chapo" not in normalize_title("Test | Chapo Trap House Podcast")
        assert "free" not in normalize_title("Test (free preview)")

    def test_removes_punctuation(self):
        result = normalize_title("Test: A 'Great' Episode!")
        assert ":" not in result
        assert "'" not in result
        assert "!" not in result

    def test_lowercases(self):
        assert normalize_title("TEST TITLE") == "test title"


class TestExtractEpisodeNumber:
    def test_extracts_episode_pattern(self):
        assert extract_episode_number("Episode 123: Title") == 123
        assert extract_episode_number("episode 456 title") == 456

    def test_extracts_ep_pattern(self):
        assert extract_episode_number("Ep. 123 Title") == 123
        assert extract_episode_number("ep 456: title") == 456

    def test_extracts_hash_pattern(self):
        assert extract_episode_number("#123 Title") == 123

    def test_returns_none_for_no_number(self):
        assert extract_episode_number("Title without number") is None


class TestMatchEpisodeToVideo:
    def setup_method(self):
        self.videos = [
            YouTubeVideo(
                video_id="abc123",
                title="Episode 500: The Big One",
                published_at=datetime(2024, 1, 15, 12, 0, 0),
                url="https://www.youtube.com/watch?v=abc123",
            ),
            YouTubeVideo(
                video_id="def456",
                title="Episode 501: Another Day",
                published_at=datetime(2024, 1, 22, 12, 0, 0),
                url="https://www.youtube.com/watch?v=def456",
            ),
            YouTubeVideo(
                video_id="ghi789",
                title="Something Completely Different",
                published_at=datetime(2024, 1, 8, 12, 0, 0),
                url="https://www.youtube.com/watch?v=ghi789",
            ),
        ]

    def test_matches_by_episode_number(self):
        result = match_episode_to_video(
            "Episode 500 - The Big One",
            datetime(2024, 1, 15),
            self.videos,
        )
        assert result is not None
        assert result.video_id == "abc123"

    def test_matches_by_title_words(self):
        result = match_episode_to_video(
            "The Big One Returns",
            datetime(2024, 1, 15),
            self.videos,
        )
        assert result is not None
        assert result.video_id == "abc123"

    def test_date_alone_not_enough_to_match(self):
        # Date proximity alone should not be sufficient for a match
        # (requires title words or episode number)
        result = match_episode_to_video(
            "Random Title",
            datetime(2024, 1, 14),
            self.videos,
        )
        assert result is None

    def test_date_proximity_boosts_title_match(self):
        # Date proximity should help when combined with title overlap
        result = match_episode_to_video(
            "Big One Special",  # "Big" and "One" overlap with "The Big One"
            datetime(2024, 1, 15),  # Same date
            self.videos,
        )
        assert result is not None
        assert result.video_id == "abc123"

    def test_returns_none_for_no_match(self):
        result = match_episode_to_video(
            "Completely Unrelated",
            datetime(2020, 1, 1),  # Way off date
            self.videos,
        )
        assert result is None

    def test_prefers_episode_number_match(self):
        # Even if title words match another video, episode number should win
        result = match_episode_to_video(
            "Episode 501: The Big One",  # ep 501 but title words match ep 500
            datetime(2024, 1, 22),
            self.videos,
        )
        assert result is not None
        assert result.video_id == "def456"  # Episode 501


class TestYouTubeClient:
    @patch('app.youtube.client.requests.Session')
    def test_get_videos_parses_rss(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Sample RSS feed response
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
              xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <yt:videoId>test123</yt:videoId>
                <title>Test Video Title</title>
                <published>2024-01-15T12:00:00+00:00</published>
            </entry>
        </feed>"""

        mock_response = Mock()
        mock_response.content = rss_xml.encode()
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        client = YouTubeClient()
        videos = client.get_videos()

        assert len(videos) == 1
        assert videos[0].video_id == "test123"
        assert videos[0].title == "Test Video Title"
        assert videos[0].url == "https://www.youtube.com/watch?v=test123"


class TestParseDuration:
    def test_parses_hours_minutes_seconds(self):
        assert _parse_duration("PT1H30M15S") == 5415  # 1*3600 + 30*60 + 15

    def test_parses_minutes_seconds(self):
        assert _parse_duration("PT45M30S") == 2730  # 45*60 + 30

    def test_parses_minutes_only(self):
        assert _parse_duration("PT30M") == 1800  # 30*60

    def test_parses_hours_only(self):
        assert _parse_duration("PT2H") == 7200  # 2*3600

    def test_returns_none_for_empty(self):
        assert _parse_duration("") is None

    def test_returns_none_for_invalid(self):
        assert _parse_duration("invalid") is None


class TestIsFreeMondayEpisode:
    def test_free_in_title(self):
        video = YouTubeVideo(
            video_id="abc",
            title="Episode 500 (Free)",
            published_at=datetime(2024, 1, 15, 12, 0),  # Monday
            url="https://youtube.com/watch?v=abc",
        )
        assert is_free_monday_episode(video) is True

    def test_free_preview_in_title(self):
        video = YouTubeVideo(
            video_id="abc",
            title="Episode 500 free preview",
            published_at=datetime(2024, 1, 16, 12, 0),  # Tuesday
            url="https://youtube.com/watch?v=abc",
        )
        assert is_free_monday_episode(video) is True

    def test_monday_with_long_duration(self):
        video = YouTubeVideo(
            video_id="abc",
            title="Episode 500: The Big One",
            published_at=datetime(2024, 1, 15, 12, 0),  # Monday
            url="https://youtube.com/watch?v=abc",
            duration_seconds=4500,  # 1.25 hours
        )
        assert is_free_monday_episode(video) is True

    def test_monday_with_episode_number_no_duration(self):
        video = YouTubeVideo(
            video_id="abc",
            title="Episode 500: The Big One",
            published_at=datetime(2024, 1, 15, 12, 0),  # Monday
            url="https://youtube.com/watch?v=abc",
        )
        assert is_free_monday_episode(video) is True

    def test_short_clip_on_monday(self):
        video = YouTubeVideo(
            video_id="abc",
            title="Funny Clip",
            published_at=datetime(2024, 1, 15, 12, 0),  # Monday
            url="https://youtube.com/watch?v=abc",
            duration_seconds=300,  # 5 minutes
        )
        assert is_free_monday_episode(video) is False

    def test_tuesday_long_episode(self):
        video = YouTubeVideo(
            video_id="abc",
            title="Episode 500: The Big One",
            published_at=datetime(2024, 1, 16, 12, 0),  # Tuesday
            url="https://youtube.com/watch?v=abc",
            duration_seconds=4500,
        )
        assert is_free_monday_episode(video) is False


class TestSaveLoadVideos:
    def test_save_and_load_round_trip(self):
        videos = [
            YouTubeVideo(
                video_id="abc123",
                title="Episode 500: Test",
                published_at=datetime(2024, 1, 15, 12, 0),
                url="https://youtube.com/watch?v=abc123",
                duration_seconds=3600,
            ),
            YouTubeVideo(
                video_id="def456",
                title="Episode 501: Another Test",
                published_at=datetime(2024, 1, 22, 12, 0),
                url="https://youtube.com/watch?v=def456",
                duration_seconds=4200,
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "videos.json"
            save_videos_to_json(videos, str(path))

            # Verify file exists and is valid JSON
            assert path.exists()
            with open(path) as f:
                data = json.load(f)
            assert len(data) == 2
            assert data[0]["video_id"] == "abc123"
            assert data[0]["is_free_monday"] is True  # Monday + duration >= 1hr

            # Load back
            loaded = load_videos_from_json(str(path))
            assert len(loaded) == 2
            assert loaded[0].video_id == "abc123"
            assert loaded[0].duration_seconds == 3600

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "dir" / "videos.json"
            save_videos_to_json([], str(path))
            assert path.exists()
