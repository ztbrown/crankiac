import pytest
from datetime import datetime
from decimal import Decimal

from app.db.models import Episode, TranscriptSegment, SpeakerMapping


@pytest.mark.unit
def test_episode_dataclass_default_values():
    """Test Episode dataclass has correct default values."""
    episode = Episode(
        id=None,
        patreon_id="test-123",
        title="Test Episode"
    )
    assert episode.id is None
    assert episode.patreon_id == "test-123"
    assert episode.title == "Test Episode"
    assert episode.audio_url is None
    assert episode.published_at is None
    assert episode.duration_seconds is None
    assert episode.youtube_url is None
    assert episode.is_free is False
    assert episode.processed is False
    assert episode.created_at is None
    assert episode.updated_at is None


@pytest.mark.unit
def test_episode_with_all_fields():
    """Test Episode dataclass with all fields populated."""
    now = datetime.now()
    episode = Episode(
        id=1,
        patreon_id="test-456",
        title="Full Episode",
        audio_url="https://example.com/audio.mp3",
        published_at=now,
        duration_seconds=3600,
        youtube_url="https://youtube.com/watch?v=abc123",
        is_free=True,
        processed=True,
        created_at=now,
        updated_at=now
    )
    assert episode.id == 1
    assert episode.patreon_id == "test-456"
    assert episode.title == "Full Episode"
    assert episode.audio_url == "https://example.com/audio.mp3"
    assert episode.published_at == now
    assert episode.duration_seconds == 3600
    assert episode.youtube_url == "https://youtube.com/watch?v=abc123"
    assert episode.is_free is True
    assert episode.processed is True
    assert episode.created_at == now
    assert episode.updated_at == now


@pytest.mark.unit
def test_episode_is_free_defaults_to_false():
    """Test that is_free defaults to False for new episodes."""
    episode = Episode(id=None, patreon_id="test", title="Test")
    assert episode.is_free is False


@pytest.mark.unit
def test_episode_youtube_url_and_is_free_independent():
    """Test that youtube_url and is_free can be set independently."""
    # Episode can have youtube_url but not be marked as free
    ep1 = Episode(
        id=None,
        patreon_id="test1",
        title="Test 1",
        youtube_url="https://youtube.com/watch?v=123",
        is_free=False
    )
    assert ep1.youtube_url is not None
    assert ep1.is_free is False

    # Episode can be marked as free without youtube_url
    ep2 = Episode(
        id=None,
        patreon_id="test2",
        title="Test 2",
        youtube_url=None,
        is_free=True
    )
    assert ep2.youtube_url is None
    assert ep2.is_free is True


@pytest.mark.unit
def test_transcript_segment_with_speaker():
    """Test TranscriptSegment includes speaker field."""
    segment = TranscriptSegment(
        id=1,
        episode_id=1,
        word="hello",
        start_time=Decimal("1.234"),
        end_time=Decimal("1.567"),
        segment_index=0,
        speaker="SPEAKER_01"
    )
    assert segment.speaker == "SPEAKER_01"


@pytest.mark.unit
def test_transcript_segment_speaker_defaults_to_none():
    """Test TranscriptSegment speaker defaults to None."""
    segment = TranscriptSegment(
        id=1,
        episode_id=1,
        word="test",
        start_time=Decimal("0.0"),
        end_time=Decimal("0.5"),
        segment_index=0
    )
    assert segment.speaker is None


@pytest.mark.unit
def test_speaker_mapping_dataclass():
    """Test SpeakerMapping dataclass with all fields."""
    now = datetime.now()
    mapping = SpeakerMapping(
        id=1,
        episode_id=1,
        speaker_label="SPEAKER_00",
        speaker_name="Matt",
        created_at=now,
        updated_at=now
    )
    assert mapping.id == 1
    assert mapping.episode_id == 1
    assert mapping.speaker_label == "SPEAKER_00"
    assert mapping.speaker_name == "Matt"
    assert mapping.created_at == now
    assert mapping.updated_at == now


@pytest.mark.unit
def test_speaker_mapping_defaults():
    """Test SpeakerMapping dataclass default values."""
    mapping = SpeakerMapping(
        id=None,
        episode_id=1,
        speaker_label="SPEAKER_01",
        speaker_name="Will"
    )
    assert mapping.id is None
    assert mapping.created_at is None
    assert mapping.updated_at is None
