import pytest
from unittest.mock import patch


@pytest.mark.unit
def test_get_cors_origins_default():
    """Test CORS_ORIGINS defaults to '*' when not set."""
    with patch.dict("os.environ", {}, clear=True):
        from app.config import Config
        # Need to reimport to pick up the changed environment
        import importlib
        import app.config
        importlib.reload(app.config)
        from app.config import Config
        assert Config.get_cors_origins() == "*"


@pytest.mark.unit
def test_get_cors_origins_wildcard():
    """Test CORS_ORIGINS='*' returns '*'."""
    with patch.dict("os.environ", {"CORS_ORIGINS": "*"}):
        from app.config import Config
        assert Config.get_cors_origins() == "*"


@pytest.mark.unit
def test_get_cors_origins_single():
    """Test CORS_ORIGINS with single origin returns list."""
    with patch.dict("os.environ", {"CORS_ORIGINS": "https://myapp.railway.app"}):
        from app.config import Config
        assert Config.get_cors_origins() == ["https://myapp.railway.app"]


@pytest.mark.unit
def test_get_cors_origins_multiple():
    """Test CORS_ORIGINS with comma-separated origins returns list."""
    origins = "https://myapp.railway.app,https://custom-domain.com"
    with patch.dict("os.environ", {"CORS_ORIGINS": origins}):
        from app.config import Config
        result = Config.get_cors_origins()
        assert result == ["https://myapp.railway.app", "https://custom-domain.com"]


@pytest.mark.unit
def test_get_cors_origins_strips_whitespace():
    """Test CORS_ORIGINS strips whitespace around origins."""
    origins = "https://myapp.railway.app , https://custom-domain.com "
    with patch.dict("os.environ", {"CORS_ORIGINS": origins}):
        from app.config import Config
        result = Config.get_cors_origins()
        assert result == ["https://myapp.railway.app", "https://custom-domain.com"]


@pytest.mark.unit
def test_get_cors_origins_empty_entries_filtered():
    """Test CORS_ORIGINS filters empty entries from trailing commas."""
    origins = "https://myapp.railway.app,,https://custom-domain.com,"
    with patch.dict("os.environ", {"CORS_ORIGINS": origins}):
        from app.config import Config
        result = Config.get_cors_origins()
        assert result == ["https://myapp.railway.app", "https://custom-domain.com"]
