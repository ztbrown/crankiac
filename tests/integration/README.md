# Integration Tests for Transcript Speaker Updates

This directory contains integration tests for the transcript speaker update functionality.

## Overview

The integration tests verify the full stack (API endpoint → storage layer → database) for the PATCH `/api/transcripts/segments/speaker` endpoint. These tests use real database connections and verify that data persists correctly.

## Test Files

- `test_transcript_speaker_update.py` - Integration tests for speaker updates using Flask test client
- `test_e2e.py` (in acceptance/) - Full end-to-end test with running server

## Running Integration Tests

### Prerequisites

You need a PostgreSQL database with the crankiac schema. You can either:

1. Use your existing development database (not recommended - tests will modify data temporarily)
2. Create a dedicated test database

### Setup Test Database

```bash
# Create test database
createdb crankiac_test

# Run migrations
export DATABASE_URL="postgresql://localhost:5432/crankiac_test"
python -m app.db.migrations
```

### Run Tests

#### Option 1: Using TEST_DATABASE_URL (Recommended)

Set `TEST_DATABASE_URL` to a separate test database:

```bash
export TEST_DATABASE_URL="postgresql://localhost:5432/crankiac_test"
python3 -m pytest tests/integration/test_transcript_speaker_update.py -v
```

#### Option 2: Using DATABASE_URL

If you don't set TEST_DATABASE_URL, the tests will use your DATABASE_URL:

```bash
export DATABASE_URL="postgresql://localhost:5432/crankiac_test"
python3 -m pytest tests/integration/test_transcript_speaker_update.py -v
```

#### Run All Integration Tests

```bash
python3 -m pytest tests/integration/ -v -m integration
```

### Run End-to-End Test

The end-to-end test starts a Flask server and makes real HTTP requests:

```bash
export TEST_DATABASE_URL="postgresql://localhost:5432/crankiac_test"
python3 -m pytest tests/acceptance/test_e2e.py::test_update_segment_speakers_e2e -v
```

## Test Coverage

### `test_update_segment_speakers_integration`

Tests the complete flow:
1. Creates test episode and transcript segments
2. Updates speakers via PATCH endpoint
3. Verifies updates persisted to database
4. Cleans up test data

### `test_update_segment_speakers_partial_update`

Tests partial update behavior when some segment IDs don't exist:
- Verifies that existing segments are updated
- Verifies that the API returns correct counts

### `test_update_segment_speakers_validation_errors`

Tests validation error handling:
- Missing `updates` field
- Empty updates array
- Invalid ID types
- Invalid speaker types
- Missing required fields

### `test_update_segment_speakers_e2e` (in acceptance/)

Full end-to-end test:
1. Starts Flask server in background
2. Creates test data in database
3. Makes HTTP PATCH requests to server
4. Verifies data persisted
5. Verifies data retrievable via search API
6. Cleans up test data

## Skipping Tests Without Database

If you don't have a test database configured, the integration tests will be automatically skipped:

```bash
$ python3 -m pytest tests/integration/test_transcript_speaker_update.py -v

tests/integration/test_transcript_speaker_update.py::test_update_segment_speakers_integration SKIPPED
tests/integration/test_transcript_speaker_update.py::test_update_segment_speakers_partial_update SKIPPED
tests/integration/test_transcript_speaker_update.py::test_update_segment_speakers_validation_errors SKIPPED

============================== 3 skipped in 0.02s ==============================
```

## CI/CD Integration

For continuous integration, set up a PostgreSQL service and configure TEST_DATABASE_URL:

```yaml
# Example GitHub Actions configuration
services:
  postgres:
    image: postgres:15
    env:
      POSTGRES_DB: crankiac_test
      POSTGRES_PASSWORD: postgres
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5

env:
  TEST_DATABASE_URL: postgresql://postgres:postgres@localhost:5432/crankiac_test
```

## Troubleshooting

### Tests are skipped

Make sure you've set either `TEST_DATABASE_URL` or `DATABASE_URL`:

```bash
echo $TEST_DATABASE_URL
# Should output: postgresql://localhost:5432/crankiac_test
```

### Connection errors

Verify PostgreSQL is running and accessible:

```bash
psql $TEST_DATABASE_URL -c "SELECT 1;"
```

### Schema errors

Make sure migrations have been run on the test database:

```bash
export DATABASE_URL="$TEST_DATABASE_URL"
python -m app.db.migrations
```

## Related Documentation

- [Transcript Editor Implementation Plan](../../docs/transcript-editor-plan.md)
- [Unit Tests](../unit/test_api.py) - Mocked unit tests for the same endpoint
- [Database Schema](../../db/migrations/README.md)
