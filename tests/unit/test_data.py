import pytest
import tempfile
import os
from unittest.mock import patch

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Patch at the usage site to avoid module import caching issues
    with patch("app.data.database.Config.DATABASE_PATH", db_path):
        from app.data.database import init_db
        init_db()
        yield db_path

    os.unlink(db_path)

@pytest.mark.unit
def test_init_db_creates_table(temp_db):
    """Test that init_db creates the items table."""
    import sqlite3
    conn = sqlite3.connect(temp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
    )
    assert cursor.fetchone() is not None
    conn.close()

@pytest.mark.unit
def test_init_db_seeds_data(temp_db):
    """Test that init_db seeds the database with sample data."""
    import sqlite3
    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("SELECT COUNT(*) FROM items")
    count = cursor.fetchone()[0]
    assert count > 0
    conn.close()

@pytest.mark.unit
def test_search_items_finds_exact_match(temp_db):
    """Test search finds exact name matches."""
    with patch("app.data.database.Config.DATABASE_PATH", temp_db):
        from app.data.database import search_items
        results = search_items("Python")
        assert any(r["name"] == "Python" for r in results)

@pytest.mark.unit
def test_search_items_finds_partial_match(temp_db):
    """Test search finds partial matches."""
    with patch("app.data.database.Config.DATABASE_PATH", temp_db):
        from app.data.database import search_items
        results = search_items("script")
        assert any("script" in r["name"].lower() or "script" in (r["description"] or "").lower()
                   for r in results)

@pytest.mark.unit
def test_search_items_returns_empty_for_no_match(temp_db):
    """Test search returns empty list for no matches."""
    with patch("app.data.database.Config.DATABASE_PATH", temp_db):
        from app.data.database import search_items
        results = search_items("xyznonexistent")
        assert results == []

@pytest.mark.unit
def test_search_items_returns_dict_format(temp_db):
    """Test search returns properly formatted dictionaries."""
    with patch("app.data.database.Config.DATABASE_PATH", temp_db):
        from app.data.database import search_items
        results = search_items("Python")
        assert len(results) > 0
        for r in results:
            assert "id" in r
            assert "name" in r
            assert "description" in r
