"""Tests for ClipExtractor class."""
import pytest
from unittest.mock import MagicMock, patch
from app.transcription.clip_extractor import ClipExtractor, SpeakerSegment


class TestSpeakerSegment:
    """Tests for SpeakerSegment dataclass."""

    @pytest.mark.unit
    def test_duration_property(self):
        """Test that duration property calculates correctly."""
        segment = SpeakerSegment(
            speaker="SPEAKER_0",
            start_time=10.5,
            end_time=15.3,
            words=["hello", "world"],
            word_count=2,
        )
        assert segment.duration == pytest.approx(4.8)


class TestClipExtractor:
    """Tests for ClipExtractor class."""

    @pytest.mark.unit
    @patch("app.transcription.clip_extractor.AudioDownloader")
    @patch("app.transcription.clip_extractor.EpisodeRepository")
    def test_init_with_session_id(self, mock_repo, mock_downloader):
        """Test ClipExtractor initialization with session_id."""
        extractor = ClipExtractor(session_id="test_session_123")
        assert extractor.session_id == "test_session_123"

    @pytest.mark.unit
    @patch.dict("os.environ", {"PATREON_SESSION_ID": "env_session_456"})
    @patch("app.transcription.clip_extractor.AudioDownloader")
    @patch("app.transcription.clip_extractor.EpisodeRepository")
    def test_init_from_env(self, mock_repo, mock_downloader):
        """Test ClipExtractor initialization from environment."""
        extractor = ClipExtractor()
        assert extractor.session_id == "env_session_456"

    @pytest.mark.unit
    @patch.dict("os.environ", {}, clear=True)
    @patch("app.transcription.clip_extractor.AudioDownloader")
    @patch("app.transcription.clip_extractor.EpisodeRepository")
    def test_init_without_session_id_raises(self, mock_repo, mock_downloader):
        """Test ClipExtractor raises if no session_id available."""
        with pytest.raises(ValueError, match="PATREON_SESSION_ID required"):
            ClipExtractor()

    @pytest.mark.unit
    @patch("app.transcription.clip_extractor.get_cursor")
    @patch("app.transcription.clip_extractor.AudioDownloader")
    @patch("app.transcription.clip_extractor.EpisodeRepository")
    def test_get_speaker_segments_groups_by_speaker(
        self, mock_repo, mock_downloader, mock_cursor
    ):
        """Test that get_speaker_segments groups consecutive words by speaker."""
        # Mock database response
        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__.return_value.fetchall.return_value = [
            {"word": "Hello", "start_time": 0.0, "end_time": 0.5, "speaker": "SPEAKER_0"},
            {"word": "world", "start_time": 0.5, "end_time": 1.0, "speaker": "SPEAKER_0"},
            {"word": "This", "start_time": 1.0, "end_time": 1.5, "speaker": "SPEAKER_0"},
            {"word": "is", "start_time": 1.5, "end_time": 1.7, "speaker": "SPEAKER_0"},
            {"word": "good", "start_time": 1.7, "end_time": 2.0, "speaker": "SPEAKER_0"},
            {"word": "Hi", "start_time": 2.0, "end_time": 2.5, "speaker": "SPEAKER_1"},
            {"word": "there", "start_time": 2.5, "end_time": 3.0, "speaker": "SPEAKER_1"},
            {"word": "my", "start_time": 3.0, "end_time": 3.2, "speaker": "SPEAKER_1"},
            {"word": "friend", "start_time": 3.2, "end_time": 3.6, "speaker": "SPEAKER_1"},
            {"word": "how", "start_time": 3.6, "end_time": 3.8, "speaker": "SPEAKER_1"},
            {"word": "are", "start_time": 3.8, "end_time": 4.0, "speaker": "SPEAKER_1"},
        ]
        mock_cursor.return_value = mock_cursor_ctx

        extractor = ClipExtractor(session_id="test")
        segments = extractor.get_speaker_segments(episode_id=123)

        # Should have 2 segments (one per speaker)
        assert len(segments) == 2

        # First segment: SPEAKER_0
        assert segments[0].speaker == "SPEAKER_0"
        assert segments[0].start_time == 0.0
        assert segments[0].end_time == 2.0
        assert segments[0].word_count == 5

        # Second segment: SPEAKER_1
        assert segments[1].speaker == "SPEAKER_1"
        assert segments[1].start_time == 2.0
        assert segments[1].end_time == 4.0
        assert segments[1].word_count == 6

    @pytest.mark.unit
    @patch("app.transcription.clip_extractor.get_cursor")
    @patch("app.transcription.clip_extractor.AudioDownloader")
    @patch("app.transcription.clip_extractor.EpisodeRepository")
    def test_get_speaker_segments_filters_short_segments(
        self, mock_repo, mock_downloader, mock_cursor
    ):
        """Test that segments too short are filtered out."""
        # Mock database response with a segment that's too short
        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__.return_value.fetchall.return_value = [
            {"word": "Hi", "start_time": 0.0, "end_time": 0.3, "speaker": "SPEAKER_0"},
            {"word": "there", "start_time": 0.3, "end_time": 0.6, "speaker": "SPEAKER_0"},
        ]
        mock_cursor.return_value = mock_cursor_ctx

        extractor = ClipExtractor(
            session_id="test",
            min_duration=2.0,  # Minimum 2 seconds
            min_words=5,  # Minimum 5 words
        )
        segments = extractor.get_speaker_segments(episode_id=123)

        # Should filter out the short segment
        assert len(segments) == 0

    @pytest.mark.unit
    @patch("app.transcription.clip_extractor.subprocess.run")
    @patch("app.transcription.clip_extractor.AudioDownloader")
    @patch("app.transcription.clip_extractor.EpisodeRepository")
    def test_extract_clip_calls_ffmpeg(self, mock_repo, mock_downloader, mock_subprocess):
        """Test that extract_clip calls ffmpeg with correct parameters."""
        mock_subprocess.return_value = MagicMock(returncode=0)

        extractor = ClipExtractor(session_id="test")
        result = extractor.extract_clip(
            audio_path="/path/to/audio.mp3",
            output_path="/path/to/output.wav",
            start_time=10.5,
            end_time=15.3,
        )

        assert result is True
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "ffmpeg"
        assert "-ss" in call_args
        assert "10.5" in call_args
        assert "-t" in call_args
        assert str(15.3 - 10.5) in call_args or "4.8" in call_args
