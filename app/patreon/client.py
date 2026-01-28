import os
import requests
from typing import Optional
from dataclasses import dataclass

PATREON_API_BASE = "https://www.patreon.com/api"
CHAPO_CREATOR_ID = "372319"  # Chapo Trap House campaign ID

@dataclass
class PatreonEpisode:
    id: str
    title: str
    audio_url: Optional[str]
    published_at: Optional[str]
    duration_seconds: Optional[int]

class PatreonClient:
    """Client for fetching episodes from Patreon."""

    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize the Patreon client.

        Args:
            session_id: Patreon session_id cookie value.
                       If not provided, reads from PATREON_SESSION_ID env var.
        """
        self.session_id = session_id or os.environ.get("PATREON_SESSION_ID")
        if not self.session_id:
            raise ValueError(
                "Patreon session_id required. Set PATREON_SESSION_ID env var "
                "or pass session_id parameter."
            )

        self.session = requests.Session()
        self.session.cookies.set("session_id", self.session_id, domain=".patreon.com")
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        })

    def get_episodes(self, limit: int = 100, cursor: Optional[str] = None) -> tuple[list[PatreonEpisode], Optional[str]]:
        """
        Fetch episodes from Chapo Trap House.

        Args:
            limit: Maximum number of episodes to fetch per request.
            cursor: Pagination cursor for fetching more episodes.

        Returns:
            Tuple of (episodes list, next cursor or None).
        """
        params = {
            "include": "audio,audio_preview",
            "fields[post]": "title,published_at,post_file,audio",
            "filter[campaign_id]": CHAPO_CREATOR_ID,
            "filter[contains_exclusive_posts]": "true",
            "filter[is_draft]": "false",
            "sort": "-published_at",
            "page[count]": str(limit),
        }

        if cursor:
            params["page[cursor]"] = cursor

        response = self.session.get(
            f"{PATREON_API_BASE}/posts",
            params=params
        )
        response.raise_for_status()

        data = response.json()
        episodes = []

        # Extract audio data from included resources
        audio_map = {}
        for included in data.get("included", []):
            if included.get("type") == "media":
                mimetype = included.get("attributes", {}).get("mimetype") or ""
                if mimetype.startswith("audio/"):
                    audio_map[included["id"]] = included.get("attributes", {}).get("download_url")

        for post in data.get("data", []):
            attrs = post.get("attributes", {})
            relationships = post.get("relationships", {})

            # Get audio URL from relationships
            audio_url = None
            audio_data = relationships.get("audio", {}).get("data")
            if audio_data:
                audio_id = audio_data.get("id")
                audio_url = audio_map.get(audio_id)

            episodes.append(PatreonEpisode(
                id=post["id"],
                title=attrs.get("title", "Untitled"),
                audio_url=audio_url,
                published_at=attrs.get("published_at"),
                duration_seconds=None,  # Duration not always available in API
            ))

        # Get next cursor for pagination
        next_cursor = None
        links = data.get("links", {})
        if "next" in links:
            # Extract cursor from next URL
            import urllib.parse
            next_url = links["next"]
            parsed = urllib.parse.urlparse(next_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            next_cursor = query_params.get("page[cursor]", [None])[0]

        return episodes, next_cursor

    def get_all_episodes(self, max_episodes: int = 1000) -> list[PatreonEpisode]:
        """
        Fetch all episodes, handling pagination.

        Args:
            max_episodes: Maximum total episodes to fetch.

        Returns:
            List of all episodes.
        """
        all_episodes = []
        cursor = None

        while len(all_episodes) < max_episodes:
            episodes, cursor = self.get_episodes(limit=100, cursor=cursor)
            all_episodes.extend(episodes)

            if not cursor or not episodes:
                break

        return all_episodes[:max_episodes]

    def get_audio_url(self, post_id: str) -> Optional[str]:
        """
        Get the audio download URL for a specific post.

        Args:
            post_id: The Patreon post ID.

        Returns:
            Audio download URL or None.
        """
        response = self.session.get(
            f"{PATREON_API_BASE}/posts/{post_id}",
            params={
                "include": "audio",
                "fields[post]": "title,post_file",
                "fields[media]": "download_url,mimetype",
            }
        )
        response.raise_for_status()

        data = response.json()

        # Find audio in included resources
        for included in data.get("included", []):
            if included.get("type") == "media":
                attrs = included.get("attributes", {})
                if attrs.get("mimetype", "").startswith("audio/"):
                    return attrs.get("download_url")

        return None
