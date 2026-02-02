"""Temporary admin routes for one-time operations."""
from flask import Blueprint, jsonify
from app.db.connection import get_cursor
from app.api.app import requires_auth

admin_api = Blueprint("admin_api", __name__, url_prefix="/admin")


@admin_api.route("/cleanup-episodes", methods=["POST"])
@requires_auth
def cleanup_episodes():
    """Delete all episodes except 1003-1006. ONE-TIME USE ONLY."""
    keep_episodes = [1003, 1004, 1005, 1006]

    # Check what we're keeping
    with get_cursor(commit=False) as cursor:
        placeholders = ",".join(["%s"] * len(keep_episodes))
        cursor.execute(
            f"""
            SELECT id, episode_number, title
            FROM episodes
            WHERE episode_number IN ({placeholders})
            ORDER BY episode_number
            """,
            keep_episodes
        )

        keep_eps = cursor.fetchall()
        keep_info = [
            {"id": ep["id"], "episode_number": ep["episode_number"], "title": ep["title"]}
            for ep in keep_eps
        ]

    # Count what we're deleting
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) as count
            FROM episodes
            WHERE episode_number IS NULL OR episode_number NOT IN ({placeholders})
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
            WHERE episode_number IS NULL OR episode_number NOT IN ({placeholders})
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
