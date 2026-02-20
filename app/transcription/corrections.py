"""Correction dictionary: load, apply, and mine word-level corrections."""
import copy
import json
import logging
import os
from typing import Optional

from app.db.connection import get_cursor

logger = logging.getLogger(__name__)


def load_corrections(corrections_file: Optional[str]) -> dict:
    """Load a correction dictionary from a JSON file.

    Returns a dict mapping old_word -> new_word.
    Returns {} if the file is missing, empty, None, or malformed.
    """
    if not corrections_file:
        return {}

    if not os.path.exists(corrections_file):
        return {}

    try:
        with open(corrections_file, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        logger.warning(f"Could not load corrections file: {corrections_file}")
        return {}


def apply_corrections(segments: list, corrections: dict) -> list:
    """Apply a correction dictionary to transcript segments.

    For each segment whose word matches a key in corrections, returns a
    copy of the segment with the corrected word. Original segments are
    never mutated.

    Args:
        segments: List of WordSegment (or any object with a .word attribute).
        corrections: Dict mapping old_word -> new_word.

    Returns:
        New list of segments with corrections applied.
    """
    if not corrections:
        return list(segments)

    result = []
    for seg in segments:
        if seg.word in corrections:
            new_seg = copy.copy(seg)
            new_seg.word = corrections[seg.word]
            result.append(new_seg)
        else:
            result.append(seg)
    return result


def mine_corrections(min_count: int = 3) -> dict:
    """Query edit_history for frequent word corrections.

    Looks for edits where field='word', groups by (old_value, new_value),
    and returns pairs that appear at least min_count times. When the same
    old_value maps to multiple new_values the most frequent new_value wins
    (the SQL query returns them ordered by count DESC, so first wins).

    Args:
        min_count: Minimum number of occurrences required.

    Returns:
        Dict mapping old_word -> most_frequent_new_word.
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT old_value, new_value, COUNT(*) AS count
            FROM edit_history
            WHERE field = 'word'
              AND old_value IS NOT NULL
              AND new_value IS NOT NULL
              AND old_value <> new_value
            GROUP BY old_value, new_value
            HAVING COUNT(*) >= %s
            ORDER BY old_value, COUNT(*) DESC
            """,
            (min_count,),
        )
        rows = cursor.fetchall()

    # Pick the most frequent new_value per old_value (first row wins since ordered DESC)
    corrections: dict = {}
    for row in rows:
        old = row["old_value"]
        if old not in corrections:
            corrections[old] = row["new_value"]

    return corrections
