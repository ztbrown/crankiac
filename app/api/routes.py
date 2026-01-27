from flask import Blueprint, jsonify, request
from app.data.database import search_items

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
