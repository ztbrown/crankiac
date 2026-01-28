"""YouTube client for fetching Chapo Trap House videos."""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import requests

CHAPO_CHANNEL_ID = "UC1XB3P7c3R3PdB4TPe-T3zA"
YOUTUBE_RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHAPO_CHANNEL_ID}"


@dataclass
class YouTubeVideo:
    video_id: str
    title: str
    published_at: datetime
    url: str


class YouTubeClient:
    """Client for fetching videos from YouTube via RSS feed."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })

    def get_videos(self, max_results: int = 100) -> list[YouTubeVideo]:
        """
        Fetch recent videos from the Chapo Trap House YouTube channel.

        Args:
            max_results: Maximum number of videos to return.

        Returns:
            List of YouTubeVideo objects.
        """
        response = self.session.get(YOUTUBE_RSS_URL)
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
            video_id = entry.find("yt:videoId", ns)
            title = entry.find("atom:title", ns)
            published = entry.find("atom:published", ns)

            if video_id is not None and title is not None:
                # Parse ISO 8601 datetime
                pub_dt = None
                if published is not None and published.text:
                    pub_dt = datetime.fromisoformat(published.text.replace("Z", "+00:00"))

                videos.append(YouTubeVideo(
                    video_id=video_id.text,
                    title=title.text or "",
                    published_at=pub_dt,
                    url=f"https://www.youtube.com/watch?v={video_id.text}",
                ))

        return videos


def normalize_title(title: str) -> str:
    """Normalize a title for matching by removing common variations."""
    title = title.lower()
    # Remove episode number patterns like "episode 123" or "ep. 123" or "#123"
    title = re.sub(r'\bepisode\s*\d+\b', '', title)
    title = re.sub(r'\bep\.?\s*\d+\b', '', title)
    title = re.sub(r'#\d+', '', title)
    # Remove common suffixes
    title = re.sub(r'\s*\(free\s*preview\).*$', '', title)
    title = re.sub(r'\s*\|\s*chapo\s*trap\s*house.*$', '', title)
    # Remove punctuation and extra whitespace
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def extract_episode_number(title: str) -> Optional[int]:
    """Extract episode number from title if present."""
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


def match_episode_to_video(
    episode_title: str,
    episode_date: Optional[datetime],
    videos: list[YouTubeVideo],
    date_tolerance_days: int = 7,
) -> Optional[YouTubeVideo]:
    """
    Match an episode to a YouTube video by title and/or date.

    Args:
        episode_title: The episode title from Patreon.
        episode_date: When the episode was published.
        videos: List of YouTube videos to match against.
        date_tolerance_days: How many days apart dates can be to still match.

    Returns:
        Matched YouTubeVideo or None.
    """
    ep_normalized = normalize_title(episode_title)
    ep_number = extract_episode_number(episode_title)

    best_match = None
    best_score = 0

    for video in videos:
        vid_normalized = normalize_title(video.title)
        vid_number = extract_episode_number(video.title)
        score = 0

        # Check episode number match (strong signal)
        if ep_number and vid_number and ep_number == vid_number:
            score += 50

        # Check title word overlap
        ep_words = set(ep_normalized.split())
        vid_words = set(vid_normalized.split())
        common_words = ep_words & vid_words
        # Filter out very common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'chapo', 'trap', 'house'}
        common_words -= stopwords
        if common_words:
            score += len(common_words) * 10

        # Check date proximity
        if episode_date and video.published_at:
            # Make both timezone-naive for comparison
            ep_dt = episode_date.replace(tzinfo=None) if episode_date.tzinfo else episode_date
            vid_dt = video.published_at.replace(tzinfo=None) if video.published_at.tzinfo else video.published_at
            days_diff = abs((ep_dt - vid_dt).days)
            if days_diff <= date_tolerance_days:
                score += max(0, 20 - days_diff * 2)

        if score > best_score:
            best_score = score
            best_match = video

    # Require minimum score to return a match
    if best_score >= 30:
        return best_match

    return None
