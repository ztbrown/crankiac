import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from decimal import Decimal
from datetime import datetime

from app.pipeline import EpisodePipeline
from app.db.models import Episode
from app.patreon.downloader import DownloadResult
from app.transcription.whisper_transcriber import TranscriptResult, WordSegment


def make_episode(id=1, patreon_id="123", title="Test Episode", audio_url="https://example.com/audio.mp3", processed=False):
    return Episode(
        id=id,
        patreon_id=patreon_id,
        title=title,
        audio_url=audio_url,
        published_at=datetime(2024, 1, 1),
        duration_seconds=3600,
        processed=processed,
    )


def make_transcript_result(num_words=3):
    segments = [
        WordSegment(word=f"word{i}", start_time=Decimal(str(i)), end_time=Decimal(str(i + 0.5)))
        for i in range(num_words)
    ]
    return TranscriptResult(
        segments=segments,
        full_text=" ".join(s.word for s in segments),
        language="en",
        duration=float(num_words),
    )


@pytest.fixture
def pipeline():
    """Create a pipeline with all dependencies mocked."""
    with patch("app.pipeline.PatreonClient"), \
         patch("app.pipeline.AudioDownloader"), \
         patch("app.pipeline.get_transcriber"), \
         patch("app.pipeline.TranscriptStorage"), \
         patch("app.pipeline.EpisodeRepository"):
        p = EpisodePipeline(session_id="test-session")
        yield p


@pytest.fixture
def pipeline_no_cleanup():
    """Create a pipeline with cleanup disabled."""
    with patch("app.pipeline.PatreonClient"), \
         patch("app.pipeline.AudioDownloader"), \
         patch("app.pipeline.get_transcriber"), \
         patch("app.pipeline.TranscriptStorage"), \
         patch("app.pipeline.EpisodeRepository"):
        p = EpisodePipeline(session_id="test-session", cleanup_audio=False)
        yield p


@pytest.mark.unit
def test_pipeline_requires_session_id():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="PATREON_SESSION_ID required"):
            EpisodePipeline(session_id=None)


@pytest.mark.unit
def test_process_episode_success(pipeline):
    episode = make_episode()
    transcript = make_transcript_result()

    pipeline.downloader.download.return_value = DownloadResult(
        success=True, file_path="/tmp/test.mp3", file_size=1000
    )
    pipeline.transcriber.transcribe.return_value = transcript
    pipeline.storage.store_transcript.return_value = 3

    result = pipeline.process_episode(episode)

    assert result is True
    pipeline.downloader.download.assert_called_once_with(episode.audio_url, episode.patreon_id)
    pipeline.transcriber.transcribe.assert_called_once_with("/tmp/test.mp3")
    pipeline.storage.delete_episode_transcript.assert_called_once_with(episode.id)
    pipeline.storage.store_transcript.assert_called_once_with(episode.id, transcript)
    pipeline.episode_repo.mark_processed.assert_called_once_with(episode.id)


@pytest.mark.unit
def test_process_episode_raises_when_id_is_none(pipeline):
    episode = make_episode(id=None)
    with pytest.raises(ValueError, match="episode.id is None"):
        pipeline.process_episode(episode)
    pipeline.downloader.download.assert_not_called()


@pytest.mark.unit
def test_process_episode_skips_already_processed(pipeline):
    episode = make_episode(processed=True)
    result = pipeline.process_episode(episode)
    assert result is True
    pipeline.downloader.download.assert_not_called()


@pytest.mark.unit
def test_process_episode_skips_no_audio_url(pipeline):
    episode = make_episode(audio_url=None)
    result = pipeline.process_episode(episode)
    assert result is False
    pipeline.downloader.download.assert_not_called()


@pytest.mark.unit
def test_process_episode_handles_download_failure(pipeline):
    episode = make_episode()
    pipeline.downloader.download.return_value = DownloadResult(
        success=False, file_path=None, error="Connection refused"
    )

    result = pipeline.process_episode(episode)

    assert result is False
    pipeline.transcriber.transcribe.assert_not_called()


@pytest.mark.unit
def test_process_episode_handles_transcription_error(pipeline):
    episode = make_episode()
    pipeline.downloader.download.return_value = DownloadResult(
        success=True, file_path="/tmp/test.mp3", file_size=1000
    )
    pipeline.transcriber.transcribe.side_effect = RuntimeError("Whisper failed")

    result = pipeline.process_episode(episode)

    assert result is False
    pipeline.episode_repo.mark_processed.assert_not_called()


@pytest.mark.unit
def test_process_episode_cleans_up_audio(pipeline, tmp_path):
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"fake audio data")

    episode = make_episode()
    pipeline.downloader.download.return_value = DownloadResult(
        success=True, file_path=str(audio_file), file_size=15
    )
    pipeline.transcriber.transcribe.return_value = make_transcript_result()
    pipeline.storage.store_transcript.return_value = 3

    result = pipeline.process_episode(episode)

    assert result is True
    assert not audio_file.exists()


@pytest.mark.unit
def test_process_episode_no_cleanup_when_disabled(pipeline_no_cleanup, tmp_path):
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"fake audio data")

    episode = make_episode()
    pipeline_no_cleanup.downloader.download.return_value = DownloadResult(
        success=True, file_path=str(audio_file), file_size=15
    )
    pipeline_no_cleanup.transcriber.transcribe.return_value = make_transcript_result()
    pipeline_no_cleanup.storage.store_transcript.return_value = 3

    result = pipeline_no_cleanup.process_episode(episode)

    assert result is True
    assert audio_file.exists()


@pytest.mark.unit
def test_process_unprocessed_with_limit(pipeline):
    episodes = [make_episode(id=i, patreon_id=str(i)) for i in range(5)]
    pipeline.episode_repo.get_unprocessed.return_value = episodes

    pipeline.downloader.download.return_value = DownloadResult(
        success=True, file_path="/tmp/test.mp3", file_size=1000
    )
    pipeline.transcriber.transcribe.return_value = make_transcript_result()
    pipeline.storage.store_transcript.return_value = 3

    stats = pipeline.process_unprocessed(limit=3)

    assert stats["total"] == 3
    assert stats["success"] == 3
    assert stats["failed"] == 0


@pytest.mark.unit
def test_process_unprocessed_all(pipeline):
    episodes = [make_episode(id=i, patreon_id=str(i)) for i in range(5)]
    pipeline.episode_repo.get_unprocessed.return_value = episodes

    pipeline.downloader.download.return_value = DownloadResult(
        success=True, file_path="/tmp/test.mp3", file_size=1000
    )
    pipeline.transcriber.transcribe.return_value = make_transcript_result()
    pipeline.storage.store_transcript.return_value = 3

    stats = pipeline.process_unprocessed(limit=None)

    assert stats["total"] == 5
    assert stats["success"] == 5


@pytest.mark.unit
def test_process_unprocessed_counts_skipped(pipeline):
    episodes = [
        make_episode(id=1, patreon_id="1", audio_url="https://example.com/a.mp3"),
        make_episode(id=2, patreon_id="2", audio_url=None),
        make_episode(id=3, patreon_id="3", audio_url=None),
    ]
    pipeline.episode_repo.get_unprocessed.return_value = episodes

    pipeline.downloader.download.return_value = DownloadResult(
        success=True, file_path="/tmp/test.mp3", file_size=1000
    )
    pipeline.transcriber.transcribe.return_value = make_transcript_result()
    pipeline.storage.store_transcript.return_value = 3

    stats = pipeline.process_unprocessed(limit=None)

    assert stats["total"] == 3
    assert stats["success"] == 1
    assert stats["skipped"] == 2


@pytest.mark.unit
def test_run_full_pipeline(pipeline):
    from app.patreon.client import PatreonEpisode

    pipeline.patreon.get_all_episodes.return_value = [
        PatreonEpisode(id="100", title="Ep 1", audio_url="https://example.com/1.mp3", published_at="2024-01-01T00:00:00Z", duration_seconds=3600),
    ]
    pipeline.episode_repo.create.return_value = make_episode(id=1, patreon_id="100")
    pipeline.episode_repo.get_unprocessed.return_value = [make_episode(id=1, patreon_id="100")]

    pipeline.downloader.download.return_value = DownloadResult(
        success=True, file_path="/tmp/test.mp3", file_size=1000
    )
    pipeline.transcriber.transcribe.return_value = make_transcript_result()
    pipeline.storage.store_transcript.return_value = 3

    results = pipeline.run(sync=True, max_sync=100, process_limit=10)

    assert results["synced"] == 1
    assert results["processed"]["success"] == 1


@pytest.mark.unit
def test_run_skip_sync(pipeline):
    pipeline.episode_repo.get_unprocessed.return_value = []

    results = pipeline.run(sync=False, process_limit=10)

    assert results["synced"] == 0
    pipeline.patreon.get_all_episodes.assert_not_called()


@pytest.mark.unit
def test_run_process_all(pipeline):
    episodes = [make_episode(id=i, patreon_id=str(i)) for i in range(20)]
    pipeline.episode_repo.get_unprocessed.return_value = episodes

    pipeline.downloader.download.return_value = DownloadResult(
        success=True, file_path="/tmp/test.mp3", file_size=1000
    )
    pipeline.transcriber.transcribe.return_value = make_transcript_result()
    pipeline.storage.store_transcript.return_value = 3

    results = pipeline.run(sync=False, process_limit=None)

    assert results["processed"]["total"] == 20
    assert results["processed"]["success"] == 20
