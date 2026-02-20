"""Speaker diarization module for identifying speakers in audio."""
import bisect
import os
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SpeakerSegment:
    """A segment of speech attributed to a speaker."""
    speaker: str
    start_time: Decimal
    end_time: Decimal
    confidence: Optional[float] = None


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
                # PyTorch 2.6+ changed weights_only default to True, which breaks
                # pyannote model loading. Patch lightning_fabric to use weights_only=False.
                import torch
                import lightning_fabric.utilities.cloud_io as cloud_io
                original_load = cloud_io._load
                def patched_load(path_or_url, map_location=None, **kwargs):
                    return torch.load(path_or_url, map_location=map_location, weights_only=False)
                cloud_io._load = patched_load

                from pyannote.audio import Pipeline

                if not self.hf_token:
                    raise ValueError(
                        "HuggingFace token required for pyannote.audio. "
                        "Set HF_TOKEN environment variable or pass hf_token parameter."
                    )

                self._pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    token=self.hf_token
                )
                if torch.cuda.is_available():
                    self._pipeline = self._pipeline.to(torch.device("cuda"))
                    logger.info("Loaded pyannote speaker diarization pipeline (GPU)")
                else:
                    logger.info("Loaded pyannote speaker diarization pipeline (CPU)")
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

        # Try loading audio as waveform via torchaudio to avoid torchcodec issues on Windows
        try:
            import torchaudio
            waveform, sample_rate = torchaudio.load(audio_path)
            audio_input = {"waveform": waveform, "sample_rate": sample_rate}
        except Exception:
            audio_input = audio_path

        diarization = self.pipeline(audio_input, **kwargs)

        segments = []
        # Handle both old (Annotation.itertracks) and new (DiarizeOutput) pyannote formats
        if hasattr(diarization, 'itertracks'):
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append(SpeakerSegment(
                    speaker=speaker,
                    start_time=Decimal(str(round(turn.start, 3))),
                    end_time=Decimal(str(round(turn.end, 3)))
                ))
        elif hasattr(diarization, 'speaker_diarization'):
            # Newer pyannote (>=3.4) returns DiarizeOutput with speaker_diarization
            for turn, speaker in diarization.speaker_diarization:
                segments.append(SpeakerSegment(
                    speaker=str(speaker),
                    start_time=Decimal(str(round(turn.start, 3))),
                    end_time=Decimal(str(round(turn.end, 3)))
                ))
        else:
            # Fallback: try iterating directly
            logger.warning(f"Unknown diarization output type: {type(diarization)}, attrs: {dir(diarization)}")
            for item in diarization:
                segments.append(SpeakerSegment(
                    speaker=str(getattr(item, 'speaker', 'unknown')),
                    start_time=Decimal(str(round(getattr(item, 'start', 0), 3))),
                    end_time=Decimal(str(round(getattr(item, 'end', 0), 3)))
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

    # Build sorted list and parallel start_times list for binary search
    sorted_speakers = sorted(speaker_segments, key=lambda s: s.start_time)
    start_times = [s.start_time for s in sorted_speakers]

    for word in word_segments:
        word_start = word.start_time
        word_end = word.end_time

        # Use bisect to find candidate segments: only those with start_time < word_end
        # can possibly overlap with the word.
        right_idx = bisect.bisect_left(start_times, word_end)

        best_speaker = None
        best_confidence = None
        max_overlap = Decimal(0)
        second_max_overlap = Decimal(0)
        for seg in sorted_speakers[:right_idx]:
            if seg.end_time <= word_start:
                continue  # segment ends before word starts — no overlap
            overlap = min(word_end, seg.end_time) - max(word_start, seg.start_time)
            if overlap > max_overlap:
                second_max_overlap = max_overlap
                max_overlap = overlap
                best_speaker = seg.speaker
                best_confidence = seg.confidence
            elif overlap > second_max_overlap:
                second_max_overlap = overlap

        word.speaker = best_speaker
        if hasattr(word, 'speaker_confidence'):
            word.speaker_confidence = best_confidence

        # Overlap detection: flag crosstalk when second-best speaker has significant overlap.
        # Conditions: second-best >= 30% of word duration AND >= 50% of best overlap.
        if max_overlap > Decimal(0):
            word_duration = word_end - word_start
            if word_duration > Decimal(0):
                is_overlap = (
                    second_max_overlap >= word_duration * Decimal("0.3")
                    and second_max_overlap >= max_overlap * Decimal("0.5")
                )
                word.is_overlap = is_overlap
            else:
                word.is_overlap = False
        else:
            word.is_overlap = False

    # Bidirectional gap-filling: for unassigned words, pick the temporally
    # closer of the nearest preceding and following assigned words.
    n = len(word_segments)

    # Forward pass: for each position record the last assigned word before it
    prev_info = [None] * n  # (speaker, confidence, time_center)
    last_assigned = None
    for i, word in enumerate(word_segments):
        if word.speaker is not None:
            last_assigned = (
                word.speaker,
                getattr(word, 'speaker_confidence', None),
                (word.start_time + word.end_time) / 2,
            )
        prev_info[i] = last_assigned

    # Backward pass: for each position record the next assigned word after it
    next_info = [None] * n
    next_assigned = None
    for i in range(n - 1, -1, -1):
        word = word_segments[i]
        if word.speaker is not None:
            next_assigned = (
                word.speaker,
                getattr(word, 'speaker_confidence', None),
                (word.start_time + word.end_time) / 2,
            )
        next_info[i] = next_assigned

    for i, word in enumerate(word_segments):
        if word.speaker is not None:
            continue

        prev = prev_info[i]
        nxt = next_info[i]

        if prev is None and nxt is None:
            continue

        word_mid = (word.start_time + word.end_time) / 2

        if prev is None:
            chosen = nxt
        elif nxt is None:
            chosen = prev
        else:
            prev_dist = abs(word_mid - prev[2])
            next_dist = abs(word_mid - nxt[2])
            chosen = prev if prev_dist <= next_dist else nxt

        word.speaker = chosen[0]
        if hasattr(word, 'speaker_confidence'):
            word.speaker_confidence = chosen[1]

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
