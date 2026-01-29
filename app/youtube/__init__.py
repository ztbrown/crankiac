"""YouTube integration for episode matching and captions."""
from .scraper import (
    sync_youtube_episodes,
    match_videos_to_episodes,
    extract_episode_number_from_title,
    MatchResult,
    SyncResult,
    print_sync_preview,
)

__all__ = [
    "sync_youtube_episodes",
    "match_videos_to_episodes",
    "extract_episode_number_from_title",
    "MatchResult",
    "SyncResult",
    "print_sync_preview",
]
