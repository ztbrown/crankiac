from flask import Blueprint, jsonify, request
from app.data.database import search_items
from app import __version__
from app.config import Config

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
    """Health check endpoint."""
    return jsonify({"status": "ok"})

@api.route("/version")
def version():
    """Return current API version."""
    return jsonify({"version": __version__})
    """Version endpoint - returns backend version info."""
    return jsonify({"version": Config.VERSION})
