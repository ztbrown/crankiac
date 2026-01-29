"""YouTube channel scraper and episode matcher.

Scrapes YouTube channel to get video IDs and titles, matches them to
database episodes by episode number, and syncs the matches.
"""
import re
from dataclasses import dataclass
from typing import Optional

from .client import YouTubeClient, YouTubeVideo, extract_episode_number
from ..db.repository import EpisodeRepository


@dataclass
class MatchResult:
    """Result of matching a YouTube video to a database episode."""
    video: YouTubeVideo
    episode_id: int
    episode_title: str
    episode_number: Optional[int]
    video_episode_number: Optional[int]
    matched: bool
    reason: str


@dataclass
class SyncResult:
    """Summary of a sync operation."""
    videos_fetched: int
    episodes_checked: int
    matches_found: int
    updates_applied: int
    skipped_already_matched: int
    no_match: int
    match_details: list[MatchResult]


def extract_episode_number_from_title(title: str) -> Optional[int]:
    """
    Extract episode number from a title using multiple patterns.

    Handles formats like:
    - Episode 123
    - Ep. 123
    - Ep 123
    - #123
    - 123: Title
    - 123 - Title

    Args:
        title: The video or episode title.

    Returns:
        Episode number if found, None otherwise.
    """
    # Use the existing function from client.py
    return extract_episode_number(title)


def match_videos_to_episodes(
    videos: list[YouTubeVideo],
    episodes: list[dict],
) -> list[MatchResult]:
    """
    Match YouTube videos to database episodes by episode number.

    Args:
        videos: List of YouTubeVideo objects from the channel.
        episodes: List of episode dicts with 'id' and 'title' keys.

    Returns:
        List of MatchResult objects showing matches and non-matches.
    """
    results = []

    # Build lookup by episode number
    episode_by_number: dict[int, dict] = {}
    for ep in episodes:
        ep_num = extract_episode_number_from_title(ep["title"])
        if ep_num is not None:
            episode_by_number[ep_num] = ep

    for video in videos:
        vid_num = extract_episode_number_from_title(video.title)

        if vid_num is not None and vid_num in episode_by_number:
            ep = episode_by_number[vid_num]
            results.append(MatchResult(
                video=video,
                episode_id=ep["id"],
                episode_title=ep["title"],
                episode_number=extract_episode_number_from_title(ep["title"]),
                video_episode_number=vid_num,
                matched=True,
                reason=f"Episode number match: {vid_num}",
            ))
        else:
            results.append(MatchResult(
                video=video,
                episode_id=0,
                episode_title="",
                episode_number=None,
                video_episode_number=vid_num,
                matched=False,
                reason="No matching episode number found" if vid_num else "No episode number in video title",
            ))

    return results


def sync_youtube_episodes(
    dry_run: bool = True,
    max_videos: int = 100,
) -> SyncResult:
    """
    Sync YouTube videos to database episodes.

    Fetches videos from the YouTube channel, matches them to episodes
    by episode number, and updates the database with youtube_id.

    Args:
        dry_run: If True, preview matches without updating database.
        max_videos: Maximum number of videos to fetch.

    Returns:
        SyncResult with operation summary.
    """
    client = YouTubeClient()
    repo = EpisodeRepository()

    # Fetch videos from YouTube (uses RSS, no API key needed)
    videos = client.get_videos(max_results=max_videos)

    # Get episodes that need youtube_id
    episodes = repo.get_episodes_for_youtube_matching()

    # Match videos to episodes
    matches = match_videos_to_episodes(videos, episodes)

    updates_applied = 0
    skipped_already_matched = 0
    no_match = 0
    matches_found = 0

    for match in matches:
        if match.matched:
            matches_found += 1
            if not dry_run:
                repo.update_youtube_id(match.episode_id, match.video.video_id)
                updates_applied += 1
        else:
            no_match += 1

    return SyncResult(
        videos_fetched=len(videos),
        episodes_checked=len(episodes),
        matches_found=matches_found,
        updates_applied=updates_applied,
        skipped_already_matched=skipped_already_matched,
        no_match=no_match,
        match_details=matches,
    )


def print_sync_preview(result: SyncResult) -> None:
    """Print a human-readable preview of sync results."""
    print(f"\n{'='*60}")
    print("YouTube Episode Sync Preview")
    print(f"{'='*60}")
    print(f"Videos fetched: {result.videos_fetched}")
    print(f"Episodes to match: {result.episodes_checked}")
    print(f"Matches found: {result.matches_found}")
    print(f"No match: {result.no_match}")
    print(f"Updates applied: {result.updates_applied}")
    print()

    if result.match_details:
        print("Matched episodes:")
        print("-" * 40)
        for match in result.match_details:
            if match.matched:
                print(f"  [{match.video_episode_number}] {match.video.title[:50]}...")
                print(f"      -> {match.episode_title[:50]}...")
                print(f"      Video ID: {match.video.video_id}")
                print()

        unmatched = [m for m in result.match_details if not m.matched]
        if unmatched:
            print("\nUnmatched videos:")
            print("-" * 40)
            for match in unmatched[:10]:  # Show first 10
                print(f"  {match.video.title[:60]}...")
                print(f"      Reason: {match.reason}")
            if len(unmatched) > 10:
                print(f"  ... and {len(unmatched) - 10} more")
