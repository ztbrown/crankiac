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
        vocabulary_file: Optional[str] = None,
        enable_speaker_id: bool = False,
        match_threshold: float = 0.70,
        embeddings_dir: str = "data/speaker_embeddings",
        expected_speakers: Optional[list[str]] = None,
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
            enable_speaker_id: Whether to identify speakers via voice embeddings.
            match_threshold: Cosine similarity threshold for speaker matching.
            embeddings_dir: Directory containing reference speaker embeddings.
        """
        self.session_id = session_id or os.environ.get("PATREON_SESSION_ID")
        if not self.session_id:
            raise ValueError("PATREON_SESSION_ID required")

        self.cleanup_audio = cleanup_audio
        self.enable_diarization = enable_diarization
        self.enable_speaker_id = enable_speaker_id
        self.expected_speakers = expected_speakers
        self.patreon = PatreonClient(self.session_id)
        self.downloader = AudioDownloader(self.session_id, download_dir)
        self.storage = TranscriptStorage()
        self.episode_repo = EpisodeRepository()

        # Load vocabulary hints from file and build initial_prompt for Whisper
        self.vocabulary_hints = self._load_vocabulary(vocabulary_file)
        initial_prompt = None
        if self.vocabulary_hints:
            initial_prompt = "Names mentioned: " + ", ".join(self.vocabulary_hints) + "."
        self.transcriber = get_transcriber(whisper_model, initial_prompt=initial_prompt)

        # Initialize diarizer if enabled
        self.diarizer = None
        if enable_diarization:
            try:
                # Infer num_speakers from expected_speakers if not explicitly set
                effective_num_speakers = num_speakers
                if effective_num_speakers is None and expected_speakers:
                    effective_num_speakers = len(expected_speakers)
                    logger.info(f"Inferring num_speakers={effective_num_speakers} from expected_speakers")
                self.diarizer = get_diarizer(hf_token=hf_token, num_speakers=effective_num_speakers)
                logger.info("Speaker diarization enabled")
            except Exception as e:
                logger.warning(f"Could not initialize diarizer: {e}. Diarization disabled.")

        # Initialize speaker identifier if enabled
        self.speaker_identifier = None
        if enable_speaker_id:
            try:
                from app.transcription.speaker_identification import SpeakerIdentifier
                self.speaker_identifier = SpeakerIdentifier(
                    embeddings_dir=embeddings_dir,
                    match_threshold=match_threshold,
                    hf_token=hf_token,
                )
                logger.info("Speaker identification enabled")
            except Exception as e:
                logger.warning(f"Could not initialize speaker identifier: {e}. Speaker ID disabled.")

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

    def process_episode(self, episode: Episode, force: bool = False) -> bool:
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
        if episode.processed and not force:
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

                    # Speaker identification (optional) — map labels to real names
                    if self.speaker_identifier:
                        logger.info(f"  Running speaker identification...")
                        try:
                            label_map = self.speaker_identifier.identify(
                                download_result.file_path, speaker_segments,
                                expected_speakers=self.expected_speakers,
                            )
                            if label_map:
                                speaker_segments = self.speaker_identifier.relabel_segments(
                                    speaker_segments, label_map
                                )
                                logger.info(f"  Identified speakers: {label_map}")
                        except Exception as e:
                            logger.warning(f"  Speaker identification failed (continuing with generic labels): {e}")

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

    def process_single(self, episode_id: int, force: bool = False) -> bool:
        """
        Process a specific episode by its database ID.

        Args:
            episode_id: Database ID of the episode to process.
            force: If True, reprocess even if already processed.

        Returns:
            True if successful, False otherwise.

        Raises:
            ValueError: If episode not found.
        """
        episode = self.episode_repo.get_by_id(episode_id)
        if episode is None:
            raise ValueError(f"Episode with id={episode_id} not found")

        return self.process_episode(episode, force=force)

    def process_unprocessed(self, limit: Optional[int] = 10, offset: int = 0, numbered_only: bool = False, force: bool = False) -> dict:
        """
        Process all unprocessed episodes.

        Args:
            limit: Maximum episodes to process in one run. None for no limit.
            offset: Number of episodes to skip before processing.
            numbered_only: If True, only process numbered episodes.
            force: If True, reprocess even if already processed.

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
            if self.process_episode(episode, force=force):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        return stats

    def diarize_episode(self, episode: Episode) -> bool:
        """
        Run speaker diarization on an already-transcribed episode.

        This downloads the audio, runs diarization, and updates existing
        transcript segments with speaker labels. Much faster than re-transcribing.

        Args:
            episode: Episode to diarize (must already have transcript).

        Returns:
            True if successful, False otherwise.
        """
        if episode.id is None:
            raise ValueError(
                f"Cannot diarize episode '{episode.title}': episode.id is None."
            )

        logger.info(f"Diarizing: {episode.title}")

        # Check if episode has transcript
        if not self.storage.has_transcript(episode.id):
            logger.warning(f"  No transcript found, skipping")
            return False

        # Skip if no audio URL
        if not episode.audio_url:
            logger.warning(f"  No audio URL, skipping")
            return False

        # Check if diarizer is available
        if not self.diarizer:
            logger.error(f"  Diarizer not initialized. Use --diarize flag or set HF_TOKEN.")
            return False

        try:
            # Download audio
            logger.info(f"  Downloading audio...")
            download_result = self.downloader.download(episode.audio_url, episode.patreon_id)
            if not download_result.success:
                logger.error(f"  Download failed: {download_result.error}")
                return False
            logger.info(f"  Downloaded: {download_result.file_size} bytes")

            # Get existing transcript segments
            logger.info(f"  Loading existing transcript...")
            segments = self.storage.get_segments_for_diarization(episode.id)
            logger.info(f"  Found {len(segments)} segments")

            # Run diarization
            logger.info(f"  Running speaker diarization...")
            speaker_segments = self.diarizer.diarize(download_result.file_path)
            logger.info(f"  Found {len(speaker_segments)} speaker segments")

            # Speaker identification (optional) — map labels to real names
            if self.speaker_identifier:
                logger.info(f"  Running speaker identification...")
                try:
                    label_map = self.speaker_identifier.identify(
                        download_result.file_path, speaker_segments,
                        expected_speakers=self.expected_speakers,
                    )
                    if label_map:
                        speaker_segments = self.speaker_identifier.relabel_segments(
                            speaker_segments, label_map
                        )
                        logger.info(f"  Identified speakers: {label_map}")
                except Exception as e:
                    logger.warning(f"  Speaker identification failed (continuing with generic labels): {e}")

            # Assign speakers to words
            from app.transcription.diarization import assign_speakers_to_words
            updated_segments = assign_speakers_to_words(segments, speaker_segments)

            speakers_found = len(set(s.speaker for s in updated_segments if s.speaker))
            logger.info(f"  Assigned {speakers_found} unique speakers")

            # Update database
            logger.info(f"  Updating transcript with speaker labels...")
            count = self.storage.update_speaker_labels(updated_segments)
            logger.info(f"  Updated {count} segments")

            # Cleanup audio file
            if self.cleanup_audio and download_result.file_path:
                self._cleanup_audio(download_result.file_path)

            logger.info(f"  Done!")
            return True

        except Exception as e:
            logger.error(f"  Error diarizing episode: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run(self, sync: bool = True, max_sync: int = 100, process_limit: Optional[int] = 10, offset: int = 0, numbered_only: bool = False, force: bool = False) -> dict:
        """
        Run the full pipeline.

        Args:
            sync: Whether to sync episodes from Patreon first.
            max_sync: Max episodes to sync.
            process_limit: Max episodes to process. None for no limit.
            offset: Number of episodes to skip before processing.
            numbered_only: If True, only process numbered episodes.
            force: If True, reprocess even if already processed.

        Returns:
            Dict with pipeline statistics.
        """
        results = {"synced": 0, "processed": {"total": 0, "success": 0, "failed": 0, "skipped": 0}}

        if sync:
            episodes = self.sync_episodes(max_sync)
            results["synced"] = len(episodes)

        process_stats = self.process_unprocessed(process_limit, offset, numbered_only=numbered_only, force=force)
        results["processed"] = process_stats

        return results
