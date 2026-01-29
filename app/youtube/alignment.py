"""YouTube/Patreon audio alignment utilities."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ..db.connection import get_cursor


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
