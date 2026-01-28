"""YouTube timestamp URL formatting utilities."""
import re
from decimal import Decimal
from typing import Optional, Union
from urllib.parse import urlparse, parse_qs


def extract_video_id(youtube_url: str) -> Optional[str]:
    """
    Extract video ID from a YouTube URL.

    Supports various YouTube URL formats:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/v/VIDEO_ID

    Args:
        youtube_url: A YouTube URL string.

    Returns:
        The video ID if found, None otherwise.
    """
    if not youtube_url:
        return None

    parsed = urlparse(youtube_url)

    # Handle youtu.be short URLs
    if parsed.netloc in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.lstrip("/").split("/")[0]
        if video_id:
            return video_id
        return None

    # Handle standard youtube.com URLs
    if parsed.netloc in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        # /watch?v=VIDEO_ID
        if parsed.path == "/watch":
            query_params = parse_qs(parsed.query)
            video_ids = query_params.get("v")
            if video_ids:
                return video_ids[0]

        # /embed/VIDEO_ID or /v/VIDEO_ID
        match = re.match(r"^/(embed|v)/([^/?]+)", parsed.path)
        if match:
            return match.group(2)

    return None


def seconds_to_hms(seconds: Union[float, Decimal, int]) -> tuple[int, int, int]:
    """
    Convert seconds to hours, minutes, seconds.

    Args:
        seconds: Time in seconds.

    Returns:
        Tuple of (hours, minutes, seconds) as integers.
    """
    total_seconds = int(float(seconds))
    if total_seconds < 0:
        total_seconds = 0

    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return hours, minutes, secs


def format_timestamp_link(seconds: Union[float, Decimal, int]) -> str:
    """
    Format seconds as YouTube link timestamp parameter (?t=XhYmZs).

    YouTube link format uses hours (h), minutes (m), and seconds (s).
    Components with 0 value are omitted unless all are 0 (then "0s").

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted timestamp string (e.g., "1h2m3s", "5m30s", "45s", "0s").
    """
    hours, mins, secs = seconds_to_hms(seconds)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0:
        parts.append(f"{mins}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return "".join(parts)


def format_timestamp_embed(seconds: Union[float, Decimal, int]) -> str:
    """
    Format seconds as YouTube embed timestamp parameter (?start=X).

    YouTube embed format uses total seconds as an integer.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted timestamp string (integer seconds as string).
    """
    total_seconds = int(float(seconds))
    if total_seconds < 0:
        total_seconds = 0
    return str(total_seconds)


def format_youtube_url(
    youtube_url: str,
    start_time: Union[float, Decimal, int],
    format_type: str = "link",
) -> str:
    """
    Format a YouTube URL with a timestamp.

    Args:
        youtube_url: The YouTube URL (can be watch, embed, or short URL).
        start_time: Start time in seconds.
        format_type: Either "link" for ?t=XhYmZs or "embed" for ?start=X.

    Returns:
        YouTube URL with timestamp parameter added.

    Raises:
        ValueError: If youtube_url is invalid or format_type is unknown.
    """
    video_id = extract_video_id(youtube_url)
    if not video_id:
        raise ValueError(f"Could not extract video ID from URL: {youtube_url}")

    if format_type == "link":
        timestamp = format_timestamp_link(start_time)
        return f"https://www.youtube.com/watch?v={video_id}&t={timestamp}"
    elif format_type == "embed":
        timestamp = format_timestamp_embed(start_time)
        return f"https://www.youtube.com/embed/{video_id}?start={timestamp}"
    else:
        raise ValueError(f"Unknown format_type: {format_type}. Use 'link' or 'embed'.")
