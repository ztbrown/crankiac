from typing import Dict, Optional
from flask import Blueprint, jsonify, request
from app.db.connection import get_cursor

transcript_api = Blueprint("transcript_api", __name__, url_prefix="/api/transcripts")


def get_speaker_mappings_for_episode(episode_id: int) -> Dict[str, str]:
    """
    Get speaker label to name mappings for an episode.

    Returns:
        Dict mapping speaker_label -> speaker_name (e.g., {"SPEAKER_00": "Matt"})
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT speaker_label, speaker_name
            FROM speaker_mappings
            WHERE episode_id = %s
            """,
            (episode_id,)
        )
        return {row["speaker_label"]: row["speaker_name"] for row in cursor.fetchall()}


def apply_speaker_mapping(speaker_label: Optional[str], mappings: Dict[str, str]) -> Optional[str]:
    """Apply speaker mapping if available, otherwise return original label."""
    if speaker_label is None:
        return None
    return mappings.get(speaker_label, speaker_label)

@transcript_api.route("/search")
def search_transcripts():
    """
    Search for words or phrases in transcripts.

    Query params:
        q: Search query (word or phrase)
        limit: Max results (default 100, max 500)
        offset: Pagination offset (default 0)
        date_from: Filter by start date (ISO format, e.g., 2023-01-01)
        date_to: Filter by end date (ISO format, e.g., 2023-12-31)
        episode_number: Filter by episode number (parsed from title)
        content_type: Filter by content type ('free', 'premium', or 'all')

    Returns:
        JSON with matches including episode info and timestamps.
    """
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 100)), 500)
    offset = int(request.args.get("offset", 0))

    # Parse filter parameters
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    episode_number = request.args.get("episode_number", "").strip()
    content_type = request.args.get("content_type", "all").strip().lower()

    filters = {
        "date_from": date_from if date_from else None,
        "date_to": date_to if date_to else None,
        "episode_number": int(episode_number) if episode_number else None,
        "content_type": content_type if content_type in ("free", "premium") else None,
    }

    if not query:
        return jsonify({"results": [], "query": "", "total": 0})

    # Split query into words for phrase search
    words = query.split()

    if len(words) == 1:
        results, total = search_single_word(query, limit, offset, filters)
    else:
        results, total = search_phrase(words, limit, offset, filters)

    return jsonify({
        "results": results,
        "query": query,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {k: v for k, v in filters.items() if v is not None}
    })


def _build_filter_conditions(filters: dict) -> tuple[str, list]:
    """Build SQL WHERE conditions and parameters from filters."""
    conditions = []
    params = []

    if filters.get("date_from"):
        conditions.append("e.published_at >= %s")
        params.append(filters["date_from"])

    if filters.get("date_to"):
        conditions.append("e.published_at <= %s")
        params.append(filters["date_to"] + " 23:59:59")

    if filters.get("episode_number"):
        # Episode titles have format "NNNN - Title", extract and match the number
        ep_num = filters["episode_number"]
        conditions.append("e.title ~ %s")
        params.append(f"^0*{ep_num} - ")

    if filters.get("content_type") == "free":
        conditions.append("e.is_free = true")
    elif filters.get("content_type") == "premium":
        conditions.append("e.is_free = false")

    return " AND ".join(conditions), params


def search_single_word(word: str, limit: int, offset: int, filters: dict = None) -> tuple[list[dict], int]:
    """Search for a single word using trigram index."""
    filters = filters or {}
    filter_sql, filter_params = _build_filter_conditions(filters)
    filter_clause = f" AND {filter_sql}" if filter_sql else ""

    with get_cursor(commit=False) as cursor:
        # Get total count
        count_query = f"""
            SELECT COUNT(*) as total
            FROM transcript_segments ts
            JOIN episodes e ON ts.episode_id = e.id
            WHERE ts.word ILIKE %s{filter_clause}
        """
        cursor.execute(count_query, [f"%{word}%"] + filter_params)
        total = cursor.fetchone()["total"]

        # Get results with context
        results_query = f"""
            SELECT
                ts.word,
                ts.start_time,
                ts.end_time,
                ts.segment_index,
                ts.speaker,
                e.id as episode_id,
                e.title as episode_title,
                e.patreon_id,
                e.published_at,
                e.youtube_url,
                e.youtube_id,
                e.is_free,
                (
                    SELECT string_agg(ts2.word, ' ' ORDER BY ts2.segment_index)
                    FROM transcript_segments ts2
                    WHERE ts2.episode_id = ts.episode_id
                    AND ts2.segment_index BETWEEN ts.segment_index - 5 AND ts.segment_index + 5
                ) as context
            FROM transcript_segments ts
            JOIN episodes e ON ts.episode_id = e.id
            WHERE ts.word ILIKE %s{filter_clause}
            ORDER BY e.published_at DESC, ts.start_time
            LIMIT %s OFFSET %s
        """
        cursor.execute(results_query, [f"%{word}%"] + filter_params + [limit, offset])

        results = []
        for row in cursor.fetchall():
            result = {
                "word": row["word"],
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]),
                "segment_index": row["segment_index"],
                "speaker": row["speaker"],
                "episode_id": row["episode_id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "is_free": row["is_free"],
                "context": row["context"]
            }
            if row["youtube_id"]:
                start_seconds = int(row["start_time"])
                result["youtube_embed_url"] = f"https://www.youtube.com/embed/{row['youtube_id']}?start={start_seconds}"
            results.append(result)

        return results, total


def search_phrase(words: list[str], limit: int, offset: int, filters: dict = None) -> tuple[list[dict], int]:
    """
    Search for a phrase (consecutive words).
    Finds the first word and verifies subsequent words match.
    """
    if not words:
        return [], 0

    filters = filters or {}
    filter_sql, filter_params = _build_filter_conditions(filters)
    filter_clause = f" AND {filter_sql}" if filter_sql else ""

    first_word = words[0]
    num_words = len(words)

    with get_cursor(commit=False) as cursor:
        # Find potential matches starting with first word
        query = f"""
            WITH potential_matches AS (
                SELECT
                    ts.episode_id,
                    ts.segment_index as start_index,
                    ts.start_time,
                    e.id,
                    e.title as episode_title,
                    e.patreon_id,
                    e.published_at,
                    e.youtube_url,
                    e.youtube_id,
                    e.is_free
                FROM transcript_segments ts
                JOIN episodes e ON ts.episode_id = e.id
                WHERE ts.word ILIKE %s{filter_clause}
            ),
            verified_matches AS (
                SELECT pm.*,
                    (
                        SELECT string_agg(ts2.word, ' ' ORDER BY ts2.segment_index)
                        FROM transcript_segments ts2
                        WHERE ts2.episode_id = pm.episode_id
                        AND ts2.segment_index >= pm.start_index
                        AND ts2.segment_index < pm.start_index + %s
                    ) as matched_phrase,
                    (
                        SELECT ts3.end_time
                        FROM transcript_segments ts3
                        WHERE ts3.episode_id = pm.episode_id
                        AND ts3.segment_index = pm.start_index + %s - 1
                    ) as end_time,
                    (
                        SELECT string_agg(ts4.word, ' ' ORDER BY ts4.segment_index)
                        FROM transcript_segments ts4
                        WHERE ts4.episode_id = pm.episode_id
                        AND ts4.segment_index BETWEEN pm.start_index - 3 AND pm.start_index + %s + 2
                    ) as context
                FROM potential_matches pm
            )
            SELECT * FROM verified_matches
            WHERE lower(matched_phrase) LIKE lower(%s)
            ORDER BY published_at DESC, start_time
            LIMIT %s OFFSET %s
        """
        params = [f"%{first_word}%"] + filter_params + [num_words, num_words, num_words, f"%{' '.join(words)}%", limit, offset]
        cursor.execute(query, params)

        results = []
        for row in cursor.fetchall():
            result = {
                "phrase": row["matched_phrase"],
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]) if row["end_time"] else None,
                "segment_index": row["start_index"],
                "episode_id": row["id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "is_free": row["is_free"],
                "context": row["context"]
            }
            if row["youtube_id"]:
                start_seconds = int(row["start_time"])
                result["youtube_embed_url"] = f"https://www.youtube.com/embed/{row['youtube_id']}?start={start_seconds}"
            results.append(result)

        # Get approximate total (expensive for phrases, so estimate)
        total = len(results) if len(results) < limit else limit * 2

        return results, total


@transcript_api.route("/context")
def get_extended_context():
    """
    Get extended context around a specific position in an episode.

    Query params:
        episode_id: Episode ID
        segment_index: Center segment index
        radius: Number of words before/after (default 50, max 200)

    Returns:
        JSON with extended context and segment info.
        Speaker labels are mapped to names if mappings exist.
    """
    episode_id = request.args.get("episode_id", type=int)
    segment_index = request.args.get("segment_index", type=int)
    radius = min(int(request.args.get("radius", 50)), 200)

    if not episode_id or segment_index is None:
        return jsonify({"error": "episode_id and segment_index required"}), 400

    # Get speaker mappings for this episode
    speaker_mappings = get_speaker_mappings_for_episode(episode_id)

    with get_cursor(commit=False) as cursor:
        # Get the extended context
        cursor.execute(
            """
            SELECT
                ts.word,
                ts.segment_index,
                ts.start_time,
                ts.end_time,
                ts.speaker
            FROM transcript_segments ts
            WHERE ts.episode_id = %s
            AND ts.segment_index BETWEEN %s AND %s
            ORDER BY ts.segment_index
            """,
            (episode_id, segment_index - radius, segment_index + radius)
        )

        segments = cursor.fetchall()
        if not segments:
            return jsonify({"error": "No segments found"}), 404

        # Build context string
        words = [row["word"] for row in segments]
        context = " ".join(words)

        # Find the center segment's position in the word list
        center_word_index = None
        center_speaker = None
        for i, row in enumerate(segments):
            if row["segment_index"] == segment_index:
                center_word_index = i
                center_speaker = apply_speaker_mapping(row["speaker"], speaker_mappings)
                break

        # Build speaker turns for the context (with mapped names and timestamps)
        speaker_turns = []
        current_speaker_label = None
        current_words = []
        current_start_time = None
        for row in segments:
            if row["speaker"] != current_speaker_label:
                if current_words:
                    speaker_turns.append({
                        "speaker": apply_speaker_mapping(current_speaker_label, speaker_mappings),
                        "text": " ".join(current_words),
                        "start_time": float(current_start_time)
                    })
                current_speaker_label = row["speaker"]
                current_words = [row["word"]]
                current_start_time = row["start_time"]
            else:
                current_words.append(row["word"])
        if current_words:
            speaker_turns.append({
                "speaker": apply_speaker_mapping(current_speaker_label, speaker_mappings),
                "text": " ".join(current_words),
                "start_time": float(current_start_time)
            })

        return jsonify({
            "context": context,
            "episode_id": episode_id,
            "center_segment_index": segment_index,
            "center_word_index": center_word_index,
            "center_speaker": center_speaker,
            "speaker_turns": speaker_turns,
            "start_time": float(segments[0]["start_time"]),
            "end_time": float(segments[-1]["end_time"]),
            "word_count": len(words)
        })


@transcript_api.route("/episodes")
def list_episodes():
    """List all episodes with transcript status."""
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT
                e.id,
                e.patreon_id,
                e.title,
                e.published_at,
                e.processed,
                COUNT(ts.id) as word_count
            FROM episodes e
            LEFT JOIN transcript_segments ts ON e.id = ts.episode_id
            GROUP BY e.id
            ORDER BY e.published_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset)
        )

        episodes = []
        for row in cursor.fetchall():
            episodes.append({
                "id": row["id"],
                "patreon_id": row["patreon_id"],
                "title": row["title"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "processed": row["processed"],
                "word_count": row["word_count"]
            })

        return jsonify({"episodes": episodes})


@transcript_api.route("/speakers")
def list_speakers():
    """
    List all unique speakers across all episodes or for a specific episode.

    Query params:
        episode_id: Optional episode ID to filter by

    Returns:
        JSON with list of speaker names and their word counts.
    """
    episode_id = request.args.get("episode_id", type=int)

    with get_cursor(commit=False) as cursor:
        if episode_id:
            cursor.execute(
                """
                SELECT speaker, COUNT(*) as word_count
                FROM transcript_segments
                WHERE episode_id = %s AND speaker IS NOT NULL
                GROUP BY speaker
                ORDER BY word_count DESC
                """,
                (episode_id,)
            )
        else:
            cursor.execute(
                """
                SELECT speaker, COUNT(*) as word_count
                FROM transcript_segments
                WHERE speaker IS NOT NULL
                GROUP BY speaker
                ORDER BY word_count DESC
                """
            )

        speakers = []
        for row in cursor.fetchall():
            speakers.append({
                "speaker": row["speaker"],
                "word_count": row["word_count"]
            })

        return jsonify({"speakers": speakers})


@transcript_api.route("/on-this-day")
def on_this_day():
    """
    Get episodes from the same month/day in previous years.

    Query params:
        month: Month (1-12), defaults to current month
        day: Day (1-31), defaults to current day
        limit: Max results (default 10)

    Returns:
        JSON with episodes from this day in history.
    """
    from datetime import date

    today = date.today()
    month = request.args.get("month", type=int) or today.month
    day = request.args.get("day", type=int) or today.day
    limit = min(int(request.args.get("limit", 10)), 50)

    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT
                e.id,
                e.patreon_id,
                e.title,
                e.published_at,
                e.youtube_url,
                e.is_free,
                EXTRACT(YEAR FROM e.published_at) as year
            FROM episodes e
            WHERE EXTRACT(MONTH FROM e.published_at) = %s
            AND EXTRACT(DAY FROM e.published_at) = %s
            ORDER BY e.published_at DESC
            LIMIT %s
            """,
            (month, day, limit)
        )

        episodes = []
        for row in cursor.fetchall():
            episodes.append({
                "id": row["id"],
                "patreon_id": row["patreon_id"],
                "title": row["title"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "is_free": row["is_free"],
                "year": int(row["year"]) if row["year"] else None
            })

        return jsonify({
            "episodes": episodes,
            "month": month,
            "day": day,
            "count": len(episodes)
        })


@transcript_api.route("/search/speaker")
def search_by_speaker():
    """
    Search transcripts filtered by speaker.

    Query params:
        q: Search query (word or phrase)
        speaker: Speaker name to filter by
        limit: Max results (default 100, max 500)
        offset: Pagination offset (default 0)

    Returns:
        JSON with matches from the specified speaker.
    """
    query = request.args.get("q", "").strip()
    speaker = request.args.get("speaker", "").strip()
    limit = min(int(request.args.get("limit", 100)), 500)
    offset = int(request.args.get("offset", 0))

    if not speaker:
        return jsonify({"error": "speaker parameter required"}), 400

    with get_cursor(commit=False) as cursor:
        # Build query with speaker filter
        if query:
            cursor.execute(
                """
                SELECT COUNT(*) as total
                FROM transcript_segments ts
                WHERE ts.word ILIKE %s AND ts.speaker = %s
                """,
                (f"%{query}%", speaker)
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*) as total
                FROM transcript_segments ts
                WHERE ts.speaker = %s
                """,
                (speaker,)
            )
        total = cursor.fetchone()["total"]

        # Get results
        if query:
            cursor.execute(
                """
                SELECT
                    ts.word,
                    ts.start_time,
                    ts.end_time,
                    ts.segment_index,
                    ts.speaker,
                    e.id as episode_id,
                    e.title as episode_title,
                    e.patreon_id,
                    e.published_at,
                    e.youtube_url,
                    e.is_free,
                    (
                        SELECT string_agg(ts2.word, ' ' ORDER BY ts2.segment_index)
                        FROM transcript_segments ts2
                        WHERE ts2.episode_id = ts.episode_id
                        AND ts2.segment_index BETWEEN ts.segment_index - 5 AND ts.segment_index + 5
                    ) as context
                FROM transcript_segments ts
                JOIN episodes e ON ts.episode_id = e.id
                WHERE ts.word ILIKE %s AND ts.speaker = %s
                ORDER BY e.published_at DESC, ts.start_time
                LIMIT %s OFFSET %s
                """,
                (f"%{query}%", speaker, limit, offset)
            )
        else:
            # Get all words from speaker (useful for speaker analysis)
            cursor.execute(
                """
                SELECT
                    ts.word,
                    ts.start_time,
                    ts.end_time,
                    ts.segment_index,
                    ts.speaker,
                    e.id as episode_id,
                    e.title as episode_title,
                    e.patreon_id,
                    e.published_at,
                    e.youtube_url,
                    e.is_free,
                    (
                        SELECT string_agg(ts2.word, ' ' ORDER BY ts2.segment_index)
                        FROM transcript_segments ts2
                        WHERE ts2.episode_id = ts.episode_id
                        AND ts2.segment_index BETWEEN ts.segment_index - 5 AND ts.segment_index + 5
                    ) as context
                FROM transcript_segments ts
                JOIN episodes e ON ts.episode_id = e.id
                WHERE ts.speaker = %s
                ORDER BY e.published_at DESC, ts.start_time
                LIMIT %s OFFSET %s
                """,
                (speaker, limit, offset)
            )

        results = []
        for row in cursor.fetchall():
            results.append({
                "word": row["word"],
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]),
                "segment_index": row["segment_index"],
                "speaker": row["speaker"],
                "episode_id": row["episode_id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "is_free": row["is_free"],
                "context": row["context"]
            })

        return jsonify({
            "results": results,
            "query": query,
            "speaker": speaker,
            "total": total,
            "limit": limit,
            "offset": offset
        })


@transcript_api.route("/speaker-mappings")
def get_speaker_mappings():
    """
    Get speaker label to name mappings for an episode.

    Query params:
        episode_id: Episode ID (required)

    Returns:
        JSON with list of mappings (speaker_label -> speaker_name).
    """
    episode_id = request.args.get("episode_id", type=int)

    if not episode_id:
        return jsonify({"error": "episode_id parameter required"}), 400

    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT id, speaker_label, speaker_name, created_at, updated_at
            FROM speaker_mappings
            WHERE episode_id = %s
            ORDER BY speaker_label
            """,
            (episode_id,)
        )

        mappings = []
        for row in cursor.fetchall():
            mappings.append({
                "id": row["id"],
                "speaker_label": row["speaker_label"],
                "speaker_name": row["speaker_name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
            })

        return jsonify({
            "episode_id": episode_id,
            "mappings": mappings
        })


@transcript_api.route("/speaker-mappings", methods=["PUT"])
def set_speaker_mappings():
    """
    Create or update speaker mappings for an episode.

    Request body (JSON):
        episode_id: Episode ID (required)
        mappings: List of {speaker_label, speaker_name} objects

    Returns:
        JSON with the updated mappings.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "JSON body required"}), 400

    episode_id = data.get("episode_id")
    mappings = data.get("mappings", [])

    if not episode_id:
        return jsonify({"error": "episode_id required"}), 400

    if not isinstance(mappings, list):
        return jsonify({"error": "mappings must be a list"}), 400

    with get_cursor(commit=True) as cursor:
        # Verify episode exists
        cursor.execute("SELECT id FROM episodes WHERE id = %s", (episode_id,))
        if not cursor.fetchone():
            return jsonify({"error": f"Episode {episode_id} not found"}), 404

        # Upsert each mapping
        for mapping in mappings:
            speaker_label = mapping.get("speaker_label", "").strip()
            speaker_name = mapping.get("speaker_name", "").strip()

            if not speaker_label or not speaker_name:
                continue

            cursor.execute(
                """
                INSERT INTO speaker_mappings (episode_id, speaker_label, speaker_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (episode_id, speaker_label)
                DO UPDATE SET speaker_name = EXCLUDED.speaker_name, updated_at = CURRENT_TIMESTAMP
                """,
                (episode_id, speaker_label, speaker_name)
            )

        # Return updated mappings
        cursor.execute(
            """
            SELECT id, speaker_label, speaker_name, created_at, updated_at
            FROM speaker_mappings
            WHERE episode_id = %s
            ORDER BY speaker_label
            """,
            (episode_id,)
        )

        result_mappings = []
        for row in cursor.fetchall():
            result_mappings.append({
                "id": row["id"],
                "speaker_label": row["speaker_label"],
                "speaker_name": row["speaker_name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
            })

        return jsonify({
            "episode_id": episode_id,
            "mappings": result_mappings
        })


@transcript_api.route("/speaker-mappings", methods=["DELETE"])
def delete_speaker_mapping():
    """
    Delete a speaker mapping.

    Query params:
        episode_id: Episode ID (required)
        speaker_label: Speaker label to delete (required)

    Returns:
        JSON with success status.
    """
    episode_id = request.args.get("episode_id", type=int)
    speaker_label = request.args.get("speaker_label", "").strip()

    if not episode_id:
        return jsonify({"error": "episode_id parameter required"}), 400

    if not speaker_label:
        return jsonify({"error": "speaker_label parameter required"}), 400

    with get_cursor(commit=True) as cursor:
        cursor.execute(
            """
            DELETE FROM speaker_mappings
            WHERE episode_id = %s AND speaker_label = %s
            RETURNING id
            """,
            (episode_id, speaker_label)
        )

        deleted = cursor.fetchone()
        if not deleted:
            return jsonify({"error": "Mapping not found"}), 404

        return jsonify({
            "success": True,
            "deleted_id": deleted["id"]
        })
