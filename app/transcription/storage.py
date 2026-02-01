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
                segment_index=idx,
                speaker=getattr(seg, 'speaker', None)
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
                    (s.episode_id, s.word, str(s.start_time), str(s.end_time), s.segment_index, s.speaker)
                    for s in batch
                ]

                # Use execute_values for efficient batch insert
                args_str = ",".join(
                    cursor.mogrify("(%s, %s, %s, %s, %s, %s)", v).decode("utf-8")
                    for v in values
                )

                cursor.execute(f"""
                    INSERT INTO transcript_segments
                    (episode_id, word, start_time, end_time, segment_index, speaker)
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

    def get_segments_for_diarization(self, episode_id: int) -> list[TranscriptSegment]:
        """
        Get all transcript segments for an episode (for diarization).

        Args:
            episode_id: Database ID of the episode.

        Returns:
            List of TranscriptSegment objects with id, start_time, end_time.
        """
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT id, episode_id, word, start_time, end_time, segment_index, speaker
                FROM transcript_segments
                WHERE episode_id = %s
                ORDER BY segment_index
                """,
                (episode_id,)
            )
            rows = cursor.fetchall()
            return [
                TranscriptSegment(
                    id=row["id"],
                    episode_id=row["episode_id"],
                    word=row["word"],
                    start_time=Decimal(str(row["start_time"])),
                    end_time=Decimal(str(row["end_time"])),
                    segment_index=row["segment_index"],
                    speaker=row["speaker"]
                )
                for row in rows
            ]

    def update_speaker_labels(self, segments: list[TranscriptSegment]) -> int:
        """
        Update speaker labels for existing transcript segments.

        Args:
            segments: List of TranscriptSegment objects with id and speaker set.

        Returns:
            Number of segments updated.
        """
        if not segments:
            return 0

        updated = 0
        with get_cursor() as cursor:
            for batch_start in range(0, len(segments), BATCH_SIZE):
                batch = segments[batch_start:batch_start + BATCH_SIZE]
                for seg in batch:
                    if seg.id is not None:
                        cursor.execute(
                            "UPDATE transcript_segments SET speaker = %s WHERE id = %s",
                            (seg.speaker, seg.id)
                        )
                        updated += cursor.rowcount

        return updated

    def update_speakers_by_ids(self, segment_ids: list[int], speaker: str) -> int:
        """
        Update speaker label for transcript segments by their IDs.

        Args:
            segment_ids: List of transcript segment IDs to update.
            speaker: Speaker label to apply to all segments.

        Returns:
            Number of segments updated.
        """
        if not segment_ids:
            return 0

        updated = 0
        with get_cursor() as cursor:
            for batch_start in range(0, len(segment_ids), BATCH_SIZE):
                batch = segment_ids[batch_start:batch_start + BATCH_SIZE]
                placeholders = ",".join(["%s"] * len(batch))
                cursor.execute(
                    f"UPDATE transcript_segments SET speaker = %s WHERE id IN ({placeholders})",
                    [speaker] + batch
                )
                updated += cursor.rowcount

        return updated
