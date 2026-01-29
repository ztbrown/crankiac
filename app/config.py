import os

class Config:
    VERSION = "0.1.0"
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "app/data/app.db")
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", 5000))

    @staticmethod
    def get_cors_origins():
        """Get allowed CORS origins from CORS_ORIGINS environment variable.

        Supports:
        - "*" for all origins (default, for development)
        - Comma-separated list of origins for production
          e.g., "https://myapp.railway.app,https://custom-domain.com"
        """
        origins_str = os.environ.get("CORS_ORIGINS", "*")
        if origins_str == "*":
            return "*"
        return [origin.strip() for origin in origins_str.split(",") if origin.strip()]
