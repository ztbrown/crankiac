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
    print(f"Running pipeline (sync={not args.no_sync}, limit={'all' if args.all else args.limit}, offset={args.offset}, cleanup={not args.no_cleanup})...")
    results = pipeline.run(
        sync=not args.no_sync,
        max_sync=args.max_sync,
        process_limit=process_limit,
        offset=args.offset
    )

    print(f"\nResults:")
    print(f"  Episodes synced: {results['synced']}")
    print(f"  Processed: {results['processed']['success']}/{results['processed']['total']} succeeded")
    if results['processed']['skipped']:
        print(f"  Skipped (no audio): {results['processed']['skipped']}")
    if results['processed']['failed']:
        print(f"  Failed: {results['processed']['failed']}")


def youtube_fetch(args):
    """Fetch YouTube videos and save to JSON."""
    from app.youtube.client import fetch_and_save_videos

    output_path = args.output or "app/data/youtube_videos.json"
    use_api = not args.rss_only

    print(f"Fetching YouTube videos (use_api={use_api}, max={args.max})...")
    videos = fetch_and_save_videos(
        output_path=output_path,
        use_api=use_api,
        max_results=args.max,
    )
    print(f"  Saved {len(videos)} videos to {output_path}")


def youtube_sync(args):
    """Sync YouTube URLs for episodes."""
    import os
    from app.db.repository import EpisodeRepository
    from app.youtube.client import (
        YouTubeClient,
        match_episode_to_video_detailed,
        load_videos_from_json,
        is_free_monday_episode,
    )

    # Load videos from JSON file or fetch fresh
    json_path = args.json or "app/data/youtube_videos.json"

    if args.fetch or not os.path.exists(json_path):
        print("Fetching YouTube videos...")
        yt_client = YouTubeClient()
        if yt_client.api_key:
            videos = yt_client.get_videos_with_duration(max_results=500)
        else:
            videos = yt_client.get_videos(max_results=100)
        print(f"  Fetched {len(videos)} videos")
    else:
        print(f"Loading YouTube videos from {json_path}...")
        videos = load_videos_from_json(json_path)
        print(f"  Loaded {len(videos)} videos")

    repo = EpisodeRepository()

    if args.all:
        episodes = repo.get_all()
    else:
        episodes = repo.get_without_youtube()

    print(f"Matching {len(episodes)} episodes...")

    matched = 0
    ambiguous = 0
    ambiguous_matches = []

    for episode in episodes:
        result = match_episode_to_video_detailed(
            episode.title,
            episode.published_at,
            videos,
            date_tolerance_days=args.tolerance,
        )

        if result.video:
            is_free = is_free_monday_episode(result.video)
            status_prefix = "[AMBIGUOUS] " if result.is_ambiguous else ""

            if result.is_ambiguous:
                ambiguous += 1
                ambiguous_matches.append({
                    "episode": episode,
                    "result": result,
                })

            if args.dry_run:
                print(f"  {status_prefix}[DRY RUN] Would match (score={result.score}): {episode.title[:40]}...")
                print(f"    -> {result.video.title[:50]}...")
                if result.is_ambiguous and result.runner_up:
                    print(f"    Runner-up (score={result.runner_up_score}): {result.runner_up.title[:50]}...")
            else:
                repo.update_free_status(episode.id, result.video.url, is_free)
                print(f"  {status_prefix}Matched (score={result.score}): {episode.title[:40]}...")
                print(f"    -> {result.video.url}")
                if result.is_ambiguous and result.runner_up:
                    print(f"    Runner-up (score={result.runner_up_score}): {result.runner_up.title[:50]}...")
            matched += 1

    print(f"\nResults:")
    print(f"  Episodes checked: {len(episodes)}")
    print(f"  Matched: {matched}")
    print(f"  Ambiguous (needs review): {ambiguous}")
    if args.dry_run:
        print("  (Dry run - no changes made)")

    # Print ambiguous matches summary for manual review
    if ambiguous_matches and args.verbose:
        print(f"\n=== Ambiguous Matches (Manual Review Required) ===")
        for item in ambiguous_matches:
            ep = item["episode"]
            res = item["result"]
            print(f"\nEpisode: {ep.title}")
            print(f"  Published: {ep.published_at}")
            print(f"  Match 1 (score={res.score}): {res.video.title}")
            print(f"    URL: {res.video.url}")
            print(f"    Reasons: {', '.join(res.match_reasons)}")
            if res.runner_up:
                print(f"  Match 2 (score={res.runner_up_score}): {res.runner_up.title}")
                print(f"    URL: {res.runner_up.url}")

def youtube_backfill(args):
    """Backfill youtube_url for episodes that don't have one."""
    import os
    from app.db.repository import EpisodeRepository
    from app.youtube.client import (
        match_episode_to_video_detailed,
        load_videos_from_json,
    )

    # Load videos from JSON file
    json_path = args.json or "app/data/youtube_videos.json"

    if not os.path.exists(json_path):
        print(f"Error: YouTube videos JSON not found at {json_path}")
        print("Run 'python manage.py youtube-fetch' first to fetch video data.")
        return

    print(f"Loading YouTube videos from {json_path}...")
    videos = load_videos_from_json(json_path)
    print(f"  Loaded {len(videos)} videos")

    repo = EpisodeRepository()
    episodes = repo.get_without_youtube()
    print(f"Found {len(episodes)} episodes without youtube_url")

    if not episodes:
        print("Nothing to backfill.")
        return

    matched = 0
    unmatched = 0
    ambiguous = 0
    unmatched_episodes = []

    print(f"\nMatching episodes...")
    for episode in episodes:
        result = match_episode_to_video_detailed(
            episode.title,
            episode.published_at,
            videos,
            date_tolerance_days=args.tolerance,
        )

        if result.video:
            if result.is_ambiguous:
                ambiguous += 1
                status = "[AMBIGUOUS] "
            else:
                status = ""

            if args.dry_run:
                print(f"  {status}[DRY RUN] Would update: {episode.title[:50]}...")
                print(f"    -> {result.video.url}")
            else:
                repo.update_youtube_url(episode.id, result.video.url)
                print(f"  {status}Updated: {episode.title[:50]}...")
                print(f"    -> {result.video.url}")
            matched += 1
        else:
            unmatched += 1
            unmatched_episodes.append(episode)
            if args.verbose:
                print(f"  [NO MATCH] {episode.title[:60]}...")
                print(f"    Published: {episode.published_at}, Best score: {result.score}")

    print(f"\n=== Backfill Results ===")
    print(f"  Episodes checked: {len(episodes)}")
    print(f"  Matched: {matched}")
    print(f"  Ambiguous (matched but needs review): {ambiguous}")
    print(f"  Unmatched: {unmatched}")
    if args.dry_run:
        print("  (Dry run - no changes made)")

    # Log unmatched episodes
    if unmatched_episodes:
        print(f"\n=== Unmatched Episodes ({len(unmatched_episodes)}) ===")
        for ep in unmatched_episodes[:20]:  # Limit output
            print(f"  - {ep.title[:60]}...")
            print(f"    Published: {ep.published_at}")
        if len(unmatched_episodes) > 20:
            print(f"  ... and {len(unmatched_episodes) - 20} more")


def backfill_is_free(args):
    """Backfill is_free=TRUE for episodes that have youtube_url."""
    from app.db.repository import EpisodeRepository

    repo = EpisodeRepository()

    if args.dry_run:
        # Count how many would be updated
        from app.db.connection import get_cursor
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM episodes WHERE youtube_url IS NOT NULL AND is_free = FALSE"
            )
            count = cursor.fetchone()[0]
        print(f"[DRY RUN] Would update {count} episodes (youtube_url set but is_free=FALSE)")
    else:
        updated = repo.backfill_is_free_from_youtube_url()
        print(f"Updated {updated} episodes: set is_free=TRUE where youtube_url was set")


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
    process_parser.add_argument("--offset", type=int, default=0, help="Number of episodes to skip before processing")
    process_parser.add_argument("--all", action="store_true", help="Process all unprocessed episodes (overrides --limit)")
    process_parser.add_argument("--model", default="base", help="Whisper model (tiny/base/small/medium/large)")
    process_parser.add_argument("--no-cleanup", action="store_true", help="Keep audio files after transcription")

    # youtube-fetch command
    fetch_parser = subparsers.add_parser("youtube-fetch", help="Fetch YouTube videos and save to JSON")
    fetch_parser.add_argument("--output", "-o", help="Output JSON file path (default: app/data/youtube_videos.json)")
    fetch_parser.add_argument("--max", type=int, default=500, help="Max videos to fetch (default: 500)")
    fetch_parser.add_argument("--rss-only", action="store_true", help="Use RSS feed only (no API key needed, ~15 videos)")

    # youtube-sync command
    yt_parser = subparsers.add_parser("youtube-sync", help="Sync YouTube URLs for free episodes")
    yt_parser.add_argument("--all", action="store_true", help="Re-match all episodes (not just those without YouTube URLs)")
    yt_parser.add_argument("--dry-run", action="store_true", help="Show matches without updating database")
    yt_parser.add_argument("--tolerance", type=int, default=7, help="Date tolerance in days for matching (default: 7)")
    yt_parser.add_argument("--json", help="Path to YouTube videos JSON file (default: app/data/youtube_videos.json)")
    yt_parser.add_argument("--fetch", action="store_true", help="Fetch fresh videos instead of using JSON file")
    yt_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed ambiguous match info for manual review")

    # youtube-backfill command
    backfill_parser = subparsers.add_parser("youtube-backfill", help="Backfill youtube_url for episodes (also sets is_free=TRUE)")
    backfill_parser.add_argument("--dry-run", action="store_true", help="Show matches without updating database")
    backfill_parser.add_argument("--tolerance", type=int, default=7, help="Date tolerance in days for matching (default: 7)")
    backfill_parser.add_argument("--json", help="Path to YouTube videos JSON file (default: app/data/youtube_videos.json)")
    backfill_parser.add_argument("--verbose", "-v", action="store_true", help="Show unmatched episodes details")

    # backfill-is-free command
    is_free_parser = subparsers.add_parser("backfill-is-free", help="Set is_free=TRUE for episodes that have youtube_url")
    is_free_parser.add_argument("--dry-run", action="store_true", help="Show count without updating database")

    args = parser.parse_args()

    if args.command == "migrate":
        migrate()
    elif args.command == "process":
        process(args)
    elif args.command == "youtube-fetch":
        youtube_fetch(args)
    elif args.command == "youtube-sync":
        youtube_sync(args)
    elif args.command == "youtube-backfill":
        youtube_backfill(args)
    elif args.command == "backfill-is-free":
        backfill_is_free(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
