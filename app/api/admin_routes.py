"""Temporary admin routes for one-time operations."""
import os
from functools import wraps
from flask import Blueprint, jsonify, request, Response
from app.db.connection import get_cursor

admin_api = Blueprint("admin_api", __name__, url_prefix="/admin")


def check_auth(username, password):
    """Check if username and password match environment variables."""
    expected_username = os.environ.get("EDITOR_USERNAME", "admin")
    expected_password = os.environ.get("EDITOR_PASSWORD", "changeme")
    return username == expected_username and password == expected_password


def authenticate():
    """Send a 401 response that enables HTTP Basic Auth."""
    return Response(
        'Authentication required. Please provide valid credentials.',
        401,
        {'WWW-Authenticate': 'Basic realm="Admin Login Required"'}
    )


def requires_auth(f):
    """Decorator to require HTTP Basic Auth for a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


@admin_api.route("/preview-title-cleanup", methods=["GET"])
@requires_auth
def preview_title_cleanup():
    """Preview which episodes would be deleted based on title pattern."""
    # Show what will be deleted
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT id, patreon_id, title
            FROM episodes
            WHERE NOT (
                title ~ '^[0-9]' OR
                title ILIKE 'BONUS:%'
            )
            ORDER BY title
        """)
        to_delete = cursor.fetchall()
        to_delete_list = [
            {"id": ep["id"], "patreon_id": ep["patreon_id"], "title": ep["title"]}
            for ep in to_delete
        ]

    # Show what will be kept
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT id, patreon_id, title
            FROM episodes
            WHERE title ~ '^[0-9]' OR title ILIKE 'BONUS:%'
            ORDER BY title
        """)
        to_keep = cursor.fetchall()
        to_keep_list = [
            {"id": ep["id"], "patreon_id": ep["patreon_id"], "title": ep["title"]}
            for ep in to_keep
        ]

    return jsonify({
        "to_delete": to_delete_list,
        "to_delete_count": len(to_delete_list),
        "to_keep": to_keep_list,
        "to_keep_count": len(to_keep_list)
    })


@admin_api.route("/cleanup-episodes", methods=["POST"])
@requires_auth
def cleanup_episodes():
    """Delete all episodes except 1003-1006. ONE-TIME USE ONLY."""
    keep_episodes = ["1003", "1004", "1005", "1006"]

    # Check what we're keeping
    with get_cursor(commit=False) as cursor:
        placeholders = ",".join(["%s"] * len(keep_episodes))
        cursor.execute(
            f"""
            SELECT id, patreon_id, title
            FROM episodes
            WHERE patreon_id IN ({placeholders})
            ORDER BY patreon_id
            """,
            keep_episodes
        )

        keep_eps = cursor.fetchall()
        keep_info = [
            {"id": ep["id"], "patreon_id": ep["patreon_id"], "title": ep["title"]}
            for ep in keep_eps
        ]

    # Count what we're deleting
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) as count
            FROM episodes
            WHERE patreon_id NOT IN ({placeholders})
            """,
            keep_episodes
        )

        delete_count = cursor.fetchone()['count']

    if delete_count == 0:
        return jsonify({
            "status": "no_action",
            "message": "No episodes to delete",
            "kept": keep_info
        })

    # Perform deletion
    with get_cursor() as cursor:
        cursor.execute(
            f"""
            DELETE FROM episodes
            WHERE patreon_id NOT IN ({placeholders})
            """,
            keep_episodes
        )

        deleted = cursor.rowcount

    # Verify
    with get_cursor(commit=False) as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM episodes")
        remaining = cursor.fetchone()['count']

    return jsonify({
        "status": "success",
        "deleted": deleted,
        "remaining": remaining,
        "kept": keep_info
    })
