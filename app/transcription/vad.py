"""Voice Activity Detection (VAD) pre-filtering using Silero VAD."""
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SpeechSegment:
    start: float  # seconds in original audio
    end: float    # seconds in original audio


class VoiceActivityDetector:
    """Silero VAD wrapper for detecting speech segments in audio."""

    def __init__(
        self,
        min_speech_duration: float = 0.25,
        min_silence_duration: float = 0.5,
        speech_pad: float = 0.1,
        threshold: float = 0.5,
    ):
        """
        Initialize the VAD.

        Args:
            min_speech_duration: Minimum duration (s) to keep a speech segment.
            min_silence_duration: Minimum silence (s) before splitting segments.
            speech_pad: Padding (s) added to each side of detected speech.
            threshold: Confidence threshold for speech detection (0-1).
        """
        self.min_speech_duration = min_speech_duration
        self.min_silence_duration = min_silence_duration
        self.speech_pad = speech_pad
        self.threshold = threshold
        self._model = None
        self._utils = None

    def _load_model(self):
        """Lazy-load the Silero VAD model."""
        if self._model is None:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self._model = model
            self._utils = utils
        return self._model, self._utils

    def detect(self, audio_path: str) -> list[SpeechSegment]:
        """
        Detect speech segments in an audio file.

        Args:
            audio_path: Path to the audio file.

        Returns:
            List of SpeechSegment with start/end times in the original audio.
        """
        import torch
        import torchaudio

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        model, utils = self._load_model()
        get_speech_timestamps, _, read_audio, _, _ = utils

        # Silero VAD expects 16kHz mono audio
        wav = read_audio(audio_path, sampling_rate=16000)

        speech_timestamps = get_speech_timestamps(
            wav,
            model,
            sampling_rate=16000,
            threshold=self.threshold,
            min_speech_duration_ms=int(self.min_speech_duration * 1000),
            min_silence_duration_ms=int(self.min_silence_duration * 1000),
            speech_pad_ms=int(self.speech_pad * 1000),
            return_seconds=True,
        )

        return [
            SpeechSegment(start=ts["start"], end=ts["end"])
            for ts in speech_timestamps
        ]

    def filter_audio(self, audio_path: str, output_path: Optional[str] = None) -> tuple[str, list[SpeechSegment]]:
        """
        Write a new audio file containing only speech segments.

        The segments are concatenated directly (no crossfades) to keep
        timestamp remapping straightforward.

        Args:
            audio_path: Path to the input audio file.
            output_path: Path for the filtered output. If None, a temp file is used.

        Returns:
            Tuple of (output_path, speech_segments) where speech_segments are
            the detected segments in the ORIGINAL audio's timeline.
        """
        import torch
        import torchaudio

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Detect speech segments
        segments = self.detect(audio_path)
        if not segments:
            logger.warning("VAD found no speech segments in audio")
            return audio_path, []

        # Load original audio at native sample rate
        waveform, sample_rate = torchaudio.load(audio_path)

        # Collect speech chunks
        chunks = []
        for seg in segments:
            start_sample = int(seg.start * sample_rate)
            end_sample = int(seg.end * sample_rate)
            end_sample = min(end_sample, waveform.shape[1])
            if start_sample < end_sample:
                chunks.append(waveform[:, start_sample:end_sample])

        if not chunks:
            return audio_path, []

        # Concatenate and write
        filtered = torch.cat(chunks, dim=1)

        if output_path is None:
            suffix = os.path.splitext(audio_path)[1] or ".wav"
            fd, output_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)

        torchaudio.save(output_path, filtered, sample_rate)
        logger.info(
            f"VAD filtered audio: {len(segments)} speech segments, "
            f"{filtered.shape[1] / sample_rate:.1f}s of speech retained"
        )
        return output_path, segments


def remap_timestamps(
    filtered_time: float,
    speech_segments: list[SpeechSegment],
) -> float:
    """
    Map a timestamp from the VAD-filtered audio back to the original timeline.

    After VAD filtering, silence is removed and segments are concatenated.
    This function converts a time in the filtered audio to the corresponding
    time in the original audio.

    Args:
        filtered_time: Timestamp (seconds) in the filtered audio.
        speech_segments: List of SpeechSegment from the original audio (in
                         original timeline order, as returned by detect()).

    Returns:
        Corresponding timestamp (seconds) in the original audio.
    """
    if not speech_segments:
        return filtered_time

    cursor = 0.0
    for seg in speech_segments:
        seg_duration = seg.end - seg.start
        if filtered_time <= cursor + seg_duration:
            # The filtered_time falls within this segment
            offset_within_seg = filtered_time - cursor
            return seg.start + offset_within_seg
        cursor += seg_duration

    # Beyond all segments — clamp to end of last segment
    return speech_segments[-1].end
