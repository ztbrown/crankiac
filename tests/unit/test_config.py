import pytest
from unittest.mock import patch


@pytest.mark.unit
class TestCorsOrigins:
    """Tests for CORS origins configuration."""

    def test_cors_origins_default_is_wildcard(self):
        """Test CORS_ORIGINS defaults to wildcard."""
        with patch.dict("os.environ", {}, clear=True):
            # Re-import to pick up new env
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import Config

            assert Config.CORS_ORIGINS == "*"

    def test_cors_origins_from_env(self):
        """Test CORS_ORIGINS is read from environment."""
        with patch.dict("os.environ", {"CORS_ORIGINS": "https://example.com"}):
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import Config

            assert Config.CORS_ORIGINS == "https://example.com"

    def test_get_cors_origins_wildcard(self):
        """Test get_cors_origins returns '*' for wildcard."""
        with patch.dict("os.environ", {"CORS_ORIGINS": "*"}):
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import Config

            result = Config.get_cors_origins()
            assert result == "*"

    def test_get_cors_origins_single_origin(self):
        """Test get_cors_origins returns list for single origin."""
        with patch.dict("os.environ", {"CORS_ORIGINS": "https://app.railway.app"}):
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import Config

            result = Config.get_cors_origins()
            assert result == ["https://app.railway.app"]

    def test_get_cors_origins_multiple_origins(self):
        """Test get_cors_origins parses comma-separated origins."""
        with patch.dict("os.environ", {"CORS_ORIGINS": "https://app.railway.app,https://custom.com"}):
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import Config

            result = Config.get_cors_origins()
            assert result == ["https://app.railway.app", "https://custom.com"]

    def test_get_cors_origins_trims_whitespace(self):
        """Test get_cors_origins trims whitespace from origins."""
        with patch.dict("os.environ", {"CORS_ORIGINS": "  https://app.railway.app , https://custom.com  "}):
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.config import Config

            result = Config.get_cors_origins()
            assert result == ["https://app.railway.app", "https://custom.com"]
