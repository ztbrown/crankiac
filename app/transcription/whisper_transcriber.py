import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
import whisper

@dataclass
class WordSegment:
    word: str
    start_time: Decimal
    end_time: Decimal
    speaker: Optional[str] = None
    word_confidence: Optional[Decimal] = None

@dataclass
class TranscriptResult:
    segments: list[WordSegment]
    full_text: str
    language: str
    duration: float

class WhisperTranscriber:
    """Transcribes audio files using OpenAI Whisper with word-level timestamps."""

    def __init__(
        self,
        model_name: str = "large-v3",
        initial_prompt: str = None,
        vad_filter: bool = False,
    ):
        """
        Initialize the transcriber.

        Args:
            model_name: Whisper model size. Options: tiny, base, small, medium, large,
                       large-v3, turbo. Larger models are more accurate but slower.
                       large-v3 offers best accuracy; turbo offers large-quality at
                       faster inference speed.
            initial_prompt: Optional text to provide context for transcription.
                           Useful for improving accuracy of proper nouns and vocabulary.
            vad_filter: If True, run Silero VAD before transcription to strip
                        non-speech audio. Timestamps are remapped back to the
                        original audio timeline after transcription.
        """
        self.model_name = model_name
        self.initial_prompt = initial_prompt
        self.vad_filter = vad_filter
        self._model = None

    @property
    def model(self):
        """Lazy load the model on GPU if available."""
        if self._model is None:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = whisper.load_model(self.model_name, device=device)
        return self._model

    def transcribe(self, audio_path: str) -> TranscriptResult:
        """
        Transcribe an audio file with word-level timestamps.

        When vad_filter=True, runs Silero VAD first to strip non-speech audio,
        then remaps Whisper's timestamps back to the original audio timeline.

        Args:
            audio_path: Path to the audio file.

        Returns:
            TranscriptResult with word segments and metadata.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        speech_segments = None
        transcribe_path = audio_path
        filtered_path = None

        if self.vad_filter:
            from app.transcription.vad import VoiceActivityDetector
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info("Running VAD pre-filter...")
            vad = VoiceActivityDetector()
            filtered_path, speech_segments = vad.filter_audio(audio_path)
            if filtered_path != audio_path:
                transcribe_path = filtered_path
                _logger.info(f"VAD filtered: {len(speech_segments)} speech segments retained")

        try:
            # Transcribe with word timestamps
            result = self.model.transcribe(
                transcribe_path,
                word_timestamps=True,
                language="en",
                condition_on_previous_text=False,
                initial_prompt=self.initial_prompt,
                verbose=False
            )
        finally:
            # Clean up the temporary filtered file
            if filtered_path and filtered_path != audio_path:
                try:
                    os.unlink(filtered_path)
                except OSError:
                    pass

        segments = []

        for segment in result.get("segments", []):
            for word_info in segment.get("words", []):
                word = word_info.get("word", "").strip()
                if word:
                    raw_start = word_info["start"]
                    raw_end = word_info["end"]

                    if speech_segments:
                        from app.transcription.vad import remap_timestamps
                        raw_start = remap_timestamps(raw_start, speech_segments)
                        raw_end = remap_timestamps(raw_end, speech_segments)

                    probability = word_info.get("probability")
                    segments.append(WordSegment(
                        word=word,
                        start_time=Decimal(str(round(raw_start, 3))),
                        end_time=Decimal(str(round(raw_end, 3))),
                        word_confidence=Decimal(str(round(probability, 3))) if probability is not None else None
                    ))

        # Get duration from the last segment
        duration = 0.0
        if result.get("segments"):
            duration = result["segments"][-1].get("end", 0.0)
            if speech_segments:
                from app.transcription.vad import remap_timestamps
                duration = remap_timestamps(duration, speech_segments)

        return TranscriptResult(
            segments=segments,
            full_text=result.get("text", "").strip(),
            language=result.get("language", "en"),
            duration=duration
        )

    def transcribe_with_chunks(
        self,
        audio_path: str,
        chunk_callback: Optional[callable] = None
    ) -> TranscriptResult:
        """
        Transcribe a long audio file, optionally reporting progress.

        Args:
            audio_path: Path to the audio file.
            chunk_callback: Optional callback(segments_so_far, progress_pct) called periodically.

        Returns:
            TranscriptResult with all word segments.
        """
        # For now, use standard transcribe - Whisper handles long files internally
        # Could add chunking logic here for very long files if needed
        return self.transcribe(audio_path)


def get_transcriber(
    model_name: Optional[str] = None,
    initial_prompt: Optional[str] = None,
    vad_filter: bool = False,
) -> WhisperTranscriber:
    """
    Factory function to get a transcriber instance.

    Args:
        model_name: Whisper model name. Defaults to WHISPER_MODEL env var or "large-v3".
        initial_prompt: Optional text to provide context for transcription.
                       Useful for improving accuracy of proper nouns and vocabulary.
        vad_filter: If True, enable Silero VAD pre-filtering before transcription.

    Returns:
        Configured WhisperTranscriber instance.
    """
    model = model_name or os.environ.get("WHISPER_MODEL", "large-v3")
    return WhisperTranscriber(model_name=model, initial_prompt=initial_prompt, vad_filter=vad_filter)
