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

@pytest.mark.unit
def test_transcribe_accepts_vocabulary_hints():
    """Test that transcribe accepts vocabulary_hints parameter."""
    transcriber = WhisperTranscriber()

    with patch.object(transcriber, '_model') as mock_model:
        mock_model.transcribe.return_value = {
            "text": "Will Menaker said hello",
            "language": "en",
            "segments": []
        }
        # Force model to be "loaded"
        transcriber._model = mock_model

        with patch("os.path.exists", return_value=True):
            # Should not raise - vocabulary_hints is accepted
            result = transcriber.transcribe(
                "/tmp/test.mp3",
                vocabulary_hints=["Will Menaker", "Matt Christman"]
            )
            assert result.full_text == "Will Menaker said hello"


@pytest.mark.unit
def test_transcribe_builds_initial_prompt_from_vocabulary():
    """Test that vocabulary_hints builds proper initial_prompt."""
    transcriber = WhisperTranscriber()

    with patch.object(transcriber, '_model') as mock_model:
        mock_model.transcribe.return_value = {
            "text": "test",
            "language": "en",
            "segments": []
        }
        transcriber._model = mock_model

        with patch("os.path.exists", return_value=True):
            transcriber.transcribe(
                "/tmp/test.mp3",
                vocabulary_hints=["Will Menaker", "Matt Christman", "Felix Biederman"]
            )

        # Verify initial_prompt was passed to model.transcribe
        call_kwargs = mock_model.transcribe.call_args[1]
        assert "initial_prompt" in call_kwargs
        assert "Will Menaker" in call_kwargs["initial_prompt"]
        assert "Matt Christman" in call_kwargs["initial_prompt"]
        assert "Felix Biederman" in call_kwargs["initial_prompt"]


@pytest.mark.unit
def test_transcribe_initial_prompt_format():
    """Test that initial_prompt has expected format with 'Names mentioned:' prefix."""
    transcriber = WhisperTranscriber()

    with patch.object(transcriber, '_model') as mock_model:
        mock_model.transcribe.return_value = {
            "text": "test",
            "language": "en",
            "segments": []
        }
        transcriber._model = mock_model

        with patch("os.path.exists", return_value=True):
            transcriber.transcribe(
                "/tmp/test.mp3",
                vocabulary_hints=["Will Menaker", "Matt Christman"]
            )

        call_kwargs = mock_model.transcribe.call_args[1]
        initial_prompt = call_kwargs["initial_prompt"]
        assert initial_prompt.startswith("Names mentioned:")
        assert "Will Menaker" in initial_prompt
        assert "Matt Christman" in initial_prompt


@pytest.mark.unit
def test_transcribe_no_vocabulary_hints_no_initial_prompt():
    """Test that no initial_prompt is passed when vocabulary_hints is None."""
    transcriber = WhisperTranscriber()

    with patch.object(transcriber, '_model') as mock_model:
        mock_model.transcribe.return_value = {
            "text": "test",
            "language": "en",
            "segments": []
        }
        transcriber._model = mock_model

        with patch("os.path.exists", return_value=True):
            transcriber.transcribe("/tmp/test.mp3")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert "initial_prompt" not in call_kwargs


@pytest.mark.unit
def test_transcribe_empty_vocabulary_hints_no_initial_prompt():
    """Test that no initial_prompt is passed when vocabulary_hints is empty."""
    transcriber = WhisperTranscriber()

    with patch.object(transcriber, '_model') as mock_model:
        mock_model.transcribe.return_value = {
            "text": "test",
            "language": "en",
            "segments": []
        }
        transcriber._model = mock_model

        with patch("os.path.exists", return_value=True):
            transcriber.transcribe("/tmp/test.mp3", vocabulary_hints=[])

        call_kwargs = mock_model.transcribe.call_args[1]
        assert "initial_prompt" not in call_kwargs
