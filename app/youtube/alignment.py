"""YouTube/Patreon audio alignment utilities."""
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from statistics import median

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

from ..db.connection import get_cursor
from .timestamp import extract_video_id


@dataclass
class AnchorPoint:
    """A single alignment anchor point between Patreon and YouTube timestamps."""
    patreon_time: Decimal
    youtube_time: Decimal
    confidence: Optional[Decimal] = None
    matched_text: Optional[str] = None


@dataclass
class AlignmentResult:
    """Result of aligning Patreon audio with YouTube video."""
    anchor_points: list[AnchorPoint]
    success: bool = True
    error_message: Optional[str] = None
    offset_seconds: Optional[float] = None  # Computed median offset


@dataclass
class CaptionSegment:
    """A segment of YouTube auto-captions with timing."""
    text: str
    start_time: float  # seconds
    duration: float  # seconds


def fetch_youtube_captions(video_id: str) -> list[CaptionSegment]:
    """Fetch auto-generated captions from YouTube.

    Uses youtube-transcript-api to get auto-generated captions.

    Args:
        video_id: YouTube video ID.

    Returns:
        List of CaptionSegment objects with text and timing.
    """
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)

        segments = []
        for entry in transcript:
            text = entry.text
            start = float(entry.start)
            duration = float(entry.duration)

            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            if text:
                segments.append(CaptionSegment(
                    text=text,
                    start_time=start,
                    duration=duration,
                ))

        return segments

    except TranscriptsDisabled:
        return []
    except NoTranscriptFound:
        return []
    except Exception:
        return []


def get_patreon_transcript_segments(episode_id: int, limit: int = 1000) -> list[tuple[str, float]]:
    """Get transcript segments from the database.

    Args:
        episode_id: Episode ID to get transcript for.
        limit: Maximum number of words to fetch.

    Returns:
        List of (word, start_time_seconds) tuples.
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT word, start_time
            FROM transcript_segments
            WHERE episode_id = %s
            ORDER BY segment_index
            LIMIT %s
            """,
            (episode_id, limit)
        )
        return [(row["word"].lower(), float(row["start_time"])) for row in cursor.fetchall()]


def normalize_word(word: str) -> str:
    """Normalize a word for matching."""
    return re.sub(r'[^\w]', '', word.lower())


def find_matching_sequences(
    patreon_words: list[tuple[str, float]],
    youtube_segments: list[CaptionSegment],
    min_match_length: int = 5,
    max_matches: int = 20,
) -> list[AnchorPoint]:
    """Find matching word sequences between Patreon transcript and YouTube captions.

    Uses a sliding window approach to find matching subsequences.

    Args:
        patreon_words: List of (word, start_time) from Patreon transcript.
        youtube_segments: List of CaptionSegment from YouTube.
        min_match_length: Minimum consecutive words to count as a match.
        max_matches: Maximum number of anchor points to return.

    Returns:
        List of AnchorPoint objects.
    """
    if not patreon_words or not youtube_segments:
        return []

    # Build a flat list of (word, time) from YouTube captions
    youtube_words = []
    for seg in youtube_segments:
        words = seg.text.split()
        # Distribute time across words in segment
        time_per_word = seg.duration / max(len(words), 1)
        for i, word in enumerate(words):
            youtube_words.append((
                normalize_word(word),
                seg.start_time + i * time_per_word
            ))

    # Normalize Patreon words
    patreon_normalized = [(normalize_word(w), t) for w, t in patreon_words]

    # Build word index for YouTube for faster lookup
    youtube_word_index: dict[str, list[int]] = {}
    for i, (word, _) in enumerate(youtube_words):
        if word not in youtube_word_index:
            youtube_word_index[word] = []
        youtube_word_index[word].append(i)

    anchors = []
    used_patreon_ranges = set()

    # Slide through Patreon transcript looking for matches
    for p_start in range(0, len(patreon_normalized) - min_match_length, min_match_length):
        if p_start in used_patreon_ranges:
            continue

        first_word = patreon_normalized[p_start][0]
        if first_word not in youtube_word_index:
            continue

        # Try each position where the first word appears in YouTube
        for y_start in youtube_word_index[first_word]:
            if y_start + min_match_length > len(youtube_words):
                continue

            # Count consecutive matching words
            match_len = 0
            for offset in range(min(50, len(patreon_normalized) - p_start, len(youtube_words) - y_start)):
                p_word = patreon_normalized[p_start + offset][0]
                y_word = youtube_words[y_start + offset][0]
                if p_word == y_word:
                    match_len += 1
                else:
                    break

            if match_len >= min_match_length:
                # Found a match - use the middle of the matched sequence
                mid_offset = match_len // 2
                p_time = patreon_normalized[p_start + mid_offset][1]
                y_time = youtube_words[y_start + mid_offset][1]

                matched_text = " ".join(
                    patreon_words[p_start + i][0]
                    for i in range(min(match_len, 10))
                )

                confidence = Decimal(str(min(match_len / 20.0, 1.0)))

                anchors.append(AnchorPoint(
                    patreon_time=Decimal(str(p_time)),
                    youtube_time=Decimal(str(y_time)),
                    confidence=confidence,
                    matched_text=matched_text[:100],
                ))

                # Mark this range as used
                for i in range(p_start, p_start + match_len):
                    used_patreon_ranges.add(i)

                break  # Move to next Patreon position

        if len(anchors) >= max_matches:
            break

    return anchors


def compute_offset(anchors: list[AnchorPoint]) -> Optional[float]:
    """Compute the median offset from anchor points.

    Args:
        anchors: List of anchor points.

    Returns:
        Median offset (patreon_time - youtube_time) in seconds, or None if no anchors.
    """
    if not anchors:
        return None

    offsets = [float(a.patreon_time - a.youtube_time) for a in anchors]
    return median(offsets)


def align_episode(episode_id: int, youtube_url: str) -> AlignmentResult:
    """Align Patreon transcript with YouTube video.

    Args:
        episode_id: Episode ID with transcript in database.
        youtube_url: YouTube video URL.

    Returns:
        AlignmentResult with anchor points and computed offset.
    """
    video_id = extract_video_id(youtube_url)
    if not video_id:
        return AlignmentResult(
            anchor_points=[],
            success=False,
            error_message=f"Could not extract video ID from URL: {youtube_url}"
        )

    # Fetch YouTube captions
    try:
        youtube_segments = fetch_youtube_captions(video_id)
    except Exception as e:
        return AlignmentResult(
            anchor_points=[],
            success=False,
            error_message=f"Failed to fetch YouTube captions: {e}"
        )

    if not youtube_segments:
        return AlignmentResult(
            anchor_points=[],
            success=False,
            error_message="No captions found for YouTube video"
        )

    # Get Patreon transcript
    patreon_words = get_patreon_transcript_segments(episode_id)
    if not patreon_words:
        return AlignmentResult(
            anchor_points=[],
            success=False,
            error_message="No transcript found for episode"
        )

    # Find matching sequences
    anchors = find_matching_sequences(patreon_words, youtube_segments)

    if not anchors:
        return AlignmentResult(
            anchor_points=[],
            success=False,
            error_message="Could not find matching sequences between transcripts"
        )

    # Compute offset
    offset = compute_offset(anchors)

    return AlignmentResult(
        anchor_points=anchors,
        success=True,
        offset_seconds=offset,
    )


def get_youtube_time(episode_id: int, patreon_time: float) -> Optional[float]:
    """Convert a Patreon timestamp to YouTube timestamp using stored anchors.

    Args:
        episode_id: Episode ID.
        patreon_time: Time in the Patreon audio (seconds).

    Returns:
        Corresponding YouTube time (seconds), or None if no anchors.
    """
    with get_cursor(commit=False) as cursor:
        # Get anchor points for this episode
        cursor.execute(
            """
            SELECT patreon_time, youtube_time
            FROM timestamp_anchors
            WHERE episode_id = %s
            ORDER BY patreon_time
            """,
            (episode_id,)
        )
        anchors = cursor.fetchall()

    if not anchors:
        return None

    # Compute offset from anchors using interpolation
    # Find the two closest anchors (before and after)
    before = None
    after = None

    for row in anchors:
        pt = float(row["patreon_time"])
        yt = float(row["youtube_time"])
        if pt <= patreon_time:
            before = (pt, yt)
        if pt >= patreon_time and after is None:
            after = (pt, yt)

    # If we only have anchors on one side, use simple offset
    if before and not after:
        offset = before[0] - before[1]
        return patreon_time - offset
    if after and not before:
        offset = after[0] - after[1]
        return patreon_time - offset

    # Interpolate between two anchors
    if before and after:
        # Linear interpolation
        p1, y1 = before
        p2, y2 = after
        if p2 == p1:
            return y1
        ratio = (patreon_time - p1) / (p2 - p1)
        return y1 + ratio * (y2 - y1)

    return None


def store_anchor_points(episode_id: int, result: AlignmentResult) -> int:
    """Store anchor points from alignment result into timestamp_anchors table.

    Args:
        episode_id: The episode ID to store anchors for.
        result: The alignment result containing anchor points.

    Returns:
        Number of anchors stored.
    """
    if not result.anchor_points:
        return 0

    with get_cursor() as cursor:
        # Delete existing anchors for this episode to handle duplicates gracefully
        cursor.execute(
            "DELETE FROM timestamp_anchors WHERE episode_id = %s",
            (episode_id,)
        )

        # Insert all anchor points
        values = [
            (episode_id, ap.patreon_time, ap.youtube_time, ap.confidence, ap.matched_text)
            for ap in result.anchor_points
        ]
        cursor.executemany(
            """
            INSERT INTO timestamp_anchors (episode_id, patreon_time, youtube_time, confidence, matched_text)
            VALUES (%s, %s, %s, %s, %s)
            """,
            values
        )

    return len(result.anchor_points)
