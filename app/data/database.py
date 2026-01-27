import sqlite3
from contextlib import contextmanager
from app.config import Config

def init_db():
    """Initialize the database with schema and seed data."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT
            )
        """)

        # Check if we need to seed
        cursor = conn.execute("SELECT COUNT(*) FROM items")
        if cursor.fetchone()[0] == 0:
            seed_data = [
                ("Python", "A versatile programming language"),
                ("JavaScript", "The language of the web"),
                ("Flask", "A lightweight Python web framework"),
                ("SQLite", "A self-contained SQL database engine"),
                ("React", "A JavaScript library for building UIs"),
                ("PostgreSQL", "An advanced open source database"),
                ("Docker", "A platform for containerized applications"),
                ("Git", "A distributed version control system"),
                ("Linux", "An open source operating system"),
                ("Kubernetes", "Container orchestration platform"),
            ]
            conn.executemany(
                "INSERT INTO items (name, description) VALUES (?, ?)",
                seed_data
            )
        conn.commit()

@contextmanager
def get_connection():
    """Get a database connection context manager."""
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def search_items(query: str) -> list[dict]:
    """Search items by name or description."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, name, description FROM items
            WHERE name LIKE ? OR description LIKE ?
            ORDER BY name
            """,
            (f"%{query}%", f"%{query}%")
        )
        return [dict(row) for row in cursor.fetchall()]
