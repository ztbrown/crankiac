"""Audio streaming API with HTTP Range support for seeking."""
import os
import re
from typing import Optional, Tuple
from flask import Blueprint, Response, request, abort, current_app

audio_api = Blueprint("audio_api", __name__, url_prefix="/api/audio")

# Default audio directory relative to app root
AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "downloads", "audio")


def get_audio_path(patreon_id: str) -> Optional[str]:
    """Get the path to an audio file for a given patreon_id."""
    audio_path = os.path.join(AUDIO_DIR, f"{patreon_id}.mp3")
    if os.path.exists(audio_path):
        return audio_path
    return None


def parse_range_header(range_header: str, file_size: int) -> Optional[Tuple[int, int]]:
    """Parse HTTP Range header and return (start, end) bytes."""
    if not range_header:
        return None

    match = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not match:
        return None

    start_str, end_str = match.groups()

    if start_str:
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
    elif end_str:
        # Suffix range: last N bytes
        start = max(0, file_size - int(end_str))
        end = file_size - 1
    else:
        return None

    # Validate range
    if start > end or start >= file_size:
        return None

    end = min(end, file_size - 1)
    return start, end


@audio_api.route("/stream/<patreon_id>")
def stream_audio(patreon_id: str):
    """
    Stream audio file with HTTP Range support for seeking.

    Supports partial content requests (HTTP 206) for efficient seeking.

    Args:
        patreon_id: The Patreon post ID for the episode

    Returns:
        Audio stream with appropriate headers for seeking.
    """
    # Validate patreon_id format (prevent path traversal)
    if not re.match(r"^\d+$", patreon_id):
        abort(400, description="Invalid patreon_id format")

    audio_path = get_audio_path(patreon_id)
    if not audio_path:
        abort(404, description="Audio file not found")

    file_size = os.path.getsize(audio_path)
    range_header = request.headers.get("Range")

    if range_header:
        # Partial content request
        range_result = parse_range_header(range_header, file_size)
        if range_result is None:
            abort(416, description="Requested range not satisfiable")

        start, end = range_result
        length = end - start + 1

        def generate():
            with open(audio_path, "rb") as f:
                f.seek(start)
                remaining = length
                chunk_size = 8192
                while remaining > 0:
                    read_size = min(chunk_size, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        response = Response(
            generate(),
            status=206,
            mimetype="audio/mpeg",
            direct_passthrough=True
        )
        response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        response.headers["Content-Length"] = length
    else:
        # Full file request
        def generate():
            with open(audio_path, "rb") as f:
                chunk_size = 8192
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break
                    yield data

        response = Response(
            generate(),
            status=200,
            mimetype="audio/mpeg",
            direct_passthrough=True
        )
        response.headers["Content-Length"] = file_size

    # Common headers for streaming
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Cache-Control"] = "public, max-age=86400"

    return response


@audio_api.route("/info/<patreon_id>")
def audio_info(patreon_id: str):
    """
    Get audio file info for a given episode.

    Args:
        patreon_id: The Patreon post ID for the episode

    Returns:
        JSON with audio availability and metadata.
    """
    # Validate patreon_id format
    if not re.match(r"^\d+$", patreon_id):
        abort(400, description="Invalid patreon_id format")

    audio_path = get_audio_path(patreon_id)
    available = audio_path is not None

    result = {
        "patreon_id": patreon_id,
        "available": available,
    }

    if available:
        result["size_bytes"] = os.path.getsize(audio_path)
        result["stream_url"] = f"/api/audio/stream/{patreon_id}"

    return result
