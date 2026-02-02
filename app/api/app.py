import os
from functools import wraps
from flask import Flask, request, Response
from flask_cors import CORS
from app.api.routes import api
from app.api.transcript_routes import transcript_api
from app.api.audio_routes import audio_api
from app.api.admin_routes import admin_api
from app.data.database import init_db
from app.config import Config

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
        {'WWW-Authenticate': 'Basic realm="Editor Login Required"'}
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

def create_app():
    # Debug: log DATABASE_URL on startup
    db_url = os.environ.get("DATABASE_URL", "NOT SET")
    # Mask password for security
    if "@" in db_url:
        masked = db_url.split("@")[0][:20] + "...@" + db_url.split("@")[1]
    else:
        masked = db_url
    print(f"[STARTUP] DATABASE_URL = {masked}")
    """Application factory."""
    app = Flask(__name__, static_folder="../ui/static", static_url_path="/static")
    CORS(app, origins=Config.get_cors_origins())

    app.register_blueprint(api)
    app.register_blueprint(transcript_api)
    app.register_blueprint(audio_api)
    app.register_blueprint(admin_api)

    # Serve the UI
    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    @app.route("/editor")
    @requires_auth
    def editor():
        return app.send_static_file("editor.html")

    # Initialize database on first request
    with app.app_context():
        init_db()

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
