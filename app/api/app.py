from flask import Flask
from flask_cors import CORS
from app.api.routes import api
from app.api.transcript_routes import transcript_api
from app.api.audio_routes import audio_api
from app.data.database import init_db
from app.config import Config

def create_app():
    """Application factory."""
    app = Flask(__name__, static_folder="../ui/static", static_url_path="/static")
    CORS(app, origins=Config.get_cors_origins())

    app.register_blueprint(api)
    app.register_blueprint(transcript_api)
    app.register_blueprint(audio_api)

    # Serve the UI
    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    # Initialize database on first request
    with app.app_context():
        init_db()

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
