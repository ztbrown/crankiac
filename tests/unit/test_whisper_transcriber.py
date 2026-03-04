"""Tests for WhisperTranscriber (faster-whisper backend)."""
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from app.transcription.whisper_transcriber import (
    WhisperTranscriber,
    get_transcriber,
    TranscriptResult,
    WordSegment,
)


@pytest.mark.unit
def test_word_segment_dataclass():
    """Test WordSegment dataclass creation."""
    segment = WordSegment(
        word="hello",
        start_time=Decimal("0.500"),
        end_time=Decimal("1.200")
    )
    assert segment.word == "hello"
    assert segment.start_time == Decimal("0.500")
    assert segment.end_time == Decimal("1.200")
    assert segment.speaker is None


@pytest.mark.unit
def test_transcript_result_dataclass():
    """Test TranscriptResult dataclass creation."""
    segments = [
        WordSegment(word="hello", start_time=Decimal("0.0"), end_time=Decimal("0.5")),
        WordSegment(word="world", start_time=Decimal("0.5"), end_time=Decimal("1.0")),
    ]
    result = TranscriptResult(
        segments=segments,
        full_text="hello world",
        language="en",
        duration=1.0
    )
    assert len(result.segments) == 2
    assert result.full_text == "hello world"
    assert result.language == "en"
    assert result.duration == 1.0


@pytest.mark.unit
def test_transcriber_init_default_model():
    """Test transcriber initializes with default model."""
    transcriber = WhisperTranscriber()
    assert transcriber.model_name == "large-v3"
    assert transcriber._model is None


@pytest.mark.unit
def test_transcriber_init_custom_model():
    """Test transcriber initializes with custom model."""
    transcriber = WhisperTranscriber(model_name="large")
    assert transcriber.model_name == "large"


@pytest.mark.unit
def test_transcribe_file_not_found():
    """Test transcribe raises error for missing file."""
    transcriber = WhisperTranscriber()
    with pytest.raises(FileNotFoundError):
        transcriber.transcribe("/nonexistent/audio.mp3")


@pytest.mark.unit
def test_get_transcriber_factory():
    """Test transcriber factory function."""
    transcriber = get_transcriber(model_name="small")
    assert isinstance(transcriber, WhisperTranscriber)
    assert transcriber.model_name == "small"


@pytest.mark.unit
def test_get_transcriber_uses_env_var():
    """Test factory uses WHISPER_MODEL env var."""
    with patch.dict("os.environ", {"WHISPER_MODEL": "medium"}):
        transcriber = get_transcriber()
        assert transcriber.model_name == "medium"


# --- Mock helpers for faster-whisper return types ---

def _make_word(word, start, end, probability=None):
    """Create a mock word object with attributes (faster-whisper style)."""
    w = MagicMock()
    w.word = word
    w.start = start
    w.end = end
    w.probability = probability
    return w


def _make_segment(words):
    """Create a mock segment object containing word objects."""
    seg = MagicMock()
    seg.words = words
    return seg


def _make_info(language="en", duration=1.0):
    """Create a mock TranscriptionInfo object."""
    info = MagicMock()
    info.language = language
    info.duration = duration
    return info


@pytest.fixture
def mock_faster_whisper_model():
    """Create a mock faster-whisper model."""
    mock_model = MagicMock()
    words = [
        _make_word("Hello", 0.0, 0.5),
        _make_word("world", 0.5, 1.0),
    ]
    segment = _make_segment(words)
    info = _make_info(language="en", duration=1.0)
    mock_model.transcribe.return_value = (iter([segment]), info)
    return mock_model


@pytest.fixture
def temp_audio_file(tmp_path):
    """Create a temporary audio file for testing."""
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"fake audio content")
    return str(audio_file)


@pytest.mark.unit
class TestWhisperTranscriberInitialPrompt:
    """Tests for initial_prompt parameter handling at instance level."""

    def test_init_accepts_initial_prompt(self):
        transcriber = WhisperTranscriber(
            model_name="base",
            initial_prompt="Dan Carlin, Hardcore History"
        )
        assert transcriber.initial_prompt == "Dan Carlin, Hardcore History"

    def test_init_default_initial_prompt_is_none(self):
        transcriber = WhisperTranscriber(model_name="base")
        assert transcriber.initial_prompt is None

    def test_transcribe_passes_initial_prompt_to_model(
        self, mock_faster_whisper_model, temp_audio_file
    ):
        with patch("app.transcription.whisper_transcriber.WhisperModel",
                    return_value=mock_faster_whisper_model):
            transcriber = WhisperTranscriber(
                model_name="base",
                initial_prompt="Ben Franklin, Thomas Jefferson"
            )
            transcriber.transcribe(temp_audio_file)

            mock_faster_whisper_model.transcribe.assert_called_once_with(
                temp_audio_file,
                language="en",
                condition_on_previous_text=False,
                initial_prompt="Ben Franklin, Thomas Jefferson",
                word_timestamps=True,
                beam_size=5,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3,
            )

    def test_transcribe_passes_none_initial_prompt_when_not_set(
        self, mock_faster_whisper_model, temp_audio_file
    ):
        with patch("app.transcription.whisper_transcriber.WhisperModel",
                    return_value=mock_faster_whisper_model):
            transcriber = WhisperTranscriber(model_name="base")
            transcriber.transcribe(temp_audio_file)

            mock_faster_whisper_model.transcribe.assert_called_once_with(
                temp_audio_file,
                language="en",
                condition_on_previous_text=False,
                initial_prompt=None,
                word_timestamps=True,
                beam_size=5,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3,
            )


@pytest.mark.unit
class TestTranscribeOutput:
    """Tests for transcribe() output construction."""

    def test_transcribe_builds_full_text_from_words(
        self, mock_faster_whisper_model, temp_audio_file
    ):
        with patch("app.transcription.whisper_transcriber.WhisperModel",
                    return_value=mock_faster_whisper_model):
            transcriber = WhisperTranscriber(model_name="base")
            result = transcriber.transcribe(temp_audio_file)

        assert result.full_text == "Hello world"
        assert len(result.segments) == 2
        assert result.segments[0].word == "Hello"
        assert result.segments[1].word == "world"

    def test_transcribe_reads_duration_from_info(self, temp_audio_file):
        mock_model = MagicMock()
        info = _make_info(language="en", duration=123.45)
        mock_model.transcribe.return_value = (iter([]), info)

        with patch("app.transcription.whisper_transcriber.WhisperModel",
                    return_value=mock_model):
            transcriber = WhisperTranscriber(model_name="base")
            result = transcriber.transcribe(temp_audio_file)

        assert result.duration == 123.45
        assert result.language == "en"
        assert result.full_text == ""
        assert result.segments == []

    def test_transcribe_extracts_word_confidence(self, temp_audio_file):
        words = [_make_word("test", 0.0, 0.5, probability=0.95)]
        segment = _make_segment(words)
        info = _make_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([segment]), info)

        with patch("app.transcription.whisper_transcriber.WhisperModel",
                    return_value=mock_model):
            transcriber = WhisperTranscriber(model_name="base")
            result = transcriber.transcribe(temp_audio_file)

        assert result.segments[0].word_confidence == Decimal("0.95")


@pytest.mark.unit
class TestGetTranscriberWithInitialPrompt:
    """Tests for get_transcriber factory function with initial_prompt."""

    def test_get_transcriber_accepts_initial_prompt(self):
        transcriber = get_transcriber(
            model_name="small",
            initial_prompt="Proper nouns: Marcus Aurelius, Seneca"
        )
        assert transcriber.initial_prompt == "Proper nouns: Marcus Aurelius, Seneca"
        assert transcriber.model_name == "small"

    def test_get_transcriber_default_initial_prompt_is_none(self):
        transcriber = get_transcriber(model_name="base")
        assert transcriber.initial_prompt is None

    def test_get_transcriber_with_env_model_and_initial_prompt(self):
        with patch.dict("os.environ", {"WHISPER_MODEL": "medium"}):
            transcriber = get_transcriber(
                initial_prompt="Test vocabulary"
            )
            assert transcriber.model_name == "medium"
            assert transcriber.initial_prompt == "Test vocabulary"
