"""Transcript alignment algorithm for matching Patreon and YouTube transcripts.

Uses sequence matching to find corresponding segments between the two transcript
sources and produces anchor points that can be used for timestamp interpolation.
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Optional


@dataclass
class AnchorPoint:
    """A mapping between Patreon and YouTube timestamps.

    Represents a point where we have high confidence that both transcripts
    are referring to the same moment in the audio/video.
    """
    patreon_time: Decimal
    youtube_time: Decimal
    confidence: float  # 0.0 to 1.0, based on match quality
    matched_text: str  # The text that was matched at this point


@dataclass
class AlignmentResult:
    """Result of aligning two transcripts."""
    anchor_points: list[AnchorPoint]
    patreon_word_count: int
    youtube_word_count: int
    coverage: float  # Percentage of Patreon words matched

    def interpolate(self, patreon_time: Decimal) -> Optional[Decimal]:
        """
        Interpolate a YouTube time from a Patreon time.

        Uses linear interpolation between the nearest anchor points.

        Args:
            patreon_time: Timestamp from Patreon transcript.

        Returns:
            Estimated YouTube timestamp, or None if no anchors available.
        """
        if not self.anchor_points:
            return None

        # Sort anchors by Patreon time
        sorted_anchors = sorted(self.anchor_points, key=lambda a: a.patreon_time)

        # Handle edge cases
        if patreon_time <= sorted_anchors[0].patreon_time:
            # Before first anchor - use first anchor's offset
            offset = sorted_anchors[0].youtube_time - sorted_anchors[0].patreon_time
            return patreon_time + offset

        if patreon_time >= sorted_anchors[-1].patreon_time:
            # After last anchor - use last anchor's offset
            offset = sorted_anchors[-1].youtube_time - sorted_anchors[-1].patreon_time
            return patreon_time + offset

        # Find surrounding anchors
        for i in range(len(sorted_anchors) - 1):
            lower = sorted_anchors[i]
            upper = sorted_anchors[i + 1]

            if lower.patreon_time <= patreon_time <= upper.patreon_time:
                # Linear interpolation
                patreon_range = upper.patreon_time - lower.patreon_time
                if patreon_range == 0:
                    return lower.youtube_time

                ratio = (patreon_time - lower.patreon_time) / patreon_range
                youtube_range = upper.youtube_time - lower.youtube_time
                return lower.youtube_time + (youtube_range * Decimal(str(ratio)))

        return None


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison.

    Removes punctuation, converts to lowercase, and collapses whitespace.
    """
    # Remove punctuation except apostrophes (for contractions)
    text = re.sub(r"[^\w\s']", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def extract_words(text: str) -> list[str]:
    """Extract normalized words from text."""
    normalized = normalize_text(text)
    return normalized.split()


def align_transcripts(
    patreon_segments: list[dict],
    youtube_segments: list[dict],
    min_match_length: int = 5,
    min_confidence: float = 0.6,
) -> AlignmentResult:
    """
    Align Patreon transcript segments with YouTube caption segments.

    Uses sequence matching to find corresponding text regions and creates
    anchor points that map timestamps between the two sources.

    Args:
        patreon_segments: List of dicts with 'word', 'start_time', 'end_time'.
            Expected format from transcript_segments table.
        youtube_segments: List of dicts with 'text', 'start_time', 'duration'.
            Expected format from YouTube caption API.
        min_match_length: Minimum number of consecutive matching words for anchor.
        min_confidence: Minimum match ratio to accept as anchor.

    Returns:
        AlignmentResult with anchor points and statistics.
    """
    # Build word sequences with timestamps
    patreon_words = []
    patreon_times = []
    for seg in patreon_segments:
        word = normalize_text(seg['word'])
        if word:
            patreon_words.append(word)
            patreon_times.append(Decimal(str(seg['start_time'])))

    youtube_words = []
    youtube_times = []
    for seg in youtube_segments:
        seg_words = extract_words(seg['text'])
        if not seg_words:
            continue

        start = Decimal(str(seg['start_time']))
        duration = Decimal(str(seg.get('duration', 0)))

        # Distribute time across words in segment
        time_per_word = duration / len(seg_words) if seg_words else Decimal('0')
        current_time = start

        for word in seg_words:
            youtube_words.append(word)
            youtube_times.append(current_time)
            current_time += time_per_word

    if not patreon_words or not youtube_words:
        return AlignmentResult(
            anchor_points=[],
            patreon_word_count=len(patreon_words),
            youtube_word_count=len(youtube_words),
            coverage=0.0,
        )

    # Use SequenceMatcher to find matching blocks
    matcher = SequenceMatcher(None, patreon_words, youtube_words, autojunk=False)
    matching_blocks = matcher.get_matching_blocks()

    anchor_points = []
    total_matched_words = 0

    for block in matching_blocks:
        patreon_start, youtube_start, length = block.a, block.b, block.size

        if length < min_match_length:
            continue

        # Calculate confidence based on surrounding context
        # Longer matches = higher confidence
        confidence = min(1.0, length / 10.0)  # Max out at 10 words

        if confidence < min_confidence:
            continue

        # Extract matched text
        matched_text = ' '.join(patreon_words[patreon_start:patreon_start + length])

        # Create anchor at the start of the match
        anchor_points.append(AnchorPoint(
            patreon_time=patreon_times[patreon_start],
            youtube_time=youtube_times[youtube_start],
            confidence=confidence,
            matched_text=matched_text[:100],  # Truncate for storage
        ))

        # Also create anchor at the end of the match for better interpolation
        if length > min_match_length * 2:
            end_idx = patreon_start + length - 1
            yt_end_idx = youtube_start + length - 1
            anchor_points.append(AnchorPoint(
                patreon_time=patreon_times[end_idx],
                youtube_time=youtube_times[yt_end_idx],
                confidence=confidence,
                matched_text=matched_text[-100:],
            ))

        total_matched_words += length

    # Sort anchors by Patreon time
    anchor_points.sort(key=lambda a: a.patreon_time)

    # Remove duplicate anchors that are too close together
    anchor_points = _deduplicate_anchors(anchor_points, min_time_gap=Decimal('5.0'))

    coverage = total_matched_words / len(patreon_words) if patreon_words else 0.0

    return AlignmentResult(
        anchor_points=anchor_points,
        patreon_word_count=len(patreon_words),
        youtube_word_count=len(youtube_words),
        coverage=coverage,
    )


def _deduplicate_anchors(
    anchors: list[AnchorPoint],
    min_time_gap: Decimal,
) -> list[AnchorPoint]:
    """
    Remove anchors that are too close together in time.

    Keeps the anchor with highest confidence when duplicates exist.
    """
    if not anchors:
        return []

    result = [anchors[0]]

    for anchor in anchors[1:]:
        if anchor.patreon_time - result[-1].patreon_time >= min_time_gap:
            result.append(anchor)
        elif anchor.confidence > result[-1].confidence:
            # Replace with higher confidence anchor
            result[-1] = anchor

    return result


def align_episode(
    episode_id: int,
    youtube_captions: list[dict],
) -> AlignmentResult:
    """
    Align transcripts for a specific episode.

    Fetches Patreon transcript from database and aligns with provided
    YouTube captions.

    Args:
        episode_id: Database ID of the episode.
        youtube_captions: YouTube caption segments with 'text', 'start_time', 'duration'.

    Returns:
        AlignmentResult with anchor points.
    """
    from app.db.connection import get_cursor

    # Fetch Patreon transcript segments
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT word, start_time, end_time, segment_index
            FROM transcript_segments
            WHERE episode_id = %s
            ORDER BY segment_index
            """,
            (episode_id,)
        )
        patreon_segments = [dict(row) for row in cursor.fetchall()]

    return align_transcripts(patreon_segments, youtube_captions)


def get_anchor_points_for_episode(episode_id: int) -> list[tuple[Decimal, Decimal]]:
    """
    Get stored anchor points for an episode as simple tuples.

    Returns:
        List of (patreon_time, youtube_time) tuples.
    """
    from app.db.connection import get_cursor

    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT patreon_time, youtube_time
            FROM timestamp_anchors
            WHERE episode_id = %s
            ORDER BY patreon_time
            """,
            (episode_id,)
        )
        return [(row['patreon_time'], row['youtube_time']) for row in cursor.fetchall()]
