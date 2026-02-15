"""Extract clean speaker audio clips from transcribed episodes for enrollment."""
import os
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

from app.db.repository import EpisodeRepository
from app.db.connection import get_cursor
from app.patreon.downloader import AudioDownloader

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "data/reference_audio"
MIN_CLIP_DURATION = 2.0  # seconds
MAX_CLIP_DURATION = 10.0  # seconds
MIN_WORD_COUNT = 5  # minimum words in a segment to be useful


@dataclass
class SpeakerSegment:
    """A continuous segment of speech from one speaker."""
    speaker: str
    start_time: float
    end_time: float
    words: List[str]
    word_count: int

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class ClipExtractor:
    """Extract clean speaker audio clips from transcript data."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        download_dir: str = "downloads/audio",
        output_dir: str = DEFAULT_OUTPUT_DIR,
        min_duration: float = MIN_CLIP_DURATION,
        max_duration: float = MAX_CLIP_DURATION,
        min_words: int = MIN_WORD_COUNT,
    ):
        """
        Initialize the clip extractor.

        Args:
            session_id: Patreon session_id for downloading audio (or from env).
            download_dir: Directory for downloaded episode audio files.
            output_dir: Root directory for extracted clips (speaker subdirs created).
            min_duration: Minimum clip duration in seconds.
            max_duration: Maximum clip duration in seconds.
            min_words: Minimum number of words in a segment.
        """
        self.session_id = session_id or os.environ.get("PATREON_SESSION_ID")
        if not self.session_id:
            raise ValueError("PATREON_SESSION_ID required")

        self.downloader = AudioDownloader(self.session_id, download_dir)
        self.episode_repo = EpisodeRepository()
        self.output_dir = Path(output_dir)
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.min_words = min_words

    def get_speaker_segments(self, episode_id: int) -> List[SpeakerSegment]:
        """
        Get continuous speaker segments from transcript data.

        Groups consecutive words by speaker, filtering for segments with
        speaker labels and sufficient duration/word count.

        Args:
            episode_id: Database ID of the episode.

        Returns:
            List of SpeakerSegment objects.
        """
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT word, start_time, end_time, speaker
                FROM transcript_segments
                WHERE episode_id = %s AND speaker IS NOT NULL
                ORDER BY segment_index
                """,
                (episode_id,)
            )
            rows = cursor.fetchall()

        if not rows:
            return []

        segments = []
        current_speaker = None
        current_words = []
        current_start = None
        current_end = None

        for row in rows:
            word = row["word"]
            start = float(row["start_time"])
            end = float(row["end_time"])
            speaker = row["speaker"]

            # Start new segment if speaker changes
            if speaker != current_speaker:
                # Save previous segment if it meets criteria
                if current_speaker and current_words:
                    duration = current_end - current_start
                    word_count = len(current_words)
                    if (word_count >= self.min_words and
                        self.min_duration <= duration <= self.max_duration):
                        segments.append(SpeakerSegment(
                            speaker=current_speaker,
                            start_time=current_start,
                            end_time=current_end,
                            words=current_words.copy(),
                            word_count=word_count,
                        ))

                # Start new segment
                current_speaker = speaker
                current_words = [word]
                current_start = start
                current_end = end
            else:
                # Continue current segment
                current_words.append(word)
                current_end = end

        # Save final segment
        if current_speaker and current_words:
            duration = current_end - current_start
            word_count = len(current_words)
            if (word_count >= self.min_words and
                self.min_duration <= duration <= self.max_duration):
                segments.append(SpeakerSegment(
                    speaker=current_speaker,
                    start_time=current_start,
                    end_time=current_end,
                    words=current_words.copy(),
                    word_count=word_count,
                ))

        return segments

    def extract_clip(
        self,
        audio_path: str,
        output_path: str,
        start_time: float,
        end_time: float,
    ) -> bool:
        """
        Extract an audio clip using ffmpeg.

        Args:
            audio_path: Path to source audio file.
            output_path: Path for extracted clip.
            start_time: Start time in seconds.
            end_time: End time in seconds.

        Returns:
            True if extraction succeeded, False otherwise.
        """
        duration = end_time - start_time

        try:
            # Use ffmpeg to extract clip
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", audio_path,
                    "-ss", str(start_time),
                    "-t", str(duration),
                    "-ar", "16000",  # 16kHz sample rate (standard for speech)
                    "-ac", "1",  # mono
                    "-y",  # overwrite output file
                    output_path,
                ],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg failed: {e.stderr.decode()}")
            return False

    def extract_clips_for_episode(
        self,
        episode_id: int,
        speaker_filter: Optional[str] = None,
        max_clips_per_speaker: Optional[int] = None,
    ) -> dict:
        """
        Extract speaker clips from an episode.

        Args:
            episode_id: Database ID of the episode.
            speaker_filter: Only extract clips for this speaker (e.g., "SPEAKER_0").
            max_clips_per_speaker: Limit number of clips per speaker.

        Returns:
            Dict with stats: {
                "episode_id": int,
                "episode_title": str,
                "speakers": {speaker: clip_count},
                "total_clips": int,
            }
        """
        # Get episode metadata
        episode = self.episode_repo.get_by_id(episode_id)
        if not episode:
            raise ValueError(f"Episode {episode_id} not found")

        if not episode.audio_url:
            raise ValueError(f"Episode {episode_id} has no audio URL")

        logger.info(f"Processing episode {episode_id}: {episode.title}")

        # Download audio if needed
        logger.info("Downloading audio...")
        result = self.downloader.download_episode(episode)
        if not result.success:
            raise RuntimeError(f"Failed to download audio: {result.error}")

        audio_path = result.file_path
        logger.info(f"Audio downloaded: {audio_path}")

        # Get speaker segments
        logger.info("Extracting speaker segments from transcript...")
        segments = self.get_speaker_segments(episode_id)

        # Filter by speaker if requested
        if speaker_filter:
            segments = [s for s in segments if s.speaker == speaker_filter]

        if not segments:
            logger.warning("No suitable speaker segments found")
            return {
                "episode_id": episode_id,
                "episode_title": episode.title,
                "speakers": {},
                "total_clips": 0,
            }

        logger.info(f"Found {len(segments)} suitable segments")

        # Group segments by speaker
        by_speaker = {}
        for seg in segments:
            if seg.speaker not in by_speaker:
                by_speaker[seg.speaker] = []
            by_speaker[seg.speaker].append(seg)

        # Extract clips
        stats = {
            "episode_id": episode_id,
            "episode_title": episode.title,
            "speakers": {},
            "total_clips": 0,
        }

        for speaker, speaker_segments in by_speaker.items():
            # Limit clips per speaker if requested
            if max_clips_per_speaker:
                speaker_segments = speaker_segments[:max_clips_per_speaker]

            # Create speaker output directory
            speaker_dir = self.output_dir / speaker
            speaker_dir.mkdir(parents=True, exist_ok=True)

            clips_extracted = 0
            for i, seg in enumerate(speaker_segments, 1):
                # Generate clip filename
                clip_name = f"ep{episode_id}_{speaker}_{i:03d}.wav"
                output_path = speaker_dir / clip_name

                # Extract clip
                logger.info(
                    f"  Extracting {speaker} clip {i}/{len(speaker_segments)}: "
                    f"{seg.start_time:.1f}s-{seg.end_time:.1f}s "
                    f"({seg.duration:.1f}s, {seg.word_count} words)"
                )

                if self.extract_clip(audio_path, str(output_path), seg.start_time, seg.end_time):
                    clips_extracted += 1
                else:
                    logger.warning(f"Failed to extract clip: {output_path}")

            stats["speakers"][speaker] = clips_extracted
            stats["total_clips"] += clips_extracted
            logger.info(f"Extracted {clips_extracted} clips for {speaker}")

        return stats
