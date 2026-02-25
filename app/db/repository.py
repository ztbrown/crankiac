from typing import Optional
from .connection import get_cursor
from .models import Episode, TranscriptSegment

class EpisodeRepository:
    """Data access for episodes."""

    def create(self, episode: Episode) -> Episode:
        """Insert a new episode."""
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO episodes (patreon_id, title, audio_url, published_at, duration_seconds, youtube_url, is_free, processed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (patreon_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    audio_url = EXCLUDED.audio_url,
                    published_at = EXCLUDED.published_at,
                    duration_seconds = EXCLUDED.duration_seconds,
                    youtube_url = COALESCE(EXCLUDED.youtube_url, episodes.youtube_url),
                    is_free = EXCLUDED.is_free OR episodes.is_free
                RETURNING id, is_free, created_at, updated_at
                """,
                (episode.patreon_id, episode.title, episode.audio_url,
                 episode.published_at, episode.duration_seconds, episode.youtube_url, episode.is_free, episode.processed)
            )
            row = cursor.fetchone()
            episode.id = row["id"]
            episode.is_free = row["is_free"]
            episode.created_at = row["created_at"]
            episode.updated_at = row["updated_at"]
            return episode

    def get_by_patreon_id(self, patreon_id: str) -> Optional[Episode]:
        """Get episode by Patreon ID."""
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT * FROM episodes WHERE patreon_id = %s",
                (patreon_id,)
            )
            row = cursor.fetchone()
            if row:
                return Episode(**row)
            return None

    def get_by_id(self, episode_id: int) -> Optional[Episode]:
        """Get episode by database ID."""
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT * FROM episodes WHERE id = %s",
                (episode_id,)
            )
            row = cursor.fetchone()
            if row:
                return Episode(**row)
            return None

    def search_by_title(self, query: str) -> list[Episode]:
        """Search episodes by title substring (case-insensitive)."""
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT * FROM episodes WHERE title ILIKE %s ORDER BY published_at DESC",
                (f"%{query}%",)
            )
            return [Episode(**row) for row in cursor.fetchall()]

    def get_unprocessed(self, numbered_only: bool = False) -> list[Episode]:
        """Get all unprocessed episodes.

        Args:
            numbered_only: If True, only return episodes with numbered titles
                          (titles starting with a digit or containing #digit pattern).
        """
        with get_cursor(commit=False) as cursor:
            if numbered_only:
                cursor.execute(
                    """
                    SELECT * FROM episodes
                    WHERE NOT processed
                      AND (title ~ '^[0-9]' OR title ~ '#[0-9]')
                    ORDER BY published_at DESC
                    """
                )
            else:
                cursor.execute(
                    "SELECT * FROM episodes WHERE NOT processed ORDER BY published_at DESC"
                )
            return [Episode(**row) for row in cursor.fetchall()]

    def mark_processed(self, episode_id: int) -> None:
        """Mark an episode as processed."""
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE episodes SET processed = TRUE WHERE id = %s",
                (episode_id,)
            )

    def get_all(self) -> list[Episode]:
        """Get all episodes."""
        with get_cursor(commit=False) as cursor:
            cursor.execute("SELECT * FROM episodes ORDER BY published_at DESC")
            return [Episode(**row) for row in cursor.fetchall()]

    def get_with_missing_word_confidence(self, limit: Optional[int] = None) -> list[Episode]:
        """Get episodes that have a transcript but at least one segment with NULL word_confidence."""
        with get_cursor(commit=False) as cursor:
            query = """
                SELECT DISTINCT e.*
                FROM episodes e
                INNER JOIN transcript_segments ts ON ts.episode_id = e.id
                WHERE ts.word_confidence IS NULL
                ORDER BY e.published_at DESC
            """
            if limit:
                query += f" LIMIT {limit}"
            cursor.execute(query)
            return [Episode(**row) for row in cursor.fetchall()]

    def get_without_youtube(self) -> list[Episode]:
        """Get episodes that don't have a YouTube URL."""
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT * FROM episodes WHERE youtube_url IS NULL ORDER BY published_at DESC"
            )
            return [Episode(**row) for row in cursor.fetchall()]

    def update_youtube_url(self, episode_id: int, youtube_url: str) -> None:
        """Update the YouTube URL for an episode and mark as free."""
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE episodes SET youtube_url = %s, is_free = TRUE WHERE id = %s",
                (youtube_url, episode_id)
            )

    def update_is_free(self, episode_id: int, is_free: bool) -> None:
        """Update the is_free flag for an episode."""
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE episodes SET is_free = %s WHERE id = %s",
                (is_free, episode_id)
            )

    def update_free_status(self, episode_id: int, youtube_url: Optional[str], is_free: bool) -> None:
        """Update both youtube_url and is_free for an episode."""
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE episodes SET youtube_url = %s, is_free = %s WHERE id = %s",
                (youtube_url, is_free, episode_id)
            )

    def get_free_episodes(self) -> list[Episode]:
        """Get all free episodes (is_free=True or has youtube_url)."""
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT * FROM episodes WHERE is_free = TRUE OR youtube_url IS NOT NULL ORDER BY published_at DESC"
            )
            return [Episode(**row) for row in cursor.fetchall()]

    def backfill_is_free_from_youtube_url(self) -> int:
        """Set is_free=TRUE for all episodes that have a youtube_url.

        Returns the number of rows updated.
        """
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE episodes SET is_free = TRUE WHERE youtube_url IS NOT NULL AND is_free = FALSE"
            )
            return cursor.rowcount

    def get_by_episode_numbers(self, numbers: list[int]) -> list[Episode]:
        """Get episodes by their episode numbers.

        Episodes have titles like "1003 - Bored of Peace feat. Derek Davison".
        This method finds episodes where the title starts with the given number pattern.

        Args:
            numbers: List of episode numbers to find.

        Returns:
            List of Episode objects matching the given numbers.
        """
        if not numbers:
            return []

        with get_cursor(commit=False) as cursor:
            # Build OR conditions for each episode number pattern
            conditions = []
            params = []
            for num in numbers:
                conditions.append("title LIKE %s")
                params.append(f"{num} -%")

            query = f"""
                SELECT * FROM episodes
                WHERE {" OR ".join(conditions)}
                ORDER BY published_at DESC
            """
            cursor.execute(query, tuple(params))
            return [Episode(**row) for row in cursor.fetchall()]


class TranscriptRepository:
    """Data access for transcript segments."""

    def bulk_insert(self, segments: list[TranscriptSegment]) -> None:
        """Insert multiple transcript segments efficiently."""
        if not segments:
            return

        with get_cursor() as cursor:
            values = [
                (s.episode_id, s.word, s.start_time, s.end_time, s.segment_index)
                for s in segments
            ]
            cursor.executemany(
                """
                INSERT INTO transcript_segments (episode_id, word, start_time, end_time, segment_index)
                VALUES (%s, %s, %s, %s, %s)
                """,
                values
            )

    def search(self, query: str, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Search for words/phrases in transcripts.
        Returns matches with episode info and timestamps.
        """
        with get_cursor(commit=False) as cursor:
            # Use trigram similarity for fuzzy prefix matching
            cursor.execute(
                """
                SELECT
                    ts.word,
                    ts.start_time,
                    ts.end_time,
                    e.id as episode_id,
                    e.title as episode_title,
                    e.patreon_id,
                    e.published_at
                FROM transcript_segments ts
                JOIN episodes e ON ts.episode_id = e.id
                WHERE ts.word ILIKE %s
                ORDER BY e.published_at DESC, ts.start_time
                LIMIT %s OFFSET %s
                """,
                (f"%{query}%", limit, offset)
            )
            return [dict(row) for row in cursor.fetchall()]

    def search_phrase(self, words: list[str], limit: int = 100) -> list[dict]:
        """
        Search for a phrase (consecutive words) in transcripts.
        Returns the starting timestamp of the phrase.
        """
        if not words:
            return []

        with get_cursor(commit=False) as cursor:
            # Find first word, then verify consecutive words follow
            cursor.execute(
                """
                WITH first_words AS (
                    SELECT ts.*, e.title as episode_title, e.patreon_id, e.published_at
                    FROM transcript_segments ts
                    JOIN episodes e ON ts.episode_id = e.id
                    WHERE ts.word ILIKE %s
                )
                SELECT * FROM first_words
                ORDER BY published_at DESC, start_time
                LIMIT %s
                """,
                (f"%{words[0]}%", limit)
            )
            return [dict(row) for row in cursor.fetchall()]
