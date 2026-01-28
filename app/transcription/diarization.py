"""Speaker diarization module for identifying speakers in audio."""
import os
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# Known speakers for the podcast
KNOWN_SPEAKERS = ["Matt", "Will", "Felix", "Amber", "Virgil"]

@dataclass
class SpeakerSegment:
    """A segment of speech attributed to a speaker."""
    speaker: str
    start_time: Decimal
    end_time: Decimal


class SpeakerDiarizer:
    """Performs speaker diarization on audio files using pyannote.audio."""

    def __init__(self, hf_token: Optional[str] = None, num_speakers: Optional[int] = None):
        """
        Initialize the diarizer.

        Args:
            hf_token: HuggingFace token for accessing pyannote models.
                      Falls back to HF_TOKEN env var.
            num_speakers: Expected number of speakers (optional hint for diarization).
        """
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        self.num_speakers = num_speakers
        self._pipeline = None

    @property
    def pipeline(self):
        """Lazy load the diarization pipeline."""
        if self._pipeline is None:
            try:
                from pyannote.audio import Pipeline

                if not self.hf_token:
                    raise ValueError(
                        "HuggingFace token required for pyannote.audio. "
                        "Set HF_TOKEN environment variable or pass hf_token parameter."
                    )

                self._pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self.hf_token
                )
                logger.info("Loaded pyannote speaker diarization pipeline")
            except ImportError:
                raise ImportError(
                    "pyannote.audio is required for speaker diarization. "
                    "Install with: pip install pyannote.audio"
                )
        return self._pipeline

    def diarize(self, audio_path: str) -> list[SpeakerSegment]:
        """
        Perform speaker diarization on an audio file.

        Args:
            audio_path: Path to the audio file.

        Returns:
            List of SpeakerSegment objects with speaker labels and timestamps.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info(f"Running speaker diarization on {audio_path}")

        # Run diarization pipeline
        kwargs = {}
        if self.num_speakers:
            kwargs["num_speakers"] = self.num_speakers

        diarization = self.pipeline(audio_path, **kwargs)

        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(SpeakerSegment(
                speaker=speaker,
                start_time=Decimal(str(round(turn.start, 3))),
                end_time=Decimal(str(round(turn.end, 3)))
            ))

        logger.info(f"Found {len(segments)} speaker segments")
        return segments

    def get_speaker_at_time(
        self,
        segments: list[SpeakerSegment],
        timestamp: Decimal
    ) -> Optional[str]:
        """
        Find which speaker is talking at a given timestamp.

        Args:
            segments: List of SpeakerSegment from diarization.
            timestamp: Time in seconds to look up.

        Returns:
            Speaker label or None if no speaker found at that time.
        """
        for seg in segments:
            if seg.start_time <= timestamp <= seg.end_time:
                return seg.speaker
        return None


def assign_speakers_to_words(
    word_segments: list,
    speaker_segments: list[SpeakerSegment]
) -> list:
    """
    Assign speaker labels to word segments based on diarization.

    Args:
        word_segments: List of word segments with start_time/end_time.
        speaker_segments: List of SpeakerSegment from diarization.

    Returns:
        The same word segments with speaker field populated.
    """
    if not speaker_segments:
        return word_segments

    # Build a sorted list of speaker segments for binary search
    sorted_speakers = sorted(speaker_segments, key=lambda s: s.start_time)

    for word in word_segments:
        # Find the speaker segment that contains this word's midpoint
        word_mid = (word.start_time + word.end_time) / 2

        speaker = None
        for seg in sorted_speakers:
            if seg.start_time <= word_mid <= seg.end_time:
                speaker = seg.speaker
                break
            elif seg.start_time > word_mid:
                # Past the word's time, stop searching
                break

        # Set the speaker (may remain None if no match)
        word.speaker = speaker

    return word_segments


def get_diarizer(
    hf_token: Optional[str] = None,
    num_speakers: Optional[int] = None
) -> SpeakerDiarizer:
    """
    Factory function to get a diarizer instance.

    Args:
        hf_token: HuggingFace token. Defaults to HF_TOKEN env var.
        num_speakers: Expected number of speakers (optional).

    Returns:
        Configured SpeakerDiarizer instance.
    """
    return SpeakerDiarizer(hf_token=hf_token, num_speakers=num_speakers)
