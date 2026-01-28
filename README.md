# Crankiac

A searchable archive of Chapo Trap House podcast transcripts with word-level timestamps, speaker identification, and advanced search capabilities.

## Features

- **Full-text search** with PostgreSQL trigram indexing for fast prefix and substring matching
- **Phrase search** for finding consecutive word sequences across transcripts
- **Fuzzy matching** with configurable similarity thresholds
- **Speaker diarization** using pyannote.audio to identify who said what
- **Audio playback integration** with precise timestamp links to Patreon and YouTube
- **Date and episode filtering** to narrow search results
- **"On This Day"** feature showing episodes from the same date in previous years
- **Context windows** displaying surrounding words for search results
- **Mobile-friendly UI** with responsive design

## Tech Stack

**Backend:**
- Python 3.9+ with Flask 3.0
- PostgreSQL with pg_trgm extension for trigram search
- OpenAI Whisper for speech-to-text transcription
- pyannote.audio for speaker diarization

**Frontend:**
- Vanilla JavaScript
- HTML5 / CSS3

**Testing:**
- pytest with coverage reporting
- playwright for browser-based acceptance tests

## Installation

### Prerequisites

- Python 3.9 or higher
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
| `HF_TOKEN` | HuggingFace token for pyannote models | - |
| `WHISPER_MODEL` | Whisper model size (tiny/base/small/medium/large) | `base` |
| `HOST` | Server hostname | `127.0.0.1` |
| `PORT` | Server port | `5000` |
| `DEBUG` | Enable Flask debug mode | `false` |

### Example Configuration

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/crankiac"
export PATREON_SESSION_ID="your_session_id_cookie"
export HF_TOKEN="hf_your_huggingface_token"
export WHISPER_MODEL="base"
```

## Database Setup

### Schema

The database consists of two main tables:

**episodes** - Podcast episode metadata
- `id` - Primary key
- `patreon_id` - Unique Patreon post ID
- `title` - Episode title
- `audio_url` - Patreon audio download URL
- `youtube_url` - Matching free YouTube video URL
- `published_at` - Publication timestamp
- `duration_seconds` - Episode duration
- `processed` - Whether transcription is complete

**transcript_segments** - Word-level transcript data
- `id` - Primary key
- `episode_id` - Foreign key to episodes
- `word` - Individual word
- `start_time` - Word start timestamp (seconds)
- `end_time` - Word end timestamp (seconds)
- `segment_index` - Word position in transcript
- `speaker` - Identified speaker name (optional)

### Migrations

Migrations are stored in `db/migrations/` and run in alphabetical order:

```bash
python manage.py migrate
```

## Running the Development Server

```bash
python run.py
```

The server starts at `http://127.0.0.1:5000` by default. Open this URL in a browser to access the search interface.

## Episode Processing Pipeline

The pipeline syncs episodes from Patreon, downloads audio, transcribes with Whisper, and stores word-level segments.

### Basic Usage

```bash
# Sync from Patreon and process up to 10 episodes
python manage.py process

# Process all unprocessed episodes
python manage.py process --all

# Skip Patreon sync, process local episodes only
python manage.py process --no-sync
```

### Pipeline Options

| Option | Description |
|--------|-------------|
| `--no-sync` | Skip fetching new episodes from Patreon |
| `--max-sync N` | Maximum episodes to sync (default: 100) |
| `--limit N` | Maximum episodes to process (default: 10) |
| `--all` | Process all unprocessed episodes |
| `--model MODEL` | Whisper model size (default: base) |
| `--no-cleanup` | Keep audio files after transcription |

### YouTube URL Sync

Match episodes to free YouTube videos:

```bash
# Sync episodes without YouTube URLs
python manage.py youtube-sync

# Re-match all episodes
python manage.py youtube-sync --all

# Preview matches without saving
python manage.py youtube-sync --dry-run

# Adjust date matching tolerance (default: 7 days)
python manage.py youtube-sync --tolerance 14
```

## API Documentation

### Search Transcripts

```
GET /api/transcripts/search
```

Search for words or phrases across all transcripts.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Search query (required) |
| `limit` | int | Maximum results (default: 100, max: 500) |
| `offset` | int | Pagination offset (default: 0) |
| `fuzzy` | bool | Enable fuzzy matching (default: true) |
| `threshold` | float | Similarity threshold 0.1-0.9 (default: 0.3) |
| `date_from` | string | Filter by start date (ISO format) |
| `date_to` | string | Filter by end date (ISO format) |
| `episode_number` | string | Filter by episode number |
| `content_type` | string | Filter: all/free/premium (default: all) |

**Response:**

```json
{
  "results": [
    {
      "word": "capitalism",
      "start_time": 1234.56,
      "end_time": 1235.12,
      "segment_index": 4521,
      "speaker": "Matt",
      "episode_id": 123,
      "episode_title": "Episode 456",
      "patreon_id": "78901234",
      "published_at": "2023-06-15T12:00:00Z",
      "youtube_url": "https://youtube.com/watch?v=...",
      "context": "...the problem with capitalism is that...",
      "similarity": 1.0
    }
  ],
  "query": "capitalism",
  "total": 1543,
  "limit": 100,
  "offset": 0,
  "fuzzy": true,
  "threshold": 0.3,
  "filters": {}
}
```

### Get Context

```
GET /api/transcripts/context
```

Get surrounding words for a specific transcript position.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `episode_id` | int | Episode ID (required) |
| `segment_index` | int | Center word index (required) |
| `radius` | int | Context radius (default: 50, max: 200) |

**Response:**

```json
{
  "context": "the full context text with surrounding words",
  "episode_id": 123,
  "center_segment_index": 4521,
  "center_word_index": 50,
  "center_speaker": "Matt",
  "speaker_turns": ["Matt", "Will", "Matt"],
  "start_time": 1200.0,
  "end_time": 1280.0,
  "word_count": 101
}
```

### On This Day

```
GET /api/transcripts/on-this-day
```

Get episodes published on this date in previous years.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `month` | int | Month 1-12 (default: current) |
| `day` | int | Day 1-31 (default: current) |
| `limit` | int | Maximum results (default: 50, max: 200) |

**Response:**

```json
{
  "episodes": [
    {
      "id": 123,
      "patreon_id": "78901234",
      "title": "Episode 456",
      "published_at": "2022-06-15T12:00:00Z",
      "youtube_url": "https://youtube.com/watch?v=...",
      "processed": true,
      "word_count": 15234,
      "year": 2022
    }
  ],
  "date": {"month": 6, "day": 15},
  "years_ago": [1, 2, 3]
}
```

### List Episodes

```
GET /api/transcripts/episodes
```

Get all episodes with processing status.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Maximum results (default: 100, max: 500) |
| `offset` | int | Pagination offset (default: 0) |

**Response:**

```json
{
  "episodes": [
    {
      "id": 123,
      "patreon_id": "78901234",
      "title": "Episode 456",
      "published_at": "2023-06-15T12:00:00Z",
      "processed": true,
      "word_count": 15234
    }
  ]
}
```

### List Speakers

```
GET /api/transcripts/speakers
```

Get unique speakers with word counts.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `episode_id` | int | Filter to specific episode (optional) |

**Response:**

```json
{
  "speakers": [
    {"speaker": "Matt", "word_count": 523456},
    {"speaker": "Will", "word_count": 498234},
    {"speaker": "Felix", "word_count": 445123}
  ]
}
```

### Search by Speaker

```
GET /api/transcripts/search/speaker
```

Search within a specific speaker's words.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Search query (optional) |
| `speaker` | string | Speaker name (required) |
| `limit` | int | Maximum results (default: 100, max: 500) |
| `offset` | int | Pagination offset (default: 0) |

### Health Check

```
GET /api/health
```

**Response:**

```json
{"status": "ok"}
```

## Testing

### Running Tests

```bash
# Run all tests
python3 -m pytest

# Run with verbose output
python3 -m pytest -v

# Run with coverage report
python3 -m pytest --cov=app

# Run specific test categories
python3 -m pytest -m unit
python3 -m pytest -m integration
```

### Test Structure

```
tests/
├── unit/                    # Unit tests for individual components
│   ├── test_search.py       # Search functionality tests
│   ├── test_filters.py      # Filter logic tests
│   └── test_youtube.py      # YouTube matching tests
├── integration/             # Integration tests with database
│   ├── test_api.py          # API endpoint tests
│   └── test_pipeline.py     # Pipeline integration tests
└── acceptance/              # End-to-end browser tests
    └── test_ui.py           # UI acceptance tests
```

## Project Structure

```
crankiac/
├── app/
│   ├── api/
│   │   ├── app.py               # Flask application factory
│   │   ├── routes.py            # Basic API routes
│   │   └── transcript_routes.py # Transcript search API
│   ├── db/
│   │   ├── connection.py        # PostgreSQL connection management
│   │   ├── models.py            # Data models
│   │   └── repository.py        # Data access layer
│   ├── patreon/
│   │   ├── client.py            # Patreon API client
│   │   └── downloader.py        # Audio file downloader
│   ├── transcription/
│   │   ├── whisper_transcriber.py  # Whisper integration
│   │   ├── diarization.py       # Speaker identification
│   │   └── storage.py           # Transcript storage
│   ├── youtube/
│   │   └── client.py            # YouTube matching
│   ├── ui/
│   │   └── static/
│   │       ├── index.html       # Web interface
│   │       ├── app.js           # Client-side JavaScript
│   │       └── styles.css       # Styling
│   ├── config.py                # Configuration
│   └── pipeline.py              # Episode processing pipeline
├── db/
│   └── migrations/              # SQL migration files
├── tests/                       # Test suite
├── manage.py                    # CLI management tool
├── run.py                       # Application entry point
├── requirements.txt             # Python dependencies
└── pyproject.toml               # Project metadata
```

## Contributing

1. Create a feature branch from `main`
2. Make your changes with clear, focused commits
3. Ensure all tests pass: `python3 -m pytest`
4. Submit a pull request with a description of changes

### Code Style

- Follow PEP 8 for Python code
- Use type hints for function signatures
- Keep functions focused and under 50 lines where practical
- Write tests for new functionality

### Commit Messages

Use conventional commit format:
- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `test:` Test additions or fixes
- `refactor:` Code refactoring

## License

This project is for personal/educational use. Podcast content is property of Chapo Trap House.
