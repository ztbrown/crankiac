"""YouTube integration for Crankiac."""
from .client import (
    YouTubeClient,
    YouTubeVideo,
    MatchResult,
    match_episode_to_video,
    match_episode_to_video_detailed,
    extract_episode_number,
    is_free_monday_episode,
    load_videos_from_json,
    save_videos_to_json,
    fetch_and_save_videos,
)
from .scraper import (
    ScrapedVideo,
    SyncResult,
    scrape_channel_videos,
    sync_youtube_episodes,
    extract_episode_number as scraper_extract_episode_number,
)

__all__ = [
    # Client
    "YouTubeClient",
    "YouTubeVideo",
    "MatchResult",
    "match_episode_to_video",
    "match_episode_to_video_detailed",
    "extract_episode_number",
    "is_free_monday_episode",
    "load_videos_from_json",
    "save_videos_to_json",
    "fetch_and_save_videos",
    # Scraper
    "ScrapedVideo",
    "SyncResult",
    "scrape_channel_videos",
    "sync_youtube_episodes",
]
