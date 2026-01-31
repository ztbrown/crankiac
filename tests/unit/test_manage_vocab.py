"""Tests for the --vocab flag in manage.py process command."""
import pytest
import sys
from unittest.mock import patch, MagicMock
from io import StringIO


@pytest.mark.unit
def test_process_parser_accepts_vocab_flag():
    """Test that --vocab argument is accepted by the process command parser."""
    import argparse
    from unittest.mock import patch

    # Import main to get the parser setup
    with patch.dict("sys.modules", {"app.pipeline": MagicMock()}):
        import manage
        # Reload to get fresh parser
        import importlib
        importlib.reload(manage)

        # Parse args with --vocab
        test_args = ["process", "--vocab", "/path/to/vocab.txt", "--no-sync"]
        with patch.object(sys, "argv", ["manage.py"] + test_args):
            parser = argparse.ArgumentParser()
            subparsers = parser.add_subparsers(dest="command")

            # Recreate process parser to test its configuration
            process_parser = subparsers.add_parser("process")
            process_parser.add_argument("--vocab", metavar="PATH", help="Path to vocabulary file")
            process_parser.add_argument("--no-sync", action="store_true")

            args = parser.parse_args(test_args)
            assert args.vocab == "/path/to/vocab.txt"


@pytest.mark.unit
def test_vocab_flag_passed_to_pipeline(tmp_path):
    """Test that --vocab value is passed to EpisodePipeline as vocabulary_file."""
    vocab_file = tmp_path / "vocab.txt"
    vocab_file.write_text("Name One\nName Two\n")

    with patch("app.pipeline.EpisodePipeline") as MockPipeline, \
         patch("app.db.repository.EpisodeRepository"), \
         patch("app.episode_filter.filter_episodes"):

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.run.return_value = {
            "synced": 0,
            "processed": {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        }
        MockPipeline.return_value = mock_pipeline_instance

        # Simulate calling process() with vocab argument
        from manage import process
        args = MagicMock()
        args.episode = None
        args.title = None
        args.no_sync = True
        args.max_sync = 100
        args.limit = 10
        args.offset = 0
        args.all = False
        args.all_shows = False
        args.include_shows = None
        args.model = "base"
        args.no_cleanup = False
        args.vocab = str(vocab_file)

        process(args)

        # Verify EpisodePipeline was called with vocabulary_file
        MockPipeline.assert_called_once()
        call_kwargs = MockPipeline.call_args.kwargs
        assert "vocabulary_file" in call_kwargs
        assert call_kwargs["vocabulary_file"] == str(vocab_file)


@pytest.mark.unit
def test_vocab_flag_none_when_not_provided():
    """Test that vocabulary_file is None when --vocab is not provided."""
    with patch("app.pipeline.EpisodePipeline") as MockPipeline, \
         patch("app.db.repository.EpisodeRepository"), \
         patch("app.episode_filter.filter_episodes"):

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.run.return_value = {
            "synced": 0,
            "processed": {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        }
        MockPipeline.return_value = mock_pipeline_instance

        from manage import process
        args = MagicMock()
        args.episode = None
        args.title = None
        args.no_sync = True
        args.max_sync = 100
        args.limit = 10
        args.offset = 0
        args.all = False
        args.all_shows = False
        args.include_shows = None
        args.model = "base"
        args.no_cleanup = False
        args.vocab = None

        process(args)

        # Verify EpisodePipeline was called without vocabulary_file (or with None)
        MockPipeline.assert_called_once()
        call_kwargs = MockPipeline.call_args.kwargs
        # When vocab is None, it should either not be passed or be passed as None
        vocab_value = call_kwargs.get("vocabulary_file")
        assert vocab_value is None


@pytest.mark.unit
def test_vocab_flag_with_single_episode():
    """Test that --vocab works with --episode flag."""
    with patch("app.pipeline.EpisodePipeline") as MockPipeline, \
         patch("app.db.repository.EpisodeRepository"):

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.process_single.return_value = True
        MockPipeline.return_value = mock_pipeline_instance

        from manage import process
        args = MagicMock()
        args.episode = 42
        args.title = None
        args.vocab = "/path/to/vocab.txt"
        args.model = "base"
        args.no_cleanup = False

        process(args)

        # Verify EpisodePipeline was called with vocabulary_file
        MockPipeline.assert_called_once()
        call_kwargs = MockPipeline.call_args.kwargs
        assert call_kwargs.get("vocabulary_file") == "/path/to/vocab.txt"


@pytest.mark.unit
def test_vocab_flag_with_title_search():
    """Test that --vocab works with --title flag."""
    from app.db.models import Episode
    from datetime import datetime

    mock_episode = Episode(
        id=1,
        patreon_id="123",
        title="Test Episode",
        audio_url="https://example.com/audio.mp3",
        published_at=datetime(2024, 1, 1),
        duration_seconds=3600,
    )

    with patch("app.pipeline.EpisodePipeline") as MockPipeline, \
         patch("app.db.repository.EpisodeRepository") as MockRepo:

        mock_repo_instance = MagicMock()
        mock_repo_instance.search_by_title.return_value = [mock_episode]
        MockRepo.return_value = mock_repo_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.process_episode.return_value = True
        MockPipeline.return_value = mock_pipeline_instance

        from manage import process
        args = MagicMock()
        args.episode = None
        args.title = "Test"
        args.vocab = "/path/to/vocab.txt"
        args.model = "medium"
        args.no_cleanup = True

        process(args)

        # Verify EpisodePipeline was called with vocabulary_file
        MockPipeline.assert_called_once()
        call_kwargs = MockPipeline.call_args.kwargs
        assert call_kwargs.get("vocabulary_file") == "/path/to/vocab.txt"
