import os
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")

def get_connection_string():
    """Get PostgreSQL connection string from environment."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://localhost:5432/crankiac"
    )

@contextmanager
def get_connection():
    """Get a database connection context manager."""
    conn = psycopg2.connect(get_connection_string())
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_cursor(commit=True):
    """Get a database cursor with automatic commit."""
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

def run_migrations(migrations_dir: str = "db/migrations"):
    """Run all SQL migration files in order."""
    import glob

    migration_files = sorted(glob.glob(f"{migrations_dir}/*.sql"))

    with get_cursor() as cursor:
        for migration_file in migration_files:
            print(f"Running migration: {migration_file}")
            with open(migration_file, "r") as f:
                cursor.execute(f.read())
            print(f"  Done: {migration_file}")
