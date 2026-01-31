import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.transcription.whisper_transcriber import (
    WordSegment,
    TranscriptResult,
    WhisperTranscriber,
    get_transcriber,
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
    assert transcriber.model_name == "base"
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


# Tests for vocabulary_hints feature
# These tests mock Whisper and verify our code passes the correct parameters

@pytest.fixture
def mock_transcriber():
    """Create a transcriber with mocked Whisper model."""
    transcriber = WhisperTranscriber()
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {
        "text": "test transcript",
        "language": "en",
        "segments": []
    }
    transcriber._model = mock_model
    return transcriber


@pytest.mark.unit
def test_transcribe_passes_initial_prompt_when_vocabulary_hints_provided(mock_transcriber):
    """Verify our code constructs initial_prompt and passes it to Whisper."""
    with patch("os.path.exists", return_value=True):
        mock_transcriber.transcribe(
            "/tmp/test.mp3",
            vocabulary_hints=["Will Menaker", "Matt Christman", "Felix Biederman"]
        )

    # Verify Whisper was called with correct initial_prompt
    call_kwargs = mock_transcriber._model.transcribe.call_args[1]
    assert "initial_prompt" in call_kwargs
    assert call_kwargs["initial_prompt"] == "Names mentioned: Will Menaker, Matt Christman, Felix Biederman."


@pytest.mark.unit
def test_transcribe_omits_initial_prompt_when_no_vocabulary_hints(mock_transcriber):
    """Verify our code doesn't pass initial_prompt when vocabulary_hints is None."""
    with patch("os.path.exists", return_value=True):
        mock_transcriber.transcribe("/tmp/test.mp3")

    call_kwargs = mock_transcriber._model.transcribe.call_args[1]
    assert "initial_prompt" not in call_kwargs


@pytest.mark.unit
def test_transcribe_omits_initial_prompt_when_vocabulary_hints_empty(mock_transcriber):
    """Verify our code doesn't pass initial_prompt when vocabulary_hints is empty list."""
    with patch("os.path.exists", return_value=True):
        mock_transcriber.transcribe("/tmp/test.mp3", vocabulary_hints=[])

    call_kwargs = mock_transcriber._model.transcribe.call_args[1]
    assert "initial_prompt" not in call_kwargs
