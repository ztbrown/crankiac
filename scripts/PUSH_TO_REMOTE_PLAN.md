# Plan: Push Local Data to Remote Database

## Context
Local PostgreSQL (`crankiac`) has all episode data, transcripts, speakers, and timestamp anchors. The goal is to push this data to the remote Railway PostgreSQL, excluding episodes whose titles don't start with a number.

## Deliverable
New file: `scripts/push_to_remote.py` — a standalone, reusable script.

## How It Works

### CLI Interface
```
python3 scripts/push_to_remote.py --remote-url <RAILWAY_DATABASE_URL>
python3 scripts/push_to_remote.py --dry-run          # preview only
python3 scripts/push_to_remote.py --skip-migrations   # skip running migrations on remote
```
- `--remote-url` or `REMOTE_DATABASE_URL` env var for the remote connection
- `--dry-run` reads local data and prints counts without touching remote
- `--batch-size` controls transcript segment batch size (default 2000)
- `--skip-migrations` skips running `db/migrations/*.sql` on remote

### Push Order (respects FK dependencies)
1. **Episodes** — filtered by `title ~ '^[0-9]'`, upserted on `patreon_id`
2. **Speakers** — upserted on `name`
3. **Transcript segments** — delete-then-reinsert for each pushed episode (no natural key for upsert). Remaps `episode_id` and `speaker_id` using local→remote ID mappings.
4. **Timestamp anchors** — upserted on `(episode_id, patreon_time)`. Remaps `episode_id`.

### ID Mapping Strategy
Local and remote auto-increment IDs will differ. The script:
1. Upserts episodes using `patreon_id` as the natural key, uses `RETURNING id` to get remote IDs → builds `local_episode_id → remote_episode_id` map
2. Upserts speakers using `name` as the natural key, uses `RETURNING id` → builds `local_speaker_id → remote_speaker_id` map
3. Rewrites FKs in transcript_segments and timestamp_anchors using these maps before inserting

### Transaction Safety
All remote writes happen in a single transaction. If any step fails, the entire transaction rolls back — no partial state.

### Key Reused Patterns
- Episode upsert SQL from `app/db/repository.py:12-22`
- Batch insert via `mogrify` from `app/transcription/storage.py:69-78`
- URL normalization (`postgres://` → `postgresql://`) from `app/db/connection.py:25-26`
- Migration runner pattern from `app/db/connection.py:53-64`

## Verification
1. `python3 scripts/push_to_remote.py --dry-run` — confirm correct episode count and no errors
2. `python3 scripts/push_to_remote.py --remote-url <URL>` — run for real
3. Verify on remote: `SELECT COUNT(*) FROM episodes; SELECT COUNT(*) FROM transcript_segments;`
