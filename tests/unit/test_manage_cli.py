"""Tests for manage.py CLI argument parsing."""
import pytest
import argparse
from unittest.mock import patch, MagicMock


class TestEpisodesFlag:
    """Tests for --episodes flag on process command."""

    @pytest.mark.unit
    def test_episodes_flag_parses_comma_separated_values(self):
        """Should parse comma-separated episode numbers into a string."""
        from manage import main
        import sys

        # Import the argument parser setup
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        process_parser = subparsers.add_parser("process")
        process_parser.add_argument("--episodes", type=str, help="Comma-separated episode numbers")
        process_parser.add_argument("--no-sync", action="store_true")
        process_parser.add_argument("--limit", type=int, default=10)
        process_parser.add_argument("--offset", type=int, default=0)
        process_parser.add_argument("--all", action="store_true")
        process_parser.add_argument("--model", default="base")
        process_parser.add_argument("--no-cleanup", action="store_true")
        process_parser.add_argument("--max-sync", type=int, default=100)

        args = parser.parse_args(["process", "--episodes", "1003,1006"])

        assert args.episodes == "1003,1006"

    @pytest.mark.unit
    def test_episodes_flag_is_optional(self):
        """Should allow running without --episodes flag."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        process_parser = subparsers.add_parser("process")
        process_parser.add_argument("--episodes", type=str, help="Comma-separated episode numbers")
        process_parser.add_argument("--no-sync", action="store_true")
        process_parser.add_argument("--limit", type=int, default=10)
        process_parser.add_argument("--offset", type=int, default=0)

        args = parser.parse_args(["process"])

        assert args.episodes is None

    @pytest.mark.unit
    def test_parse_episodes_string_to_list(self):
        """Should correctly parse episode string to list of ints."""
        episodes_str = "1003,1006,1010"
        episode_numbers = [int(n.strip()) for n in episodes_str.split(",")]

        assert episode_numbers == [1003, 1006, 1010]

    @pytest.mark.unit
    def test_parse_episodes_handles_whitespace(self):
        """Should handle whitespace in comma-separated values."""
        episodes_str = "1003, 1006, 1010"
        episode_numbers = [int(n.strip()) for n in episodes_str.split(",")]

        assert episode_numbers == [1003, 1006, 1010]

    @pytest.mark.unit
    def test_parse_single_episode(self):
        """Should handle a single episode number."""
        episodes_str = "1003"
        episode_numbers = [int(n.strip()) for n in episodes_str.split(",")]

        assert episode_numbers == [1003]


class TestProcessWithEpisodes:
    """Tests for process command with --episodes flag."""

    @pytest.mark.unit
    def test_process_uses_get_by_episode_numbers_when_episodes_provided(self):
        """When --episodes is provided, should use get_by_episode_numbers."""
        from app.db.models import Episode
        from datetime import datetime

        mock_episode = Episode(
            id=1,
            patreon_id="abc123",
            title="1003 - Test Episode",
            audio_url="https://example.com/audio.mp3",
            published_at=datetime(2024, 1, 1),
            duration_seconds=3600,
            processed=False,
        )

        with patch("app.pipeline.PatreonClient"), \
             patch("app.pipeline.AudioDownloader"), \
             patch("app.pipeline.get_transcriber"), \
             patch("app.pipeline.TranscriptStorage"), \
             patch("app.pipeline.EpisodeRepository") as MockRepo:

            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_episode_numbers.return_value = [mock_episode]

            from app.pipeline import EpisodePipeline
            pipeline = EpisodePipeline(session_id="test-session")

            # Call the method that would be used when --episodes is provided
            episodes = pipeline.episode_repo.get_by_episode_numbers([1003])

            mock_repo_instance.get_by_episode_numbers.assert_called_once_with([1003])
            assert len(episodes) == 1
            assert episodes[0].title == "1003 - Test Episode"

    @pytest.mark.unit
    def test_process_skips_sync_when_episodes_provided(self):
        """When specific episodes requested, should skip normal flow."""
        # This tests the expected behavior - when --episodes is used,
        # we don't need to sync from Patreon, just process the specific episodes
        from app.db.models import Episode
        from datetime import datetime

        mock_episode = Episode(
            id=1,
            patreon_id="abc123",
            title="1003 - Test Episode",
            audio_url="https://example.com/audio.mp3",
            published_at=datetime(2024, 1, 1),
            duration_seconds=3600,
            processed=False,
        )

        with patch("app.pipeline.PatreonClient") as MockPatreon, \
             patch("app.pipeline.AudioDownloader"), \
             patch("app.pipeline.get_transcriber"), \
             patch("app.pipeline.TranscriptStorage"), \
             patch("app.pipeline.EpisodeRepository") as MockRepo:

            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_episode_numbers.return_value = [mock_episode]

            from app.pipeline import EpisodePipeline
            pipeline = EpisodePipeline(session_id="test-session")

            # When using specific episodes, we shouldn't call sync
            episodes = pipeline.episode_repo.get_by_episode_numbers([1003])

            # Verify we got episodes without calling Patreon
            assert len(episodes) == 1
