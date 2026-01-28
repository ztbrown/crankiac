from flask import Blueprint, jsonify, request
from app.db.connection import get_cursor

transcript_api = Blueprint("transcript_api", __name__, url_prefix="/api/transcripts")

@transcript_api.route("/search")
def search_transcripts():
    """
    Search for words or phrases in transcripts.

    Query params:
        q: Search query (word or phrase)
        limit: Max results (default 100, max 500)
        offset: Pagination offset (default 0)
        fuzzy: Enable fuzzy matching (default true)
        threshold: Similarity threshold for fuzzy matching (default 0.3, range 0.1-0.9)

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
    fuzzy = request.args.get("fuzzy", "true").lower() != "false"
    threshold = max(0.1, min(0.9, float(request.args.get("threshold", 0.3))))

    # New filter params
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
        if fuzzy:
            results, total = search_fuzzy_word(query, limit, offset, threshold, filters)
        else:
            results, total = search_single_word(query, limit, offset, filters)
    else:
        if fuzzy:
            results, total = search_fuzzy_phrase(words, limit, offset, threshold, filters)
        else:
            results, total = search_phrase(words, limit, offset, filters)

    return jsonify({
        "results": results,
        "query": query,
        "total": total,
        "limit": limit,
        "offset": offset,
        "fuzzy": fuzzy,
        "threshold": threshold if fuzzy else None,
        "filters": {k: v for k, v in filters.items() if v is not None}
    })


def build_filter_clauses(filters: dict) -> tuple[str, list]:
    """Build SQL WHERE clauses and params from filter dict."""
    clauses = []
    params = []

    if filters.get("date_from"):
        clauses.append("e.published_at >= %s")
        params.append(filters["date_from"])

    if filters.get("date_to"):
        clauses.append("e.published_at <= %s")
        params.append(filters["date_to"] + " 23:59:59")

    if filters.get("episode_number"):
        # Match episode number in title patterns like "Episode 123", "123 -", "#123"
        clauses.append("(e.title ~* %s)")
        ep_num = filters["episode_number"]
        params.append(f"(Episode\\s+{ep_num}\\b|\\b{ep_num}\\s*[-–:]|#{ep_num}\\b)")

    if filters.get("content_type") == "free":
        clauses.append("e.youtube_url IS NOT NULL")
    elif filters.get("content_type") == "premium":
        clauses.append("e.youtube_url IS NULL")

    return " AND ".join(clauses) if clauses else "", params


def search_single_word(word: str, limit: int, offset: int, filters: dict = None) -> tuple[list[dict], int]:
    """Search for a single word using trigram index."""
    filters = filters or {}
    filter_sql, filter_params = build_filter_clauses(filters)
    filter_clause = f" AND {filter_sql}" if filter_sql else ""

    with get_cursor(commit=False) as cursor:
        # Get total count
        count_query = f"""
            SELECT COUNT(*) as total
            FROM transcript_segments ts
            JOIN episodes e ON ts.episode_id = e.id
            WHERE ts.word ILIKE %s{filter_clause}
            """
        cursor.execute(count_query, (f"%{word}%", *filter_params))
        total = cursor.fetchone()["total"]

        # Get results with context
        search_query = f"""
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
        cursor.execute(search_query, (f"%{word}%", *filter_params, limit, offset))

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
                "context": row["context"]
            })

        return results, total


def search_fuzzy_word(word: str, limit: int, offset: int, threshold: float, filters: dict = None) -> tuple[list[dict], int]:
    """Search for a single word using trigram similarity for fuzzy matching."""
    filters = filters or {}
    filter_sql, filter_params = build_filter_clauses(filters)
    filter_clause = f" AND {filter_sql}" if filter_sql else ""

    with get_cursor(commit=False) as cursor:
        # Set the similarity threshold for this session
        cursor.execute("SELECT set_limit(%s)", (threshold,))

        # Get total count of fuzzy matches
        count_query = f"""
            SELECT COUNT(*) as total
            FROM transcript_segments ts
            JOIN episodes e ON ts.episode_id = e.id
            WHERE (ts.word %% %s OR ts.word ILIKE %s){filter_clause}
            """
        cursor.execute(count_query, (word, f"%{word}%", *filter_params))
        total = cursor.fetchone()["total"]

        # Get results with context, ordered by similarity
        search_query = f"""
            SELECT
                ts.word,
                ts.start_time,
                ts.end_time,
                ts.segment_index,
                e.id as episode_id,
                e.title as episode_title,
                e.patreon_id,
                e.published_at,
                e.youtube_url,
                similarity(ts.word, %s) as similarity_score,
                (
                    SELECT string_agg(ts2.word, ' ' ORDER BY ts2.segment_index)
                    FROM transcript_segments ts2
                    WHERE ts2.episode_id = ts.episode_id
                    AND ts2.segment_index BETWEEN ts.segment_index - 5 AND ts.segment_index + 5
                ) as context
            FROM transcript_segments ts
            JOIN episodes e ON ts.episode_id = e.id
            WHERE (ts.word %% %s OR ts.word ILIKE %s){filter_clause}
            ORDER BY similarity(ts.word, %s) DESC, e.published_at DESC, ts.start_time
            LIMIT %s OFFSET %s
            """
        cursor.execute(search_query, (word, word, f"%{word}%", *filter_params, word, limit, offset))

        results = []
        for row in cursor.fetchall():
            results.append({
                "word": row["word"],
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]),
                "segment_index": row["segment_index"],
                "episode_id": row["episode_id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "context": row["context"],
                "similarity": round(float(row["similarity_score"]), 3)
            })

        return results, total


def search_fuzzy_phrase(words: list[str], limit: int, offset: int, threshold: float, filters: dict = None) -> tuple[list[dict], int]:
    """
    Search for a phrase with fuzzy matching on individual words.
    Finds sequences where each word is similar to the corresponding query word.
    """
    if not words:
        return [], 0

    filters = filters or {}
    filter_sql, filter_params = build_filter_clauses(filters)
    filter_clause = f" AND {filter_sql}" if filter_sql else ""

    first_word = words[0]
    num_words = len(words)

    with get_cursor(commit=False) as cursor:
        # Set the similarity threshold
        cursor.execute("SELECT set_limit(%s)", (threshold,))

        # Build similarity conditions for each word in the phrase
        # We check if consecutive words are similar to our query words
        query = f"""
            WITH potential_matches AS (
                SELECT
                    ts.episode_id,
                    ts.segment_index as start_index,
                    ts.start_time,
                    similarity(ts.word, %s) as first_word_sim,
                    e.title as episode_title,
                    e.patreon_id,
                    e.published_at,
                    e.youtube_url
                FROM transcript_segments ts
                JOIN episodes e ON ts.episode_id = e.id
                WHERE (ts.word %% %s OR ts.word ILIKE %s){filter_clause}
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
                    ) as context,
                    (
                        SELECT AVG(best_sim)
                        FROM (
                            SELECT
                                ts5.segment_index - pm.start_index as word_pos,
                                GREATEST(
                                    similarity(ts5.word, (SELECT unnest FROM unnest(%s::text[]) WITH ORDINALITY u(unnest, ord) WHERE ord = ts5.segment_index - pm.start_index + 1 LIMIT 1)),
                                    CASE WHEN ts5.word ILIKE '%%' || (SELECT unnest FROM unnest(%s::text[]) WITH ORDINALITY u(unnest, ord) WHERE ord = ts5.segment_index - pm.start_index + 1 LIMIT 1) || '%%' THEN 1.0 ELSE 0.0 END
                                ) as best_sim
                            FROM transcript_segments ts5
                            WHERE ts5.episode_id = pm.episode_id
                            AND ts5.segment_index >= pm.start_index
                            AND ts5.segment_index < pm.start_index + %s
                        ) sims
                    ) as avg_similarity
                FROM potential_matches pm
            )
            SELECT * FROM verified_matches
            WHERE avg_similarity >= %s
            ORDER BY avg_similarity DESC, published_at DESC, start_time
            LIMIT %s OFFSET %s
            """
        cursor.execute(
            query,
            (first_word, first_word, f"%{first_word}%", *filter_params, num_words, num_words, num_words,
             words, words, num_words, threshold, limit, offset)
        )

        results = []
        for row in cursor.fetchall():
            results.append({
                "phrase": row["matched_phrase"],
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]) if row["end_time"] else None,
                "segment_index": row["start_index"],
                "episode_id": row["episode_id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "context": row["context"],
                "similarity": round(float(row["avg_similarity"]), 3) if row["avg_similarity"] else 0.0
            })

        # Get approximate total
        total = len(results) if len(results) < limit else limit * 2

        return results, total


def search_phrase(words: list[str], limit: int, offset: int, filters: dict = None) -> tuple[list[dict], int]:
    """
    Search for a phrase (consecutive words).
    Finds the first word and verifies subsequent words match.
    """
    if not words:
        return [], 0

    filters = filters or {}
    filter_sql, filter_params = build_filter_clauses(filters)
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
                    e.title as episode_title,
                    e.patreon_id,
                    e.published_at,
                    e.youtube_url
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
        cursor.execute(
            query,
            (f"%{first_word}%", *filter_params, num_words, num_words, num_words, f"%{' '.join(words)}%", limit, offset)
        )

        results = []
        for row in cursor.fetchall():
            results.append({
                "phrase": row["matched_phrase"],
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]) if row["end_time"] else None,
                "segment_index": row["start_index"],
                "episode_id": row["episode_id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "context": row["context"]
            })

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
    """
    episode_id = request.args.get("episode_id", type=int)
    segment_index = request.args.get("segment_index", type=int)
    radius = min(int(request.args.get("radius", 50)), 200)

    if not episode_id or segment_index is None:
        return jsonify({"error": "episode_id and segment_index required"}), 400

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
                center_speaker = row["speaker"]
                break

        # Build speaker turns for the context
        speaker_turns = []
        current_speaker = None
        current_words = []
        for row in segments:
            if row["speaker"] != current_speaker:
                if current_words:
                    speaker_turns.append({
                        "speaker": current_speaker,
                        "text": " ".join(current_words)
                    })
                current_speaker = row["speaker"]
                current_words = [row["word"]]
            else:
                current_words.append(row["word"])
        if current_words:
            speaker_turns.append({
                "speaker": current_speaker,
                "text": " ".join(current_words)
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


@transcript_api.route("/on-this-day")
def on_this_day():
    """
    Get episodes from the same calendar date in previous years.

    Query params:
        month: Month (1-12), defaults to current month
        day: Day (1-31), defaults to current day
        limit: Max results (default 50, max 200)

    Returns:
        JSON with episodes from the same month/day in previous years.
    """
    from datetime import date

    today = date.today()
    month = request.args.get("month", type=int, default=today.month)
    day = request.args.get("day", type=int, default=today.day)
    limit = min(int(request.args.get("limit", 50)), 200)

    # Validate month and day
    if not (1 <= month <= 12):
        return jsonify({"error": "month must be between 1 and 12"}), 400
    if not (1 <= day <= 31):
        return jsonify({"error": "day must be between 1 and 31"}), 400

    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT
                e.id,
                e.patreon_id,
                e.title,
                e.published_at,
                e.youtube_url,
                e.processed,
                COUNT(ts.id) as word_count,
                EXTRACT(YEAR FROM e.published_at) as year
            FROM episodes e
            LEFT JOIN transcript_segments ts ON e.id = ts.episode_id
            WHERE EXTRACT(MONTH FROM e.published_at) = %s
            AND EXTRACT(DAY FROM e.published_at) = %s
            AND EXTRACT(YEAR FROM e.published_at) < %s
            GROUP BY e.id
            ORDER BY e.published_at DESC
            LIMIT %s
            """,
            (month, day, today.year, limit)
        )

        episodes = []
        for row in cursor.fetchall():
            episodes.append({
                "id": row["id"],
                "patreon_id": row["patreon_id"],
                "title": row["title"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "processed": row["processed"],
                "word_count": row["word_count"],
                "year": int(row["year"]) if row["year"] else None
            })

        return jsonify({
            "episodes": episodes,
            "date": {"month": month, "day": day},
            "years_ago": [today.year - ep["year"] for ep in episodes if ep["year"]]
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
