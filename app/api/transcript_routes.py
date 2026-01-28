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

    Returns:
        JSON with matches including episode info and timestamps.
    """
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 100)), 500)
    offset = int(request.args.get("offset", 0))

    if not query:
        return jsonify({"results": [], "query": "", "total": 0})

    # Split query into words for phrase search
    words = query.split()

    if len(words) == 1:
        results, total = search_single_word(query, limit, offset)
    else:
        results, total = search_phrase(words, limit, offset)

    return jsonify({
        "results": results,
        "query": query,
        "total": total,
        "limit": limit,
        "offset": offset
    })


def search_single_word(word: str, limit: int, offset: int) -> tuple[list[dict], int]:
    """Search for a single word using trigram index."""
    with get_cursor(commit=False) as cursor:
        # Get total count
        cursor.execute(
            """
            SELECT COUNT(*) as total
            FROM transcript_segments ts
            WHERE ts.word ILIKE %s
            """,
            (f"%{word}%",)
        )
        total = cursor.fetchone()["total"]

        # Get results with context
        cursor.execute(
            """
            SELECT
                ts.word,
                ts.start_time,
                ts.end_time,
                ts.segment_index,
                e.id as episode_id,
                e.title as episode_title,
                e.patreon_id,
                e.published_at,
                (
                    SELECT string_agg(ts2.word, ' ' ORDER BY ts2.segment_index)
                    FROM transcript_segments ts2
                    WHERE ts2.episode_id = ts.episode_id
                    AND ts2.segment_index BETWEEN ts.segment_index - 5 AND ts.segment_index + 5
                ) as context
            FROM transcript_segments ts
            JOIN episodes e ON ts.episode_id = e.id
            WHERE ts.word ILIKE %s
            ORDER BY e.published_at DESC, ts.start_time
            LIMIT %s OFFSET %s
            """,
            (f"%{word}%", limit, offset)
        )

        results = []
        for row in cursor.fetchall():
            results.append({
                "word": row["word"],
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]),
                "episode_id": row["episode_id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "context": row["context"]
            })

        return results, total


def search_phrase(words: list[str], limit: int, offset: int) -> tuple[list[dict], int]:
    """
    Search for a phrase (consecutive words).
    Finds the first word and verifies subsequent words match.
    """
    if not words:
        return [], 0

    first_word = words[0]
    num_words = len(words)

    with get_cursor(commit=False) as cursor:
        # Find potential matches starting with first word
        cursor.execute(
            """
            WITH potential_matches AS (
                SELECT
                    ts.episode_id,
                    ts.segment_index as start_index,
                    ts.start_time,
                    e.id,
                    e.title as episode_title,
                    e.patreon_id,
                    e.published_at
                FROM transcript_segments ts
                JOIN episodes e ON ts.episode_id = e.id
                WHERE ts.word ILIKE %s
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
            """,
            (f"%{first_word}%", num_words, num_words, num_words, f"%{' '.join(words)}%", limit, offset)
        )

        results = []
        for row in cursor.fetchall():
            results.append({
                "phrase": row["matched_phrase"],
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]) if row["end_time"] else None,
                "episode_id": row["id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "context": row["context"]
            })

        # Get approximate total (expensive for phrases, so estimate)
        total = len(results) if len(results) < limit else limit * 2

        return results, total


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
