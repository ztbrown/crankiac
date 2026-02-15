import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from decimal import Decimal

from app.transcription.clip_extractor import (
    ClipExtractor,
    SpeechSegment,
)


@pytest.mark.unit
def test_clip_extractor_init():
    """ClipExtractor initializes with default parameters."""
    extractor = ClipExtractor()
    assert extractor.output_dir == Path("data/reference_audio")
    assert extractor.min_duration == 10.0
    assert extractor.max_duration == 20.0


@pytest.mark.unit
def test_clip_extractor_init_custom_params():
    """ClipExtractor accepts custom parameters."""
    extractor = ClipExtractor(
        output_dir="/tmp/clips",
        min_duration=5.0,
        max_duration=15.0
    )
    assert extractor.output_dir == Path("/tmp/clips")
    assert extractor.min_duration == 5.0
    assert extractor.max_duration == 15.0


@pytest.mark.unit
def test_clip_extractor_rejects_invalid_durations():
    """ClipExtractor validates duration parameters."""
    with pytest.raises(ValueError, match="min_duration.*must be less than"):
        ClipExtractor(min_duration=10.0, max_duration=5.0)

    with pytest.raises(ValueError, match="min_duration must be non-negative"):
        ClipExtractor(min_duration=-1.0)


@pytest.mark.unit
def test_sanitize_speaker_name():
    """Speaker names are sanitized for file paths."""
    # Test problematic characters
    assert ClipExtractor._sanitize_speaker_name("Matt") == "Matt"
    assert ClipExtractor._sanitize_speaker_name("Matt/Chris") == "Matt_Chris"
    assert ClipExtractor._sanitize_speaker_name("Speaker<01>") == "Speaker_01_"
    assert ClipExtractor._sanitize_speaker_name('Test"Name') == 'Test_Name'
    assert ClipExtractor._sanitize_speaker_name("Test:Name") == "Test_Name"

    # Test whitespace and dots
    assert ClipExtractor._sanitize_speaker_name("  Matt  ") == "Matt"
    assert ClipExtractor._sanitize_speaker_name("Matt.") == "Matt"
    assert ClipExtractor._sanitize_speaker_name("..") == "unknown_speaker"
    assert ClipExtractor._sanitize_speaker_name("") == "unknown_speaker"


@pytest.mark.unit
def test_group_into_segments():
    """Word data is grouped into continuous speech segments."""
    extractor = ClipExtractor(min_duration=2.0, max_duration=5.0)

    word_data = [
        ("Speaker1", Decimal("0.0"), Decimal("0.5")),
        ("Speaker1", Decimal("0.6"), Decimal("1.1")),
        ("Speaker1", Decimal("1.2"), Decimal("1.7")),
        ("Speaker1", Decimal("2.0"), Decimal("2.5")),  # 0.3s gap - should continue
        ("Speaker2", Decimal("3.0"), Decimal("3.5")),  # Different speaker - new segment
        ("Speaker2", Decimal("4.0"), Decimal("4.5")),
        ("Speaker2", Decimal("4.6"), Decimal("5.5")),  # Extended to meet min_duration
    ]

    segments = extractor._group_into_segments(word_data, max_gap=0.5)

    # Should create 2 segments (one per speaker)
    assert len(segments) == 2

    # First segment: Speaker1 from 0.0 to 2.5
    seg1 = segments[0]
    assert seg1.speaker == "Speaker1"
    assert seg1.start_time == 0.0
    assert seg1.end_time == 2.5
    assert seg1.duration == 2.5
    assert seg1.word_count == 4

    # Second segment: Speaker2 from 3.0 to 5.5
    seg2 = segments[1]
    assert seg2.speaker == "Speaker2"
    assert seg2.start_time == 3.0
    assert seg2.end_time == 5.5
    assert seg2.duration == 2.5
    assert seg2.word_count == 3


@pytest.mark.unit
def test_group_into_segments_filters_by_duration():
    """Segments outside duration range are filtered."""
    extractor = ClipExtractor(min_duration=3.0, max_duration=8.0)

    word_data = [
        # Too short (2s)
        ("Speaker1", Decimal("0.0"), Decimal("0.5")),
        ("Speaker1", Decimal("0.6"), Decimal("1.1")),
        ("Speaker1", Decimal("1.2"), Decimal("2.0")),
        # Gap too large - new segment
        # Valid (4s)
        ("Speaker1", Decimal("5.0"), Decimal("5.5")),
        ("Speaker1", Decimal("5.6"), Decimal("6.1")),
        ("Speaker1", Decimal("6.2"), Decimal("7.5")),
        ("Speaker1", Decimal("7.6"), Decimal("9.0")),
    ]

    segments = extractor._group_into_segments(word_data, max_gap=0.5)

    # Only the second segment should be returned (4s duration)
    assert len(segments) == 1
    assert segments[0].start_time == 5.0
    assert segments[0].end_time == 9.0
    assert segments[0].duration == 4.0


@pytest.mark.unit
def test_extract_clips_no_segments(tmp_path):
    """extract_clips handles episodes with no speaker-labeled segments."""
    extractor = ClipExtractor(output_dir=str(tmp_path))

    with patch("app.db.connection.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_ctx
        mock_ctx.fetchall.return_value = []  # No segments

        result = extractor.extract_clips(
            episode_id=123,
            audio_path="/fake/path.mp3",
        )

        assert result == {}


@pytest.mark.unit
def test_speech_segment_duration_property():
    """SpeechSegment calculates duration correctly."""
    segment = SpeechSegment(
        speaker="Matt",
        start_time=10.5,
        end_time=15.3,
        word_count=12
    )
    assert segment.duration == pytest.approx(4.8)
