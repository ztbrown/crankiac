import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.transcription.diarization import (
    SpeakerSegment,
    SpeakerDiarizer,
    assign_speakers_to_words,
    get_diarizer,
)


@pytest.mark.unit
def test_speaker_segment_dataclass():
    """Test SpeakerSegment dataclass creation."""
    segment = SpeakerSegment(
        speaker="SPEAKER_01",
        start_time=Decimal("0.500"),
        end_time=Decimal("5.200")
    )
    assert segment.speaker == "SPEAKER_01"
    assert segment.start_time == Decimal("0.500")
    assert segment.end_time == Decimal("5.200")


@pytest.mark.unit
def test_assign_speakers_to_words_empty():
    """Test assigning speakers to empty word list."""
    result = assign_speakers_to_words([], [])
    assert result == []


@pytest.mark.unit
def test_assign_speakers_to_words_no_speaker_segments():
    """Test word list remains unchanged when no speaker segments."""
    # Create mock word segments with speaker attribute
    word1 = MagicMock()
    word1.start_time = Decimal("0.0")
    word1.end_time = Decimal("0.5")
    word1.speaker = None

    word2 = MagicMock()
    word2.start_time = Decimal("0.5")
    word2.end_time = Decimal("1.0")
    word2.speaker = None

    words = [word1, word2]
    result = assign_speakers_to_words(words, [])

    assert len(result) == 2
    assert result[0].speaker is None
    assert result[1].speaker is None


@pytest.mark.unit
def test_assign_speakers_to_words_assigns_correctly():
    """Test that speakers are correctly assigned based on timestamps."""
    # Create speaker segments
    speaker_segments = [
        SpeakerSegment(speaker="SPEAKER_01", start_time=Decimal("0.0"), end_time=Decimal("2.0")),
        SpeakerSegment(speaker="SPEAKER_02", start_time=Decimal("2.0"), end_time=Decimal("4.0")),
    ]

    # Create mock word segments
    word1 = MagicMock()
    word1.start_time = Decimal("0.2")
    word1.end_time = Decimal("0.5")
    word1.speaker = None

    word2 = MagicMock()
    word2.start_time = Decimal("1.5")
    word2.end_time = Decimal("1.8")
    word2.speaker = None

    word3 = MagicMock()
    word3.start_time = Decimal("2.5")
    word3.end_time = Decimal("3.0")
    word3.speaker = None

    words = [word1, word2, word3]
    result = assign_speakers_to_words(words, speaker_segments)

    assert result[0].speaker == "SPEAKER_01"  # 0.35 midpoint in 0-2 range
    assert result[1].speaker == "SPEAKER_01"  # 1.65 midpoint in 0-2 range
    assert result[2].speaker == "SPEAKER_02"  # 2.75 midpoint in 2-4 range


@pytest.mark.unit
def test_assign_speakers_to_words_handles_gaps():
    """Test that lone gap words (no assigned word neighbors) stay unassigned."""
    speaker_segments = [
        SpeakerSegment(speaker="SPEAKER_01", start_time=Decimal("0.0"), end_time=Decimal("1.0")),
        SpeakerSegment(speaker="SPEAKER_02", start_time=Decimal("3.0"), end_time=Decimal("4.0")),
    ]

    # Single word with no overlap and no assigned word neighbors
    word = MagicMock()
    word.start_time = Decimal("1.5")
    word.end_time = Decimal("2.5")
    word.speaker = None

    result = assign_speakers_to_words([word], speaker_segments)
    assert result[0].speaker is None


@pytest.mark.unit
def test_assign_speakers_to_words_overlap_at_transition():
    """Test overlap-based assignment for words spanning speaker transitions."""
    speaker_segments = [
        SpeakerSegment(speaker="SPEAKER_01", start_time=Decimal("0.0"), end_time=Decimal("2.0")),
        SpeakerSegment(speaker="SPEAKER_02", start_time=Decimal("2.0"), end_time=Decimal("4.0")),
    ]

    # Word mostly in SPEAKER_01 (1.0s overlap vs 0.5s)
    word_a = MagicMock()
    word_a.start_time = Decimal("1.0")
    word_a.end_time = Decimal("2.5")
    word_a.speaker = None

    # Word mostly in SPEAKER_02 (0.5s overlap vs 1.0s)
    word_b = MagicMock()
    word_b.start_time = Decimal("1.5")
    word_b.end_time = Decimal("3.0")
    word_b.speaker = None

    result_a = assign_speakers_to_words([word_a], speaker_segments)
    result_b = assign_speakers_to_words([word_b], speaker_segments)

    assert result_a[0].speaker == "SPEAKER_01"  # 1.0s overlap wins
    assert result_b[0].speaker == "SPEAKER_02"  # 1.0s overlap wins


@pytest.mark.unit
def test_assign_speakers_to_words_bidirectional_gap_fill():
    """Test bidirectional gap-filling picks the temporally closer assigned word."""
    speaker_segments = [
        SpeakerSegment(speaker="SPEAKER_01", start_time=Decimal("0.0"), end_time=Decimal("1.0")),
        SpeakerSegment(speaker="SPEAKER_02", start_time=Decimal("5.0"), end_time=Decimal("6.0")),
    ]

    # w1 assigned to SPEAKER_01 (midpoint 0.5)
    w1 = MagicMock()
    w1.start_time = Decimal("0.2")
    w1.end_time = Decimal("0.8")
    w1.speaker = None

    # w2 gap — midpoint 1.75, closer to SPEAKER_01 word (dist 1.25) than SPEAKER_02 word (dist 3.75)
    w2 = MagicMock()
    w2.start_time = Decimal("1.5")
    w2.end_time = Decimal("2.0")
    w2.speaker = None

    # w3 gap — midpoint 3.5, closer to SPEAKER_02 word (dist 2.0) than SPEAKER_01 word (dist 3.0)
    w3 = MagicMock()
    w3.start_time = Decimal("3.0")
    w3.end_time = Decimal("4.0")
    w3.speaker = None

    # w4 assigned to SPEAKER_02 (midpoint 5.5)
    w4 = MagicMock()
    w4.start_time = Decimal("5.2")
    w4.end_time = Decimal("5.8")
    w4.speaker = None

    result = assign_speakers_to_words([w1, w2, w3, w4], speaker_segments)

    assert result[0].speaker == "SPEAKER_01"
    assert result[1].speaker == "SPEAKER_01"  # closer to w1 (dist 1.25) than w4 (dist 3.75)
    assert result[2].speaker == "SPEAKER_02"  # closer to w4 (dist 2.0) than w1 (dist 3.0)
    assert result[3].speaker == "SPEAKER_02"


@pytest.mark.unit
def test_get_diarizer_factory():
    """Test diarizer factory function."""
    diarizer = get_diarizer(hf_token="test_token", num_speakers=3)
    assert isinstance(diarizer, SpeakerDiarizer)
    assert diarizer.hf_token == "test_token"
    assert diarizer.num_speakers == 3


@pytest.mark.unit
def test_diarizer_init_without_token():
    """Test diarizer initializes without token (will fail on use)."""
    with patch.dict("os.environ", {}, clear=True):
        diarizer = SpeakerDiarizer()
        assert diarizer.hf_token is None
        assert diarizer._pipeline is None


@pytest.mark.unit
def test_diarizer_init_with_env_token():
    """Test diarizer uses HF_TOKEN from environment."""
    with patch.dict("os.environ", {"HF_TOKEN": "env_token"}):
        diarizer = SpeakerDiarizer()
        assert diarizer.hf_token == "env_token"


@pytest.mark.unit
def test_diarizer_get_speaker_at_time():
    """Test getting speaker at a specific timestamp."""
    diarizer = SpeakerDiarizer(hf_token="test")
    segments = [
        SpeakerSegment(speaker="SPEAKER_01", start_time=Decimal("0.0"), end_time=Decimal("2.0")),
        SpeakerSegment(speaker="SPEAKER_02", start_time=Decimal("2.0"), end_time=Decimal("4.0")),
    ]

    assert diarizer.get_speaker_at_time(segments, Decimal("1.0")) == "SPEAKER_01"
    assert diarizer.get_speaker_at_time(segments, Decimal("3.0")) == "SPEAKER_02"
    assert diarizer.get_speaker_at_time(segments, Decimal("5.0")) is None


@pytest.mark.unit
def test_diarizer_diarize_file_not_found():
    """Test diarize raises error for missing file."""
    diarizer = SpeakerDiarizer(hf_token="test")
    with pytest.raises(FileNotFoundError):
        diarizer.diarize("/nonexistent/audio.mp3")
