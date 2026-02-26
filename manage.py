#!/usr/bin/env python3
"""Crankiac management CLI."""
import argparse
import os
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

    expected_speakers = None
    if args.expected_speakers:
        expected_speakers = [s.strip() for s in args.expected_speakers.split(",")]

    pipeline = EpisodePipeline(
        whisper_model=args.model,
        cleanup_audio=not args.no_cleanup,
        enable_diarization=args.diarize,
        num_speakers=args.num_speakers,
        vocabulary_file=args.vocab,
        enable_speaker_id=args.identify_speakers,
        match_threshold=args.match_threshold,
        expected_speakers=expected_speakers,
        enable_vad=args.vad,
    )

    # Handle single episode processing by ID
    if args.episode:
        print(f"Processing single episode ID={args.episode}...")
        try:
            success = pipeline.process_single(args.episode, force=args.force)
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
        success = pipeline.process_episode(episode, force=args.force)
        if success:
            print("Episode processed successfully.")
        else:
            print("Episode processing failed.")
            sys.exit(1)
        return

    # Handle --episodes flag: process specific episodes by their episode number
    if args.episodes:
        episode_numbers = [int(n.strip()) for n in args.episodes.split(",")]
        repo = EpisodeRepository()
        episodes = repo.get_by_episode_numbers(episode_numbers)

        # If any requested episodes are missing, sync from Patreon and retry
        if len(episodes) < len(episode_numbers):
            found_numbers = set()
            for ep in episodes:
                import re
                m = re.match(r'^(\d+)\s*-', ep.title)
                if m:
                    found_numbers.add(int(m.group(1)))
            missing = [n for n in episode_numbers if n not in found_numbers]
            if missing:
                print(f"Episodes {missing} not found locally, syncing from Patreon...")
                pipeline.sync_episodes(args.max_sync)
                episodes = repo.get_by_episode_numbers(episode_numbers)

        if not episodes:
            print(f"No episodes found matching: {args.episodes}")
            sys.exit(1)

        print(f"Processing {len(episodes)} specific episodes: {args.episodes}")
        stats = {"total": len(episodes), "success": 0, "failed": 0, "skipped": 0}

        for i, episode in enumerate(episodes, 1):
            print(f"[{i}/{len(episodes)}] {episode.title}")
            if not episode.audio_url:
                stats["skipped"] += 1
                continue
            if pipeline.process_episode(episode, force=args.force):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        print(f"\nResults:")
        print(f"  Episodes synced: 0 (skipped - specific episodes requested)")
        print(f"  Processed: {stats['success']}/{stats['total']} succeeded")
        if stats['skipped']:
            print(f"  Skipped (no audio): {stats['skipped']}")
        if stats['failed']:
            print(f"  Failed: {stats['failed']}")
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
            if pipeline.process_episode(episode, force=args.force):
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
        numbered_only=numbered_only,
        force=args.force
    )

    print(f"\nResults:")
    print(f"  Episodes synced: {results['synced']}")
    print(f"  Processed: {results['processed']['success']}/{results['processed']['total']} succeeded")
    if results['processed']['skipped']:
        print(f"  Skipped (no audio): {results['processed']['skipped']}")
    if results['processed']['failed']:
        print(f"  Failed: {results['processed']['failed']}")


def diarize(args):
    """Run speaker diarization on already-transcribed episodes."""
    from app.pipeline import EpisodePipeline
    from app.db.repository import EpisodeRepository

    expected_speakers = None
    if args.expected_speakers:
        expected_speakers = [s.strip() for s in args.expected_speakers.split(",")]

    pipeline = EpisodePipeline(
        cleanup_audio=not args.no_cleanup,
        enable_diarization=True,
        num_speakers=args.num_speakers,
        enable_speaker_id=args.identify_speakers,
        match_threshold=args.match_threshold,
        expected_speakers=expected_speakers,
    )

    repo = EpisodeRepository()

    # Handle --episodes flag: diarize specific episodes by number
    if args.episodes:
        episode_numbers = [int(n.strip()) for n in args.episodes.split(",")]
        episodes = repo.get_by_episode_numbers(episode_numbers)

        if not episodes:
            print(f"No episodes found matching: {args.episodes}")
            sys.exit(1)

        print(f"Diarizing {len(episodes)} episodes: {args.episodes}")
        stats = {"total": len(episodes), "success": 0, "failed": 0, "skipped": 0}

        for i, episode in enumerate(episodes, 1):
            print(f"[{i}/{len(episodes)}] {episode.title}")
            if pipeline.diarize_episode(episode):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        print(f"\nResults:")
        print(f"  Diarized: {stats['success']}/{stats['total']} succeeded")
        if stats['failed']:
            print(f"  Failed: {stats['failed']}")
        return

    # Handle --episode flag: diarize single episode by ID
    if args.episode:
        episode = repo.get_by_id(args.episode)
        if not episode:
            print(f"Episode with ID {args.episode} not found")
            sys.exit(1)

        print(f"Diarizing: {episode.title}")
        if pipeline.diarize_episode(episode):
            print("Diarization complete.")
        else:
            print("Diarization failed.")
            sys.exit(1)
        return

    print("Error: Must specify --episodes or --episode")
    sys.exit(1)


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

    if hasattr(args, 'episodes') and args.episodes:
        episode_numbers = [int(n.strip()) for n in args.episodes.split(",")]
        episodes = repo.get_by_episode_numbers(episode_numbers)
        if not episodes:
            print(f"No episodes found matching: {args.episodes}")
            sys.exit(1)
    elif args.all:
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


def cleanup_episodes(args):
    """Delete all episodes except specified episode numbers."""
    from app.db.connection import get_cursor

    keep_episodes = args.keep
    if not keep_episodes:
        print("ERROR: No episodes specified to keep")
        print("Usage: python manage.py cleanup-episodes --keep 1003,1004,1005,1006")
        sys.exit(1)

    # Parse episode numbers
    episode_numbers = [int(n.strip()) for n in keep_episodes.split(",")]

    print(f"Checking episodes to keep: {episode_numbers}")
    with get_cursor(commit=False) as cursor:
        placeholders = ",".join(["%s"] * len(episode_numbers))
        cursor.execute(
            f"""
            SELECT id, episode_number, title
            FROM episodes
            WHERE episode_number IN ({placeholders})
            ORDER BY episode_number
            """,
            episode_numbers
        )

        keep_eps = cursor.fetchall()
        print(f"\nFound {len(keep_eps)} episodes to keep:")
        for ep in keep_eps:
            print(f"  Keep: Episode {ep['episode_number']} - {ep['title']}")

    print("\nCounting episodes to delete...")
    with get_cursor(commit=False) as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) as count
            FROM episodes
            WHERE episode_number IS NULL OR episode_number NOT IN ({placeholders})
            """,
            episode_numbers
        )

        delete_count = cursor.fetchone()['count']
        print(f"Episodes to DELETE: {delete_count}")

    if delete_count == 0:
        print("No episodes to delete. Exiting.")
        return

    if not args.confirm:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
        print("Add --confirm to actually delete episodes")
        return

    print("\n⚠️  DELETING EPISODES...")
    with get_cursor() as cursor:
        cursor.execute(
            f"""
            DELETE FROM episodes
            WHERE episode_number IS NULL OR episode_number NOT IN ({placeholders})
            """,
            episode_numbers
        )

        deleted = cursor.rowcount
        print(f"✅ Deleted {deleted} episodes")

    print("\nVerifying...")
    with get_cursor(commit=False) as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM episodes")
        remaining = cursor.fetchone()['count']
        print(f"✅ Remaining episodes: {remaining}")

    print("\n✅ Done!")


def llm_correct_cmd(args):
    """Run LLM-based correction on low-confidence transcript words."""
    from app.db.connection import get_cursor
    from app.db.repository import EpisodeRepository
    from app.db.models import Episode
    from app.transcription.llm_corrector import LLMCorrector

    repo = EpisodeRepository()
    corrector = LLMCorrector(model=args.model, threshold=args.threshold)

    # Determine episodes to process
    batch_mode = not args.episode and not args.episodes
    if args.episode:
        episode = repo.get_by_id(args.episode)
        if not episode:
            print(f"Episode ID {args.episode} not found")
            sys.exit(1)
        episodes = [episode]
    elif args.episodes:
        episode_numbers = [int(n.strip()) for n in args.episodes.split(",")]
        episodes = repo.get_by_episode_numbers(episode_numbers)
        if not episodes:
            print(f"No episodes found matching: {args.episodes}")
            sys.exit(1)
    else:
        # Batch mode: get episodes with word_confidence data, not yet corrected
        with get_cursor(commit=False) as cursor:
            if args.force:
                cursor.execute(
                    """
                    SELECT DISTINCT e.*
                    FROM episodes e
                    INNER JOIN transcript_segments ts ON ts.episode_id = e.id
                    WHERE ts.word_confidence IS NOT NULL
                    ORDER BY e.published_at DESC
                    LIMIT %s
                    """,
                    (args.limit,)
                )
            else:
                cursor.execute(
                    """
                    SELECT DISTINCT e.*
                    FROM episodes e
                    INNER JOIN transcript_segments ts ON ts.episode_id = e.id
                    WHERE e.llm_corrected = FALSE
                      AND e.manually_reviewed = FALSE
                      AND ts.word_confidence IS NOT NULL
                    ORDER BY e.published_at DESC
                    LIMIT %s
                    """,
                    (args.limit,)
                )
            rows = cursor.fetchall()
        episodes = [Episode(**row) for row in rows]

    print(f"Found {len(episodes)} episode(s) to process")

    total_corrections = 0
    total_skipped = 0

    for episode in episodes:
        print(f"\n[{episode.id}] {episode.title}")

        # In batch mode, skip manually_reviewed unless --force
        if batch_mode and episode.manually_reviewed and not args.force:
            print(f"  Skipping (manually_reviewed=TRUE, use --force to override)")
            total_skipped += 1
            continue

        # Fetch segments
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                """SELECT id, word, segment_index, word_confidence, speaker
                   FROM transcript_segments
                   WHERE episode_id = %s
                   ORDER BY segment_index""",
                (episode.id,)
            )
            rows = cursor.fetchall()

        if not rows:
            print(f"  WARNING: No transcript found, skipping")
            total_skipped += 1
            continue

        segments = [dict(row) for row in rows]
        word_count = len(segments)

        has_confidence = any(s.get("word_confidence") is not None for s in segments)
        if not has_confidence:
            print(f"  WARNING: No word_confidence data found, skipping")
            total_skipped += 1
            continue

        regions = corrector.identify_low_confidence_regions(segments)
        chunks = corrector.build_chunks(segments, regions)
        low_conf_count = sum(len(r["flagged"]) for r in regions)

        print(f"  Words: {word_count}, Low-confidence: {low_conf_count}, Chunks: {len(chunks)}")

        if not chunks:
            print(f"  No low-confidence regions found")
            continue

        if args.dry_run:
            ep_corrections = 0
            total_input_tokens = 0

            for i, chunk in enumerate(chunks):
                formatted = corrector.format_chunk(chunk)
                total_input_tokens += len(formatted.split()) * 2  # rough token estimate

                if args.verbose:
                    print(f"\n  Chunk {i + 1} prompt:")
                    print(f"    {formatted}")

                raw_corrections = corrector.call_llm(formatted)

                if args.verbose:
                    print(f"  Chunk {i + 1} response: {raw_corrections}")

                flagged_ids = {chunk["segments"][j]["id"] for j in chunk["flagged"]}
                id_to_seg = {seg["id"]: seg for seg in chunk["segments"]}

                for key, new_word in raw_corrections.items():
                    try:
                        seg_id = int(key)
                    except (ValueError, TypeError):
                        continue
                    if seg_id not in flagged_ids:
                        continue
                    new_word = str(new_word)
                    if " " in new_word:
                        continue
                    seg = id_to_seg.get(seg_id)
                    if not seg or seg["word"] == new_word:
                        continue

                    conf = seg.get("word_confidence")
                    conf_str = f"{float(conf):.2f}" if conf is not None else "?"
                    print(f"  [{seg_id}] {seg['word']!r} -> {new_word!r}  (confidence: {conf_str})")
                    ep_corrections += 1

            # Estimated cost (Haiku: $0.80/MTok input, $4.00/MTok output)
            estimated_output_tokens = len(chunks) * 50
            input_cost = total_input_tokens * 0.0000008
            output_cost = estimated_output_tokens * 0.000004
            total_cost = input_cost + output_cost

            print(f"  Summary: {ep_corrections} correction(s) would be applied")
            print(f"  Estimated cost: ${total_cost:.4f}")
            total_corrections += ep_corrections

        else:
            # For --force, reset llm_corrected so advisory lock can claim it
            if args.force and episode.llm_corrected:
                with get_cursor() as cursor:
                    cursor.execute(
                        "UPDATE episodes SET llm_corrected = FALSE WHERE id = %s",
                        (episode.id,)
                    )

            count = corrector.correct_episode(episode.id)
            if count == -1:
                print(f"  Already corrected (skipped)")
                total_skipped += 1
            else:
                print(f"  Applied {count} correction(s)")
                total_corrections += count

    print(f"\nResults: {total_corrections} total correction(s)")
    if total_skipped:
        print(f"  Skipped: {total_skipped}")
    if args.dry_run:
        print("  (Dry run - no changes made)")


def mine_corrections_cmd(args):
    """Mine frequent corrections from edit_history and output JSON."""
    import json
    from app.transcription.corrections import mine_corrections

    corrections = mine_corrections(min_count=args.min_count)

    if not corrections:
        print(f"No corrections found with min_count={args.min_count}")
        return

    output_path = args.output or "data/correction_dictionary.json"

    if args.dry_run:
        print(f"[DRY RUN] Would write {len(corrections)} corrections to {output_path}:")
        for old, new in sorted(corrections.items()):
            print(f"  {old!r} -> {new!r}")
        return

    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(corrections, f, indent=2, sort_keys=True)

    print(f"Wrote {len(corrections)} corrections to {output_path}")
    for old, new in sorted(corrections.items()):
        print(f"  {old!r} -> {new!r}")


def enroll_speaker_cmd(args):
    """Enroll a speaker from reference audio clips."""
    from app.transcription.enroll import enroll_speaker, enroll_all_speakers

    if args.all:
        print(f"Enrolling all speakers from {args.audio_dir}...")
        enrolled = enroll_all_speakers(
            audio_dir=args.audio_dir,
            output_dir=args.output_dir,
        )
        print(f"\nEnrolled {len(enrolled)} speakers: {', '.join(enrolled)}")
    else:
        if not args.name:
            print("Error: --name is required (or use --all to enroll all speakers)")
            sys.exit(1)

        print(f"Enrolling speaker '{args.name}' from {args.audio_dir}/{args.name}/...")
        try:
            npy_path = enroll_speaker(
                name=args.name,
                audio_dir=args.audio_dir,
                output_dir=args.output_dir,
            )
            print(f"Saved embedding to {npy_path}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)


def youtube_align(args):
    """Align Patreon transcripts with YouTube captions to compute timestamp offsets."""
    from app.db.connection import get_cursor
    from app.youtube.alignment import align_episode, store_anchor_points

    # Get episodes to align
    if hasattr(args, 'episodes') and args.episodes:
        from app.db.repository import EpisodeRepository
        repo = EpisodeRepository()
        episode_numbers = [int(n.strip()) for n in args.episodes.split(",")]
        ep_objects = repo.get_by_episode_numbers(episode_numbers)
        if not ep_objects:
            print(f"No episodes found matching: {args.episodes}")
            return
        # Convert to dicts matching the query format below
        episodes = []
        for ep in ep_objects:
            if not ep.youtube_url:
                print(f"  [SKIP] {ep.title[:50]}... (no youtube_url)")
                continue
            episodes.append({"id": ep.id, "title": ep.title, "youtube_url": ep.youtube_url, "published_at": ep.published_at})
    else:
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


def extract_clips(args):
    """Extract speaker audio clips from transcribed episodes for enrollment."""
    from app.db.repository import EpisodeRepository
    from app.transcription.clip_extractor import ClipExtractor
    from app.patreon.downloader import AudioDownloader

    repo = EpisodeRepository()
    extractor = ClipExtractor(
        output_dir=args.output_dir,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
    )

    # Handle single episode by ID
    if args.episode:
        episode = repo.get_by_id(args.episode)
        if not episode:
            print(f"Episode with ID {args.episode} not found")
            sys.exit(1)

        # Determine audio path
        if not episode.audio_url:
            print(f"Episode {episode.id} has no audio_url")
            sys.exit(1)

        # Check if audio file exists locally
        session_id = os.environ.get("PATREON_SESSION_ID")
        if not session_id:
            print("Error: PATREON_SESSION_ID environment variable not set")
            sys.exit(1)

        downloader = AudioDownloader(session_id)
        audio_path = str(downloader.get_file_path(episode.patreon_id))

        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            print("Run 'python manage.py process --episode {args.episode}' first to download audio")
            sys.exit(1)

        print(f"Extracting clips from: {episode.title}")
        clips = extractor.extract_clips(
            episode_id=episode.id,
            audio_path=audio_path,
            speaker_name=args.speaker,
            max_clips_per_speaker=args.max_clips
        )

        if not clips:
            print("No clips extracted")
        else:
            print(f"\n✓ Extracted clips:")
            for speaker, paths in clips.items():
                print(f"  {speaker}: {len(paths)} clips")
                if args.verbose:
                    for path in paths:
                        print(f"    - {path}")
        return

    # Handle --episodes flag: extract clips from specific episodes by number
    if args.episodes:
        episode_numbers = [int(n.strip()) for n in args.episodes.split(",")]
        episodes = repo.get_by_episode_numbers(episode_numbers)

        if not episodes:
            print(f"No episodes found matching: {args.episodes}")
            sys.exit(1)

        print(f"Extracting clips from {len(episodes)} episodes: {args.episodes}")

        session_id = os.environ.get("PATREON_SESSION_ID")
        if not session_id:
            print("Error: PATREON_SESSION_ID environment variable not set")
            sys.exit(1)

        downloader = AudioDownloader(session_id)

        total_clips = 0
        processed = 0
        skipped = 0

        for episode in episodes:
            audio_path = str(downloader.get_file_path(episode.patreon_id))

            if not os.path.exists(audio_path):
                print(f"  [SKIP] {episode.title[:50]}... (audio file not found)")
                skipped += 1
                continue

            print(f"  Processing: {episode.title[:50]}...")

            clips = extractor.extract_clips(
                episode_id=episode.id,
                audio_path=audio_path,
                speaker_name=args.speaker,
                max_clips_per_speaker=args.max_clips
            )

            if clips:
                clip_count = sum(len(paths) for paths in clips.values())
                total_clips += clip_count
                processed += 1

        print(f"\n=== Extraction Results ===")
        print(f"  Episodes processed: {processed}")
        print(f"  Episodes skipped: {skipped}")
        print(f"  Total clips extracted: {total_clips}")
        print(f"  Output directory: {args.output_dir}")
        return

    # Handle batch processing (all processed episodes with transcripts)
    from app.db.connection import get_cursor

    with get_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT DISTINCT e.id, e.title, e.patreon_id
            FROM episodes e
            JOIN transcript_segments ts ON e.id = ts.episode_id
            WHERE ts.speaker IS NOT NULL
            ORDER BY e.published_at DESC
            LIMIT %s
            """,
            (args.limit,)
        )
        episodes = cursor.fetchall()

    if not episodes:
        print("No episodes found with speaker-labeled transcripts")
        return

    print(f"Found {len(episodes)} episodes with speaker labels")

    session_id = os.environ.get("PATREON_SESSION_ID")
    if not session_id:
        print("Error: PATREON_SESSION_ID environment variable not set")
        sys.exit(1)

    downloader = AudioDownloader(session_id)

    total_clips = 0
    processed = 0
    skipped = 0

    for ep in episodes:
        episode_id = ep["id"]
        title = ep["title"]
        patreon_id = ep["patreon_id"]

        audio_path = str(downloader.get_file_path(patreon_id))

        if not os.path.exists(audio_path):
            print(f"  [SKIP] {title[:50]}... (audio file not found)")
            skipped += 1
            continue

        print(f"  Processing: {title[:50]}...")

        clips = extractor.extract_clips(
            episode_id=episode_id,
            audio_path=audio_path,
            speaker_name=args.speaker,
            max_clips_per_speaker=args.max_clips
        )

        if clips:
            clip_count = sum(len(paths) for paths in clips.values())
            total_clips += clip_count
            processed += 1

    print(f"\n=== Extraction Results ===")
    print(f"  Episodes processed: {processed}")
    print(f"  Episodes skipped: {skipped}")
    print(f"  Total clips extracted: {total_clips}")
    print(f"  Output directory: {args.output_dir}")


def backfill_word_confidence(args):
    """Re-extract word_confidence for episodes with missing data."""
    import os
    from pathlib import Path
    from app.db.repository import EpisodeRepository
    from app.transcription.storage import TranscriptStorage
    from app.transcription.whisper_transcriber import get_transcriber
    from app.patreon.downloader import AudioDownloader
    from app.patreon.client import PatreonClient

    session_id = os.environ.get("PATREON_SESSION_ID")
    if not session_id:
        print("Error: PATREON_SESSION_ID environment variable required")
        sys.exit(1)

    repo = EpisodeRepository()
    storage = TranscriptStorage()

    # Select episodes to process
    if args.episode_id:
        episode = repo.get_by_id(args.episode_id)
        if not episode:
            print(f"Episode ID {args.episode_id} not found")
            sys.exit(1)
        episodes = [episode]
    else:
        episodes = repo.get_with_missing_word_confidence(limit=args.limit)

    print(f"Found {len(episodes)} episode(s) to backfill")

    if args.dry_run:
        from app.db.connection import get_cursor
        for ep in episodes:
            with get_cursor(commit=False) as cursor:
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM transcript_segments WHERE episode_id = %s AND word_confidence IS NULL",
                    (ep.id,)
                )
                row = cursor.fetchone()
                null_count = row["cnt"] if row else 0
            print(f"  [{ep.id}] {ep.title} — {null_count} segments missing word_confidence")
        print("\nDry run complete. No changes made.")
        return

    transcriber = get_transcriber(args.model)
    patreon = PatreonClient(session_id)
    downloader = AudioDownloader(session_id, "downloads/audio")

    stats = {"total": len(episodes), "success": 0, "failed": 0, "skipped": 0}

    for i, episode in enumerate(episodes, 1):
        print(f"[{i}/{len(episodes)}] {episode.title}")

        if not storage.has_transcript(episode.id):
            print(f"  No transcript, skipping")
            stats["skipped"] += 1
            continue

        # Resolve audio URL
        audio_url = None
        if episode.patreon_id:
            try:
                audio_url = patreon.get_audio_url(episode.patreon_id)
            except Exception as e:
                print(f"  Could not fetch fresh audio URL: {e}")
        if not audio_url:
            audio_url = episode.audio_url
        if not audio_url:
            print(f"  No audio URL, skipping")
            stats["skipped"] += 1
            continue

        try:
            print(f"  Downloading audio...")
            download_result = downloader.download(audio_url, episode.patreon_id)
            if not download_result.success:
                print(f"  Download failed: {download_result.error}")
                stats["failed"] += 1
                continue

            print(f"  Transcribing (word_timestamps=True)...")
            transcript = transcriber.transcribe(download_result.file_path)
            print(f"  Got {len(transcript.segments)} words from Whisper")

            # Build segment_index -> confidence map from the new transcription
            index_to_confidence = {
                idx: seg.word_confidence
                for idx, seg in enumerate(transcript.segments)
                if seg.word_confidence is not None
            }

            updated = storage.update_word_confidence_batch(episode.id, index_to_confidence)
            print(f"  Updated {updated} segments with word_confidence")
            stats["success"] += 1

            # Cleanup audio
            audio_path = Path(download_result.file_path)
            if audio_path.exists():
                audio_path.unlink()
                print(f"  Cleaned up audio file")

        except Exception as e:
            print(f"  Error: {e}")
            stats["failed"] += 1

    print(f"\nResults: {stats['success']}/{stats['total']} succeeded, "
          f"{stats['failed']} failed, {stats['skipped']} skipped")


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
    process_parser.add_argument("--model", default="large-v3", help="Whisper model (tiny/base/small/medium/large/large-v3/turbo)")
    process_parser.add_argument("--no-cleanup", action="store_true", help="Keep audio files after transcription")
    # Diarization options
    process_parser.add_argument("--diarize", action="store_true", help="Enable speaker diarization")
    process_parser.add_argument("--num-speakers", type=int, default=None, help="Hint for number of speakers (optional)")
    # Speaker identification options
    process_parser.add_argument("--identify-speakers", action="store_true", help="Enable speaker identification via voice embeddings")
    process_parser.add_argument("--match-threshold", type=float, default=0.70, help="Cosine similarity threshold for speaker matching (default: 0.70)")
    process_parser.add_argument("--expected-speakers", type=str, help="Comma-separated expected speaker names (e.g., 'Will Menaker,Felix Biederman')")
    # Episode selection by number
    process_parser.add_argument("--episodes", type=str, help="Comma-separated episode numbers to process (e.g., 1003,1006)")
    # Vocabulary hints
    process_parser.add_argument("--vocab", metavar="PATH", help="Path to vocabulary file (names/terms, one per line)")
    # VAD pre-filtering
    process_parser.add_argument("--vad", action="store_true", help="Enable Silero VAD pre-filtering to strip non-speech before transcription")
    # Reprocessing
    process_parser.add_argument("--force", action="store_true", help="Force reprocessing of already-processed episodes")

    # diarize command
    diarize_parser = subparsers.add_parser("diarize", help="Run speaker diarization on already-transcribed episodes")
    diarize_parser.add_argument("--episodes", type=str, help="Comma-separated episode numbers to diarize (e.g., 1003,1006)")
    diarize_parser.add_argument("--episode", type=int, metavar="ID", help="Diarize a specific episode by database ID")
    diarize_parser.add_argument("--num-speakers", type=int, default=None, help="Hint for number of speakers (optional)")
    diarize_parser.add_argument("--no-cleanup", action="store_true", help="Keep audio files after diarization")
    # Speaker identification options
    diarize_parser.add_argument("--identify-speakers", action="store_true", help="Enable speaker identification via voice embeddings")
    diarize_parser.add_argument("--match-threshold", type=float, default=0.70, help="Cosine similarity threshold for speaker matching (default: 0.70)")
    diarize_parser.add_argument("--expected-speakers", type=str, help="Comma-separated expected speaker names (e.g., 'Will Menaker,Felix Biederman')")

    # youtube-fetch command
    fetch_parser = subparsers.add_parser("youtube-fetch", help="Fetch YouTube videos and save to JSON")
    fetch_parser.add_argument("--output", "-o", help="Output JSON file path (default: app/data/youtube_videos.json)")
    fetch_parser.add_argument("--max", type=int, default=500, help="Max videos to fetch (default: 500)")
    fetch_parser.add_argument("--rss-only", action="store_true", help="Use RSS feed only (no API key needed, ~15 videos)")

    # youtube-sync command
    yt_parser = subparsers.add_parser("youtube-sync", help="Sync YouTube URLs for free episodes")
    yt_parser.add_argument("--episodes", type=str, help="Comma-separated episode numbers to sync (e.g., 1007,1008)")
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
    align_parser.add_argument("--episodes", type=str, help="Comma-separated episode numbers to align (e.g., 1007,1008)")
    align_parser.add_argument("--limit", type=int, default=50, help="Max episodes to align (default: 50)")
    align_parser.add_argument("--dry-run", action="store_true", help="Show alignment results without storing")
    align_parser.add_argument("--force", action="store_true", help="Re-align episodes that already have anchors")
    align_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed alignment info")

    # cleanup-episodes command
    cleanup_parser = subparsers.add_parser("cleanup-episodes", help="Delete all episodes except specified ones")
    cleanup_parser.add_argument("--keep", required=True, help="Comma-separated episode numbers to keep (e.g., 1003,1004,1005,1006)")
    cleanup_parser.add_argument("--confirm", action="store_true", help="Actually delete (without this, runs in dry-run mode)")

    # mine-corrections command
    mine_parser = subparsers.add_parser("mine-corrections", help="Mine frequent corrections from edit_history")
    mine_parser.add_argument("--min-count", type=int, default=3, help="Minimum occurrences required (default: 3)")
    mine_parser.add_argument("--output", "-o", help="Output JSON file path (default: data/correction_dictionary.json)")
    mine_parser.add_argument("--dry-run", action="store_true", help="Show corrections without writing file")

    # enroll-speaker command
    enroll_parser = subparsers.add_parser("enroll-speaker", help="Enroll speaker(s) from reference audio clips")
    enroll_parser.add_argument("--name", help="Speaker name (must match a subdirectory in reference audio dir)")
    enroll_parser.add_argument("--all", action="store_true", help="Enroll all speakers with reference audio directories")
    enroll_parser.add_argument("--audio-dir", default="data/reference_audio", help="Root directory with speaker subdirectories (default: data/reference_audio)")
    enroll_parser.add_argument("--output-dir", default="data/speaker_embeddings", help="Directory to save embeddings (default: data/speaker_embeddings)")

    # llm-correct command
    llm_parser = subparsers.add_parser("llm-correct", help="Run LLM-based correction on low-confidence transcript words")
    llm_parser.add_argument("--episode", type=int, metavar="ID", help="Correct a specific episode by database ID")
    llm_parser.add_argument("--episodes", type=str, help="Comma-separated episode numbers to correct (e.g., 1003,1006)")
    llm_parser.add_argument("--limit", type=int, default=10, help="Max episodes to process in batch mode (default: 10)")
    llm_parser.add_argument("--model", default="claude-haiku-4-5-20251001", help="Claude model to use (default: claude-haiku-4-5-20251001)")
    llm_parser.add_argument("--threshold", type=float, default=0.7, help="Confidence threshold below which words are flagged (default: 0.7)")
    llm_parser.add_argument("--dry-run", action="store_true", help="Show corrections without applying to database")
    llm_parser.add_argument("--force", action="store_true", help="Re-run on already-corrected episodes and ignore manually_reviewed flag")
    llm_parser.add_argument("--verbose", "-v", action="store_true", help="Show full prompts and responses")

    # backfill-word-confidence command
    bwc_parser = subparsers.add_parser("backfill-word-confidence", help="Re-extract word_confidence for episodes with missing data")
    bwc_parser.add_argument("--episode-id", type=int, metavar="ID", help="Backfill a specific episode by database ID")
    bwc_parser.add_argument("--limit", type=int, default=None, help="Max episodes to process in batch mode")
    bwc_parser.add_argument("--model", default="large-v3", help="Whisper model to use (default: large-v3)")
    bwc_parser.add_argument("--dry-run", action="store_true", help="Preview what would be updated without making changes")

    # extract-clips command
    clips_parser = subparsers.add_parser("extract-clips", help="Extract speaker audio clips from transcribed episodes")
    clips_parser.add_argument("--episode", type=int, metavar="ID", help="Extract clips from a specific episode by database ID")
    clips_parser.add_argument("--episodes", type=str, help="Comma-separated episode numbers (e.g., 1003,1004,1005)")
    clips_parser.add_argument("--speaker", help="Extract clips for a specific speaker only")
    clips_parser.add_argument("--limit", type=int, default=10, help="Max episodes to process in batch mode (default: 10)")
    clips_parser.add_argument("--max-clips", type=int, default=10, help="Max clips to extract per speaker per episode (default: 10)")
    clips_parser.add_argument("--min-duration", type=float, default=10.0, help="Minimum clip duration in seconds (default: 10.0)")
    clips_parser.add_argument("--max-duration", type=float, default=20.0, help="Maximum clip duration in seconds (default: 20.0)")
    clips_parser.add_argument("--output-dir", default="data/reference_audio", help="Directory to save clips (default: data/reference_audio)")
    clips_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output including clip paths")

    args = parser.parse_args()

    if args.command == "migrate":
        migrate()
    elif args.command == "process":
        process(args)
    elif args.command == "diarize":
        diarize(args)
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
    elif args.command == "cleanup-episodes":
        cleanup_episodes(args)
    elif args.command == "mine-corrections":
        mine_corrections_cmd(args)
    elif args.command == "enroll-speaker":
        enroll_speaker_cmd(args)
    elif args.command == "extract-clips":
        extract_clips(args)
    elif args.command == "llm-correct":
        llm_correct_cmd(args)
    elif args.command == "backfill-word-confidence":
        backfill_word_confidence(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
