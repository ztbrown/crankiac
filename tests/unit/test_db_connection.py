"""Regression tests for database connection and environment loading."""
import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
def test_dotenv_loaded_before_env_access():
    """Test that dotenv is loaded before DATABASE_URL is accessed."""
    # This verifies the fix for the DATABASE_URL not loading issue
    with patch.dict(os.environ, {}, clear=True):
        with patch("dotenv.load_dotenv") as mock_load:
            # Re-import to trigger module load
            import importlib
            import app.db.connection as conn_module
            importlib.reload(conn_module)

            # Verify load_dotenv was called (may be called multiple times due to reload)
            assert mock_load.called, "load_dotenv should be called when module loads"


@pytest.mark.unit
def test_get_connection_string_from_env():
    """Test that DATABASE_URL is read from environment."""
    test_url = "postgresql://testuser:testpass@testhost:5432/testdb"
    with patch.dict(os.environ, {"DATABASE_URL": test_url}):
        import importlib
        import app.db.connection as conn_module
        importlib.reload(conn_module)

        result = conn_module.get_connection_string()
        assert result == test_url


@pytest.mark.unit
def test_get_connection_string_fallback():
    """Test fallback when DATABASE_URL is not set."""
    with patch.dict(os.environ, {}, clear=True):
        with patch("dotenv.load_dotenv"):
            import importlib
            import app.db.connection as conn_module
            importlib.reload(conn_module)

            result = conn_module.get_connection_string()
            assert result == "postgresql://localhost:5432/crankiac"


@pytest.mark.unit
def test_get_cursor_context_manager():
    """Test get_cursor returns a working context manager."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("app.db.connection.get_connection") as mock_get_conn:
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        from app.db.connection import get_cursor

        with get_cursor() as cursor:
            assert cursor == mock_cursor

        mock_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()


@pytest.mark.unit
def test_get_cursor_rollback_on_exception():
    """Test get_cursor rolls back on exception."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("app.db.connection.get_connection") as mock_get_conn:
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        from app.db.connection import get_cursor

        with pytest.raises(ValueError):
            with get_cursor() as cursor:
                raise ValueError("test error")

        mock_conn.rollback.assert_called_once()
        mock_cursor.close.assert_called_once()


@pytest.mark.unit
def test_all_api_endpoints_return_200():
    """Regression test: all basic API endpoints should return 200, not 500."""
    with patch("app.data.database.init_db"):
        from app.api.app import create_app
        app = create_app()
        app.config["TESTING"] = True

        with app.test_client() as client:
            # Core endpoints that should always work
            endpoints = [
                "/api/health",
                "/api/version",
                "/api/search",
                "/api/search?q=",
            ]

            for endpoint in endpoints:
                response = client.get(endpoint)
                assert response.status_code == 200, f"{endpoint} returned {response.status_code}"


@pytest.mark.unit
def test_transcript_endpoints_return_200_not_500():
    """Regression test: transcript endpoints should return 200/400, never 500."""
    with patch("app.data.database.init_db"):
        from app.api.app import create_app
        app = create_app()
        app.config["TESTING"] = True

        with app.test_client() as client:
            # These should return 200 with empty results, not 500
            response = client.get("/api/transcripts/search?q=")
            assert response.status_code == 200, f"search returned {response.status_code}"

            # These should return 400 (bad request) for missing params, not 500
            response = client.get("/api/transcripts/context")
            assert response.status_code == 400, f"context returned {response.status_code}"

            # Speaker search without speaker param should return 400, not 500
            response = client.get("/api/transcripts/search/speaker?q=test")
            assert response.status_code == 400, f"speaker search returned {response.status_code}"
