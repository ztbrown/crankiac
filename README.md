# Crankiac

A searchable archive of Chapo Trap House podcast transcripts with word-level timestamps, speaker identification, and YouTube integration.

## Features

- **Full-text search** with PostgreSQL trigram indexing for fast prefix and substring matching
- **Phrase search** for finding consecutive word sequences across transcripts
- **Speaker diarization** using pyannote.audio to identify who said what
- **Speaker identification** via voice embeddings — matches speakers to enrolled reference audio
- **VAD pre-filtering** to skip silence before transcription
- **YouTube timestamp alignment** — syncs Patreon transcript times with YouTube video times
- **Audio streaming** with HTTP Range support for in-browser playback
- **Transcript editing** — reassign speakers, edit words, insert/delete segments
- **Date and episode filtering** to narrow search results
- **"On This Day"** feature showing episodes from the same date in previous years
- **Context windows** with speaker turns for search results
- **Mobile-friendly UI** with responsive design

## Tech Stack

**Backend:**
- Python 3.9+ with Flask 3.0
- PostgreSQL with pg_trgm extension for trigram search
- OpenAI Whisper (large-v3 default) for speech-to-text transcription
- pyannote.audio for speaker diarization
- speechbrain for speaker verification/enrollment

**Frontend:**
- Vanilla JavaScript
- HTML5 / CSS3

**Testing:**
- pytest with coverage reporting
- playwright for browser-based acceptance tests

## Installation

### Prerequisites

- Python 3.9 or higher (3.12 recommended for CUDA/Windows)
- PostgreSQL 12 or higher with pg_trgm extension
- ffmpeg (required by Whisper for audio processing)

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd crankiac
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create the PostgreSQL database:
   ```bash
   createdb crankiac
   ```

4. Enable the trigram extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   ```

5. Run database migrations:
   ```bash
   python manage.py migrate
   ```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://localhost:5432/crankiac` |
| `PATREON_SESSION_ID` | Patreon authentication cookie (required for syncing) | - |
| `YOUTUBE_API_KEY` | YouTube Data API key (enables video duration fetching) | - |
| `HF_TOKEN` | HuggingFace token for pyannote models | - |
| `WHISPER_MODEL` | Whisper model size (tiny/base/small/medium/large/large-v3) | `large-v3` |
| `EDITOR_USERNAME` | HTTP Basic Auth username for admin endpoints | `admin` |
| `EDITOR_PASSWORD` | HTTP Basic Auth password for admin endpoints | `changeme` |
| `CORS_ORIGINS` | CORS allowed origins | `*` |
| `HOST` | Server hostname | `127.0.0.1` |
| `PORT` | Server port | `5000` |
| `DEBUG` | Enable Flask debug mode | `false` |

### Example Configuration

```bash
export DATABASE_URL="postgresql://postgres@localhost:5432/crankiac"
export PATREON_SESSION_ID="your_session_id_cookie"
export YOUTUBE_API_KEY="your_youtube_api_key"
export HF_TOKEN="hf_your_huggingface_token"
```

## Database Schema

### Tables

**episodes** — Podcast episode metadata
- `id` — Primary key
- `patreon_id` — Unique Patreon post ID
- `title` — Episode title
- `audio_url` — Patreon audio download URL
- `youtube_url` — Matching free YouTube video URL
- `published_at` — Publication timestamp
- `duration_seconds` — Episode duration
- `is_free` — Whether the episode is freely available on YouTube
- `processed` — Whether transcription is complete

**transcript_segments** — Word-level transcript data
- `id` — Primary key
- `episode_id` — Foreign key to episodes
- `word` — Individual word
- `start_time` / `end_time` — Timestamps in seconds (NUMERIC 10,3)
- `segment_index` — Word position in transcript
- `speaker` — Speaker label (legacy, e.g. "SPEAKER_00")
- `speaker_id` — Foreign key to speakers table
- `speaker_confidence` — Confidence score for speaker assignment (0-1)

**speakers** — Identified speaker names
- `id` — Primary key
- `name` — Unique speaker name (e.g. "Matt", "Felix")

**timestamp_anchors** — Patreon-to-YouTube time alignment
- `id` — Primary key
- `episode_id` — Foreign key to episodes
- `patreon_time` / `youtube_time` — Corresponding timestamps
- `confidence` — Alignment confidence score
- `matched_text` — Text used for alignment matching

### Migrations

Migrations are stored in `db/migrations/` and run in alphabetical order:

```bash
python manage.py migrate
```

## Running the Development Server

```bash
python run.py
```

The server starts at `http://127.0.0.1:5000` by default.

## CLI Commands

### Episode Processing

```bash
# Sync from Patreon and process up to 10 episodes
python manage.py process

# Process specific episodes by number
python manage.py process --episodes 1003,1004,1005

# Process all unprocessed, with diarization and speaker ID
python manage.py process --all --diarize --identify-speakers

# Use a specific Whisper model
python manage.py process --model large-v3

# Enable VAD pre-filtering
python manage.py process --vad
```

| Option | Description |
|--------|-------------|
| `--episode ID` | Process a specific episode by database ID |
| `--title SEARCH` | Find and process episode matching title |
| `--episodes NUMS` | Comma-separated episode numbers (e.g. 1003,1004) |
| `--no-sync` | Skip fetching new episodes from Patreon |
| `--max-sync N` | Maximum episodes to sync (default: 100) |
| `--limit N` | Maximum episodes to process (default: 10) |
| `--offset N` | Skip N episodes before processing |
| `--all` | Process all unprocessed episodes |
| `--model MODEL` | Whisper model size (default: large-v3) |
| `--no-cleanup` | Keep audio files after transcription |
| `--diarize` | Enable speaker diarization |
| `--num-speakers N` | Hint for number of speakers |
| `--identify-speakers` | Enable speaker ID via voice embeddings |
| `--match-threshold F` | Cosine similarity threshold (default: 0.70) |
| `--expected-speakers` | Comma-separated expected speaker names |
| `--vad` | Enable VAD pre-filtering |
| `--vocab PATH` | Path to vocabulary file |
| `--force` | Reprocess already-processed episodes |
| `--all-shows` | Include all show types (not just numbered) |
| `--include-shows` | Comma-separated shows to include |

### Speaker Diarization (re-run on existing transcripts)

```bash
python manage.py diarize --episodes 1003,1004 --identify-speakers
```

### Speaker Enrollment

```bash
# Enroll a single speaker from reference audio
python manage.py enroll-speaker --name "Felix Biederman"

# Enroll all speakers with reference audio directories
python manage.py enroll-speaker --all
```

Reference audio goes in `data/reference_audio/<Speaker Name>/`, embeddings are saved to `data/speaker_embeddings/`.

### Audio Clip Extraction

```bash
# Extract speaker clips from an episode for enrollment
python manage.py extract-clips --episode 123 --speaker "Matt"

# Batch extract from specific episodes
python manage.py extract-clips --episodes 1003,1004,1005
```

### YouTube

```bash
# Fetch YouTube video metadata
python manage.py youtube-fetch

# Match episodes to YouTube videos
python manage.py youtube-sync
python manage.py youtube-sync --all --dry-run

# Align Patreon transcript timestamps with YouTube
python manage.py youtube-align --episodes 1003,1004 --verbose

# Backfill youtube_url and is_free for unmatched episodes
python manage.py youtube-backfill
python manage.py backfill-is-free
```

### Maintenance

```bash
# Delete all episodes except specified ones
python manage.py cleanup-episodes --keep 1003,1004,1005 --confirm
```

## API Endpoints

### Search

`GET /api/transcripts/search` — Search for words or phrases across all transcripts.

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Search query (required) |
| `limit` | int | Maximum results (default: 100, max: 500) |
| `offset` | int | Pagination offset (default: 0) |
| `date_from` | string | Filter by start date (ISO format) |
| `date_to` | string | Filter by end date (ISO format) |
| `episode_number` | int | Filter by episode number |
| `content_type` | string | Filter: all/free/premium (default: all) |

`GET /api/transcripts/search/speaker` — Search within a specific speaker's words. Requires `speaker` parameter.

### Context and Episodes

`GET /api/transcripts/context` — Extended context around a transcript position (episode_id, segment_index, radius).

`GET /api/transcripts/episodes` — List all episodes with processing status.

`GET /api/transcripts/on-this-day` — Episodes published on this date in previous years.

`GET /api/transcripts/speakers` — List speakers. Optional `q` for search, `episode_id` for per-episode stats.

### Transcript Editing

`GET /api/transcripts/episode/<id>/segments` — Paginated transcript segments for an episode.

`GET /api/transcripts/episode/<id>/paragraphs` — Segments grouped by speaker turns.

`GET /api/transcripts/episode/<id>/speakers` — Available speakers for an episode.

`PATCH /api/transcripts/segments/speaker` — Batch update speaker labels.

`PATCH /api/transcripts/assign-speaker` — Assign speaker to a range of segments.

`PATCH /api/transcripts/segments/<id>/word` — Edit a segment's word text.

`POST /api/transcripts/segments/<id>/insert-after` — Insert a new segment.

`DELETE /api/transcripts/segments/<id>` — Delete a segment.

`POST /api/transcripts/speakers` — Create a new speaker.

### Audio

`GET /api/audio/stream/<patreon_id>` — Stream audio with HTTP Range support.

`GET /api/audio/info/<patreon_id>` — Audio file availability and metadata.

### Other

`GET /api/health` — Health check.

## Testing

```bash
# Run all tests
python3 -m pytest

# Run with verbose output
python3 -m pytest -v

# Run with coverage
python3 -m pytest --cov=app

# Run specific categories
python3 -m pytest tests/unit/
python3 -m pytest tests/integration/
python3 -m pytest tests/acceptance/
```

## Project Structure

```
crankiac/
├── app/
│   ├── api/
│   │   ├── app.py                    # Flask application factory
│   │   ├── routes.py                 # Basic API routes (health check)
│   │   ├── transcript_routes.py      # Transcript search & editing API
│   │   ├── audio_routes.py           # Audio streaming API
│   │   └── admin_routes.py           # Admin endpoints (auth-protected)
│   ├── db/
│   │   ├── connection.py             # PostgreSQL connection management
│   │   ├── models.py                 # Data models
│   │   └── repository.py             # Data access layer
│   ├── filters/
│   │   └── episode_filter.py         # Search filter builder (date, episode, content type)
│   ├── patreon/
│   │   ├── client.py                 # Patreon API client
│   │   └── downloader.py             # Audio file downloader
│   ├── transcription/
│   │   ├── whisper_transcriber.py    # Whisper integration
│   │   ├── diarization.py            # pyannote speaker diarization
│   │   ├── speaker_identification.py # Voice embedding speaker matching
│   │   ├── enroll.py                 # Speaker enrollment from reference audio
│   │   ├── clip_extractor.py         # Extract speaker audio clips
│   │   ├── vad.py                    # Voice activity detection pre-filter
│   │   └── storage.py                # Transcript storage layer
│   ├── youtube/
│   │   ├── client.py                 # YouTube video matching
│   │   ├── alignment.py              # Patreon/YouTube timestamp alignment
│   │   └── timestamp.py              # YouTube URL timestamp formatting
│   ├── ui/
│   │   └── static/
│   │       ├── index.html            # Web interface
│   │       ├── app.js                # Client-side JavaScript
│   │       └── styles.css            # Styling
│   ├── config.py                     # Configuration
│   └── pipeline.py                   # Episode processing pipeline
├── db/
│   └── migrations/                   # SQL migration files (001-008)
├── data/
│   ├── reference_audio/              # Speaker reference clips for enrollment
│   └── speaker_embeddings/           # .npy voice embedding files
├── scripts/
│   ├── push_to_remote.py             # Push local DB to Railway
│   └── extract_cth_names.py          # Extract speaker names from transcripts
├── tests/
│   ├── unit/                         # Unit tests
│   ├── integration/                  # Database integration tests
│   ├── api/                          # API endpoint tests
│   └── acceptance/                   # End-to-end browser tests
├── manage.py                         # CLI management tool
├── run.py                            # Application entry point
├── requirements.txt                  # Python dependencies
└── pyproject.toml                    # Project metadata
```

## License

This project is for personal/educational use. Podcast content is property of Chapo Trap House.
