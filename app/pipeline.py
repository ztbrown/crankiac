"""Episode processing pipeline - orchestrates fetch, download, transcribe, store."""
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.patreon.client import PatreonClient, PatreonEpisode
from app.patreon.downloader import AudioDownloader
from app.transcription.whisper_transcriber import get_transcriber
from app.transcription.storage import TranscriptStorage
from app.transcription.diarization import get_diarizer, assign_speakers_to_words
from app.db.repository import EpisodeRepository
from app.db.models import Episode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EpisodePipeline:
    """Orchestrates the full episode processing pipeline."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        whisper_model: str = "base",
        download_dir: str = "downloads/audio",
        cleanup_audio: bool = True,
        enable_diarization: bool = False,
        hf_token: Optional[str] = None,
        num_speakers: Optional[int] = None,
        vocabulary_file: Optional[str] = None
    ):
        """
        Initialize the pipeline.

        Args:
            session_id: Patreon session_id cookie (or from env).
            whisper_model: Whisper model size to use.
            download_dir: Directory for downloaded audio files.
            cleanup_audio: Delete audio files after successful transcription.
            enable_diarization: Whether to run speaker diarization.
            hf_token: HuggingFace token for pyannote (or from HF_TOKEN env).
            num_speakers: Expected number of speakers (optional hint).
            vocabulary_file: Path to file with vocabulary hints (one per line).
        """
        self.session_id = session_id or os.environ.get("PATREON_SESSION_ID")
        if not self.session_id:
            raise ValueError("PATREON_SESSION_ID required")

        self.cleanup_audio = cleanup_audio
        self.enable_diarization = enable_diarization
        self.patreon = PatreonClient(self.session_id)
        self.downloader = AudioDownloader(self.session_id, download_dir)
        self.storage = TranscriptStorage()
        self.episode_repo = EpisodeRepository()

        # Load vocabulary hints from file and build initial_prompt for Whisper
        vocabulary_hints = self._load_vocabulary(vocabulary_file)
        initial_prompt = None
        if vocabulary_hints:
            initial_prompt = "Names mentioned: " + ", ".join(vocabulary_hints) + "."
        self.transcriber = get_transcriber(whisper_model, initial_prompt=initial_prompt)

        # Initialize diarizer if enabled
        self.diarizer = None
        if enable_diarization:
            try:
                self.diarizer = get_diarizer(hf_token=hf_token, num_speakers=num_speakers)
                logger.info("Speaker diarization enabled")
            except Exception as e:
                logger.warning(f"Could not initialize diarizer: {e}. Diarization disabled.")

    def _load_vocabulary(self, vocabulary_file: Optional[str]) -> list[str]:
        """Load vocabulary hints from file.

        Args:
            vocabulary_file: Path to file with vocabulary hints (one per line).

        Returns:
            List of vocabulary hints, or empty list if file not provided/found.
        """
        if not vocabulary_file:
            return []

        path = Path(vocabulary_file)
        if not path.exists():
            logger.warning(f"Vocabulary file not found: {vocabulary_file}")
            return []

        try:
            hints = []
            for line in path.read_text().splitlines():
                line = line.strip()
                if line:
                    hints.append(line)
            logger.info(f"Loaded {len(hints)} vocabulary hints from {vocabulary_file}")
            return hints
        except Exception as e:
            logger.warning(f"Failed to load vocabulary file: {e}")
            return []

    def sync_episodes(self, max_episodes: int = 100) -> list[Episode]:
        """
        Fetch episodes from Patreon and sync to database.

        Args:
            max_episodes: Maximum episodes to fetch.

        Returns:
            List of Episode objects (new and existing).
        """
        logger.info(f"Fetching up to {max_episodes} episodes from Patreon...")
        patreon_episodes = self.patreon.get_all_episodes(max_episodes)
        logger.info(f"Found {len(patreon_episodes)} episodes")

        episodes = []
        for pe in patreon_episodes:
            episode = Episode(
                id=None,
                patreon_id=pe.id,
                title=pe.title,
                audio_url=pe.audio_url,
                published_at=datetime.fromisoformat(pe.published_at.replace("Z", "+00:00")) if pe.published_at else None,
                duration_seconds=pe.duration_seconds
            )
            saved = self.episode_repo.create(episode)
            episodes.append(saved)

        logger.info(f"Synced {len(episodes)} episodes to database")
        return episodes

    def process_episode(self, episode: Episode) -> bool:
        """
        Process a single episode: download, transcribe, store, cleanup.

        Args:
            episode: Episode to process.

        Returns:
            True if successful, False otherwise.

        Raises:
            ValueError: If episode.id is None (episode must be persisted first).
        """
        if episode.id is None:
            raise ValueError(
                f"Cannot process episode '{episode.title}': episode.id is None. "
                "Episode must be saved to database before processing."
            )

        logger.info(f"Processing: {episode.title}")

        # Skip if already processed
        if episode.processed:
            logger.info(f"  Already processed, skipping")
            return True

        # Skip if no audio URL
        if not episode.audio_url:
            logger.warning(f"  No audio URL, skipping")
            return False

        try:
            # Download
            logger.info(f"  Downloading audio...")
            download_result = self.downloader.download(episode.audio_url, episode.patreon_id)
            if not download_result.success:
                logger.error(f"  Download failed: {download_result.error}")
                return False
            logger.info(f"  Downloaded: {download_result.file_size} bytes")

            # Transcribe
            logger.info(f"  Transcribing...")
            transcript = self.transcriber.transcribe(download_result.file_path)
            logger.info(f"  Transcribed: {len(transcript.segments)} words")

            # Speaker diarization (optional)
            if self.diarizer:
                logger.info(f"  Running speaker diarization...")
                try:
                    speaker_segments = self.diarizer.diarize(download_result.file_path)
                    transcript.segments = assign_speakers_to_words(
                        transcript.segments, speaker_segments
                    )
                    speakers_found = len(set(
                        s.speaker for s in transcript.segments if s.speaker
                    ))
                    logger.info(f"  Diarization complete: {speakers_found} unique speakers")
                except Exception as e:
                    logger.warning(f"  Diarization failed (continuing without): {e}")

            # Store
            logger.info(f"  Storing transcript...")
            self.storage.delete_episode_transcript(episode.id)  # Clear any existing
            count = self.storage.store_transcript(episode.id, transcript)
            logger.info(f"  Stored: {count} segments")

            # Mark processed
            self.episode_repo.mark_processed(episode.id)
            logger.info(f"  Done!")

            # Cleanup audio file
            if self.cleanup_audio and download_result.file_path:
                self._cleanup_audio(download_result.file_path)

            return True

        except Exception as e:
            logger.error(f"  Error processing episode: {e}")
            return False

    def _cleanup_audio(self, file_path: str) -> None:
        """Delete an audio file after successful transcription."""
        try:
            path = Path(file_path)
            if path.exists():
                size_mb = path.stat().st_size / (1024 * 1024)
                path.unlink()
                logger.info(f"  Cleaned up audio file ({size_mb:.1f} MB freed)")
        except OSError as e:
            logger.warning(f"  Failed to clean up audio file: {e}")

    def process_single(self, episode_id: int) -> bool:
        """
        Process a specific episode by its database ID.

        Args:
            episode_id: Database ID of the episode to process.

        Returns:
            True if successful, False otherwise.

        Raises:
            ValueError: If episode not found.
        """
        episode = self.episode_repo.get_by_id(episode_id)
        if episode is None:
            raise ValueError(f"Episode with id={episode_id} not found")

        return self.process_episode(episode)

    def process_unprocessed(self, limit: Optional[int] = 10, offset: int = 0, numbered_only: bool = False) -> dict:
        """
        Process all unprocessed episodes.

        Args:
            limit: Maximum episodes to process in one run. None for no limit.
            offset: Number of episodes to skip before processing.
            numbered_only: If True, only process numbered episodes.

        Returns:
            Dict with processing statistics.
        """
        all_unprocessed = self.episode_repo.get_unprocessed(numbered_only=numbered_only)
        if limit is None:
            episodes = all_unprocessed[offset:]
        else:
            episodes = all_unprocessed[offset:offset + limit]
        total = len(episodes)
        logger.info(f"Found {len(all_unprocessed)} unprocessed episodes, processing {total}")

        stats = {"total": total, "success": 0, "failed": 0, "skipped": 0}

        for i, episode in enumerate(episodes, 1):
            logger.info(f"[{i}/{total}] {episode.title}")
            if not episode.audio_url:
                stats["skipped"] += 1
                continue
            if self.process_episode(episode):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        return stats

    def run(self, sync: bool = True, max_sync: int = 100, process_limit: Optional[int] = 10, offset: int = 0, numbered_only: bool = False) -> dict:
        """
        Run the full pipeline.

        Args:
            sync: Whether to sync episodes from Patreon first.
            max_sync: Max episodes to sync.
            process_limit: Max episodes to process. None for no limit.
            offset: Number of episodes to skip before processing.
            numbered_only: If True, only process numbered episodes.

        Returns:
            Dict with pipeline statistics.
        """
        results = {"synced": 0, "processed": {"total": 0, "success": 0, "failed": 0, "skipped": 0}}

        if sync:
            episodes = self.sync_episodes(max_sync)
            results["synced"] = len(episodes)

        process_stats = self.process_unprocessed(process_limit, offset, numbered_only=numbered_only)
        results["processed"] = process_stats

        return results
