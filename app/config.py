import os

class Config:
    VERSION = "0.1.0"
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "app/data/app.db")
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", 5000))
