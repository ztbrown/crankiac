# Database Schema

This document describes the PostgreSQL database schema for Crankiac (bart).

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EPISODES                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ id              SERIAL PRIMARY KEY                                           │
│ patreon_id      VARCHAR(255) UNIQUE NOT NULL     ← Source identifier         │
│ title           VARCHAR(500) NOT NULL                                        │
│ audio_url       TEXT                             ← Patreon audio URL         │
│ published_at    TIMESTAMP WITH TIME ZONE                                     │
│ duration_seconds INTEGER                                                     │
│ youtube_url     TEXT                             ← Free episodes on YT       │
│ youtube_id      VARCHAR(255)                                                 │
│ is_free         BOOLEAN DEFAULT FALSE            ← Available on YouTube?     │
│ processed       BOOLEAN DEFAULT FALSE            ← Transcription done?       │
│ created_at      TIMESTAMP WITH TIME ZONE                                     │
│ updated_at      TIMESTAMP WITH TIME ZONE         ← Auto-updated via trigger  │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          │ 1
          │
          ├──────────────────────────────────┐
          │                                  │
          ▼ *                                ▼ *
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│     TRANSCRIPT_SEGMENTS         │   │      TIMESTAMP_ANCHORS          │
├─────────────────────────────────┤   ├─────────────────────────────────┤
│ id            SERIAL PK         │   │ id            SERIAL PK         │
│ episode_id    INTEGER FK ──────►│   │ episode_id    INTEGER FK ──────►│
│ word          TEXT NOT NULL     │   │ patreon_time  NUMERIC(10,3)     │
│ start_time    NUMERIC(10,3)     │   │ youtube_time  NUMERIC(10,3)     │
│ end_time      NUMERIC(10,3)     │   │ confidence    NUMERIC(5,4)      │
│ segment_index INTEGER           │   │ matched_text  TEXT              │
│ speaker       VARCHAR(100)      │   │ created_at    TIMESTAMP         │
│ created_at    TIMESTAMP         │   └─────────────────────────────────┘
└─────────────────────────────────┘
```

## Data Flow

```
                    ┌──────────────┐
                    │   PATREON    │
                    │     API      │
                    └──────┬───────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EPISODE PIPELINE                                   │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐      │
│  │   FETCH     │──▶│  DOWNLOAD   │──▶│ TRANSCRIBE  │──▶│   STORE     │      │
│  │  Episodes   │   │   Audio     │   │  (Whisper)  │   │  Segments   │      │
│  └─────────────┘   └─────────────┘   └──────┬──────┘   └─────────────┘      │
│                                             │                                │
│                                             ▼                                │
│                                      ┌─────────────┐                        │
│                                      │  DIARIZE    │  (optional)            │
│                                      │ (pyannote)  │                        │
│                                      └─────────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │   PostgreSQL    │
                                    │    (Railway)    │
                                    └─────────────────┘
```

## Tables

### episodes

The main table tracking podcast episodes from Patreon.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `patreon_id` | VARCHAR(255) | Unique ID from Patreon API |
| `title` | VARCHAR(500) | Episode title |
| `audio_url` | TEXT | Direct link to MP3 on Patreon CDN |
| `published_at` | TIMESTAMP | When the episode was published |
| `duration_seconds` | INTEGER | Episode length in seconds |
| `youtube_url` | TEXT | Link for "Free Monday" episodes on YouTube |
| `youtube_id` | VARCHAR(255) | YouTube video ID |
| `is_free` | BOOLEAN | TRUE if available publicly on YouTube |
| `processed` | BOOLEAN | TRUE after transcription is stored |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last update time (auto-updated via trigger) |

### transcript_segments

Word-level transcript data with timestamps and optional speaker labels.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `episode_id` | INTEGER | Foreign key to episodes |
| `word` | TEXT | The transcribed word |
| `start_time` | NUMERIC(10,3) | Start time in seconds (millisecond precision) |
| `end_time` | NUMERIC(10,3) | End time in seconds |
| `segment_index` | INTEGER | Word order within episode |
| `speaker` | VARCHAR(100) | Speaker label from diarization (e.g., "SPEAKER_0") |
| `created_at` | TIMESTAMP | Record creation time |

Example data:

```
Episode 1003: "Hello everyone welcome to the show"

┌────┬────────────┬───────────┬──────────┬──────────┬─────────┬──────────┐
│ id │ episode_id │   word    │  start   │   end    │  index  │ speaker  │
├────┼────────────┼───────────┼──────────┼──────────┼─────────┼──────────┤
│  1 │       1003 │ Hello     │    0.000 │    0.340 │       0 │ SPEAKER_0│
│  2 │       1003 │ everyone  │    0.340 │    0.780 │       1 │ SPEAKER_0│
│  3 │       1003 │ welcome   │    0.820 │    1.200 │       2 │ SPEAKER_0│
│  4 │       1003 │ to        │    1.200 │    1.320 │       3 │ SPEAKER_0│
│  5 │       1003 │ the       │    1.320 │    1.440 │       4 │ SPEAKER_0│
│  6 │       1003 │ show      │    1.440 │    1.800 │       5 │ SPEAKER_0│
└────┴────────────┴───────────┴──────────┴──────────┴─────────┴──────────┘
```

### timestamp_anchors

Maps Patreon timestamps to YouTube timestamps for syncing playback between sources.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `episode_id` | INTEGER | Foreign key to episodes |
| `patreon_time` | NUMERIC(10,3) | Timestamp in Patreon audio (seconds) |
| `youtube_time` | NUMERIC(10,3) | Corresponding timestamp in YouTube video |
| `confidence` | NUMERIC(5,4) | Alignment confidence score (0.0000 to 1.0000) |
| `matched_text` | TEXT | Text that was matched for alignment |
| `created_at` | TIMESTAMP | Record creation time |

Example data:

```
┌──────────────┬──────────────┬────────────┬─────────────────────────┐
│ patreon_time │ youtube_time │ confidence │      matched_text       │
├──────────────┼──────────────┼────────────┼─────────────────────────┤
│        0.000 │       12.500 │     0.9500 │ "Hello everyone"        │
│      120.000 │      132.340 │     0.9200 │ "that's a great point"  │
│      300.000 │      312.100 │     0.8800 │ "let me tell you"       │
└──────────────┴──────────────┴────────────┴─────────────────────────┘

YouTube has ~12.5 second intro before Patreon audio starts
```

## Indexes

### episodes

| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_episodes_patreon_id` | `patreon_id` | Fast lookup by Patreon ID |
| `idx_episodes_processed` | `processed` WHERE NOT processed | Find unprocessed episodes |
| `idx_episodes_is_free` | `is_free` WHERE is_free = true | Find free episodes |

### transcript_segments

| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_..._episode_id` | `episode_id` | Filter by episode |
| `idx_..._word_trgm` | `word` USING gin (pg_trgm) | Fast fuzzy/prefix search |
| `idx_..._episode_time` | `episode_id, start_time` | Ordered retrieval by time |
| `idx_..._word_btree` | `lower(word)` | Exact word matching |
| `idx_..._speaker` | `speaker` | Filter by speaker |
| `idx_..._episode_speaker` | `episode_id, speaker` | Filter by episode + speaker |

### timestamp_anchors

| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_..._episode_id` | `episode_id` | Filter by episode |
| `idx_..._episode_time` | `episode_id, patreon_time` | Ordered retrieval |

## Extensions

- **pg_trgm**: Enables trigram-based fuzzy text search for fast prefix/substring matching on transcript words.

## Triggers

- **update_episodes_updated_at**: Automatically updates `updated_at` column on episodes table when a row is modified.

## Common Queries

### Get transcript for an episode
```sql
SELECT word, start_time, end_time, speaker
FROM transcript_segments
WHERE episode_id = 123
ORDER BY segment_index;
```

### Search for a phrase across all episodes
```sql
SELECT e.title, ts.word, ts.start_time
FROM transcript_segments ts
JOIN episodes e ON e.id = ts.episode_id
WHERE ts.word ILIKE '%bitcoin%'
ORDER BY e.published_at DESC, ts.start_time;
```

### Get unique speakers for an episode
```sql
SELECT DISTINCT speaker
FROM transcript_segments
WHERE episode_id = 123
AND speaker IS NOT NULL;
```

### Get unprocessed episodes
```sql
SELECT id, title, published_at
FROM episodes
WHERE processed = FALSE
ORDER BY published_at DESC;
```

### Convert Patreon timestamp to YouTube timestamp
```sql
SELECT
    patreon_time,
    youtube_time,
    youtube_time - patreon_time as offset
FROM timestamp_anchors
WHERE episode_id = 123
ORDER BY patreon_time;
```

## Scale Reference

For a typical episode (e.g., Episode 1003 - ~1.5 hours):
- **~15,000** transcript segments (words)
- **~800** speaker segments identified by diarization
- **~5-7** unique speakers detected
