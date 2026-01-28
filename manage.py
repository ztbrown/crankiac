#!/usr/bin/env python3
"""Crankiac management CLI."""
import argparse
import sys

def migrate():
    """Run database migrations."""
    from app.db.connection import run_migrations
    print("Running migrations...")
    run_migrations()
    print("Migrations complete.")

def process(args):
    """Run the episode processing pipeline."""
    from app.pipeline import EpisodePipeline

    pipeline = EpisodePipeline(whisper_model=args.model)

    print(f"Running pipeline (sync={not args.no_sync}, limit={args.limit})...")
    results = pipeline.run(
        sync=not args.no_sync,
        max_sync=args.max_sync,
        process_limit=args.limit
    )

    print(f"\nResults:")
    print(f"  Episodes synced: {results['synced']}")
    print(f"  Processed: {results['processed']['success']}/{results['processed']['total']} succeeded")
    if results['processed']['failed']:
        print(f"  Failed: {results['processed']['failed']}")

def main():
    parser = argparse.ArgumentParser(description="Crankiac management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # migrate command
    subparsers.add_parser("migrate", help="Run database migrations")

    # process command
    process_parser = subparsers.add_parser("process", help="Process episodes (fetch, download, transcribe)")
    process_parser.add_argument("--no-sync", action="store_true", help="Skip syncing from Patreon")
    process_parser.add_argument("--max-sync", type=int, default=100, help="Max episodes to sync")
    process_parser.add_argument("--limit", type=int, default=10, help="Max episodes to process")
    process_parser.add_argument("--model", default="base", help="Whisper model (tiny/base/small/medium/large)")

    args = parser.parse_args()

    if args.command == "migrate":
        migrate()
    elif args.command == "process":
        process(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
