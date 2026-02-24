# Plan: LLM-Powered Transcript Search (Approach 4)

## Context

The current transcript search (`/api/transcripts/search`) only matches literal words/phrases via PostgreSQL trigram indexes. Searching "felix talking about fighter jets" won't find paragraphs where Felix discusses "the F-35 program" or "Lockheed Martin". We want natural language queries that understand speaker names and expand topics semantically.

**Approach**: Use a local Ollama model to expand the user's query into structured filters (speaker + expanded keywords), then run those against the existing search infrastructure. No new database extensions needed.

## Files to Modify

| File | Change |
|------|--------|
| `app/search/query_expander.py` | **New** — `QueryExpander` class: calls Ollama to parse/expand queries |
| `app/api/transcript_routes.py` | Add `/api/transcripts/smart-search` endpoint |
| `manage.py` | Add `search` subcommand for CLI testing |
| `app/ui/static/app.js` | Wire existing "fuzzy search" checkbox to use smart-search endpoint |
| `.env.example` | Add `OLLAMA_MODEL` and `OLLAMA_URL` vars |

## Implementation

### 1. `app/search/query_expander.py` (new)

```python
class QueryExpander:
    def __init__(self, model="llama3.2", base_url="http://localhost:11434"):
        ...

    def expand(self, query: str, speakers: list[str]) -> ExpandedQuery:
        """Call Ollama to decompose natural language into structured search."""
        # Returns: ExpandedQuery(speaker=str|None, keywords=list[str], original=str)
```

**Prompt strategy**: Provide the list of known speakers from the DB. Ask the model to return JSON with:
- `speaker`: resolved full name (or null if not specified)
- `keywords`: list of 5-10 search terms including synonyms, related concepts, names
- `topic_summary`: one-line description of what the user is looking for

**Ollama integration**: Simple HTTP POST to `http://localhost:11434/api/generate` — no SDK needed, just `requests` (already a dependency). Use `format: "json"` for structured output.

**Fallback**: If Ollama is unreachable or returns bad JSON, fall back to the original query string passed through to existing search.

### 2. `/api/transcripts/smart-search` endpoint

New route in `transcript_routes.py`:

1. Receive query string + existing filters (date range, episode, content type)
2. Fetch speaker list from DB: `SELECT DISTINCT speaker FROM transcript_segments WHERE speaker IS NOT NULL`
3. Call `QueryExpander.expand(query, speakers)`
4. Build search: for each keyword, run the existing `search_single_word()` logic with speaker filter applied
5. Merge results, deduplicate by segment_id, rank by number of keyword hits
6. Apply `EpisodeFilter` for date/episode/content-type filtering
7. Return same JSON shape as existing search (results, query, total, filters) plus `expanded_query` field showing what the LLM produced

**Speaker filtering**: If the LLM returns a speaker, add `AND speaker = %s` to the WHERE clause. Reuse existing search helpers.

**Ranking**: Simple hit-count ranking — paragraphs that match more expanded keywords score higher. Tiebreak by recency.

### 3. `manage.py search` subcommand

```bash
python manage.py search "felix talking about fighter jets"
python manage.py search "will menaker discusses wisconsin" --verbose
```

- Calls `QueryExpander.expand()` and prints the expansion
- Runs the search and prints top 10 results with speaker, timestamp, text preview
- `--verbose` shows the full LLM prompt/response for debugging
- `--no-expand` bypasses LLM and runs raw keyword search (for comparison)

### 4. Frontend wiring (`app.js`)

The UI already has a `filter-fuzzy` checkbox that's unused. Wire it:
- When fuzzy is checked, `performSearch()` hits `/api/transcripts/smart-search` instead of `/api/transcripts/search`
- Display the `expanded_query` info (speaker resolved, keywords used) above results so the user sees what the LLM understood
- Everything else (result rendering, expand, speaker turns) stays the same since response shape is identical

### 5. Config (`.env.example`)

```
OLLAMA_MODEL=llama3.2
OLLAMA_URL=http://localhost:11434
```

## Key Decisions

- **No new pip dependencies** — Ollama is called via `requests` HTTP POST, already in deps
- **No database changes** — works with existing tables and indexes
- **Graceful degradation** — if Ollama is down, falls back to literal search
- **Same response shape** — frontend code changes are minimal (just which endpoint to call)

## Verification

1. Ensure Ollama is running: `ollama list` (should show llama3.2 or similar)
2. Test CLI: `python manage.py search "felix talking about fighter jets" --verbose`
   - Should show LLM expansion: speaker=Felix Biederman, keywords=[fighter jets, F-35, ...]
   - Should return relevant transcript results
3. Test API: `curl "localhost:5000/api/transcripts/smart-search?q=felix+talking+about+fighter+jets"`
   - Should return JSON with results + expanded_query field
4. Test fallback: stop Ollama, run same search — should fall back to literal "felix talking about fighter jets" search
5. Test UI: check "fuzzy search" box, type query, verify results use smart-search endpoint
