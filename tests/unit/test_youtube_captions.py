"""Tests for YouTube captions fetching and storage."""
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from app.youtube.captions import (
    CaptionSegment,
    CaptionResult,
    CaptionFetchError,
    YouTubeCaptionClient,
    fetch_captions_for_video,
    captions_to_word_segments,
)


class TestCaptionSegment:
    def test_end_time_calculation(self):
        segment = CaptionSegment(
            text="Hello world",
            start_time=Decimal("10.5"),
            duration=Decimal("2.5"),
        )
        assert segment.end_time == Decimal("13.0")

    def test_zero_duration(self):
        segment = CaptionSegment(
            text="Quick",
            start_time=Decimal("5.0"),
            duration=Decimal("0"),
        )
        assert segment.end_time == Decimal("5.0")


class TestCaptionResult:
    def test_creates_with_all_fields(self):
        segments = [
            CaptionSegment(
                text="Test caption",
                start_time=Decimal("0"),
                duration=Decimal("5"),
            )
        ]
        result = CaptionResult(
            video_id="abc123",
            segments=segments,
            language="en",
            is_auto_generated=True,
            source="youtube_captions",
        )
        assert result.video_id == "abc123"
        assert len(result.segments) == 1
        assert result.language == "en"
        assert result.is_auto_generated is True
        assert result.source == "youtube_captions"


class TestCaptionsToWordSegments:
    def test_splits_text_into_words(self):
        result = CaptionResult(
            video_id="test",
            segments=[
                CaptionSegment(
                    text="Hello world",
                    start_time=Decimal("0"),
                    duration=Decimal("2"),
                )
            ],
            language="en",
            is_auto_generated=True,
            source="youtube_captions",
        )

        word_segments = captions_to_word_segments(result)

        assert len(word_segments) == 2
        assert word_segments[0]['word'] == "Hello"
        assert word_segments[1]['word'] == "world"

    def test_distributes_time_evenly(self):
        result = CaptionResult(
            video_id="test",
            segments=[
                CaptionSegment(
                    text="one two three four",
                    start_time=Decimal("0"),
                    duration=Decimal("4"),
                )
            ],
            language="en",
            is_auto_generated=True,
            source="youtube_captions",
        )

        word_segments = captions_to_word_segments(result)

        assert len(word_segments) == 4
        # Each word should get 1 second (4 seconds / 4 words)
        assert word_segments[0]['start_time'] == Decimal("0")
        assert word_segments[0]['end_time'] == Decimal("1")
        assert word_segments[1]['start_time'] == Decimal("1")
        assert word_segments[1]['end_time'] == Decimal("2")
        assert word_segments[2]['start_time'] == Decimal("2")
        assert word_segments[2]['end_time'] == Decimal("3")
        assert word_segments[3]['start_time'] == Decimal("3")
        assert word_segments[3]['end_time'] == Decimal("4")

    def test_increments_segment_index(self):
        result = CaptionResult(
            video_id="test",
            segments=[
                CaptionSegment(
                    text="first second",
                    start_time=Decimal("0"),
                    duration=Decimal("2"),
                ),
                CaptionSegment(
                    text="third fourth",
                    start_time=Decimal("2"),
                    duration=Decimal("2"),
                ),
            ],
            language="en",
            is_auto_generated=True,
            source="youtube_captions",
        )

        word_segments = captions_to_word_segments(result)

        assert len(word_segments) == 4
        assert word_segments[0]['segment_index'] == 0
        assert word_segments[1]['segment_index'] == 1
        assert word_segments[2]['segment_index'] == 2
        assert word_segments[3]['segment_index'] == 3

    def test_handles_empty_segments(self):
        result = CaptionResult(
            video_id="test",
            segments=[
                CaptionSegment(
                    text="",
                    start_time=Decimal("0"),
                    duration=Decimal("1"),
                ),
                CaptionSegment(
                    text="word",
                    start_time=Decimal("1"),
                    duration=Decimal("1"),
                ),
            ],
            language="en",
            is_auto_generated=True,
            source="youtube_captions",
        )

        word_segments = captions_to_word_segments(result)

        assert len(word_segments) == 1
        assert word_segments[0]['word'] == "word"

    def test_preserves_punctuation_in_words(self):
        result = CaptionResult(
            video_id="test",
            segments=[
                CaptionSegment(
                    text="Hello, world!",
                    start_time=Decimal("0"),
                    duration=Decimal("2"),
                )
            ],
            language="en",
            is_auto_generated=True,
            source="youtube_captions",
        )

        word_segments = captions_to_word_segments(result)

        # Punctuation is preserved as part of words
        assert len(word_segments) == 2
        assert word_segments[0]['word'] == "Hello,"
        assert word_segments[1]['word'] == "world!"


class TestYouTubeCaptionClient:
    @patch('app.youtube.captions.YouTubeTranscriptApi')
    def test_fetch_captions_success(self, mock_api):
        # Mock the transcript list
        mock_transcript = Mock()
        mock_transcript.language_code = "en"
        mock_transcript.fetch.return_value = [
            {'text': 'Hello world', 'start': 0.0, 'duration': 2.0},
            {'text': 'How are you', 'start': 2.0, 'duration': 1.5},
        ]

        mock_transcript_list = Mock()
        mock_transcript_list.find_generated_transcript.return_value = mock_transcript
        mock_api.list_transcripts.return_value = mock_transcript_list

        client = YouTubeCaptionClient()
        result = client.fetch_captions(
            "https://www.youtube.com/watch?v=abc123",
            fallback_to_whisper=False,
        )

        assert result is not None
        assert result.video_id == "abc123"
        assert len(result.segments) == 2
        assert result.segments[0].text == "Hello world"
        assert result.segments[0].start_time == Decimal("0.0")
        assert result.is_auto_generated is True
        assert result.source == "youtube_captions"

    @patch('app.youtube.captions.YouTubeTranscriptApi')
    def test_fetch_captions_falls_back_to_manual(self, mock_api):
        from youtube_transcript_api import NoTranscriptFound

        # Mock to fail on auto-generated, succeed on manual
        mock_manual_transcript = Mock()
        mock_manual_transcript.language_code = "en"
        mock_manual_transcript.fetch.return_value = [
            {'text': 'Manual caption', 'start': 0.0, 'duration': 2.0},
        ]

        mock_transcript_list = Mock()
        mock_transcript_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "abc123", ["en"], None
        )
        mock_transcript_list.find_manually_created_transcript.return_value = mock_manual_transcript
        mock_api.list_transcripts.return_value = mock_transcript_list

        client = YouTubeCaptionClient()
        result = client.fetch_captions(
            "https://www.youtube.com/watch?v=abc123",
            fallback_to_whisper=False,
        )

        assert result is not None
        assert result.is_auto_generated is False

    @patch('app.youtube.captions.YouTubeTranscriptApi')
    def test_fetch_captions_returns_none_when_disabled(self, mock_api):
        from youtube_transcript_api import TranscriptsDisabled

        mock_api.list_transcripts.side_effect = TranscriptsDisabled("abc123")

        client = YouTubeCaptionClient()
        result = client.fetch_captions(
            "https://www.youtube.com/watch?v=abc123",
            fallback_to_whisper=False,
        )

        assert result is None

    @patch('app.youtube.captions.YouTubeTranscriptApi')
    def test_fetch_captions_raises_for_unavailable_video(self, mock_api):
        from youtube_transcript_api import VideoUnavailable

        mock_api.list_transcripts.side_effect = VideoUnavailable("abc123")

        client = YouTubeCaptionClient()

        with pytest.raises(CaptionFetchError) as exc_info:
            client.fetch_captions(
                "https://www.youtube.com/watch?v=abc123",
                fallback_to_whisper=False,
            )

        assert "unavailable" in str(exc_info.value).lower()

    def test_extract_video_id_from_various_urls(self):
        client = YouTubeCaptionClient()

        # Standard watch URL
        with patch.object(client, '_fetch_youtube_captions', return_value=None):
            try:
                client.fetch_captions(
                    "https://www.youtube.com/watch?v=abc123",
                    fallback_to_whisper=False,
                )
            except Exception:
                pass

        # Verify video ID extraction happens correctly
        from app.youtube.timestamp import extract_video_id

        assert extract_video_id("https://www.youtube.com/watch?v=abc123") == "abc123"
        assert extract_video_id("https://youtu.be/abc123") == "abc123"
        assert extract_video_id("https://www.youtube.com/embed/abc123") == "abc123"

    def test_invalid_url_raises_error(self):
        client = YouTubeCaptionClient()

        with pytest.raises(CaptionFetchError) as exc_info:
            client.fetch_captions(
                "not-a-valid-url",
                fallback_to_whisper=False,
            )

        assert "Could not extract video ID" in str(exc_info.value)


class TestFetchCaptionsForVideo:
    @patch('app.youtube.captions.YouTubeCaptionClient')
    def test_convenience_function_creates_client(self, mock_client_class):
        mock_client = Mock()
        mock_client.fetch_captions.return_value = None
        mock_client_class.return_value = mock_client

        fetch_captions_for_video(
            "https://www.youtube.com/watch?v=abc123",
            fallback_to_whisper=False,
            whisper_model="tiny",
        )

        mock_client_class.assert_called_once_with(whisper_model="tiny")
        mock_client.fetch_captions.assert_called_once()


class TestYoutubeCaptionsCommand:
    """Tests for the youtube-captions CLI command."""

    def test_captions_command_is_registered(self):
        """Verify youtube-captions command is available in manage.py."""
        import subprocess
        import os

        result = subprocess.run(
            ["python3", "manage.py", "--help"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )

        assert "youtube-captions" in result.stdout
        assert result.returncode == 0

    def test_captions_command_has_expected_options(self):
        """Verify command has --episode-id, --limit, --force, --no-fallback options."""
        import subprocess
        import os

        result = subprocess.run(
            ["python3", "manage.py", "youtube-captions", "--help"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )

        assert "--episode-id" in result.stdout
        assert "--limit" in result.stdout
        assert "--force" in result.stdout
        assert "--no-fallback" in result.stdout
        assert "--model" in result.stdout
        assert result.returncode == 0
