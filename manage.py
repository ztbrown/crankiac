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
    from app.db.repository import EpisodeRepository
    from app.episode_filter import filter_episodes, EXCLUDED_SHOWS

    pipeline = EpisodePipeline(
        whisper_model=args.model,
        cleanup_audio=not args.no_cleanup,
        vocabulary_file=args.vocab
    )

    # Handle single episode processing by ID
    if args.episode:
        print(f"Processing single episode ID={args.episode}...")
        try:
            success = pipeline.process_single(args.episode)
            if success:
                print("Episode processed successfully.")
            else:
                print("Episode processing failed.")
                sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    # Handle single episode processing by title search
    if args.title:
        repo = EpisodeRepository()
        matches = repo.search_by_title(args.title)
        if not matches:
            print(f"No episodes found matching '{args.title}'")
            sys.exit(1)
        if len(matches) > 1:
            print(f"Multiple episodes match '{args.title}':")
            for ep in matches[:10]:
                print(f"  ID={ep.id}: {ep.title}")
            if len(matches) > 10:
                print(f"  ... and {len(matches) - 10} more")
            print("\nUse --episode ID to specify which one to process.")
            sys.exit(1)
        episode = matches[0]
        print(f"Processing: {episode.title} (ID={episode.id})...")
        success = pipeline.process_episode(episode)
        if success:
            print("Episode processed successfully.")
        else:
            print("Episode processing failed.")
            sys.exit(1)
        return

    # Batch processing mode
    # Determine filtering mode: --all-shows disables numbered_only filter
    numbered_only = not args.all_shows

    # Parse --include-shows if provided
    include_shows = None
    if args.include_shows:
        include_shows = set(s.strip().lower() for s in args.include_shows.split(','))
        print(f"Including shows: {', '.join(include_shows)}")

    # If --include-shows is used, we need custom filtering
    if include_shows:
        # Sync first if needed
        if not args.no_sync:
            print(f"Syncing episodes from Patreon (max={args.max_sync})...")
            episodes = pipeline.sync_episodes(args.max_sync)
            synced_count = len(episodes)
        else:
            synced_count = 0

        # Get unprocessed episodes and apply custom filtering
        repo = EpisodeRepository()
        all_unprocessed = repo.get_unprocessed(numbered_only=False)  # Get all, we'll filter ourselves

        # Custom filter: include numbered episodes + specifically included shows
        filtered = []
        for ep in all_unprocessed:
            title_lower = ep.title.lower()
            # Check if it's a specifically included show
            is_included_show = any(show in title_lower for show in include_shows)
            # Check if it's an excluded show (but not in include list)
            is_excluded = any(show in title_lower for show in EXCLUDED_SHOWS) and not is_included_show

            if is_excluded:
                continue

            # If numbered_only, also check that it matches number pattern OR is an included show
            if numbered_only:
                from app.episode_filter import is_numbered_episode
                if not is_numbered_episode(ep.title) and not is_included_show:
                    continue

            filtered.append(ep)

        # Apply offset and limit
        process_limit = None if args.all else args.limit
        if process_limit is None:
            episodes_to_process = filtered[args.offset:]
        else:
            episodes_to_process = filtered[args.offset:args.offset + process_limit]

        total = len(episodes_to_process)
        print(f"Found {len(filtered)} matching episodes, processing {total} (offset={args.offset})...")

        stats = {"total": total, "success": 0, "failed": 0, "skipped": 0}
        for i, episode in enumerate(episodes_to_process, 1):
            print(f"[{i}/{total}] {episode.title}")
            if not episode.audio_url:
                stats["skipped"] += 1
                continue
            if pipeline.process_episode(episode):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        print(f"\nResults:")
        print(f"  Episodes synced: {synced_count}")
        print(f"  Processed: {stats['success']}/{stats['total']} succeeded")
        if stats['skipped']:
            print(f"  Skipped (no audio): {stats['skipped']}")
        if stats['failed']:
            print(f"  Failed: {stats['failed']}")
        return

    # Standard batch processing (no --include-shows)
    process_limit = None if args.all else args.limit
    print(f"Running pipeline (sync={not args.no_sync}, limit={'all' if args.all else args.limit}, offset={args.offset}, cleanup={not args.no_cleanup}, numbered_only={numbered_only})...")
    results = pipeline.run(
        sync=not args.no_sync,
        max_sync=args.max_sync,
        process_limit=process_limit,
        offset=args.offset,
        numbered_only=numbered_only
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
                "SELECT COUNT(*) AS count FROM episodes WHERE youtube_url IS NOT NULL AND is_free = FALSE"
            )
            count = cursor.fetchone()["count"]
        print(f"[DRY RUN] Would update {count} episodes (youtube_url set but is_free=FALSE)")
    else:
        updated = repo.backfill_is_free_from_youtube_url()
        print(f"Updated {updated} episodes: set is_free=TRUE where youtube_url was set")


def youtube_align(args):
    """Align Patreon transcripts with YouTube captions to compute timestamp offsets."""
    from app.db.connection import get_cursor
    from app.youtube.alignment import align_episode, store_anchor_points

    # Get episodes with youtube_url and transcripts
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT e.id, e.title, e.youtube_url, e.published_at
            FROM episodes e
            WHERE e.youtube_url IS NOT NULL
            AND EXISTS (SELECT 1 FROM transcript_segments ts WHERE ts.episode_id = e.id)
            ORDER BY e.published_at DESC
            LIMIT %s
            """,
            (args.limit,)
        )
        episodes = cursor.fetchall()

    print(f"Found {len(episodes)} episodes with YouTube URLs and transcripts")

    if not episodes:
        print("No episodes to align.")
        return

    aligned = 0
    failed = 0
    skipped = 0

    for ep in episodes:
        episode_id = ep["id"]
        title = ep["title"]
        youtube_url = ep["youtube_url"]

        # Check if already aligned (unless --force)
        if not args.force:
            with get_cursor(commit=False) as cursor:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM timestamp_anchors WHERE episode_id = %s",
                    (episode_id,)
                )
                existing = cursor.fetchone()["count"]
                if existing > 0:
                    if args.verbose:
                        print(f"  [SKIP] {title[:50]}... (already has {existing} anchors)")
                    skipped += 1
                    continue

        print(f"  Aligning: {title[:50]}...")

        result = align_episode(episode_id, youtube_url)

        if result.success:
            if args.dry_run:
                print(f"    [DRY RUN] Would store {len(result.anchor_points)} anchors, offset={result.offset_seconds:.2f}s")
            else:
                stored = store_anchor_points(episode_id, result)
                print(f"    Stored {stored} anchors, offset={result.offset_seconds:.2f}s")
            aligned += 1

            if args.verbose and result.anchor_points:
                print(f"    Sample matches:")
                for anchor in result.anchor_points[:3]:
                    print(f"      Patreon {float(anchor.patreon_time):.1f}s -> YouTube {float(anchor.youtube_time):.1f}s")
                    print(f"        \"{anchor.matched_text}\"")
        else:
            print(f"    [FAILED] {result.error_message}")
            failed += 1

    print(f"\n=== Alignment Results ===")
    print(f"  Episodes processed: {len(episodes)}")
    print(f"  Aligned: {aligned}")
    print(f"  Skipped (already aligned): {skipped}")
    print(f"  Failed: {failed}")
    if args.dry_run:
        print("  (Dry run - no changes made)")


def main():
    parser = argparse.ArgumentParser(description="Crankiac management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # migrate command
    subparsers.add_parser("migrate", help="Run database migrations")

    # process command
    process_parser = subparsers.add_parser("process", help="Process episodes (fetch, download, transcribe)")
    # Single episode selection
    process_parser.add_argument("--episode", type=int, metavar="ID", help="Process a specific episode by database ID")
    process_parser.add_argument("--title", metavar="SEARCH", help="Find and process episode matching title (must be unique match)")
    # Batch processing options
    process_parser.add_argument("--no-sync", action="store_true", help="Skip syncing from Patreon")
    process_parser.add_argument("--max-sync", type=int, default=100, help="Max episodes to sync")
    process_parser.add_argument("--limit", type=int, default=10, help="Max episodes to process")
    process_parser.add_argument("--offset", type=int, default=0, help="Number of episodes to skip before processing")
    process_parser.add_argument("--all", action="store_true", help="Process all unprocessed episodes (overrides --limit)")
    # Filtering options
    process_parser.add_argument("--all-shows", action="store_true", help="Include all show types (override default numbered-only filter)")
    process_parser.add_argument("--include-shows", metavar="SHOWS", help="Comma-separated shows to include (e.g., 'players club,movie mindset')")
    # Processing options
    process_parser.add_argument("--model", default="base", help="Whisper model (tiny/base/small/medium/large)")
    process_parser.add_argument("--no-cleanup", action="store_true", help="Keep audio files after transcription")
    process_parser.add_argument("--vocab", metavar="PATH", help="Path to vocabulary file (names/terms, one per line)")

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

    # youtube-align command
    align_parser = subparsers.add_parser("youtube-align", help="Align Patreon transcripts with YouTube captions")
    align_parser.add_argument("--limit", type=int, default=50, help="Max episodes to align (default: 50)")
    align_parser.add_argument("--dry-run", action="store_true", help="Show alignment results without storing")
    align_parser.add_argument("--force", action="store_true", help="Re-align episodes that already have anchors")
    align_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed alignment info")

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
    elif args.command == "youtube-align":
        youtube_align(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
