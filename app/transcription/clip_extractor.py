"""Extract clean speaker audio clips from transcribed episodes for enrollment.

Uses transcript data with speaker labels to identify clean speech segments,
then extracts those segments from the audio file for use in speaker enrollment.
"""
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "data/reference_audio"
DEFAULT_MIN_DURATION = 10.0  # seconds
DEFAULT_MAX_DURATION = 20.0  # seconds
DEFAULT_MAX_CLIPS_PER_SPEAKER = 10


@dataclass
class SpeechSegment:
    """A continuous segment of speech by a single speaker."""
    speaker: str
    start_time: float
    end_time: float
    word_count: int

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class ClipExtractor:
    """Extracts speaker audio clips from transcribed episodes."""

    def __init__(
        self,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        min_duration: float = DEFAULT_MIN_DURATION,
        max_duration: float = DEFAULT_MAX_DURATION,
    ):
        """Initialize the clip extractor.

        Args:
            output_dir: Directory to save extracted clips (organized by speaker).
            min_duration: Minimum clip duration in seconds.
            max_duration: Maximum clip duration in seconds.
        """
        if min_duration >= max_duration:
            raise ValueError(f"min_duration ({min_duration}) must be less than max_duration ({max_duration})")
        if min_duration < 0:
            raise ValueError(f"min_duration must be non-negative, got {min_duration}")

        self.output_dir = Path(output_dir)
        self.min_duration = min_duration
        self.max_duration = max_duration

    @staticmethod
    def _sanitize_speaker_name(name: str) -> str:
        """Sanitize speaker name for use in file paths.

        Args:
            name: Speaker name from database.

        Returns:
            Sanitized name safe for use in file paths.
        """
        # Replace problematic characters with underscores
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Remove leading/trailing whitespace and dots (problematic on Windows)
        sanitized = sanitized.strip(' .')
        # Ensure not empty
        if not sanitized:
            sanitized = "unknown_speaker"
        return sanitized

    def _get_speaker_segments_from_db(
        self,
        episode_id: int,
        speaker_name: Optional[str] = None
    ) -> List[Tuple[str, Decimal, Decimal]]:
        """Query transcript segments from database.

        Args:
            episode_id: Database ID of the episode.
            speaker_name: Optional speaker name to filter by.

        Returns:
            List of (speaker, start_time, end_time) tuples.
        """
        from app.db.connection import get_cursor

        with get_cursor(commit=False) as cursor:
            if speaker_name:
                cursor.execute(
                    """
                    SELECT speaker, start_time, end_time
                    FROM transcript_segments
                    WHERE episode_id = %s AND speaker = %s
                    ORDER BY start_time
                    """,
                    (episode_id, speaker_name)
                )
            else:
                cursor.execute(
                    """
                    SELECT speaker, start_time, end_time
                    FROM transcript_segments
                    WHERE episode_id = %s AND speaker IS NOT NULL
                    ORDER BY start_time
                    """,
                    (episode_id,)
                )

            return [
                (row["speaker"], row["start_time"], row["end_time"])
                for row in cursor.fetchall()
            ]

    def _group_into_segments(
        self,
        word_data: List[Tuple[str, Decimal, Decimal]],
        max_gap: float = 0.5
    ) -> List[SpeechSegment]:
        """Group consecutive words by same speaker into continuous segments.

        Args:
            word_data: List of (speaker, start_time, end_time) tuples.
            max_gap: Maximum gap between words to still consider them continuous (seconds).

        Returns:
            List of SpeechSegment objects representing continuous speech.
        """
        if not word_data:
            return []

        segments = []
        current_speaker = word_data[0][0]
        current_start = float(word_data[0][1])
        current_end = float(word_data[0][2])
        current_words = 1

        for speaker, start, end in word_data[1:]:
            start_f = float(start)
            end_f = float(end)
            gap = start_f - current_end

            # Check if we should continue the current segment or start a new one
            if speaker == current_speaker and gap <= max_gap:
                # Continue current segment
                current_end = end_f
                current_words += 1
            else:
                # Save current segment if it meets duration requirements
                duration = current_end - current_start
                if self.min_duration <= duration <= self.max_duration:
                    segments.append(SpeechSegment(
                        speaker=current_speaker,
                        start_time=current_start,
                        end_time=current_end,
                        word_count=current_words
                    ))

                # Start new segment
                current_speaker = speaker
                current_start = start_f
                current_end = end_f
                current_words = 1

        # Don't forget the last segment
        duration = current_end - current_start
        if self.min_duration <= duration <= self.max_duration:
            segments.append(SpeechSegment(
                speaker=current_speaker,
                start_time=current_start,
                end_time=current_end,
                word_count=current_words
            ))

        return segments

    def _extract_audio_segment(
        self,
        audio_path: str,
        segment: SpeechSegment,
        output_path: Path
    ) -> bool:
        """Extract a single audio segment using ffmpeg.

        Args:
            audio_path: Path to the source audio file.
            segment: SpeechSegment defining the time range to extract.
            output_path: Path where the extracted clip should be saved.

        Returns:
            True if extraction succeeded, False otherwise.
        """
        try:
            import subprocess

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Use ffmpeg to extract the segment
            # -ss: start time, -t: duration, -c copy would be faster but we want to normalize
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file if exists
                "-i", audio_path,
                "-ss", str(segment.start_time),
                "-t", str(segment.duration),
                "-ar", "16000",  # Resample to 16kHz (standard for speech models)
                "-ac", "1",  # Convert to mono
                "-q:a", "0",  # Best quality
                str(output_path)
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            logger.debug(f"Extracted clip: {output_path.name} ({segment.duration:.1f}s)")
            return True

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to extract clip: {e.stderr.decode()}")
            return False
        except Exception as e:
            logger.warning(f"Failed to extract clip: {e}")
            return False

    def extract_clips(
        self,
        episode_id: int,
        audio_path: str,
        speaker_name: Optional[str] = None,
        max_clips_per_speaker: int = DEFAULT_MAX_CLIPS_PER_SPEAKER
    ) -> dict[str, List[str]]:
        """Extract speaker clips from an episode.

        Args:
            episode_id: Database ID of the episode.
            audio_path: Path to the episode audio file.
            speaker_name: Optional speaker name to extract clips for (extracts all if None).
            max_clips_per_speaker: Maximum number of clips to extract per speaker.

        Returns:
            Dict mapping speaker names to lists of extracted clip paths.
        """
        logger.info(f"Extracting clips from episode {episode_id}...")

        # Query transcript segments
        word_data = self._get_speaker_segments_from_db(episode_id, speaker_name)

        if not word_data:
            logger.warning(f"No speaker-labeled segments found for episode {episode_id}")
            return {}

        # Group into continuous speech segments
        all_segments = self._group_into_segments(word_data)

        if not all_segments:
            logger.warning(f"No valid segments found (duration requirements: {self.min_duration}-{self.max_duration}s)")
            return {}

        # Group segments by speaker
        segments_by_speaker: dict[str, List[SpeechSegment]] = {}
        for seg in all_segments:
            if seg.speaker not in segments_by_speaker:
                segments_by_speaker[seg.speaker] = []
            segments_by_speaker[seg.speaker].append(seg)

        # Extract clips for each speaker
        extracted_clips: dict[str, List[str]] = {}

        for speaker, segments in segments_by_speaker.items():
            logger.info(f"  {speaker}: {len(segments)} valid segments found")

            # Sort by duration (prefer longer clips) and take the best ones
            segments_sorted = sorted(segments, key=lambda s: s.duration, reverse=True)
            segments_to_extract = segments_sorted[:max_clips_per_speaker]

            # Sanitize speaker name for directory creation
            safe_speaker_name = self._sanitize_speaker_name(speaker)
            speaker_dir = self.output_dir / safe_speaker_name
            speaker_dir.mkdir(parents=True, exist_ok=True)

            extracted_clips[speaker] = []

            for idx, segment in enumerate(segments_to_extract):
                output_path = speaker_dir / f"episode_{episode_id}_clip_{idx:02d}.wav"

                if self._extract_audio_segment(audio_path, segment, output_path):
                    extracted_clips[speaker].append(str(output_path))

            logger.info(f"  {speaker}: Extracted {len(extracted_clips[speaker])} clips")

        return extracted_clips
