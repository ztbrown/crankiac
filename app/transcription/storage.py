from typing import Optional, TYPE_CHECKING
from decimal import Decimal
from app.db.connection import get_cursor
from app.db.models import TranscriptSegment

# Lazy import to avoid loading whisper in production API
if TYPE_CHECKING:
    from app.transcription.whisper_transcriber import TranscriptResult, WordSegment

BATCH_SIZE = 1000

class TranscriptStorage:
    """Stores transcripts in PostgreSQL with batch inserts."""

    def store_transcript(self, episode_id: int, result: "TranscriptResult") -> int:
        """
        Store a transcript result for an episode.

        Args:
            episode_id: Database ID of the episode.
            result: TranscriptResult from whisper transcription.

        Returns:
            Number of segments stored.
        """
        # Import here to avoid loading whisper in production API
        from app.transcription.whisper_transcriber import TranscriptResult

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

    def _resolve_speaker_id(self, cursor, speaker_name: Optional[str]) -> Optional[int]:
        """Resolve a speaker name to a speaker_id, creating the speaker if needed.

        Args:
            cursor: Database cursor.
            speaker_name: Speaker name to resolve (e.g., "Matt", "SPEAKER_00").

        Returns:
            Speaker ID from the speakers table, or None if speaker_name is None.
        """
        if not speaker_name:
            return None

        # Skip generic diarization labels (SPEAKER_00, etc.) — no need to create entries
        if speaker_name.startswith("SPEAKER_"):
            return None

        # Try to find existing speaker
        cursor.execute(
            "SELECT id FROM speakers WHERE name = %s",
            (speaker_name,)
        )
        row = cursor.fetchone()
        if row:
            return row["id"]

        # Create new speaker
        cursor.execute(
            "INSERT INTO speakers (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = %s RETURNING id",
            (speaker_name, speaker_name)
        )
        row = cursor.fetchone()
        return row["id"] if row else None

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
            # Pre-resolve speaker IDs for all unique speaker names
            unique_speakers = set(s.speaker for s in segments if s.speaker)
            speaker_id_cache = {}
            for speaker_name in unique_speakers:
                speaker_id_cache[speaker_name] = self._resolve_speaker_id(cursor, speaker_name)

            # Process in batches
            for i in range(0, len(segments), BATCH_SIZE):
                batch = segments[i:i + BATCH_SIZE]
                values = [
                    (s.episode_id, s.word, str(s.start_time), str(s.end_time),
                     s.segment_index, s.speaker, speaker_id_cache.get(s.speaker))
                    for s in batch
                ]

                # Use execute_values for efficient batch insert
                args_str = ",".join(
                    cursor.mogrify("(%s, %s, %s, %s, %s, %s, %s)", v).decode("utf-8")
                    for v in values
                )

                cursor.execute(f"""
                    INSERT INTO transcript_segments
                    (episode_id, word, start_time, end_time, segment_index, speaker, speaker_id)
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
            # Pre-resolve speaker IDs for all unique speaker names
            unique_speakers = set(s.speaker for s in segments if s.speaker)
            speaker_id_cache = {}
            for speaker_name in unique_speakers:
                speaker_id_cache[speaker_name] = self._resolve_speaker_id(cursor, speaker_name)

            for batch_start in range(0, len(segments), BATCH_SIZE):
                batch = segments[batch_start:batch_start + BATCH_SIZE]
                for seg in batch:
                    if seg.id is not None:
                        speaker_id = speaker_id_cache.get(seg.speaker)
                        cursor.execute(
                            "UPDATE transcript_segments SET speaker = %s, speaker_id = %s WHERE id = %s",
                            (seg.speaker, speaker_id, seg.id)
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

    def get_segments_paginated(
        self,
        episode_id: int,
        limit: int = 100,
        offset: int = 0,
        speaker: Optional[str] = None
    ) -> tuple[list[TranscriptSegment], int]:
        """
        Get paginated transcript segments for an episode.

        Args:
            episode_id: Database ID of the episode.
            limit: Maximum number of segments to return.
            offset: Number of segments to skip.
            speaker: Optional speaker filter.

        Returns:
            Tuple of (segments list, total count).
        """
        with get_cursor(commit=False) as cursor:
            # Build query with optional speaker filter
            where_clause = "WHERE episode_id = %s"
            params = [episode_id]

            if speaker is not None:
                where_clause += " AND speaker = %s"
                params.append(speaker)

            # Get total count
            cursor.execute(
                f"SELECT COUNT(*) as count FROM transcript_segments {where_clause}",
                params
            )
            total = cursor.fetchone()["count"]

            # Get paginated segments
            cursor.execute(
                f"""
                SELECT id, episode_id, word, start_time, end_time, segment_index, speaker
                FROM transcript_segments
                {where_clause}
                ORDER BY segment_index
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset]
            )

            rows = cursor.fetchall()
            segments = [
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

            return segments, total

    def update_word_text(self, segment_id: int, new_word: str) -> bool:
        """
        Update the word text for a specific transcript segment.

        Args:
            segment_id: ID of the segment to update.
            new_word: New word text.

        Returns:
            True if segment was found and updated, False otherwise.
        """
        if not new_word or not new_word.strip():
            return False

        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE transcript_segments SET word = %s WHERE id = %s",
                (new_word.strip(), segment_id)
            )
            return cursor.rowcount > 0

    def get_all_speakers(self, search: Optional[str] = None) -> list[dict]:
        """
        Get all speakers from the speakers table, optionally filtered by search term.

        Args:
            search: Optional search term for autocomplete (case-insensitive partial match).

        Returns:
            List of speaker dicts with id and name.
        """
        with get_cursor(commit=False) as cursor:
            if search:
                cursor.execute(
                    """
                    SELECT id, name, created_at
                    FROM speakers
                    WHERE name ILIKE %s
                    ORDER BY name
                    """,
                    (f"%{search}%",)
                )
            else:
                cursor.execute(
                    """
                    SELECT id, name, created_at
                    FROM speakers
                    ORDER BY name
                    """
                )

            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                }
                for row in rows
            ]

    def create_speaker(self, name: str) -> Optional[dict]:
        """
        Create a new speaker in the speakers table.

        Args:
            name: Speaker name (must be unique).

        Returns:
            Dict with id, name, and created_at if successful, None if speaker already exists.
        """
        if not name or not name.strip():
            return None

        name = name.strip()

        with get_cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO speakers (name)
                    VALUES (%s)
                    RETURNING id, name, created_at
                    """,
                    (name,)
                )
                row = cursor.fetchone()
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                }
            except Exception:
                # Speaker already exists (UNIQUE constraint violation)
                return None

    def get_episode_paragraphs(self, episode_id: int) -> list[dict]:
        """
        Get transcript segments grouped by speaker turns (paragraphs).
        A new paragraph starts when the speaker changes.

        Args:
            episode_id: Database ID of the episode.

        Returns:
            List of paragraph dicts with speaker, text, start_time, end_time, segment_ids.
        """
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT
                    ts.id,
                    ts.word,
                    ts.start_time,
                    ts.end_time,
                    ts.segment_index,
                    ts.speaker,
                    s.name as speaker_name
                FROM transcript_segments ts
                LEFT JOIN speakers s ON ts.speaker_id = s.id
                WHERE ts.episode_id = %s
                ORDER BY ts.segment_index
                """,
                (episode_id,)
            )

            rows = cursor.fetchall()

            if not rows:
                return []

            # Group consecutive segments by speaker into paragraphs
            paragraphs = []
            current_paragraph = None

            for row in rows:
                speaker = row["speaker_name"] or row["speaker"] or "Unknown Speaker"

                # Start new paragraph if speaker changed or this is the first segment
                if current_paragraph is None or current_paragraph["speaker"] != speaker:
                    if current_paragraph:
                        paragraphs.append(current_paragraph)

                    current_paragraph = {
                        "speaker": speaker,
                        "text": row["word"],
                        "start_time": float(row["start_time"]),
                        "end_time": float(row["end_time"]),
                        "segment_ids": [row["id"]]
                    }
                else:
                    # Add to current paragraph
                    current_paragraph["text"] += " " + row["word"]
                    current_paragraph["end_time"] = float(row["end_time"])
                    current_paragraph["segment_ids"].append(row["id"])

            # Add the last paragraph
            if current_paragraph:
                paragraphs.append(current_paragraph)

            return paragraphs

    def assign_speaker_to_range(
        self,
        episode_id: int,
        start_segment_id: int,
        end_segment_id: int,
        speaker_id: int
    ) -> int:
        """
        Assign a speaker to a range of segments.

        Args:
            episode_id: Database ID of the episode.
            start_segment_id: First segment ID in the range.
            end_segment_id: Last segment ID in the range.
            speaker_id: Speaker ID from speakers table.

        Returns:
            Number of segments updated.
        """
        with get_cursor() as cursor:
            # Get the segment indices for the range
            # Handle both single word (start == end) and range selections
            if start_segment_id == end_segment_id:
                # Single word selection
                cursor.execute(
                    """
                    SELECT segment_index
                    FROM transcript_segments
                    WHERE id = %s AND episode_id = %s
                    """,
                    (start_segment_id, episode_id)
                )
                row = cursor.fetchone()
                if not row:
                    return 0
                start_index = end_index = row["segment_index"]
            else:
                # Range selection
                cursor.execute(
                    """
                    SELECT segment_index
                    FROM transcript_segments
                    WHERE id IN (%s, %s) AND episode_id = %s
                    ORDER BY segment_index
                    """,
                    (start_segment_id, end_segment_id, episode_id)
                )
                rows = cursor.fetchall()

                if len(rows) != 2:
                    return 0

                start_index = rows[0]["segment_index"]
                end_index = rows[1]["segment_index"]

            # Update all segments in the range
            cursor.execute(
                """
                UPDATE transcript_segments
                SET speaker_id = %s
                WHERE episode_id = %s
                AND segment_index BETWEEN %s AND %s
                """,
                (speaker_id, episode_id, start_index, end_index)
            )

            return cursor.rowcount
