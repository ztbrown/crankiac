#!/usr/bin/env python3
"""Push local crankiac data to a remote PostgreSQL database.

Reads episodes, speakers, transcript segments, and timestamp anchors from
the local database and upserts them into the remote, remapping auto-increment
IDs via natural keys (patreon_id for episodes, name for speakers).

Usage:
    python3 scripts/push_to_remote.py --remote-url <RAILWAY_DATABASE_URL>
    python3 scripts/push_to_remote.py --dry-run
    python3 scripts/push_to_remote.py --skip-migrations
"""

import argparse
import glob
import os
import sys
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Project root for finding migrations and .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """Convert postgres:// to postgresql:// and ensure sslmode for Railway."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Ensure sslmode for Railway connections
    if "rlwy.net" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url += f"{sep}sslmode=require"
    return url


def local_connection_string() -> str:
    """Build the local DATABASE_URL (same logic as app/db/connection.py)."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/crankiac")
    return normalize_url(url)


def run_migrations(cursor, migrations_dir: Optional[str] = None):
    """Run all SQL migration files on the remote database."""
    if migrations_dir is None:
        migrations_dir = str(PROJECT_ROOT / "db" / "migrations")
    migration_files = sorted(glob.glob(f"{migrations_dir}/*.sql"))
    for mf in migration_files:
        print(f"  migration: {Path(mf).name}")
        with open(mf) as f:
            cursor.execute(f.read())
    print(f"  {len(migration_files)} migrations applied")


# ---------------------------------------------------------------------------
# Data reading (local)
# ---------------------------------------------------------------------------

def read_local_episodes(cur) -> list[dict]:
    """Read numbered episodes from the local database."""
    cur.execute(
        "SELECT * FROM episodes WHERE title ~ '^[0-9]' ORDER BY id"
    )
    return [dict(row) for row in cur.fetchall()]


def read_local_speakers(cur) -> list[dict]:
    cur.execute("SELECT * FROM speakers ORDER BY id")
    return [dict(row) for row in cur.fetchall()]


def read_local_segments(cur, episode_ids: list[int]) -> list[dict]:
    """Read transcript segments for the given local episode IDs."""
    if not episode_ids:
        return []
    placeholders = ",".join(["%s"] * len(episode_ids))
    cur.execute(
        f"SELECT * FROM transcript_segments WHERE episode_id IN ({placeholders}) ORDER BY id",
        episode_ids,
    )
    return [dict(row) for row in cur.fetchall()]


def read_local_anchors(cur, episode_ids: list[int]) -> list[dict]:
    """Read timestamp anchors for the given local episode IDs."""
    if not episode_ids:
        return []
    placeholders = ",".join(["%s"] * len(episode_ids))
    cur.execute(
        f"SELECT * FROM timestamp_anchors WHERE episode_id IN ({placeholders}) ORDER BY id",
        episode_ids,
    )
    return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Remote writes
# ---------------------------------------------------------------------------

def upsert_episodes(cur, episodes: list[dict]) -> dict[int, int]:
    """Upsert episodes on remote, return local_id → remote_id map."""
    id_map: dict[int, int] = {}
    for ep in episodes:
        cur.execute(
            """
            INSERT INTO episodes (patreon_id, title, audio_url, published_at,
                                  duration_seconds, youtube_url, is_free, processed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (patreon_id) DO UPDATE SET
                title = EXCLUDED.title,
                audio_url = EXCLUDED.audio_url,
                published_at = EXCLUDED.published_at,
                duration_seconds = EXCLUDED.duration_seconds,
                youtube_url = COALESCE(EXCLUDED.youtube_url, episodes.youtube_url),
                is_free = EXCLUDED.is_free OR episodes.is_free
            RETURNING id
            """,
            (
                ep["patreon_id"], ep["title"], ep["audio_url"],
                ep["published_at"], ep["duration_seconds"],
                ep["youtube_url"], ep["is_free"], ep["processed"],
            ),
        )
        remote_id = cur.fetchone()["id"]
        id_map[ep["id"]] = remote_id
    return id_map


def upsert_speakers(cur, speakers: list[dict]) -> dict[int, int]:
    """Upsert speakers on remote, return local_id → remote_id map."""
    id_map: dict[int, int] = {}
    for sp in speakers:
        cur.execute(
            """
            INSERT INTO speakers (name)
            VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (sp["name"],),
        )
        remote_id = cur.fetchone()["id"]
        id_map[sp["id"]] = remote_id
    return id_map


def push_segments(cur, segments: list[dict], episode_map: dict[int, int],
                  speaker_map: dict[int, int], batch_size: int):
    """Delete-then-reinsert transcript segments for pushed episodes."""
    # Delete existing segments for all pushed episodes on remote
    remote_episode_ids = list(episode_map.values())
    if remote_episode_ids:
        placeholders = ",".join(["%s"] * len(remote_episode_ids))
        cur.execute(
            f"DELETE FROM transcript_segments WHERE episode_id IN ({placeholders})",
            remote_episode_ids,
        )
        print(f"  deleted {cur.rowcount} existing remote segments")

    if not segments:
        return

    # Batch insert with mogrify for performance
    total = 0
    for i in range(0, len(segments), batch_size):
        batch = segments[i : i + batch_size]
        values = []
        for s in batch:
            remote_ep_id = episode_map.get(s["episode_id"])
            if remote_ep_id is None:
                continue  # episode was filtered out
            remote_speaker_id = speaker_map.get(s["speaker_id"]) if s.get("speaker_id") else None
            values.append((
                remote_ep_id,
                s["word"],
                str(s["start_time"]),
                str(s["end_time"]),
                s["segment_index"],
                s.get("speaker"),
                remote_speaker_id,
            ))

        if not values:
            continue

        args_str = ",".join(
            cur.mogrify("(%s,%s,%s,%s,%s,%s,%s)", v).decode("utf-8")
            for v in values
        )
        cur.execute(f"""
            INSERT INTO transcript_segments
            (episode_id, word, start_time, end_time, segment_index, speaker, speaker_id)
            VALUES {args_str}
        """)
        total += len(values)
        if (i // batch_size) % 10 == 0:
            print(f"  segments: {total}/{len(segments)}")

    print(f"  inserted {total} segments")


def upsert_anchors(cur, anchors: list[dict], episode_map: dict[int, int]):
    """Upsert timestamp anchors on remote, remapping episode_id."""
    count = 0
    for a in anchors:
        remote_ep_id = episode_map.get(a["episode_id"])
        if remote_ep_id is None:
            continue
        cur.execute(
            """
            INSERT INTO timestamp_anchors
                (episode_id, patreon_time, youtube_time, confidence, matched_text)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (episode_id, patreon_time) DO UPDATE SET
                youtube_time = EXCLUDED.youtube_time,
                confidence = EXCLUDED.confidence,
                matched_text = EXCLUDED.matched_text
            """,
            (
                remote_ep_id,
                str(a["patreon_time"]),
                str(a["youtube_time"]),
                str(a["confidence"]) if a.get("confidence") is not None else None,
                a.get("matched_text"),
            ),
        )
        count += 1
    print(f"  upserted {count} timestamp anchors")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Push local crankiac data to remote PostgreSQL")
    parser.add_argument("--remote-url", help="Remote DATABASE_URL (or set REMOTE_DATABASE_URL env var)")
    parser.add_argument("--dry-run", action="store_true", help="Read local data and print counts only")
    parser.add_argument("--batch-size", type=int, default=2000, help="Transcript segment batch size")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip running migrations on remote")
    args = parser.parse_args()

    remote_url = args.remote_url or os.environ.get("REMOTE_DATABASE_URL")
    if not remote_url and not args.dry_run:
        print("ERROR: Provide --remote-url or set REMOTE_DATABASE_URL", file=sys.stderr)
        sys.exit(1)

    # ---- Read local data ----
    print("Reading local database...")
    local_conn = psycopg2.connect(local_connection_string())
    try:
        with local_conn.cursor(cursor_factory=RealDictCursor) as cur:
            episodes = read_local_episodes(cur)
            episode_ids = [e["id"] for e in episodes]
            speakers = read_local_speakers(cur)
            segments = read_local_segments(cur, episode_ids)
            anchors = read_local_anchors(cur, episode_ids)
    finally:
        local_conn.close()

    print(f"  {len(episodes)} episodes (numbered titles)")
    print(f"  {len(speakers)} speakers")
    print(f"  {len(segments)} transcript segments")
    print(f"  {len(anchors)} timestamp anchors")

    if args.dry_run:
        print("\n--dry-run: no remote changes made.")
        return

    # ---- Push to remote ----
    # Group segments and anchors by episode for per-episode commits
    segments_by_ep: dict[int, list[dict]] = {}
    for s in segments:
        segments_by_ep.setdefault(s["episode_id"], []).append(s)
    anchors_by_ep: dict[int, list[dict]] = {}
    for a in anchors:
        anchors_by_ep.setdefault(a["episode_id"], []).append(a)

    remote_url_normalized = normalize_url(remote_url)

    # Phase 1: migrations + episodes + speakers (small, one transaction)
    print(f"\nConnecting to remote...")
    remote_conn = psycopg2.connect(remote_url_normalized)
    try:
        remote_conn.autocommit = False
        with remote_conn.cursor(cursor_factory=RealDictCursor) as cur:
            if not args.skip_migrations:
                print("Running migrations...")
                run_migrations(cur)

            print("Upserting episodes...")
            episode_map = upsert_episodes(cur, episodes)
            print(f"  {len(episode_map)} episodes mapped")

            print("Upserting speakers...")
            speaker_map = upsert_speakers(cur, speakers)
            print(f"  {len(speaker_map)} speakers mapped")

        remote_conn.commit()
        print("Phase 1 committed (migrations, episodes, speakers)")
    except Exception:
        remote_conn.rollback()
        print("\nERROR: Phase 1 rolled back.", file=sys.stderr)
        raise
    finally:
        remote_conn.close()

    # Phase 2: segments + anchors, one transaction per episode
    print("\nPushing transcript segments & anchors per episode...")
    total_segs = 0
    total_anchors = 0
    for i, ep in enumerate(episodes):
        local_ep_id = ep["id"]
        remote_ep_id = episode_map.get(local_ep_id)
        if remote_ep_id is None:
            continue

        ep_segs = segments_by_ep.get(local_ep_id, [])
        ep_anchors = anchors_by_ep.get(local_ep_id, [])

        if not ep_segs and not ep_anchors:
            continue

        conn = psycopg2.connect(remote_url_normalized)
        try:
            conn.autocommit = False
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Delete existing segments for this episode
                cur.execute(
                    "DELETE FROM transcript_segments WHERE episode_id = %s",
                    (remote_ep_id,),
                )

                # Insert segments in batches
                for j in range(0, len(ep_segs), args.batch_size):
                    batch = ep_segs[j : j + args.batch_size]
                    values = []
                    for s in batch:
                        remote_speaker_id = speaker_map.get(s["speaker_id"]) if s.get("speaker_id") else None
                        values.append((
                            remote_ep_id,
                            s["word"],
                            str(s["start_time"]),
                            str(s["end_time"]),
                            s["segment_index"],
                            s.get("speaker"),
                            remote_speaker_id,
                        ))
                    if values:
                        args_str = ",".join(
                            cur.mogrify("(%s,%s,%s,%s,%s,%s,%s)", v).decode("utf-8")
                            for v in values
                        )
                        cur.execute(f"""
                            INSERT INTO transcript_segments
                            (episode_id, word, start_time, end_time, segment_index, speaker, speaker_id)
                            VALUES {args_str}
                        """)

                # Upsert anchors for this episode
                for a in ep_anchors:
                    cur.execute(
                        """
                        INSERT INTO timestamp_anchors
                            (episode_id, patreon_time, youtube_time, confidence, matched_text)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (episode_id, patreon_time) DO UPDATE SET
                            youtube_time = EXCLUDED.youtube_time,
                            confidence = EXCLUDED.confidence,
                            matched_text = EXCLUDED.matched_text
                        """,
                        (
                            remote_ep_id,
                            str(a["patreon_time"]),
                            str(a["youtube_time"]),
                            str(a["confidence"]) if a.get("confidence") is not None else None,
                            a.get("matched_text"),
                        ),
                    )

            conn.commit()
            total_segs += len(ep_segs)
            total_anchors += len(ep_anchors)
            print(f"  [{i+1}/{len(episodes)}] {ep['title'][:50]}  ({len(ep_segs)} segs, {len(ep_anchors)} anchors)")

        except Exception:
            conn.rollback()
            print(f"\nERROR: Failed on episode {ep['title']}", file=sys.stderr)
            raise
        finally:
            conn.close()

    print(f"\nDone. {total_segs} segments, {total_anchors} anchors pushed across {len(episodes)} episodes.")


if __name__ == "__main__":
    main()
