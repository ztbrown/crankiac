"""Tests for VAD pre-filtering, timestamp remapping, and faster-whisper VAD integration."""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.transcription.vad import (
    VoiceActivityDetector,
    SpeechSegment,
    remap_timestamps,
)
from app.transcription.whisper_transcriber import (
    WhisperTranscriber,
    get_transcriber,
    WordSegment,
)


# ---------------------------------------------------------------------------
# remap_timestamps
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRemapTimestamps:
    """Unit tests for the remap_timestamps helper."""

    def test_empty_segments_returns_input(self):
        assert remap_timestamps(5.0, []) == 5.0

    def test_single_segment_offset(self):
        segments = [SpeechSegment(start=10.0, end=20.0)]
        assert remap_timestamps(0.0, segments) == 10.0
        assert remap_timestamps(5.0, segments) == 15.0
        assert remap_timestamps(10.0, segments) == 20.0

    def test_two_segments(self):
        segments = [
            SpeechSegment(start=5.0, end=10.0),
            SpeechSegment(start=20.0, end=25.0),
        ]
        assert remap_timestamps(0.0, segments) == 5.0
        assert remap_timestamps(3.0, segments) == 8.0
        assert remap_timestamps(5.0, segments) == 10.0
        assert remap_timestamps(6.0, segments) == 21.0
        assert remap_timestamps(7.5, segments) == 22.5
        assert remap_timestamps(10.0, segments) == 25.0

    def test_beyond_all_segments_clamps_to_last_end(self):
        segments = [
            SpeechSegment(start=0.0, end=5.0),
            SpeechSegment(start=10.0, end=15.0),
        ]
        assert remap_timestamps(100.0, segments) == 15.0

    def test_at_segment_boundary_falls_in_first_segment(self):
        segments = [
            SpeechSegment(start=0.0, end=3.0),
            SpeechSegment(start=6.0, end=9.0),
        ]
        result = remap_timestamps(3.0, segments)
        assert result == 3.0


# ---------------------------------------------------------------------------
# VoiceActivityDetector
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVoiceActivityDetector:
    """Tests for VoiceActivityDetector without loading real models."""

    def test_init_defaults(self):
        vad = VoiceActivityDetector()
        assert vad.min_speech_duration == 0.25
        assert vad.min_silence_duration == 0.5
        assert vad.speech_pad == 0.1
        assert vad.threshold == 0.5
        assert vad._model is None

    def test_init_custom_params(self):
        vad = VoiceActivityDetector(
            min_speech_duration=0.5,
            min_silence_duration=1.0,
            speech_pad=0.2,
            threshold=0.6,
        )
        assert vad.min_speech_duration == 0.5
        assert vad.min_silence_duration == 1.0
        assert vad.speech_pad == 0.2
        assert vad.threshold == 0.6

    def test_detect_raises_on_missing_file(self):
        vad = VoiceActivityDetector()
        with pytest.raises(FileNotFoundError):
            vad.detect("/nonexistent/file.mp3")

    def test_filter_audio_raises_on_missing_file(self):
        vad = VoiceActivityDetector()
        with pytest.raises(FileNotFoundError):
            vad.filter_audio("/nonexistent/file.mp3")

    def test_detect_calls_silero_correctly(self, tmp_path):
        """detect() should call torch.hub.load with Silero and parse results."""
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio")

        mock_timestamps = [
            {"start": 1.0, "end": 5.0},
            {"start": 7.0, "end": 12.0},
        ]
        mock_wav = MagicMock()
        mock_get_speech = MagicMock(return_value=mock_timestamps)
        mock_read_audio = MagicMock(return_value=mock_wav)
        mock_utils = (mock_get_speech, None, mock_read_audio, None, None)
        mock_model = MagicMock()

        with patch("torch.hub.load", return_value=(mock_model, mock_utils)):
            vad = VoiceActivityDetector(threshold=0.6, speech_pad=0.2)
            segments = vad.detect(str(audio_file))

        assert len(segments) == 2
        assert segments[0] == SpeechSegment(start=1.0, end=5.0)
        assert segments[1] == SpeechSegment(start=7.0, end=12.0)

        mock_get_speech.assert_called_once_with(
            mock_wav,
            mock_model,
            sampling_rate=16000,
            threshold=0.6,
            min_speech_duration_ms=250,
            min_silence_duration_ms=500,
            speech_pad_ms=200,
            return_seconds=True,
        )

    def test_filter_audio_returns_original_path_when_no_speech(self, tmp_path):
        """filter_audio() returns original path when VAD finds no speech."""
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"silence")

        vad = VoiceActivityDetector()
        with patch.object(vad, "detect", return_value=[]):
            result_path, segments = vad.filter_audio(str(audio_file))

        assert result_path == str(audio_file)
        assert segments == []

    def test_filter_audio_writes_speech_only_file(self, tmp_path):
        """filter_audio() concatenates speech chunks and saves to output."""
        import torch
        audio_file = tmp_path / "audio.wav"
        output_file = tmp_path / "filtered.wav"
        audio_file.write_bytes(b"fake audio")

        speech_segs = [
            SpeechSegment(start=1.0, end=3.0),
            SpeechSegment(start=5.0, end=7.0),
        ]
        fake_waveform = torch.zeros(1, 160000)
        sample_rate = 16000

        vad = VoiceActivityDetector()
        with patch.object(vad, "detect", return_value=speech_segs), \
             patch("torchaudio.load", return_value=(fake_waveform, sample_rate)), \
             patch("torchaudio.save") as mock_save:
            result_path, result_segs = vad.filter_audio(
                str(audio_file), output_path=str(output_file)
            )

        assert result_path == str(output_file)
        assert result_segs == speech_segs
        mock_save.assert_called_once()
        saved_path, saved_tensor, saved_sr = mock_save.call_args[0]
        assert saved_path == str(output_file)
        assert saved_sr == sample_rate
        assert saved_tensor.shape[1] == 64000


# ---------------------------------------------------------------------------
# WhisperTranscriber with vad_filter (faster-whisper built-in VAD)
# ---------------------------------------------------------------------------

def _make_word(word, start, end, probability=None):
    w = MagicMock()
    w.word = word
    w.start = start
    w.end = end
    w.probability = probability
    return w


def _make_segment(words):
    seg = MagicMock()
    seg.words = words
    return seg


def _make_info(language="en", duration=1.0):
    info = MagicMock()
    info.language = language
    info.duration = duration
    return info


@pytest.mark.unit
class TestWhisperTranscriberVAD:
    """Tests for WhisperTranscriber.vad_filter integration with faster-whisper."""

    def test_init_vad_filter_default_false(self):
        t = WhisperTranscriber()
        assert t.vad_filter is False

    def test_init_vad_filter_true(self):
        t = WhisperTranscriber(vad_filter=True)
        assert t.vad_filter is True

    def test_transcribe_no_vad_does_not_pass_vad_params(self, tmp_path):
        """When vad_filter=False, vad_filter/vad_parameters should not be in kwargs."""
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"fake audio")

        words = [_make_word("hello", 0.0, 1.0)]
        segment = _make_segment(words)
        info = _make_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([segment]), info)

        with patch("app.transcription.whisper_transcriber.WhisperModel",
                    return_value=mock_model):
            t = WhisperTranscriber(model_name="base", vad_filter=False)
            t.transcribe(str(audio_file))

        call_kwargs = mock_model.transcribe.call_args[1]
        assert "vad_filter" not in call_kwargs
        assert "vad_parameters" not in call_kwargs

    def test_transcribe_with_vad_passes_vad_params(self, tmp_path):
        """When vad_filter=True, vad_filter and vad_parameters are passed to model."""
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"fake audio")

        words = [
            _make_word("hello", 0.0, 0.5),
            _make_word("world", 0.5, 1.0),
        ]
        segment = _make_segment(words)
        info = _make_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([segment]), info)

        with patch("app.transcription.whisper_transcriber.WhisperModel",
                    return_value=mock_model):
            t = WhisperTranscriber(model_name="base", vad_filter=True)
            result = t.transcribe(str(audio_file))

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["vad_filter"] is True
        assert "vad_parameters" in call_kwargs
        vad_params = call_kwargs["vad_parameters"]
        assert vad_params["min_speech_duration_ms"] == 250
        assert vad_params["min_silence_duration_ms"] == 500
        assert vad_params["speech_pad_ms"] == 100
        assert vad_params["threshold"] == 0.5

        # Output still correct
        assert result.segments[0].word == "hello"
        assert result.segments[1].word == "world"

    def test_transcribe_vad_no_external_vad_module(self, tmp_path):
        """vad_filter=True should NOT import or call VoiceActivityDetector."""
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"fake audio")

        info = _make_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), info)

        with patch("app.transcription.whisper_transcriber.WhisperModel",
                    return_value=mock_model), \
             patch("app.transcription.vad.VoiceActivityDetector") as mock_vad_cls:
            t = WhisperTranscriber(model_name="base", vad_filter=True)
            t.transcribe(str(audio_file))

        mock_vad_cls.assert_not_called()


# ---------------------------------------------------------------------------
# get_transcriber factory
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetTranscriberVAD:
    def test_get_transcriber_vad_filter_false_by_default(self):
        t = get_transcriber(model_name="base")
        assert t.vad_filter is False

    def test_get_transcriber_vad_filter_true(self):
        t = get_transcriber(model_name="base", vad_filter=True)
        assert t.vad_filter is True


# ---------------------------------------------------------------------------
# Pipeline enable_vad
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPipelineEnableVAD:
    """Tests for EpisodePipeline enable_vad wiring."""

    def test_pipeline_passes_vad_filter_to_transcriber(self):
        from app.pipeline import EpisodePipeline

        with patch("app.pipeline.PatreonClient"), \
             patch("app.pipeline.AudioDownloader"), \
             patch("app.pipeline.get_transcriber") as mock_get_transcriber, \
             patch("app.pipeline.TranscriptStorage"), \
             patch("app.pipeline.EpisodeRepository"):
            EpisodePipeline(session_id="test", enable_vad=True)

        mock_get_transcriber.assert_called_once()
        kwargs = mock_get_transcriber.call_args[1]
        assert kwargs.get("vad_filter") is True

    def test_pipeline_vad_disabled_by_default(self):
        from app.pipeline import EpisodePipeline

        with patch("app.pipeline.PatreonClient"), \
             patch("app.pipeline.AudioDownloader"), \
             patch("app.pipeline.get_transcriber") as mock_get_transcriber, \
             patch("app.pipeline.TranscriptStorage"), \
             patch("app.pipeline.EpisodeRepository"):
            EpisodePipeline(session_id="test")

        kwargs = mock_get_transcriber.call_args[1]
        assert kwargs.get("vad_filter") is False
