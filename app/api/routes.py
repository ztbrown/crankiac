from flask import Blueprint, jsonify, request
from app.data.database import search_items, get_connection
from app import __version__

api = Blueprint("api", __name__, url_prefix="/api")

@api.route("/search")
def search():
    """Search endpoint - returns matching items as JSON."""
    query = request.args.get("q", "")

    if not query:
        return jsonify({"results": [], "query": ""})

    results = search_items(query)
    return jsonify({"results": results, "query": query})

@api.route("/health")
def health():
    """Health check endpoint with database connectivity check."""
    db_status = "ok"
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_status = "error"

    status = "ok" if db_status == "ok" else "degraded"
    return jsonify({"status": status, "database": db_status})

@api.route("/version")
def version():
    """Return current API version."""
    return jsonify({"version": __version__})
