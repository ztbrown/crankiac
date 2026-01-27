#!/usr/bin/env python3
from app.api.app import create_app
from app.config import Config

if __name__ == "__main__":
    app = create_app()
    print(f"Starting server at http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
