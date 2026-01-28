#!/usr/bin/env python3
"""Database management CLI."""
import argparse
import sys

def migrate():
    """Run database migrations."""
    from app.db.connection import run_migrations
    print("Running migrations...")
    run_migrations()
    print("Migrations complete.")

def main():
    parser = argparse.ArgumentParser(description="Crankiac management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("migrate", help="Run database migrations")

    args = parser.parse_args()

    if args.command == "migrate":
        migrate()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
