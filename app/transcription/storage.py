from typing import Optional
from decimal import Decimal
from app.db.connection import get_cursor
from app.db.models import TranscriptSegment
from app.transcription.whisper_transcriber import TranscriptResult, WordSegment

BATCH_SIZE = 1000

class TranscriptStorage:
    """Stores transcripts in PostgreSQL with batch inserts."""

    def store_transcript(self, episode_id: int, result: TranscriptResult) -> int:
        """
        Store a transcript result for an episode.

        Args:
            episode_id: Database ID of the episode.
            result: TranscriptResult from whisper transcription.

        Returns:
            Number of segments stored.
        """
        segments = [
            TranscriptSegment(
                id=None,
                episode_id=episode_id,
                word=seg.word,
                start_time=seg.start_time,
                end_time=seg.end_time,
                segment_index=idx
            )
            for idx, seg in enumerate(result.segments)
        ]

        return self.bulk_insert(segments)

    def bulk_insert(self, segments: list[TranscriptSegment]) -> int:
        """
        Insert transcript segments in batches for performance.

        Args:
            segments: List of TranscriptSegment objects.

        Returns:
            Number of segments inserted.
        """
        if not segments:
            return 0

        total_inserted = 0

        with get_cursor() as cursor:
            # Process in batches
            for i in range(0, len(segments), BATCH_SIZE):
                batch = segments[i:i + BATCH_SIZE]
                values = [
                    (s.episode_id, s.word, str(s.start_time), str(s.end_time), s.segment_index)
                    for s in batch
                ]

                # Use execute_values for efficient batch insert
                args_str = ",".join(
                    cursor.mogrify("(%s, %s, %s, %s, %s)", v).decode("utf-8")
                    for v in values
                )

                cursor.execute(f"""
                    INSERT INTO transcript_segments
                    (episode_id, word, start_time, end_time, segment_index)
                    VALUES {args_str}
                """)

                total_inserted += len(batch)

        return total_inserted

    def delete_episode_transcript(self, episode_id: int) -> int:
        """
        Delete all transcript segments for an episode.

        Args:
            episode_id: Database ID of the episode.

        Returns:
            Number of segments deleted.
        """
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM transcript_segments WHERE episode_id = %s",
                (episode_id,)
            )
            return cursor.rowcount

    def get_episode_word_count(self, episode_id: int) -> int:
        """Get the number of words stored for an episode."""
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM transcript_segments WHERE episode_id = %s",
                (episode_id,)
            )
            row = cursor.fetchone()
            return row["count"] if row else 0

    def has_transcript(self, episode_id: int) -> bool:
        """Check if an episode has any transcript segments."""
        return self.get_episode_word_count(episode_id) > 0
