"""Episode filtering utilities for CTH podcast episodes."""
import re
from typing import Union

from app.patreon.client import PatreonEpisode
from app.db.models import Episode


# Shows to exclude from processing
EXCLUDED_SHOWS = frozenset([
    "players club",
    "movie mindset",
    "hell on earth",
])


def is_numbered_episode(title: str) -> bool:
    """
    Check if title matches numbered CTH episode pattern.

    Numbered episodes start with digits and end with a date in parentheses.
    Examples: "832 - Title (1/27/25)", "500 - Special Episode (12/1/21)"

    Args:
        title: Episode title to check.

    Returns:
        True if title matches numbered episode pattern.
    """
    if not title:
        return False

    # Must start with digits
    if not re.match(r'^\d+', title):
        return False

    # Must end with date in parentheses: (M/D/YY) or (MM/DD/YY)
    if not re.search(r'\(\d{1,2}/\d{1,2}/\d{2,4}\)\s*$', title):
        return False

    return True


def is_excluded_show(title: str) -> bool:
    """
    Check if title indicates an excluded show type.

    Excluded shows: Players Club, Movie Mindset, Hell on Earth.

    Args:
        title: Episode title to check.

    Returns:
        True if title contains an excluded show name.
    """
    if not title:
        return False

    title_lower = title.lower()
    return any(show in title_lower for show in EXCLUDED_SHOWS)


def filter_episodes(
    episodes: list[Union[PatreonEpisode, Episode]],
    numbered_only: bool = True
) -> list[Union[PatreonEpisode, Episode]]:
    """
    Filter episodes based on criteria.

    Args:
        episodes: List of episodes to filter.
        numbered_only: If True, only include numbered episodes.
                      Excluded shows are always filtered out.

    Returns:
        Filtered list of episodes.
    """
    filtered = []
    for ep in episodes:
        title = ep.title

        # Always exclude certain shows
        if is_excluded_show(title):
            continue

        # Optionally filter to numbered episodes only
        if numbered_only and not is_numbered_episode(title):
            continue

        filtered.append(ep)

    return filtered
