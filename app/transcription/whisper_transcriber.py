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

@dataclass
class TranscriptResult:
    segments: list[WordSegment]
    full_text: str
    language: str
    duration: float

class WhisperTranscriber:
    """Transcribes audio files using OpenAI Whisper with word-level timestamps."""

    def __init__(self, model_name: str = "base"):
        """
        Initialize the transcriber.

        Args:
            model_name: Whisper model size. Options: tiny, base, small, medium, large.
                       Larger models are more accurate but slower.
        """
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        """Lazy load the model."""
        if self._model is None:
            self._model = whisper.load_model(self.model_name)
        return self._model

    def transcribe(self, audio_path: str) -> TranscriptResult:
        """
        Transcribe an audio file with word-level timestamps.

        Args:
            audio_path: Path to the audio file.

        Returns:
            TranscriptResult with word segments and metadata.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Transcribe with word timestamps
        result = self.model.transcribe(
            audio_path,
            word_timestamps=True,
            verbose=False
        )

        segments = []
        segment_index = 0

        for segment in result.get("segments", []):
            for word_info in segment.get("words", []):
                word = word_info.get("word", "").strip()
                if word:
                    segments.append(WordSegment(
                        word=word,
                        start_time=Decimal(str(round(word_info["start"], 3))),
                        end_time=Decimal(str(round(word_info["end"], 3)))
                    ))
                    segment_index += 1

        # Get duration from the last segment
        duration = 0.0
        if result.get("segments"):
            duration = result["segments"][-1].get("end", 0.0)

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


def get_transcriber(model_name: Optional[str] = None) -> WhisperTranscriber:
    """
    Factory function to get a transcriber instance.

    Args:
        model_name: Whisper model name. Defaults to WHISPER_MODEL env var or "base".

    Returns:
        Configured WhisperTranscriber instance.
    """
    model = model_name or os.environ.get("WHISPER_MODEL", "base")
    return WhisperTranscriber(model_name=model)
