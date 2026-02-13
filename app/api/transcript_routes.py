import re
from typing import Optional
from flask import Blueprint, jsonify, request
from app.db.connection import get_cursor
from app.filters import EpisodeFilter
# Known speakers for display mapping (SPEAKER_XX -> real name)
KNOWN_SPEAKERS = ["Matt", "Will", "Felix", "Amber", "Virgil", "Derek Davison"]

transcript_api = Blueprint("transcript_api", __name__, url_prefix="/api/transcripts")


def map_speaker_to_name(speaker: Optional[str]) -> Optional[str]:
    """
    Map generic speaker labels (SPEAKER_00, SPEAKER_01, etc.) to known host names.

    Args:
        speaker: Speaker label from the transcript, e.g., "SPEAKER_00" or "Matt"

    Returns:
        Known speaker name if mapping exists, otherwise the original label.
        Returns None if input is None.
    """
    if speaker is None:
        return None

    # If already a known speaker name, return as-is
    if speaker in KNOWN_SPEAKERS:
        return speaker

    # Try to extract index from SPEAKER_XX format
    match = re.match(r"^SPEAKER_(\d+)$", speaker)
    if match:
        index = int(match.group(1))
        if index < len(KNOWN_SPEAKERS):
            return KNOWN_SPEAKERS[index]

    # No mapping available, return original
    return speaker

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
        Each result includes:
            - word/phrase: The matched text
            - start_time, end_time: Timestamps in seconds
            - segment_index: Position in transcript
            - episode_id, episode_title, patreon_id: Episode identifiers
            - published_at: Publication date (ISO format)
            - youtube_url: YouTube video URL (null if not available)
            - is_free: Boolean indicating if episode is free content
            - context: Surrounding words for context
    """
    query = request.args.get("q", "").strip()
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    # Parse filter parameters using EpisodeFilter module
    date_from = request.args.get("date_from", "").strip() or None
    date_to = request.args.get("date_to", "").strip() or None
    episode_number_str = request.args.get("episode_number", "").strip()
    episode_number = int(episode_number_str) if episode_number_str else None
    content_type = request.args.get("content_type", "all").strip().lower()

    episode_filter = (
        EpisodeFilter()
        .with_date_from(date_from)
        .with_date_to(date_to)
        .with_episode_number(episode_number)
        .with_content_type(content_type)
    )

    if not query:
        return jsonify({"results": [], "query": "", "total": 0})

    # Split query into words for phrase search
    words = query.split()

    if len(words) == 1:
        results, total = search_single_word(query, limit, offset, episode_filter)
    else:
        results, total = search_phrase(words, limit, offset, episode_filter)

    return jsonify({
        "results": results,
        "query": query,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": episode_filter.to_dict()
    })


def search_single_word(
    word: str, limit: int, offset: int, episode_filter: Optional[EpisodeFilter] = None
) -> tuple[list[dict], int]:
    """Search for a single word using trigram index."""
    episode_filter = episode_filter or EpisodeFilter()
    filter_clause, filter_params = episode_filter.build_clause()

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
                COALESCE(s.name, ts.speaker) as speaker,
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
            LEFT JOIN speakers s ON ts.speaker_id = s.id
            WHERE ts.word ILIKE %s{filter_clause}
            ORDER BY e.published_at DESC, ts.start_time
            LIMIT %s OFFSET %s
        """
        cursor.execute(results_query, [f"%{word}%"] + filter_params + [limit, offset])

        # Import alignment function for YouTube time conversion
        from ..youtube.alignment import get_youtube_time

        # Start YouTube video a few seconds early to provide context
        YOUTUBE_LEAD_TIME = 2  # seconds

        results = []
        for row in cursor.fetchall():
            start_time = float(row["start_time"])
            youtube_start_time = None
            if row["youtube_url"]:
                yt_time = get_youtube_time(row["episode_id"], start_time)
                if yt_time is not None:
                    youtube_start_time = max(0, yt_time - YOUTUBE_LEAD_TIME)

            results.append({
                "word": row["word"],
                "start_time": start_time,
                "end_time": float(row["end_time"]),
                "segment_index": row["segment_index"],
                "speaker": row["speaker"],
                "episode_id": row["episode_id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "youtube_start_time": youtube_start_time,
                "is_free": row["is_free"],
                "context": row["context"]
            })

        return results, total


def search_phrase(
    words: list[str], limit: int, offset: int, episode_filter: Optional[EpisodeFilter] = None
) -> tuple[list[dict], int]:
    """
    Search for a phrase (consecutive words).
    Finds the first word and verifies subsequent words match.
    """
    if not words:
        return [], 0

    episode_filter = episode_filter or EpisodeFilter()
    filter_clause, filter_params = episode_filter.build_clause()

    first_word = words[0]
    num_words = len(words)

    with get_cursor(commit=False) as cursor:
        # Get total count for phrase matches
        count_query = f"""
            WITH potential_matches AS (
                SELECT
                    ts.episode_id,
                    ts.segment_index as start_index
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
                    ) as matched_phrase
                FROM potential_matches pm
            )
            SELECT COUNT(*) as total FROM verified_matches
            WHERE lower(matched_phrase) LIKE lower(%s)
        """
        count_params = [f"%{first_word}%"] + filter_params + [num_words, f"%{' '.join(words)}%"]
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()["total"]

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

        # Import alignment function for YouTube time conversion
        from ..youtube.alignment import get_youtube_time

        # Start YouTube video a few seconds early to provide context
        YOUTUBE_LEAD_TIME = 2  # seconds

        results = []
        for row in cursor.fetchall():
            start_time = float(row["start_time"])
            youtube_start_time = None
            if row["youtube_url"]:
                yt_time = get_youtube_time(row["id"], start_time)
                if yt_time is not None:
                    youtube_start_time = max(0, yt_time - YOUTUBE_LEAD_TIME)

            results.append({
                "phrase": row["matched_phrase"],
                "start_time": start_time,
                "end_time": float(row["end_time"]) if row["end_time"] else None,
                "segment_index": row["start_index"],
                "episode_id": row["id"],
                "episode_title": row["episode_title"],
                "patreon_id": row["patreon_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "youtube_url": row["youtube_url"],
                "youtube_start_time": youtube_start_time,
                "is_free": row["is_free"],
                "context": row["context"]
            })

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
    try:
        radius = min(int(request.args.get("radius", 50)), 200)
    except ValueError:
        return jsonify({"error": "radius must be an integer"}), 400

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
                COALESCE(s.name, ts.speaker) as speaker
            FROM transcript_segments ts
            LEFT JOIN speakers s ON ts.speaker_id = s.id
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
                center_speaker = map_speaker_to_name(row["speaker"])
                break

        # Build speaker turns for the context
        speaker_turns = []
        current_speaker = None
        current_words = []
        for row in segments:
            mapped_speaker = map_speaker_to_name(row["speaker"])
            if mapped_speaker != current_speaker:
                if current_words:
                    speaker_turns.append({
                        "speaker": current_speaker,
                        "text": " ".join(current_words)
                    })
                current_speaker = mapped_speaker
                current_words = [row["word"]]
            else:
                current_words.append(row["word"])
        if current_words:
            speaker_turns.append({
                "speaker": current_speaker,
                "text": " ".join(current_words)
            })

        # Get episode's youtube_url and compute embed URL with offset
        youtube_url = None
        youtube_embed_url = None
        cursor.execute(
            "SELECT youtube_url FROM episodes WHERE id = %s",
            (episode_id,)
        )
        episode_row = cursor.fetchone()
        if episode_row and episode_row["youtube_url"]:
            from ..youtube.alignment import get_youtube_time
            from ..youtube.timestamp import format_youtube_url

            youtube_url = episode_row["youtube_url"]
            # Find center segment's start time
            center_start_time = None
            for row in segments:
                if row["segment_index"] == segment_index:
                    center_start_time = float(row["start_time"])
                    break

            if center_start_time is not None:
                # Start YouTube video a few seconds early to provide context
                YOUTUBE_LEAD_TIME = 2  # seconds

                # Try to get aligned YouTube time
                youtube_time = get_youtube_time(episode_id, center_start_time)
                if youtube_time is not None:
                    try:
                        adjusted_time = max(0, youtube_time - YOUTUBE_LEAD_TIME)
                        youtube_embed_url = format_youtube_url(youtube_url, adjusted_time, "embed")
                    except ValueError:
                        pass
                else:
                    # Fall back to using Patreon time directly (no offset)
                    try:
                        adjusted_time = max(0, center_start_time - YOUTUBE_LEAD_TIME)
                        youtube_embed_url = format_youtube_url(youtube_url, adjusted_time, "embed")
                    except ValueError:
                        pass

        return jsonify({
            "context": context,
            "episode_id": episode_id,
            "center_segment_index": segment_index,
            "center_word_index": center_word_index,
            "center_speaker": center_speaker,
            "speaker_turns": speaker_turns,
            "start_time": float(segments[0]["start_time"]),
            "end_time": float(segments[-1]["end_time"]),
            "word_count": len(words),
            "youtube_url": youtube_url,
            "youtube_embed_url": youtube_embed_url,
        })


@transcript_api.route("/episodes")
def list_episodes():
    """List all episodes with transcript status."""
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

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
    List all speakers from the speakers table.

    Query params:
        q: Optional search term for autocomplete (case-insensitive partial match)
        episode_id: Optional episode ID to get speaker stats for that episode

    Returns:
        JSON with list of speakers. If episode_id provided, includes word_count per speaker.
        Otherwise returns all speakers from speakers table with id, name, created_at.
    """
    from app.transcription.storage import TranscriptStorage

    search = request.args.get("q", "").strip() or None
    episode_id = request.args.get("episode_id", type=int)

    # If episode_id is provided, get speaker stats for that episode
    if episode_id:
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT s.id, s.name, COUNT(*) as word_count
                FROM transcript_segments ts
                JOIN speakers s ON ts.speaker_id = s.id
                WHERE ts.episode_id = %s
                GROUP BY s.id, s.name
                ORDER BY word_count DESC
                """,
                (episode_id,)
            )

            speakers = []
            for row in cursor.fetchall():
                speakers.append({
                    "id": row["id"],
                    "name": row["name"],
                    "word_count": row["word_count"]
                })

            return jsonify({"speakers": speakers, "total": len(speakers)})

    # Otherwise, get all speakers with optional search filter
    storage = TranscriptStorage()
    speakers = storage.get_all_speakers(search=search)

    return jsonify({
        "speakers": speakers,
        "total": len(speakers)
    })


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
    try:
        limit = min(int(request.args.get("limit", 10)), 50)
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400

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
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

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


@transcript_api.route("/episode/<int:episode_id>/speakers")
def get_episode_speakers(episode_id: int):
    """
    Get available speakers for an episode.

    Returns KNOWN_SPEAKERS constant plus distinct speakers from episode's segments.

    Args:
        episode_id: Episode ID

    Returns:
        JSON: {"known_speakers": [...], "episode_speakers": [...]}
        404 if episode doesn't exist
    """
    with get_cursor(commit=False) as cursor:
        # Check if episode exists
        cursor.execute("SELECT id FROM episodes WHERE id = %s", (episode_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Episode not found"}), 404

        # Get distinct speakers from episode's segments
        cursor.execute(
            """
            SELECT DISTINCT speaker
            FROM transcript_segments
            WHERE episode_id = %s AND speaker IS NOT NULL
            ORDER BY speaker
            """,
            (episode_id,)
        )

        episode_speakers = [row["speaker"] for row in cursor.fetchall()]

        return jsonify({
            "known_speakers": KNOWN_SPEAKERS,
            "episode_speakers": episode_speakers
        })


@transcript_api.route("/segments/speaker", methods=["PATCH"])
def update_segment_speakers():
    """
    Update speaker labels for transcript segments.

    Request body:
        {
            "updates": [
                {"id": 123, "speaker": "Matt"},
                {"id": 124, "speaker": "Trey"}
            ]
        }

    Returns:
        JSON with number of segments updated.
    """
    from app.db.models import TranscriptSegment
    from app.transcription.storage import TranscriptStorage
    from decimal import Decimal

    data = request.get_json()
    if not data or "updates" not in data:
        return jsonify({"error": "updates array required in request body"}), 400

    updates = data["updates"]
    if not isinstance(updates, list):
        return jsonify({"error": "updates must be an array"}), 400

    if not updates:
        return jsonify({"error": "updates array cannot be empty"}), 400

    # Validate and convert to TranscriptSegment objects
    segments = []
    for i, update in enumerate(updates):
        if not isinstance(update, dict):
            return jsonify({"error": f"update at index {i} must be an object"}), 400

        if "id" not in update:
            return jsonify({"error": f"update at index {i} missing required field: id"}), 400

        if "speaker" not in update:
            return jsonify({"error": f"update at index {i} missing required field: speaker"}), 400

        try:
            segment_id = int(update["id"])
        except (ValueError, TypeError):
            return jsonify({"error": f"update at index {i}: id must be an integer"}), 400

        speaker = update["speaker"]
        if not isinstance(speaker, str):
            return jsonify({"error": f"update at index {i}: speaker must be a string"}), 400

        # Create a minimal TranscriptSegment with just id and speaker
        # The storage layer only needs these fields for the update
        segment = TranscriptSegment(
            id=segment_id,
            episode_id=0,  # Not needed for update
            word="",  # Not needed for update
            start_time=Decimal(0),  # Not needed for update
            end_time=Decimal(0),  # Not needed for update
            segment_index=0,  # Not needed for update
            speaker=speaker
        )
        segments.append(segment)

    # Perform the update
    storage = TranscriptStorage()
    updated_count = storage.update_speaker_labels(segments)

    return jsonify({
        "updated": updated_count,
        "requested": len(segments)
    })


@transcript_api.route("/episode/<int:episode_id>/segments")
def get_episode_segments(episode_id: int):
    """
    Get paginated transcript segments for an episode.

    Query params:
        limit: Max segments per page (default 100, max 500)
        offset: Pagination offset (default 0)
        speaker: Optional speaker filter

    Returns:
        JSON with segments list, total count, episode info, and available speakers.
    """
    from app.transcription.storage import TranscriptStorage

    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    speaker_filter = request.args.get("speaker", "").strip() or None

    # Get episode info
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            "SELECT id, title FROM episodes WHERE id = %s",
            (episode_id,)
        )
        episode = cursor.fetchone()
        if not episode:
            return jsonify({"error": "Episode not found"}), 404

        # Get available speakers for this episode
        cursor.execute(
            """
            SELECT DISTINCT speaker
            FROM transcript_segments
            WHERE episode_id = %s AND speaker IS NOT NULL
            ORDER BY speaker
            """,
            (episode_id,)
        )
        episode_speakers = [row["speaker"] for row in cursor.fetchall()]

    # Get paginated segments
    storage = TranscriptStorage()
    segments, total = storage.get_segments_paginated(
        episode_id, limit, offset, speaker_filter
    )

    # Convert segments to dict format
    segments_data = [
        {
            "id": seg.id,
            "word": seg.word,
            "start_time": float(seg.start_time),
            "end_time": float(seg.end_time),
            "segment_index": seg.segment_index,
            "speaker": seg.speaker
        }
        for seg in segments
    ]

    return jsonify({
        "segments": segments_data,
        "total": total,
        "episode_id": episode_id,
        "episode_title": episode["title"],
        "episode_speakers": episode_speakers,
        "known_speakers": KNOWN_SPEAKERS,
        "limit": limit,
        "offset": offset,
        "speaker_filter": speaker_filter
    })


@transcript_api.route("/segments/<int:segment_id>/word", methods=["PATCH"])
def update_segment_word(segment_id: int):
    """
    Update word text for a transcript segment.

    Request body:
        {
            "word": "corrected_word"
        }

    Returns:
        JSON with updated segment info.
    """
    from app.transcription.storage import TranscriptStorage

    data = request.get_json()
    if not data or "word" not in data:
        return jsonify({"error": "word field required in request body"}), 400

    new_word = data["word"]
    if not isinstance(new_word, str):
        return jsonify({"error": "word must be a string"}), 400

    new_word = new_word.strip()
    if not new_word:
        return jsonify({"error": "word cannot be empty"}), 400

    if len(new_word) > 200:
        return jsonify({"error": "word too long (max 200 characters)"}), 400

    # Update the word
    storage = TranscriptStorage()
    success = storage.update_word_text(segment_id, new_word)

    if not success:
        return jsonify({"error": "Segment not found"}), 404

    return jsonify({
        "id": segment_id,
        "word": new_word,
        "updated": True
    })


@transcript_api.route("/segments/<int:segment_id>", methods=["DELETE"])
def delete_segment(segment_id: int):
    """
    Delete a transcript segment.

    Returns:
        JSON with deletion confirmation or 404 if not found.
    """
    from app.transcription.storage import TranscriptStorage

    storage = TranscriptStorage()
    success = storage.delete_segment(segment_id)

    if not success:
        return jsonify({"error": "Segment not found"}), 404

    return jsonify({
        "id": segment_id,
        "deleted": True
    })


@transcript_api.route("/segments/<int:segment_id>/insert-after", methods=["POST"])
def insert_segment_after(segment_id: int):
    """
    Insert a new segment after an existing one, copying its timing and speaker.

    Request body:
        {"word": "text"}

    Returns:
        JSON with the new segment ID.
    """
    from app.transcription.storage import TranscriptStorage

    data = request.get_json()
    if not data or not data.get("word"):
        return jsonify({"error": "word is required"}), 400

    storage = TranscriptStorage()
    new_id = storage.insert_segment_after(segment_id, data["word"])

    if new_id is None:
        return jsonify({"error": "Reference segment not found"}), 404

    return jsonify({"id": new_id, "created": True}), 201


# Speaker management endpoints

@transcript_api.route("/speakers", methods=["POST"])
def create_speaker():
    """
    Create a new speaker.

    Request body:
        {
            "name": "Speaker Name"
        }

    Returns:
        JSON with created speaker info or error if speaker already exists.
    """
    from app.transcription.storage import TranscriptStorage

    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "name field required in request body"}), 400

    name = data["name"]
    if not isinstance(name, str):
        return jsonify({"error": "name must be a string"}), 400

    name = name.strip()
    if not name:
        return jsonify({"error": "name cannot be empty"}), 400

    if len(name) > 100:
        return jsonify({"error": "name too long (max 100 characters)"}), 400

    storage = TranscriptStorage()
    speaker = storage.create_speaker(name)

    if not speaker:
        return jsonify({"error": "Speaker already exists"}), 409

    return jsonify(speaker), 201


@transcript_api.route("/episode/<int:episode_id>/paragraphs", methods=["GET"])
def get_episode_paragraphs(episode_id: int):
    """
    Get transcript segments grouped by speaker turns (paragraphs).
    A new paragraph starts when the speaker changes.

    Returns:
        JSON with list of paragraphs, each containing:
            - speaker: Speaker name (or "Unknown Speaker")
            - text: Complete paragraph text
            - start_time: Start time of first word in paragraph
            - end_time: End time of last word in paragraph
            - segment_ids: List of segment IDs that make up this paragraph
    """
    from app.transcription.storage import TranscriptStorage

    # Verify episode exists
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            "SELECT id, title FROM episodes WHERE id = %s",
            (episode_id,)
        )
        episode = cursor.fetchone()

    if not episode:
        return jsonify({"error": "Episode not found"}), 404

    storage = TranscriptStorage()
    paragraphs = storage.get_episode_paragraphs(episode_id)

    return jsonify({
        "episode_id": episode_id,
        "episode_title": episode["title"],
        "paragraphs": paragraphs,
        "total": len(paragraphs)
    })


@transcript_api.route("/assign-speaker", methods=["PATCH"])
def assign_speaker():
    """
    Assign a speaker to a range of transcript segments.
    This is used when a user selects text in the paragraph editor
    and assigns a speaker, which splits paragraphs.

    Request body:
        {
            "episode_id": 123,
            "start_segment_id": 456,
            "end_segment_id": 789,
            "speaker_id": 2
        }

    Returns:
        JSON with number of segments updated.
    """
    from app.transcription.storage import TranscriptStorage

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    required_fields = ["episode_id", "start_segment_id", "end_segment_id", "speaker_id"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"{field} field required"}), 400
        if not isinstance(data[field], int):
            return jsonify({"error": f"{field} must be an integer"}), 400

    episode_id = data["episode_id"]
    start_segment_id = data["start_segment_id"]
    end_segment_id = data["end_segment_id"]
    speaker_id = data["speaker_id"]

    # Verify speaker exists
    with get_cursor(commit=False) as cursor:
        cursor.execute("SELECT id FROM speakers WHERE id = %s", (speaker_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Speaker not found"}), 404

    storage = TranscriptStorage()
    updated = storage.assign_speaker_to_range(
        episode_id, start_segment_id, end_segment_id, speaker_id
    )

    if updated == 0:
        return jsonify({"error": "No segments found in range"}), 404

    return jsonify({
        "updated": updated,
        "episode_id": episode_id,
        "speaker_id": speaker_id
    })
