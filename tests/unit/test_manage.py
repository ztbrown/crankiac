"""Tests for manage.py CLI argument parsing."""
import pytest
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Get the project root directory (two levels up from this test file)
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestProcessCommandArgs:
    """Tests for process command argument parsing."""

    @pytest.mark.unit
    def test_diarize_flag_in_help(self):
        """Test that --diarize flag appears in help."""
        result = subprocess.run(
            [sys.executable, "manage.py", "process", "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )
        assert "--diarize" in result.stdout, f"--diarize flag not found in help. stdout: {result.stdout}"

    @pytest.mark.unit
    def test_num_speakers_flag_in_help(self):
        """Test that --num-speakers flag appears in help."""
        result = subprocess.run(
            [sys.executable, "manage.py", "process", "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )
        assert "--num-speakers" in result.stdout, f"--num-speakers flag not found in help. stdout: {result.stdout}"


class TestProcessCommandIntegration:
    """Integration tests for process command with EpisodePipeline."""

    @pytest.mark.unit
    @patch("app.pipeline.PatreonClient")
    @patch("app.pipeline.AudioDownloader")
    @patch("app.pipeline.get_transcriber")
    @patch("app.pipeline.TranscriptStorage")
    @patch("app.pipeline.EpisodeRepository")
    def test_process_passes_diarize_flag_to_pipeline(
        self, mock_repo, mock_storage, mock_transcriber, mock_downloader, mock_patreon
    ):
        """Test that process() passes enable_diarization to EpisodePipeline."""
        from types import SimpleNamespace
        from app.pipeline import EpisodePipeline

        with patch.object(EpisodePipeline, '__init__', return_value=None) as mock_init:
            with patch.object(EpisodePipeline, 'run') as mock_run:
                mock_run.return_value = {
                    "synced": 0,
                    "processed": {"total": 0, "success": 0, "failed": 0, "skipped": 0}
                }

                import manage

                # Create args with diarize=True
                args = SimpleNamespace(
                    model="base",
                    no_cleanup=False,
                    diarize=True,
                    num_speakers=None,
                    no_sync=True,
                    max_sync=100,
                    limit=10,
                    offset=0,
                    all=False,
                    all_shows=False,
                    include_shows=None,
                    episode=None,
                    title=None,
                    vocab=None,
                    episodes=None,
                    identify_speakers=False,
                    match_threshold=0.70,
                    force=False,
                    expected_speakers=None,
                    vad=False,
                )

                manage.process(args)

                # Verify EpisodePipeline was called with enable_diarization=True
                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args[1]
                assert call_kwargs.get("enable_diarization") is True

    @pytest.mark.unit
    @patch("app.pipeline.PatreonClient")
    @patch("app.pipeline.AudioDownloader")
    @patch("app.pipeline.get_transcriber")
    @patch("app.pipeline.TranscriptStorage")
    @patch("app.pipeline.EpisodeRepository")
    def test_process_passes_num_speakers_to_pipeline(
        self, mock_repo, mock_storage, mock_transcriber, mock_downloader, mock_patreon
    ):
        """Test that process() passes num_speakers to EpisodePipeline."""
        from types import SimpleNamespace
        from app.pipeline import EpisodePipeline

        with patch.object(EpisodePipeline, '__init__', return_value=None) as mock_init:
            with patch.object(EpisodePipeline, 'run') as mock_run:
                mock_run.return_value = {
                    "synced": 0,
                    "processed": {"total": 0, "success": 0, "failed": 0, "skipped": 0}
                }

                import manage

                # Create args with num_speakers=5
                args = SimpleNamespace(
                    model="base",
                    no_cleanup=False,
                    diarize=True,
                    num_speakers=5,
                    no_sync=True,
                    max_sync=100,
                    limit=10,
                    offset=0,
                    all=False,
                    all_shows=False,
                    include_shows=None,
                    episode=None,
                    title=None,
                    vocab=None,
                    episodes=None,
                    identify_speakers=False,
                    match_threshold=0.70,
                    force=False,
                    expected_speakers=None,
                    vad=False,
                )

                manage.process(args)

                # Verify EpisodePipeline was called with num_speakers=5
                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args[1]
                assert call_kwargs.get("num_speakers") == 5

    @pytest.mark.unit
    @patch("app.pipeline.PatreonClient")
    @patch("app.pipeline.AudioDownloader")
    @patch("app.pipeline.get_transcriber")
    @patch("app.pipeline.TranscriptStorage")
    @patch("app.pipeline.EpisodeRepository")
    def test_process_diarize_defaults_to_false(
        self, mock_repo, mock_storage, mock_transcriber, mock_downloader, mock_patreon
    ):
        """Test that process() defaults enable_diarization to False."""
        from types import SimpleNamespace
        from app.pipeline import EpisodePipeline

        with patch.object(EpisodePipeline, '__init__', return_value=None) as mock_init:
            with patch.object(EpisodePipeline, 'run') as mock_run:
                mock_run.return_value = {
                    "synced": 0,
                    "processed": {"total": 0, "success": 0, "failed": 0, "skipped": 0}
                }

                import manage

                # Create args with diarize=False (default)
                args = SimpleNamespace(
                    model="base",
                    no_cleanup=False,
                    diarize=False,
                    num_speakers=None,
                    no_sync=True,
                    max_sync=100,
                    limit=10,
                    offset=0,
                    all=False,
                    all_shows=False,
                    include_shows=None,
                    episode=None,
                    title=None,
                    vocab=None,
                    episodes=None,
                    identify_speakers=False,
                    match_threshold=0.70,
                    force=False,
                    expected_speakers=None,
                    vad=False,
                )

                manage.process(args)

                # Verify EpisodePipeline was called with enable_diarization=False
                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args[1]
                assert call_kwargs.get("enable_diarization") is False
                assert call_kwargs.get("num_speakers") is None


class TestPipelineAcceptsDiarizationParams:
    """Tests that EpisodePipeline correctly accepts diarization parameters."""

    @pytest.mark.unit
    @patch("app.pipeline.PatreonClient")
    @patch("app.pipeline.AudioDownloader")
    @patch("app.pipeline.get_transcriber")
    @patch("app.pipeline.TranscriptStorage")
    @patch("app.pipeline.EpisodeRepository")
    def test_pipeline_stores_enable_diarization(
        self, mock_repo, mock_storage, mock_transcriber, mock_downloader, mock_patreon
    ):
        """Test that EpisodePipeline stores enable_diarization attribute."""
        from app.pipeline import EpisodePipeline

        pipeline = EpisodePipeline(
            session_id="test-session",
            enable_diarization=True,
            num_speakers=None
        )

        assert pipeline.enable_diarization is True

    @pytest.mark.unit
    @patch("app.pipeline.PatreonClient")
    @patch("app.pipeline.AudioDownloader")
    @patch("app.pipeline.get_transcriber")
    @patch("app.pipeline.TranscriptStorage")
    @patch("app.pipeline.EpisodeRepository")
    def test_pipeline_passes_num_speakers_to_diarizer(
        self, mock_repo, mock_storage, mock_transcriber, mock_downloader, mock_patreon
    ):
        """Test that EpisodePipeline passes num_speakers to get_diarizer."""
        from app.pipeline import EpisodePipeline

        with patch("app.pipeline.get_diarizer") as mock_diarizer:
            mock_diarizer.return_value = MagicMock()
            pipeline = EpisodePipeline(
                session_id="test-session",
                enable_diarization=True,
                num_speakers=3
            )

            # Verify get_diarizer was called with correct num_speakers
            mock_diarizer.assert_called_once()
            call_kwargs = mock_diarizer.call_args
            assert call_kwargs[1]["num_speakers"] == 3

    @pytest.mark.unit
    @patch("app.pipeline.PatreonClient")
    @patch("app.pipeline.AudioDownloader")
    @patch("app.pipeline.get_transcriber")
    @patch("app.pipeline.TranscriptStorage")
    @patch("app.pipeline.EpisodeRepository")
    def test_pipeline_diarization_disabled_by_default(
        self, mock_repo, mock_storage, mock_transcriber, mock_downloader, mock_patreon
    ):
        """Test that EpisodePipeline has diarization disabled by default."""
        from app.pipeline import EpisodePipeline

        pipeline = EpisodePipeline(session_id="test-session")

        assert pipeline.enable_diarization is False
        assert pipeline.diarizer is None
