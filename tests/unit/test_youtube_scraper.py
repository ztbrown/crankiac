"""Tests for YouTube scraper and episode matcher."""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from app.youtube.scraper import (
    extract_episode_number_from_title,
    match_videos_to_episodes,
    sync_youtube_episodes,
    MatchResult,
    SyncResult,
    print_sync_preview,
)
from app.youtube.client import YouTubeVideo


class TestExtractEpisodeNumberFromTitle:
    """Tests for episode number extraction."""

    def test_episode_pattern(self):
        assert extract_episode_number_from_title("Episode 123: Great Show") == 123
        assert extract_episode_number_from_title("episode 456 title") == 456

    def test_ep_pattern(self):
        assert extract_episode_number_from_title("Ep. 123 Title") == 123
        assert extract_episode_number_from_title("Ep 456: Something") == 456
        assert extract_episode_number_from_title("ep 789") == 789

    def test_hash_pattern(self):
        assert extract_episode_number_from_title("#123 Title Here") == 123
        assert extract_episode_number_from_title("Show #456") == 456

    def test_numbered_title_pattern(self):
        assert extract_episode_number_from_title("123: Title") == 123
        assert extract_episode_number_from_title("456 - Another Title") == 456

    def test_no_number(self):
        assert extract_episode_number_from_title("Title Without Number") is None
        assert extract_episode_number_from_title("Just Some Text") is None

    def test_number_in_text_not_matched(self):
        # Numbers that don't match episode patterns
        assert extract_episode_number_from_title("The 2020 Election") is None


class TestMatchVideosToEpisodes:
    """Tests for matching videos to episodes by episode number."""

    def setup_method(self):
        self.videos = [
            YouTubeVideo(
                video_id="vid1",
                title="Episode 500: The Big One",
                published_at=datetime(2024, 1, 15),
                url="https://youtube.com/watch?v=vid1",
            ),
            YouTubeVideo(
                video_id="vid2",
                title="Ep. 501 Another Day",
                published_at=datetime(2024, 1, 22),
                url="https://youtube.com/watch?v=vid2",
            ),
            YouTubeVideo(
                video_id="vid3",
                title="#502 The Third",
                published_at=datetime(2024, 1, 29),
                url="https://youtube.com/watch?v=vid3",
            ),
            YouTubeVideo(
                video_id="vid4",
                title="Some Random Clip",
                published_at=datetime(2024, 2, 1),
                url="https://youtube.com/watch?v=vid4",
            ),
        ]
        self.episodes = [
            {"id": 1, "title": "Episode 500 - The Big One"},
            {"id": 2, "title": "Episode 501: Another Day"},
            {"id": 3, "title": "Episode 503: Not on YouTube"},
        ]

    def test_matches_by_episode_number(self):
        results = match_videos_to_episodes(self.videos, self.episodes)

        # Episode 500 should match
        ep500_match = next(r for r in results if r.video.video_id == "vid1")
        assert ep500_match.matched is True
        assert ep500_match.episode_id == 1
        assert ep500_match.video_episode_number == 500

        # Episode 501 should match
        ep501_match = next(r for r in results if r.video.video_id == "vid2")
        assert ep501_match.matched is True
        assert ep501_match.episode_id == 2
        assert ep501_match.video_episode_number == 501

    def test_no_match_for_missing_episode(self):
        results = match_videos_to_episodes(self.videos, self.episodes)

        # Episode 502 is on YouTube but not in DB
        ep502_match = next(r for r in results if r.video.video_id == "vid3")
        assert ep502_match.matched is False
        assert ep502_match.video_episode_number == 502

    def test_no_match_for_video_without_number(self):
        results = match_videos_to_episodes(self.videos, self.episodes)

        clip_match = next(r for r in results if r.video.video_id == "vid4")
        assert clip_match.matched is False
        assert clip_match.video_episode_number is None

    def test_match_result_includes_reason(self):
        results = match_videos_to_episodes(self.videos, self.episodes)

        matched = [r for r in results if r.matched]
        for m in matched:
            assert "Episode number match" in m.reason

        unmatched = [r for r in results if not r.matched]
        for u in unmatched:
            assert "No" in u.reason

    def test_empty_inputs(self):
        assert match_videos_to_episodes([], []) == []
        assert match_videos_to_episodes(self.videos, []) != []
        assert match_videos_to_episodes([], self.episodes) == []


class TestSyncYoutubeEpisodes:
    """Tests for the sync function."""

    @patch('app.youtube.scraper.YouTubeClient')
    @patch('app.youtube.scraper.EpisodeRepository')
    def test_dry_run_does_not_update_db(self, mock_repo_class, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_videos.return_value = [
            YouTubeVideo(
                video_id="vid1",
                title="Episode 500: Test",
                published_at=datetime(2024, 1, 15),
                url="https://youtube.com/watch?v=vid1",
            ),
        ]

        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_episodes_for_youtube_matching.return_value = [
            {"id": 1, "title": "Episode 500: Test"},
        ]

        result = sync_youtube_episodes(dry_run=True)

        assert result.matches_found == 1
        assert result.updates_applied == 0
        mock_repo.update_youtube_id.assert_not_called()

    @patch('app.youtube.scraper.YouTubeClient')
    @patch('app.youtube.scraper.EpisodeRepository')
    def test_non_dry_run_updates_db(self, mock_repo_class, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_videos.return_value = [
            YouTubeVideo(
                video_id="vid1",
                title="Episode 500: Test",
                published_at=datetime(2024, 1, 15),
                url="https://youtube.com/watch?v=vid1",
            ),
        ]

        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_episodes_for_youtube_matching.return_value = [
            {"id": 1, "title": "Episode 500: Test"},
        ]

        result = sync_youtube_episodes(dry_run=False)

        assert result.matches_found == 1
        assert result.updates_applied == 1
        mock_repo.update_youtube_id.assert_called_once_with(1, "vid1")

    @patch('app.youtube.scraper.YouTubeClient')
    @patch('app.youtube.scraper.EpisodeRepository')
    def test_returns_sync_result(self, mock_repo_class, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_videos.return_value = []

        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_episodes_for_youtube_matching.return_value = []

        result = sync_youtube_episodes(dry_run=True)

        assert isinstance(result, SyncResult)
        assert result.videos_fetched == 0
        assert result.episodes_checked == 0

    @patch('app.youtube.scraper.YouTubeClient')
    @patch('app.youtube.scraper.EpisodeRepository')
    def test_max_videos_param(self, mock_repo_class, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_videos.return_value = []

        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_episodes_for_youtube_matching.return_value = []

        sync_youtube_episodes(dry_run=True, max_videos=50)

        mock_client.get_videos.assert_called_once_with(max_results=50)


class TestPrintSyncPreview:
    """Tests for the preview printer."""

    def test_prints_summary(self, capsys):
        result = SyncResult(
            videos_fetched=10,
            episodes_checked=5,
            matches_found=3,
            updates_applied=0,
            skipped_already_matched=0,
            no_match=7,
            match_details=[],
        )

        print_sync_preview(result)
        captured = capsys.readouterr()

        assert "Videos fetched: 10" in captured.out
        assert "Matches found: 3" in captured.out
        assert "No match: 7" in captured.out

    def test_prints_matched_episodes(self, capsys):
        result = SyncResult(
            videos_fetched=1,
            episodes_checked=1,
            matches_found=1,
            updates_applied=0,
            skipped_already_matched=0,
            no_match=0,
            match_details=[
                MatchResult(
                    video=YouTubeVideo(
                        video_id="vid1",
                        title="Episode 500: Test",
                        published_at=datetime(2024, 1, 15),
                        url="https://youtube.com/watch?v=vid1",
                    ),
                    episode_id=1,
                    episode_title="Episode 500: Test",
                    episode_number=500,
                    video_episode_number=500,
                    matched=True,
                    reason="Episode number match: 500",
                ),
            ],
        )

        print_sync_preview(result)
        captured = capsys.readouterr()

        assert "Matched episodes" in captured.out
        assert "Episode 500" in captured.out
        assert "vid1" in captured.out

    def test_prints_unmatched_videos(self, capsys):
        result = SyncResult(
            videos_fetched=1,
            episodes_checked=0,
            matches_found=0,
            updates_applied=0,
            skipped_already_matched=0,
            no_match=1,
            match_details=[
                MatchResult(
                    video=YouTubeVideo(
                        video_id="vid1",
                        title="Random Clip",
                        published_at=datetime(2024, 1, 15),
                        url="https://youtube.com/watch?v=vid1",
                    ),
                    episode_id=0,
                    episode_title="",
                    episode_number=None,
                    video_episode_number=None,
                    matched=False,
                    reason="No episode number in video title",
                ),
            ],
        )

        print_sync_preview(result)
        captured = capsys.readouterr()

        assert "Unmatched videos" in captured.out
        assert "Random Clip" in captured.out
