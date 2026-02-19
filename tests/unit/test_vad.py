"""Tests for VAD pre-filtering and timestamp remapping."""
import os
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

from app.transcription.vad import (
    VoiceActivityDetector,
    SpeechSegment,
    remap_timestamps,
)
from app.transcription.whisper_transcriber import (
    WhisperTranscriber,
    get_transcriber,
    TranscriptResult,
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
        # 0.0 in filtered → 10.0 in original
        assert remap_timestamps(0.0, segments) == 10.0
        # 5.0 in filtered → 15.0 in original
        assert remap_timestamps(5.0, segments) == 15.0
        # 10.0 (boundary) → 20.0
        assert remap_timestamps(10.0, segments) == 20.0

    def test_two_segments(self):
        segments = [
            SpeechSegment(start=5.0, end=10.0),   # 5s of speech
            SpeechSegment(start=20.0, end=25.0),  # 5s of speech, 10s silence removed
        ]
        # 0.0 → 5.0 (start of first segment)
        assert remap_timestamps(0.0, segments) == 5.0
        # 3.0 → 8.0 (within first segment)
        assert remap_timestamps(3.0, segments) == 8.0
        # 5.0 (exactly at boundary) — belongs to first segment → 10.0 (end of first)
        assert remap_timestamps(5.0, segments) == 10.0
        # 6.0 (in second segment: offset 1.0) → 21.0
        assert remap_timestamps(6.0, segments) == 21.0
        # 7.5 → 22.5 (within second segment)
        assert remap_timestamps(7.5, segments) == 22.5
        # 10.0 (end of second segment) → 25.0
        assert remap_timestamps(10.0, segments) == 25.0

    def test_beyond_all_segments_clamps_to_last_end(self):
        segments = [
            SpeechSegment(start=0.0, end=5.0),
            SpeechSegment(start=10.0, end=15.0),
        ]
        # 100s beyond all segments → last end
        assert remap_timestamps(100.0, segments) == 15.0

    def test_at_segment_boundary_falls_in_first_segment(self):
        segments = [
            SpeechSegment(start=0.0, end=3.0),
            SpeechSegment(start=6.0, end=9.0),
        ]
        # 3.0 is the boundary (end of first segment duration).
        # With <= semantics: belongs to first segment → maps to 3.0 (end of first)
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
            SpeechSegment(start=1.0, end=3.0),  # 2s
            SpeechSegment(start=5.0, end=7.0),  # 2s
        ]
        # 10s at 16kHz — large enough to cover both segments
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
        # Expect 4s of audio: 2s from seg1 + 2s from seg2 = 4 * 16000 = 64000 samples
        assert saved_tensor.shape[1] == 64000


# ---------------------------------------------------------------------------
# WhisperTranscriber with vad_filter
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWhisperTranscriberVAD:
    """Tests for WhisperTranscriber.vad_filter integration."""

    def test_init_vad_filter_default_false(self):
        t = WhisperTranscriber()
        assert t.vad_filter is False

    def test_init_vad_filter_true(self):
        t = WhisperTranscriber(vad_filter=True)
        assert t.vad_filter is True

    def test_transcribe_no_vad_skips_vad(self, tmp_path):
        """When vad_filter=False, VAD should not be called."""
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"fake audio")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "hello",
            "language": "en",
            "segments": [
                {"start": 0.0, "end": 1.0, "words": [
                    {"word": "hello", "start": 0.0, "end": 1.0}
                ]}
            ],
        }

        with patch("whisper.load_model", return_value=mock_model), \
             patch("app.transcription.vad.VoiceActivityDetector") as mock_vad_cls:
            t = WhisperTranscriber(model_name="base", vad_filter=False)
            result = t.transcribe(str(audio_file))

        mock_vad_cls.assert_not_called()
        assert result.segments[0].start_time == Decimal("0.0")

    def test_transcribe_with_vad_remaps_timestamps(self, tmp_path):
        """When vad_filter=True, timestamps are remapped via speech_segments."""
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"fake audio")
        filtered_file = tmp_path / "filtered.wav"
        filtered_file.write_bytes(b"filtered audio")

        # Whisper sees the filtered file and returns timestamps in filtered time:
        # "hello" at 0.0–0.5, "world" at 0.5–1.0
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "hello world",
            "language": "en",
            "segments": [
                {"start": 0.0, "end": 1.0, "words": [
                    {"word": "hello", "start": 0.0, "end": 0.5},
                    {"word": "world", "start": 0.5, "end": 1.0},
                ]}
            ],
        }

        # VAD found speech from 10.0–11.0 in original (1s segment)
        speech_segs = [SpeechSegment(start=10.0, end=11.0)]

        mock_vad_instance = MagicMock()
        mock_vad_instance.filter_audio.return_value = (str(filtered_file), speech_segs)

        with patch("whisper.load_model", return_value=mock_model), \
             patch("app.transcription.vad.VoiceActivityDetector",
                   return_value=mock_vad_instance), \
             patch("os.unlink"):
            t = WhisperTranscriber(model_name="base", vad_filter=True)
            result = t.transcribe(str(audio_file))

        # "hello": filtered 0.0 → original 10.0
        assert result.segments[0].word == "hello"
        assert result.segments[0].start_time == Decimal("10.0")
        assert result.segments[0].end_time == Decimal("10.5")
        # "world": filtered 0.5 → original 10.5, filtered 1.0 → original 11.0
        assert result.segments[1].word == "world"
        assert result.segments[1].start_time == Decimal("10.5")
        assert result.segments[1].end_time == Decimal("11.0")

    def test_transcribe_vad_cleans_up_temp_file(self, tmp_path):
        """filter_audio temp file is deleted after transcription."""
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"fake audio")
        filtered_file = tmp_path / "filtered.wav"
        filtered_file.write_bytes(b"filtered")

        speech_segs = [SpeechSegment(start=0.0, end=1.0)]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "", "language": "en", "segments": []
        }
        mock_vad = MagicMock()
        mock_vad.filter_audio.return_value = (str(filtered_file), speech_segs)

        with patch("whisper.load_model", return_value=mock_model), \
             patch("app.transcription.vad.VoiceActivityDetector",
                   return_value=mock_vad), \
             patch("os.unlink") as mock_unlink:
            t = WhisperTranscriber(model_name="base", vad_filter=True)
            t.transcribe(str(audio_file))

        mock_unlink.assert_called_once_with(str(filtered_file))

    def test_transcribe_vad_no_speech_uses_original(self, tmp_path):
        """When VAD returns original path (no speech), transcribe proceeds normally."""
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"fake audio")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "hello", "language": "en",
            "segments": [
                {"start": 0.0, "end": 1.0, "words": [
                    {"word": "hello", "start": 0.0, "end": 1.0}
                ]}
            ],
        }
        mock_vad = MagicMock()
        # Returns original path (no filtering done)
        mock_vad.filter_audio.return_value = (str(audio_file), [])

        with patch("whisper.load_model", return_value=mock_model), \
             patch("app.transcription.vad.VoiceActivityDetector",
                   return_value=mock_vad):
            t = WhisperTranscriber(model_name="base", vad_filter=True)
            result = t.transcribe(str(audio_file))

        # No remapping — timestamps come through as-is
        assert result.segments[0].start_time == Decimal("0.0")
        assert result.segments[0].end_time == Decimal("1.0")
        # Whisper was called with the original file (not a filtered path)
        mock_model.transcribe.assert_called_once()
        assert mock_model.transcribe.call_args[0][0] == str(audio_file)


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
        """enable_vad=True should pass vad_filter=True to get_transcriber."""
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
        """enable_vad defaults to False."""
        from app.pipeline import EpisodePipeline

        with patch("app.pipeline.PatreonClient"), \
             patch("app.pipeline.AudioDownloader"), \
             patch("app.pipeline.get_transcriber") as mock_get_transcriber, \
             patch("app.pipeline.TranscriptStorage"), \
             patch("app.pipeline.EpisodeRepository"):
            EpisodePipeline(session_id="test")

        kwargs = mock_get_transcriber.call_args[1]
        assert kwargs.get("vad_filter") is False
