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


def youtube_sync(args):
    """Sync YouTube URLs for episodes."""
    from app.db.repository import EpisodeRepository
    from app.youtube.client import YouTubeClient, match_episode_to_video

    print("Fetching YouTube videos...")
    yt_client = YouTubeClient()
    videos = yt_client.get_videos(max_results=100)
    print(f"  Found {len(videos)} videos")

    repo = EpisodeRepository()

    if args.all:
        episodes = repo.get_all()
    else:
        episodes = repo.get_without_youtube()

    print(f"Matching {len(episodes)} episodes...")

    matched = 0
    for episode in episodes:
        video = match_episode_to_video(
            episode.title,
            episode.published_at,
            videos,
            date_tolerance_days=args.tolerance,
        )
        if video:
            if args.dry_run:
                print(f"  [DRY RUN] Would match: {episode.title[:50]}... -> {video.title[:50]}...")
            else:
                repo.update_youtube_url(episode.id, video.url)
                print(f"  Matched: {episode.title[:50]}... -> {video.url}")
            matched += 1

    print(f"\nResults:")
    print(f"  Episodes checked: {len(episodes)}")
    print(f"  Matched: {matched}")
    if args.dry_run:
        print("  (Dry run - no changes made)")

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

    # youtube-sync command
    yt_parser = subparsers.add_parser("youtube-sync", help="Sync YouTube URLs for free episodes")
    yt_parser.add_argument("--all", action="store_true", help="Re-match all episodes (not just those without YouTube URLs)")
    yt_parser.add_argument("--dry-run", action="store_true", help="Show matches without updating database")
    yt_parser.add_argument("--tolerance", type=int, default=7, help="Date tolerance in days for matching (default: 7)")

    args = parser.parse_args()

    if args.command == "migrate":
        migrate()
    elif args.command == "process":
        process(args)
    elif args.command == "youtube-sync":
        youtube_sync(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
