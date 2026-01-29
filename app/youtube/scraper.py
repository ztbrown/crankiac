"""YouTube channel scraper for syncing video IDs to episodes."""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import requests


DEFAULT_CHAPO_CHANNEL_URL = "https://www.youtube.com/@chapotraphouse"
RSS_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


@dataclass
class ScrapedVideo:
    """A video scraped from YouTube."""
    video_id: str
    title: str
    published_at: Optional[datetime] = None
    episode_number: Optional[int] = None


@dataclass
class SyncResult:
    """Result of syncing YouTube videos to episodes."""
    videos_found: int
    episodes_matched: int
    unmatched_videos: list[ScrapedVideo]
    matched_pairs: list[tuple[dict, ScrapedVideo]]  # (episode, video) pairs


def extract_episode_number(title: str) -> Optional[int]:
    """
    Extract episode number from a video or episode title.

    Handles formats like:
    - "Episode 123"
    - "Ep. 123"
    - "Ep 123"
    - "#123"
    - "123 -" or "123:"

    Args:
        title: The title to extract episode number from.

    Returns:
        Episode number as int, or None if not found.
    """
    patterns = [
        r'\bepisode\s*(\d+)\b',
        r'\bep\.?\s*(\d+)\b',
        r'#(\d+)\b',
        r'^(\d+)\s*[-:.]',
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def get_channel_id_from_url(channel_url: str, session: Optional[requests.Session] = None) -> Optional[str]:
    """
    Get the channel ID from a YouTube channel URL.

    Scrapes the channel page to find the channel ID since URLs like
    @chapotraphouse don't directly contain the ID.

    Args:
        channel_url: URL like https://www.youtube.com/@chapotraphouse
        session: Optional requests session to use.

    Returns:
        Channel ID string or None if not found.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })

    try:
        response = session.get(channel_url)
        response.raise_for_status()

        # Look for channel ID in the page
        # It appears in various places like meta tags or embedded JSON
        patterns = [
            r'"channelId":"([^"]+)"',
            r'channel_id=([a-zA-Z0-9_-]+)',
            r'"externalId":"([^"]+)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, response.text)
            if match:
                return match.group(1)

    except requests.RequestException:
        pass

    return None


def scrape_channel_videos(
    channel_url: str = DEFAULT_CHAPO_CHANNEL_URL,
    max_results: int = 100,
) -> list[ScrapedVideo]:
    """
    Scrape videos from a YouTube channel using RSS feed.

    Note: RSS feed typically only returns the most recent ~15 videos.
    For more videos, use the YouTube Data API.

    Args:
        channel_url: YouTube channel URL (e.g., https://www.youtube.com/@chapotraphouse)
        max_results: Maximum number of videos to return.

    Returns:
        List of ScrapedVideo objects with video_id, title, and episode_number.

    Raises:
        ValueError: If channel ID cannot be found.
        requests.RequestException: If network requests fail.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })

    # Get channel ID from URL
    channel_id = get_channel_id_from_url(channel_url, session)
    if not channel_id:
        raise ValueError(f"Could not find channel ID for URL: {channel_url}")

    # Fetch RSS feed
    rss_url = RSS_TEMPLATE.format(channel_id=channel_id)
    response = session.get(rss_url)
    response.raise_for_status()

    # Parse XML feed
    root = ET.fromstring(response.content)

    # Define namespaces
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }

    videos = []
    for entry in root.findall("atom:entry", ns)[:max_results]:
        video_id_elem = entry.find("yt:videoId", ns)
        title_elem = entry.find("atom:title", ns)
        published_elem = entry.find("atom:published", ns)

        if video_id_elem is not None and title_elem is not None:
            video_id = video_id_elem.text
            title = title_elem.text or ""

            # Parse published date
            pub_dt = None
            if published_elem is not None and published_elem.text:
                pub_dt = datetime.fromisoformat(published_elem.text.replace("Z", "+00:00"))

            # Extract episode number
            ep_num = extract_episode_number(title)

            videos.append(ScrapedVideo(
                video_id=video_id,
                title=title,
                published_at=pub_dt,
                episode_number=ep_num,
            ))

    return videos


def sync_youtube_episodes(
    channel_url: str = DEFAULT_CHAPO_CHANNEL_URL,
    dry_run: bool = False,
) -> SyncResult:
    """
    Sync YouTube video IDs to database episodes by matching episode numbers.

    Args:
        channel_url: YouTube channel URL to scrape.
        dry_run: If True, don't update the database.

    Returns:
        SyncResult with statistics about the sync operation.
    """
    from app.db.repository import EpisodeRepository

    # Scrape videos from channel
    videos = scrape_channel_videos(channel_url)

    # Get episodes needing youtube_id
    repo = EpisodeRepository()
    episodes = repo.get_episodes_for_youtube_matching()

    # Build lookup of episodes by title (for episode number extraction)
    episode_by_number: dict[int, dict] = {}
    for ep in episodes:
        ep_num = extract_episode_number(ep["title"])
        if ep_num:
            episode_by_number[ep_num] = ep

    # Match videos to episodes
    matched_pairs = []
    unmatched_videos = []

    for video in videos:
        if video.episode_number and video.episode_number in episode_by_number:
            episode = episode_by_number[video.episode_number]
            matched_pairs.append((episode, video))

            if not dry_run:
                repo.update_youtube_id(episode["id"], video.video_id)
        else:
            unmatched_videos.append(video)

    return SyncResult(
        videos_found=len(videos),
        episodes_matched=len(matched_pairs),
        unmatched_videos=unmatched_videos,
        matched_pairs=matched_pairs,
    )
