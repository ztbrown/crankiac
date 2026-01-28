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

    pipeline = EpisodePipeline(
        whisper_model=args.model,
        cleanup_audio=not args.no_cleanup
    )

    process_limit = None if args.all else args.limit
    print(f"Running pipeline (sync={not args.no_sync}, limit={'all' if args.all else args.limit}, cleanup={not args.no_cleanup})...")
    results = pipeline.run(
        sync=not args.no_sync,
        max_sync=args.max_sync,
        process_limit=process_limit
    )

    print(f"\nResults:")
    print(f"  Episodes synced: {results['synced']}")
    print(f"  Processed: {results['processed']['success']}/{results['processed']['total']} succeeded")
    if results['processed']['skipped']:
        print(f"  Skipped (no audio): {results['processed']['skipped']}")
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
    process_parser.add_argument("--all", action="store_true", help="Process all unprocessed episodes (overrides --limit)")
    process_parser.add_argument("--model", default="base", help="Whisper model (tiny/base/small/medium/large)")
    process_parser.add_argument("--no-cleanup", action="store_true", help="Keep audio files after transcription")

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
