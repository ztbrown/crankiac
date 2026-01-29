"""Tests for YouTube channel scraper."""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from app.youtube.scraper import (
    extract_episode_number,
    get_channel_id_from_url,
    scrape_channel_videos,
    sync_youtube_episodes,
    ScrapedVideo,
    SyncResult,
    DEFAULT_CHAPO_CHANNEL_URL,
)


class TestExtractEpisodeNumber:
    """Tests for extract_episode_number function."""

    def test_episode_format(self):
        assert extract_episode_number("Episode 123: Some Title") == 123
        assert extract_episode_number("Episode 1 - Pilot") == 1
        assert extract_episode_number("EPISODE 500") == 500

    def test_ep_format(self):
        assert extract_episode_number("Ep. 45 - Title") == 45
        assert extract_episode_number("Ep 123") == 123
        assert extract_episode_number("EP.789 Some text") == 789

    def test_hash_format(self):
        assert extract_episode_number("#123 Title") == 123
        assert extract_episode_number("Some #456 in middle") == 456

    def test_number_at_start(self):
        assert extract_episode_number("123 - Episode Title") == 123
        assert extract_episode_number("456: Another Title") == 456
        assert extract_episode_number("789. Third Title") == 789

    def test_no_episode_number(self):
        assert extract_episode_number("Just a title") is None
        assert extract_episode_number("Contains 123 number in middle") is None
        assert extract_episode_number("") is None


class TestGetChannelIdFromUrl:
    """Tests for get_channel_id_from_url function."""

    def test_extracts_channel_id_from_page(self):
        mock_response = MagicMock()
        mock_response.text = '"channelId":"UC1XB3P7c3R3PdB4TPe-T3zA"'
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        result = get_channel_id_from_url("https://www.youtube.com/@chapotraphouse", mock_session)
        assert result == "UC1XB3P7c3R3PdB4TPe-T3zA"

    def test_extracts_external_id(self):
        mock_response = MagicMock()
        mock_response.text = '"externalId":"UCABC123DEF456"'
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        result = get_channel_id_from_url("https://www.youtube.com/@somechannel", mock_session)
        assert result == "UCABC123DEF456"

    def test_returns_none_on_error(self):
        import requests
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.RequestException("Network error")

        result = get_channel_id_from_url("https://www.youtube.com/@somechannel", mock_session)
        assert result is None

    def test_returns_none_if_not_found(self):
        mock_response = MagicMock()
        mock_response.text = "No channel ID here"
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        result = get_channel_id_from_url("https://www.youtube.com/@somechannel", mock_session)
        assert result is None


class TestScrapeChannelVideos:
    """Tests for scrape_channel_videos function."""

    @patch('app.youtube.scraper.get_channel_id_from_url')
    @patch('requests.Session')
    def test_scrapes_videos_from_rss(self, mock_session_class, mock_get_channel_id):
        mock_get_channel_id.return_value = "UC1XB3P7c3R3PdB4TPe-T3zA"

        # Sample RSS feed content
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
              xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <yt:videoId>abc123</yt:videoId>
                <title>Episode 500: Test Episode</title>
                <published>2024-01-15T12:00:00+00:00</published>
            </entry>
            <entry>
                <yt:videoId>def456</yt:videoId>
                <title>#501 Another Episode</title>
                <published>2024-01-16T12:00:00+00:00</published>
            </entry>
        </feed>"""

        mock_response = MagicMock()
        mock_response.content = rss_content.encode('utf-8')
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        videos = scrape_channel_videos()

        assert len(videos) == 2
        assert videos[0].video_id == "abc123"
        assert videos[0].title == "Episode 500: Test Episode"
        assert videos[0].episode_number == 500
        assert videos[1].video_id == "def456"
        assert videos[1].episode_number == 501

    @patch('app.youtube.scraper.get_channel_id_from_url')
    def test_raises_on_missing_channel_id(self, mock_get_channel_id):
        mock_get_channel_id.return_value = None

        with pytest.raises(ValueError, match="Could not find channel ID"):
            scrape_channel_videos("https://www.youtube.com/@invalid")


class TestSyncYoutubeEpisodes:
    """Tests for sync_youtube_episodes function."""

    @patch('app.youtube.scraper.scrape_channel_videos')
    @patch('app.db.repository.EpisodeRepository')
    def test_matches_episodes_by_episode_number(self, mock_repo_class, mock_scrape):
        # Mock scraped videos
        mock_scrape.return_value = [
            ScrapedVideo(video_id="vid1", title="Episode 100", episode_number=100),
            ScrapedVideo(video_id="vid2", title="Episode 101", episode_number=101),
            ScrapedVideo(video_id="vid3", title="Some Clip", episode_number=None),
        ]

        # Mock episodes from DB
        mock_repo = MagicMock()
        mock_repo.get_episodes_for_youtube_matching.return_value = [
            {"id": 1, "title": "Episode 100 - Title"},
            {"id": 2, "title": "Ep. 101 - Another Title"},
            {"id": 3, "title": "No Episode Number Here"},
        ]
        mock_repo_class.return_value = mock_repo

        result = sync_youtube_episodes(dry_run=False)

        assert result.videos_found == 3
        assert result.episodes_matched == 2
        assert len(result.unmatched_videos) == 1
        assert result.unmatched_videos[0].video_id == "vid3"

        # Verify update_youtube_id was called
        assert mock_repo.update_youtube_id.call_count == 2
        mock_repo.update_youtube_id.assert_any_call(1, "vid1")
        mock_repo.update_youtube_id.assert_any_call(2, "vid2")

    @patch('app.youtube.scraper.scrape_channel_videos')
    @patch('app.db.repository.EpisodeRepository')
    def test_dry_run_does_not_update(self, mock_repo_class, mock_scrape):
        mock_scrape.return_value = [
            ScrapedVideo(video_id="vid1", title="Episode 100", episode_number=100),
        ]

        mock_repo = MagicMock()
        mock_repo.get_episodes_for_youtube_matching.return_value = [
            {"id": 1, "title": "Episode 100 - Title"},
        ]
        mock_repo_class.return_value = mock_repo

        result = sync_youtube_episodes(dry_run=True)

        assert result.episodes_matched == 1
        mock_repo.update_youtube_id.assert_not_called()

    @patch('app.youtube.scraper.scrape_channel_videos')
    @patch('app.db.repository.EpisodeRepository')
    def test_custom_channel_url(self, mock_repo_class, mock_scrape):
        mock_scrape.return_value = []
        mock_repo = MagicMock()
        mock_repo.get_episodes_for_youtube_matching.return_value = []
        mock_repo_class.return_value = mock_repo

        custom_url = "https://www.youtube.com/@customchannel"
        sync_youtube_episodes(channel_url=custom_url)

        mock_scrape.assert_called_once_with(custom_url)
