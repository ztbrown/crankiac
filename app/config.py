import os

class Config:
    VERSION = "0.1.0"
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "app/data/app.db")
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", 5000))
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    @classmethod
    def get_cors_origins(cls):
        """Get CORS origins as a list or wildcard.

        Returns '*' for wildcard (all origins allowed), or a list of
        specific origins from comma-separated CORS_ORIGINS env var.

        Examples:
            CORS_ORIGINS='*' -> '*'
            CORS_ORIGINS='https://app.railway.app' -> ['https://app.railway.app']
            CORS_ORIGINS='https://app.railway.app,https://custom.com' -> ['https://app.railway.app', 'https://custom.com']
        """
        if cls.CORS_ORIGINS == "*":
            return "*"
        return [origin.strip() for origin in cls.CORS_ORIGINS.split(",") if origin.strip()]
