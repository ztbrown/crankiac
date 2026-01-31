"""Tests for YouTube timestamp URL formatting utilities."""
import pytest
from decimal import Decimal

from app.youtube.timestamp import (
    extract_video_id,
    seconds_to_hms,
    format_timestamp_link,
    format_timestamp_embed,
    format_youtube_url,
)


class TestExtractVideoId:
    """Tests for extract_video_id function."""

    def test_standard_watch_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url_with_timestamp(self):
        url = "https://youtu.be/dQw4w9WgXcQ?t=123"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_embed_url(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_embed_url_with_params(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ?start=60"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_v_url(self):
        url = "https://www.youtube.com/v/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_mobile_url(self):
        url = "https://m.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_empty_string(self):
        assert extract_video_id("") is None

    def test_none(self):
        assert extract_video_id(None) is None

    def test_invalid_url(self):
        assert extract_video_id("not a url") is None

    def test_non_youtube_url(self):
        assert extract_video_id("https://vimeo.com/123456") is None

    def test_youtube_url_without_video_id(self):
        assert extract_video_id("https://www.youtube.com/") is None


class TestSecondsToHms:
    """Tests for seconds_to_hms function."""

    def test_zero_seconds(self):
        assert seconds_to_hms(0) == (0, 0, 0)

    def test_seconds_only(self):
        assert seconds_to_hms(45) == (0, 0, 45)

    def test_minutes_and_seconds(self):
        assert seconds_to_hms(125) == (0, 2, 5)

    def test_hours_minutes_seconds(self):
        assert seconds_to_hms(3723) == (1, 2, 3)

    def test_large_value(self):
        # 10 hours, 30 minutes, 45 seconds
        assert seconds_to_hms(37845) == (10, 30, 45)

    def test_float_truncates(self):
        assert seconds_to_hms(123.9) == (0, 2, 3)

    def test_decimal_input(self):
        assert seconds_to_hms(Decimal("123.456")) == (0, 2, 3)

    def test_negative_becomes_zero(self):
        assert seconds_to_hms(-10) == (0, 0, 0)


class TestFormatTimestampLink:
    """Tests for format_timestamp_link function."""

    def test_zero_seconds(self):
        assert format_timestamp_link(0) == "0s"

    def test_seconds_only(self):
        assert format_timestamp_link(45) == "45s"

    def test_minutes_and_seconds(self):
        assert format_timestamp_link(125) == "2m5s"

    def test_minutes_only(self):
        assert format_timestamp_link(120) == "2m"

    def test_hours_minutes_seconds(self):
        assert format_timestamp_link(3723) == "1h2m3s"

    def test_hours_and_minutes(self):
        assert format_timestamp_link(3720) == "1h2m"

    def test_hours_and_seconds(self):
        assert format_timestamp_link(3603) == "1h3s"

    def test_hours_only(self):
        assert format_timestamp_link(3600) == "1h"

    def test_float_input(self):
        assert format_timestamp_link(123.7) == "2m3s"

    def test_decimal_input(self):
        assert format_timestamp_link(Decimal("3723.5")) == "1h2m3s"

    def test_negative_becomes_zero(self):
        assert format_timestamp_link(-100) == "0s"


class TestFormatTimestampEmbed:
    """Tests for format_timestamp_embed function."""

    def test_zero_seconds(self):
        assert format_timestamp_embed(0) == "0"

    def test_positive_integer(self):
        assert format_timestamp_embed(123) == "123"

    def test_float_truncates(self):
        assert format_timestamp_embed(123.9) == "123"

    def test_decimal_input(self):
        assert format_timestamp_embed(Decimal("456.789")) == "456"

    def test_large_value(self):
        assert format_timestamp_embed(37845) == "37845"

    def test_negative_becomes_zero(self):
        assert format_timestamp_embed(-50) == "0"


class TestFormatYoutubeUrl:
    """Tests for format_youtube_url function."""

    def test_link_format_basic(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = format_youtube_url(url, 123)
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=2m3s"

    def test_link_format_from_short_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        result = format_youtube_url(url, 65)
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1m5s"

    def test_link_format_zero_seconds(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = format_youtube_url(url, 0)
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s"

    def test_link_format_long_timestamp(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = format_youtube_url(url, 7265)  # 2h1m5s
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=2h1m5s"

    def test_embed_format_basic(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = format_youtube_url(url, 123, format_type="embed")
        assert result == "https://www.youtube.com/embed/dQw4w9WgXcQ?start=123&autoplay=1"

    def test_embed_format_from_short_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        result = format_youtube_url(url, 60, format_type="embed")
        assert result == "https://www.youtube.com/embed/dQw4w9WgXcQ?start=60&autoplay=1"

    def test_embed_format_zero_seconds(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = format_youtube_url(url, 0, format_type="embed")
        assert result == "https://www.youtube.com/embed/dQw4w9WgXcQ?start=0&autoplay=1"

    def test_decimal_start_time(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = format_youtube_url(url, Decimal("123.456"))
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=2m3s"

    def test_invalid_url_raises_error(self):
        with pytest.raises(ValueError, match="Could not extract video ID"):
            format_youtube_url("not a url", 123)

    def test_non_youtube_url_raises_error(self):
        with pytest.raises(ValueError, match="Could not extract video ID"):
            format_youtube_url("https://vimeo.com/123456", 60)

    def test_invalid_format_type_raises_error(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        with pytest.raises(ValueError, match="Unknown format_type"):
            format_youtube_url(url, 123, format_type="invalid")

    def test_strips_existing_timestamp_from_short_url(self):
        # When input has a timestamp, we extract just the video ID
        # and build a new clean URL with the new timestamp
        url = "https://youtu.be/dQw4w9WgXcQ?t=999"
        result = format_youtube_url(url, 30)
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s"

    def test_normalizes_embed_url_to_link_format(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ?start=999"
        result = format_youtube_url(url, 45, format_type="link")
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=45s"
