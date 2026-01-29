"""Regression tests for database connection and dotenv loading."""
import os
import pytest
from unittest.mock import patch, MagicMock


class TestDotenvLoading:
    """Tests to verify dotenv loading in connection module."""

    def test_dotenv_is_loaded_on_import(self):
        """Verify that dotenv loading code exists in connection module."""
        from app.db import connection
        import importlib

        # Re-import to ensure dotenv loading runs
        importlib.reload(connection)

        # Verify the module has load_dotenv imported
        assert hasattr(connection, 'load_dotenv')

    def test_connection_string_uses_env_var(self):
        """Verify DATABASE_URL env var is used when set."""
        test_url = "postgresql://testuser:testpass@testhost:5432/testdb"

        with patch.dict(os.environ, {"DATABASE_URL": test_url}):
            from app.db.connection import get_connection_string
            assert get_connection_string() == test_url

    def test_connection_string_has_default(self):
        """Verify default connection string when DATABASE_URL not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove DATABASE_URL if present
            os.environ.pop("DATABASE_URL", None)
            from app.db import connection
            import importlib
            importlib.reload(connection)

            result = connection.get_connection_string()
            assert "postgresql://" in result
            assert "crankiac" in result


class TestEndpointsReturn200:
    """Regression tests to verify all endpoints return 200, not 500."""

    @pytest.fixture
    def client(self):
        """Create a test client with mocked database."""
        with patch("app.data.database.init_db"):
            from app.api.app import create_app
            app = create_app()
            app.config["TESTING"] = True
            with app.test_client() as client:
                yield client

    @pytest.fixture
    def mock_cursor(self):
        """Create a mock cursor for database operations."""
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchall.return_value = []
        mock_ctx.fetchone.return_value = {"total": 0}
        return mock_ctx

    @pytest.mark.integration
    def test_health_endpoint_returns_200(self, client):
        """Health endpoint must return 200."""
        response = client.get("/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    @pytest.mark.integration
    def test_version_endpoint_returns_200(self, client):
        """Version endpoint must return 200."""
        response = client.get("/api/version")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    @pytest.mark.integration
    def test_search_endpoint_returns_200(self, client):
        """Search endpoint must return 200."""
        response = client.get("/api/search")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    @pytest.mark.integration
    def test_transcript_search_returns_200(self, client, mock_cursor):
        """Transcript search endpoint must return 200."""
        with patch("app.api.transcript_routes.get_cursor", return_value=mock_cursor):
            response = client.get("/api/transcripts/search?q=test")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    @pytest.mark.integration
    def test_transcript_episodes_returns_200(self, client, mock_cursor):
        """Episodes endpoint must return 200."""
        with patch("app.api.transcript_routes.get_cursor", return_value=mock_cursor):
            response = client.get("/api/transcripts/episodes")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    @pytest.mark.integration
    def test_transcript_speakers_returns_200(self, client, mock_cursor):
        """Speakers endpoint must return 200."""
        with patch("app.api.transcript_routes.get_cursor", return_value=mock_cursor):
            response = client.get("/api/transcripts/speakers")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    @pytest.mark.integration
    def test_on_this_day_returns_200(self, client, mock_cursor):
        """On-this-day endpoint must return 200."""
        with patch("app.api.transcript_routes.get_cursor", return_value=mock_cursor):
            response = client.get("/api/transcripts/on-this-day")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    @pytest.mark.integration
    def test_audio_info_invalid_id_returns_400_not_500(self, client):
        """Audio info with invalid ID returns 400, not 500."""
        response = client.get("/api/audio/info/invalid-id")
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    @pytest.mark.integration
    def test_audio_stream_invalid_id_returns_400_not_500(self, client):
        """Audio stream with invalid ID returns 400, not 500."""
        response = client.get("/api/audio/stream/invalid-id")
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


class TestConnectionContextManagers:
    """Tests for connection context manager behavior."""

    def test_get_cursor_context_manager(self):
        """Verify get_cursor works as context manager."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("app.db.connection.psycopg2.connect", return_value=mock_conn):
            from app.db.connection import get_cursor

            with get_cursor() as cursor:
                assert cursor is not None

            # Verify cleanup
            mock_conn.commit.assert_called_once()
            mock_cursor.close.assert_called_once()
            mock_conn.close.assert_called_once()

    def test_get_cursor_rollback_on_exception(self):
        """Verify get_cursor rolls back on exception."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("app.db.connection.psycopg2.connect", return_value=mock_conn):
            from app.db.connection import get_cursor

            with pytest.raises(ValueError):
                with get_cursor() as cursor:
                    raise ValueError("test error")

            # Verify rollback was called
            mock_conn.rollback.assert_called_once()
            mock_cursor.close.assert_called_once()
