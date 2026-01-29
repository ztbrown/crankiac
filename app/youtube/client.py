"""YouTube client for fetching Chapo Trap House videos."""
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
import requests

CHAPO_CHANNEL_ID = "UC1XB3P7c3R3PdB4TPe-T3zA"
YOUTUBE_RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHAPO_CHANNEL_ID}"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


@dataclass
class YouTubeVideo:
    video_id: str
    title: str
    published_at: datetime
    url: str
    duration_seconds: Optional[int] = None


@dataclass
class MatchResult:
    """Result of matching an episode to a YouTube video."""
    video: Optional["YouTubeVideo"]
    score: int
    is_ambiguous: bool = False
    runner_up: Optional["YouTubeVideo"] = None
    runner_up_score: int = 0
    match_reasons: list[str] = None

    def __post_init__(self):
        if self.match_reasons is None:
            self.match_reasons = []


class YouTubeClient:
    """Client for fetching videos from YouTube via RSS feed or API."""

    def __init__(self, api_key: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY")

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

    def get_videos_with_duration(self, max_results: int = 500) -> list[YouTubeVideo]:
        """
        Fetch videos from YouTube channel using Data API (includes duration).

        Requires YOUTUBE_API_KEY environment variable.

        Args:
            max_results: Maximum number of videos to return.

        Returns:
            List of YouTubeVideo objects with duration_seconds populated.

        Raises:
            ValueError: If no API key is configured.
        """
        if not self.api_key:
            raise ValueError("YOUTUBE_API_KEY environment variable is required")

        videos = []
        page_token = None

        while len(videos) < max_results:
            # First, search for videos on the channel
            params = {
                "key": self.api_key,
                "channelId": CHAPO_CHANNEL_ID,
                "part": "snippet",
                "type": "video",
                "maxResults": min(50, max_results - len(videos)),
                "order": "date",
            }
            if page_token:
                params["pageToken"] = page_token

            response = self.session.get(f"{YOUTUBE_API_BASE}/search", params=params)
            response.raise_for_status()
            data = response.json()

            video_ids = [item["id"]["videoId"] for item in data.get("items", [])]
            if not video_ids:
                break

            # Get video details including duration
            details_response = self.session.get(
                f"{YOUTUBE_API_BASE}/videos",
                params={
                    "key": self.api_key,
                    "id": ",".join(video_ids),
                    "part": "snippet,contentDetails",
                }
            )
            details_response.raise_for_status()
            details_data = details_response.json()

            for item in details_data.get("items", []):
                video_id = item["id"]
                snippet = item["snippet"]
                content_details = item.get("contentDetails", {})

                pub_dt = None
                if snippet.get("publishedAt"):
                    pub_dt = datetime.fromisoformat(
                        snippet["publishedAt"].replace("Z", "+00:00")
                    )

                duration_seconds = _parse_duration(content_details.get("duration", ""))

                videos.append(YouTubeVideo(
                    video_id=video_id,
                    title=snippet.get("title", ""),
                    published_at=pub_dt,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    duration_seconds=duration_seconds,
                ))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return videos

    def enrich_with_duration(self, videos: list[YouTubeVideo]) -> list[YouTubeVideo]:
        """
        Add duration to videos that are missing it using the API.

        Args:
            videos: List of videos to enrich.

        Returns:
            Same videos with duration_seconds populated.
        """
        if not self.api_key:
            return videos

        # Find videos missing duration
        videos_needing_duration = [v for v in videos if v.duration_seconds is None]
        if not videos_needing_duration:
            return videos

        # Batch API calls (max 50 IDs per request)
        video_id_to_duration = {}
        for i in range(0, len(videos_needing_duration), 50):
            batch = videos_needing_duration[i:i + 50]
            video_ids = [v.video_id for v in batch]

            response = self.session.get(
                f"{YOUTUBE_API_BASE}/videos",
                params={
                    "key": self.api_key,
                    "id": ",".join(video_ids),
                    "part": "contentDetails",
                }
            )
            response.raise_for_status()
            data = response.json()

            for item in data.get("items", []):
                duration_str = item.get("contentDetails", {}).get("duration", "")
                video_id_to_duration[item["id"]] = _parse_duration(duration_str)

        # Update videos with duration
        for video in videos:
            if video.video_id in video_id_to_duration:
                video.duration_seconds = video_id_to_duration[video.video_id]

        return videos


def _parse_duration(duration_str: str) -> Optional[int]:
    """
    Parse ISO 8601 duration string (e.g., PT1H30M15S) to seconds.

    Args:
        duration_str: ISO 8601 duration like "PT1H30M15S" or "PT45M".

    Returns:
        Duration in seconds, or None if parsing fails.
    """
    if not duration_str:
        return None

    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
    if not match:
        return None

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return hours * 3600 + minutes * 60 + seconds


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
    result = match_episode_to_video_detailed(
        episode_title, episode_date, videos, date_tolerance_days
    )
    return result.video


def match_episode_to_video_detailed(
    episode_title: str,
    episode_date: Optional[datetime],
    videos: list[YouTubeVideo],
    date_tolerance_days: int = 7,
    ambiguous_threshold: int = 10,
) -> MatchResult:
    """
    Match an episode to a YouTube video with detailed results.

    Args:
        episode_title: The episode title from Patreon.
        episode_date: When the episode was published.
        videos: List of YouTube videos to match against.
        date_tolerance_days: How many days apart dates can be to still match.
        ambiguous_threshold: Score difference below which a match is ambiguous.

    Returns:
        MatchResult with match details including ambiguity detection.
    """
    ep_normalized = normalize_title(episode_title)
    ep_number = extract_episode_number(episode_title)

    # Track top two matches for ambiguity detection
    best_match = None
    best_score = 0
    best_reasons: list[str] = []
    runner_up = None
    runner_up_score = 0

    for video in videos:
        vid_normalized = normalize_title(video.title)
        vid_number = extract_episode_number(video.title)
        score = 0
        reasons: list[str] = []

        # Check episode number match (strong signal)
        if ep_number and vid_number and ep_number == vid_number:
            score += 50
            reasons.append(f"episode_number={ep_number}")

        # Check title word overlap
        ep_words = set(ep_normalized.split())
        vid_words = set(vid_normalized.split())
        common_words = ep_words & vid_words
        # Filter out very common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'chapo', 'trap', 'house'}
        common_words -= stopwords
        if common_words:
            word_score = len(common_words) * 10
            score += word_score
            reasons.append(f"title_words={','.join(sorted(common_words))}(+{word_score})")

        # Check date proximity
        if episode_date and video.published_at:
            # Make both timezone-naive for comparison
            ep_dt = episode_date.replace(tzinfo=None) if episode_date.tzinfo else episode_date
            vid_dt = video.published_at.replace(tzinfo=None) if video.published_at.tzinfo else video.published_at
            days_diff = abs((ep_dt - vid_dt).days)
            if days_diff <= date_tolerance_days:
                date_score = max(0, 20 - days_diff * 2)
                score += date_score
                if date_score > 0:
                    reasons.append(f"date_proximity={days_diff}d(+{date_score})")

        if score > best_score:
            # Current best becomes runner up
            runner_up = best_match
            runner_up_score = best_score
            # New best
            best_match = video
            best_score = score
            best_reasons = reasons
        elif score > runner_up_score:
            runner_up = video
            runner_up_score = score

    # Require minimum score to return a match
    if best_score < 30:
        return MatchResult(
            video=None,
            score=best_score,
            is_ambiguous=False,
            runner_up=runner_up,
            runner_up_score=runner_up_score,
            match_reasons=best_reasons,
        )

    # Detect ambiguous matches (runner-up is close in score)
    is_ambiguous = (
        runner_up is not None
        and runner_up_score >= 30
        and (best_score - runner_up_score) < ambiguous_threshold
    )

    return MatchResult(
        video=best_match,
        score=best_score,
        is_ambiguous=is_ambiguous,
        runner_up=runner_up,
        runner_up_score=runner_up_score,
        match_reasons=best_reasons,
    )


def is_free_monday_episode(video: YouTubeVideo) -> bool:
    """
    Determine if a video is a free Monday episode.

    Free Monday episodes are typically:
    - Published on Mondays
    - Have titles indicating they're free/public episodes
    - Are full-length episodes (not clips/previews)

    Args:
        video: The YouTube video to check.

    Returns:
        True if this appears to be a free Monday episode.
    """
    title_lower = video.title.lower()

    # Check for explicit free indicators
    if "(free)" in title_lower or "free preview" in title_lower:
        return True

    # Check if published on Monday
    if video.published_at:
        if video.published_at.weekday() == 0:  # Monday
            # Full episodes are typically > 1 hour
            if video.duration_seconds and video.duration_seconds >= 3600:
                return True
            # If we don't have duration, check title for episode indicators
            if extract_episode_number(video.title):
                return True

    return False


def save_videos_to_json(videos: list[YouTubeVideo], path: str) -> None:
    """
    Save videos to a JSON file for the matching task.

    Args:
        videos: List of videos to save.
        path: Path to the output JSON file.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = []
    for video in videos:
        video_dict = {
            "video_id": video.video_id,
            "title": video.title,
            "published_at": video.published_at.isoformat() if video.published_at else None,
            "url": video.url,
            "duration_seconds": video.duration_seconds,
            "is_free_monday": is_free_monday_episode(video),
        }
        data.append(video_dict)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def load_videos_from_json(path: str) -> list[YouTubeVideo]:
    """
    Load videos from a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        List of YouTubeVideo objects.
    """
    with open(path) as f:
        data = json.load(f)

    videos = []
    for item in data:
        pub_dt = None
        if item.get("published_at"):
            pub_dt = datetime.fromisoformat(item["published_at"])

        videos.append(YouTubeVideo(
            video_id=item["video_id"],
            title=item["title"],
            published_at=pub_dt,
            url=item["url"],
            duration_seconds=item.get("duration_seconds"),
        ))

    return videos


def fetch_and_save_videos(
    output_path: str = "app/data/youtube_videos.json",
    use_api: bool = True,
    max_results: int = 500,
) -> list[YouTubeVideo]:
    """
    Fetch videos from YouTube and save to JSON for matching.

    Args:
        output_path: Where to save the JSON file.
        use_api: Whether to use the YouTube Data API (requires API key).
        max_results: Maximum number of videos to fetch.

    Returns:
        List of fetched videos.
    """
    client = YouTubeClient()

    if use_api and client.api_key:
        videos = client.get_videos_with_duration(max_results=max_results)
    else:
        # Fall back to RSS (limited to ~15 videos, no duration)
        videos = client.get_videos(max_results=max_results)
        # Try to enrich with duration if API key is available
        if client.api_key:
            videos = client.enrich_with_duration(videos)

    save_videos_to_json(videos, output_path)
    return videos
