import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from faster_whisper import WhisperModel

_logger = logging.getLogger(__name__)

@dataclass
class WordSegment:
    word: str
    start_time: Decimal
    end_time: Decimal
    speaker: Optional[str] = None
    speaker_confidence: Optional[Decimal] = None
    word_confidence: Optional[Decimal] = None

@dataclass
class TranscriptResult:
    segments: list[WordSegment]
    full_text: str
    language: str
    duration: float

class WhisperTranscriber:
    """Transcribes audio files using faster-whisper with word-level timestamps."""

    def __init__(
        self,
        model_name: str = "large-v3",
        initial_prompt: str = None,
        vad_filter: bool = False,
    ):
        self.model_name = model_name
        self.initial_prompt = initial_prompt
        self.vad_filter = vad_filter
        self._model = None

    @property
    def model(self):
        """Lazy load the model with optimal device/compute settings."""
        if self._model is None:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
            else:
                device = "cpu"
                compute_type = "int8"
            compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", compute_type)
            self._model = WhisperModel(
                self.model_name,
                device=device,
                compute_type=compute_type,
            )
        return self._model

    def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe an audio file with word-level timestamps."""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        kwargs = dict(
            language="en",
            condition_on_previous_text=False,
            initial_prompt=self.initial_prompt,
            word_timestamps=True,
            beam_size=5,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
        )

        if self.vad_filter:
            kwargs["vad_filter"] = True
            kwargs["vad_parameters"] = dict(
                min_speech_duration_ms=250,
                min_silence_duration_ms=500,
                speech_pad_ms=100,
                threshold=0.5,
            )

        segments_gen, info = self.model.transcribe(audio_path, **kwargs)

        segments = []
        words_list = []

        for segment in segments_gen:
            if segment.words:
                for w in segment.words:
                    word = w.word.strip()
                    if word:
                        words_list.append(word)
                        segments.append(WordSegment(
                            word=word,
                            start_time=Decimal(str(round(w.start, 3))),
                            end_time=Decimal(str(round(w.end, 3))),
                            word_confidence=Decimal(str(round(w.probability, 3))) if w.probability is not None else None,
                        ))

        full_text = " ".join(words_list)

        return TranscriptResult(
            segments=segments,
            full_text=full_text,
            language=info.language,
            duration=info.duration,
        )

    def transcribe_with_chunks(
        self,
        audio_path: str,
        chunk_callback: Optional[callable] = None
    ) -> TranscriptResult:
        """Transcribe a long audio file, optionally reporting progress."""
        return self.transcribe(audio_path)


def get_transcriber(
    model_name: Optional[str] = None,
    initial_prompt: Optional[str] = None,
    vad_filter: bool = False,
) -> WhisperTranscriber:
    """Factory function to get a transcriber instance."""
    model = model_name or os.environ.get("WHISPER_MODEL", "large-v3")
    return WhisperTranscriber(model_name=model, initial_prompt=initial_prompt, vad_filter=vad_filter)
