# Transcript Search: "clips of felix talking about fighter jets"

## The Problem

We have word-level transcript data with speaker labels and timestamps. We want natural language queries like "clips of felix talking about fighter jets" to return ranked results with playable timestamps.

**Current data**: ~105k words across 8 diarized episodes, 6 identified speakers. Each word has `speaker`, `start_time`, `end_time`. Paragraphs are reconstructed by grouping consecutive words by speaker (via `TranscriptStorage.get_episode_paragraphs()`).

## What the Query Implies

"clips of felix talking about fighter jets" decomposes into:

| Component | Type | Example |
|-----------|------|---------|
| **speaker filter** | structured | `speaker = 'Felix Biederman'` |
| **topic/semantic match** | unstructured | paragraphs *about* fighter jets (not just containing the words) |
| **result format** | audio clips | start/end timestamps for playback |

The hard part is the semantic match — "fighter jets" should also match "F-35", "stealth bomber", "Top Gun", "the Pentagon's new plane", etc.

---

## Approach 1: PostgreSQL Full-Text Search + Speaker Filter

**Complexity**: Low | **New deps**: None | **Semantic understanding**: None

Use PostgreSQL's built-in `tsvector`/`tsquery` on a materialized paragraph table. Already have `pg_trgm` installed for fuzzy matching.

```sql
-- New table: materialized paragraphs
CREATE TABLE transcript_paragraphs (
  id SERIAL PRIMARY KEY,
  episode_id INT REFERENCES episodes(id),
  speaker VARCHAR,
  text TEXT,
  start_time NUMERIC,
  end_time NUMERIC,
  tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);
CREATE INDEX idx_paragraphs_tsv ON transcript_paragraphs USING gin(tsv);
CREATE INDEX idx_paragraphs_speaker ON transcript_paragraphs(speaker);
```

```sql
-- Query: "felix talking about fighter jets"
SELECT * FROM transcript_paragraphs
WHERE speaker ILIKE '%felix%'
  AND tsv @@ plainto_tsquery('english', 'fighter jets')
ORDER BY ts_rank(tsv, plainto_tsquery('english', 'fighter jets')) DESC
LIMIT 20;
```

**Pros**: Zero new infrastructure, fast, works today.
**Cons**: Only matches literal words. "fighter jets" won't find "F-35" or "the plane costs a trillion dollars". No semantic understanding at all.

**Good for**: Known-keyword searches ("felix mentions Luigi Mangione", "will talks about Wisconsin").

---

## Approach 2: Paragraph Embeddings + Vector Search (pgvector)

**Complexity**: Medium | **New deps**: `pgvector`, embedding model | **Semantic understanding**: High

Embed each paragraph into a vector, store in PostgreSQL with pgvector, do cosine similarity search.

**Pipeline**:
1. Materialize paragraphs from word-level data (same as Approach 1)
2. Embed each paragraph using a model (OpenAI `text-embedding-3-small`, or local `all-MiniLM-L6-v2`)
3. Store embeddings in a `vector` column
4. Query = embed the search string, find nearest neighbors

```sql
CREATE EXTENSION vector;

ALTER TABLE transcript_paragraphs
  ADD COLUMN embedding vector(384);  -- dimension depends on model

-- Query
SELECT *, 1 - (embedding <=> $query_embedding) as similarity
FROM transcript_paragraphs
WHERE speaker ILIKE '%felix%'
ORDER BY embedding <=> $query_embedding
LIMIT 20;
```

**Embedding choices**:

| Model | Dim | Speed | Quality | Cost |
|-------|-----|-------|---------|------|
| `all-MiniLM-L6-v2` (local) | 384 | Fast | Good | Free |
| `text-embedding-3-small` (OpenAI) | 1536 | API call | Better | ~$0.01 for all 8 eps |
| `nomic-embed-text` (local) | 768 | Medium | Great | Free |

**Paragraph chunking strategy**: The natural speaker-turn paragraphs from `get_episode_paragraphs()` vary wildly in length (1 word to 500+ words). For embedding quality:
- Merge very short paragraphs (< 20 words) with their neighbors (same speaker)
- Split very long paragraphs (> 200 words) into ~100-word overlapping windows
- Target: 50-150 word chunks, each with speaker + timestamps

**Pros**: Understands meaning. "fighter jets" matches "the F-35 program" and "military aviation". Speaker filter is trivial.
**Cons**: Requires embedding pipeline (one-time batch + incremental on new episodes). Needs pgvector extension. Embedding quality depends on chunk size.

**Good for**: Exactly the use case described. This is the right tool for semantic search.

---

## Approach 3: Hybrid (FTS + Embeddings + Reranking)

**Complexity**: Medium-High | **New deps**: pgvector, embedding model, reranker | **Semantic understanding**: Highest

Combine Approaches 1 and 2 with a reranking step.

**Pipeline**:
1. **Retrieve** (broad): Pull top 50 candidates via both FTS and vector similarity
2. **Rerank** (precise): Use a cross-encoder or LLM to rerank the candidates against the original query
3. **Return**: Top 10 results with confidence scores

```python
# Retrieve from both sources
fts_results = db.fts_search(speaker="Felix", query="fighter jets", limit=50)
vec_results = db.vector_search(speaker="Felix", query="fighter jets", limit=50)

# Merge and deduplicate
candidates = merge_unique(fts_results, vec_results)

# Rerank with cross-encoder (fast, local)
from sentence_transformers import CrossEncoder
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
scores = reranker.predict([(query, c.text) for c in candidates])

# Return top results
ranked = sorted(zip(candidates, scores), key=lambda x: -x[1])[:10]
```

**Pros**: Best result quality. FTS catches exact matches that embeddings sometimes miss. Reranker adds precision.
**Cons**: Most complex. Three-stage pipeline. Cross-encoder adds latency (~200ms for 50 candidates).

**Good for**: Production search where result quality really matters.

---

## Approach 4: LLM-as-Search (Query Understanding + Structured Retrieval)

**Complexity**: Low-Medium | **New deps**: LLM API | **Semantic understanding**: Depends on retrieval layer

Use an LLM to decompose the natural language query into structured filters, then run those against whatever retrieval layer exists.

```python
def search(query: str):
    # Step 1: LLM decomposes the query
    prompt = f"""Parse this transcript search query into structured filters.
    Query: "{query}"
    Available speakers: {speaker_list}
    Return JSON: {{"speaker": "...", "keywords": [...], "topic": "..."}}"""

    filters = llm.parse(prompt)
    # => {"speaker": "Felix Biederman", "keywords": ["fighter jets", "F-35", "military"], "topic": "military aviation"}

    # Step 2: Use expanded keywords for FTS or vector search
    results = db.fts_search(
        speaker=filters["speaker"],
        query=" OR ".join(filters["keywords"])
    )
    return results
```

**Pros**: Natural query understanding. LLM resolves "felix" → "Felix Biederman" and expands "fighter jets" into related terms. Works on top of Approach 1 (no embeddings needed).
**Cons**: LLM latency on every query. Keyword expansion is only as good as the LLM's guesses. Still no true semantic matching in the retrieval layer.

**Good for**: Making Approach 1 (FTS) much smarter without building an embedding pipeline. Good stepping stone.

---

## Approach 5: Pre-computed Topic Segments (Offline Summarization)

**Complexity**: Medium | **New deps**: LLM API | **Semantic understanding**: High (offline)

Instead of searching raw transcripts, pre-process episodes into topic segments with summaries and tags. Search over the summaries.

**Offline pipeline**:
1. Take each episode's full transcript
2. Use an LLM to segment into topics: "0:00-4:30 — Intro and news roundup", "4:30-15:00 — Discussion of F-35 program and military spending", etc.
3. Store topic segments with: summary, tags, speaker breakdown, timestamps
4. FTS or embeddings on the summaries (much smaller corpus)

```sql
CREATE TABLE topic_segments (
  id SERIAL PRIMARY KEY,
  episode_id INT REFERENCES episodes(id),
  start_time NUMERIC,
  end_time NUMERIC,
  summary TEXT,
  tags TEXT[],            -- ['military', 'fighter jets', 'F-35', 'pentagon']
  speakers TEXT[],        -- ['Felix Biederman', 'Will Menaker']
  primary_speaker VARCHAR
);
```

```sql
-- "felix talking about fighter jets"
SELECT * FROM topic_segments
WHERE 'Felix Biederman' = ANY(speakers)
  AND (tags && ARRAY['fighter jets', 'military', 'aviation']
       OR summary ILIKE '%fighter%' OR summary ILIKE '%jet%')
ORDER BY start_time;
```

**Pros**: Best user experience — returns coherent topic segments, not arbitrary paragraph chunks. Tags enable faceted search. Summaries are human-readable. Tiny search corpus.
**Cons**: Expensive upfront LLM cost to process all episodes. Needs to run on every new episode. Topic boundaries are subjective.

**Good for**: Building a browseable episode index / "chapter markers" that also enables search.

---

## Recommendation

For where we are now (8 episodes, ~105k words, PostgreSQL):

| Phase | Approach | Why |
|-------|----------|-----|
| **Now** | **Approach 4** (LLM query expansion + FTS) | Cheapest path to useful search. No new infra. LLM turns "felix fighter jets" into a good SQL query. |
| **Soon** | **Approach 2** (pgvector embeddings) | When FTS misses too much. One-time embed pipeline, then semantic search just works. |
| **Later** | **Approach 5** (topic segments) | When you want chapter markers / browseable episode structure anyway. Doubles as search. |

Approach 3 (hybrid + reranking) is worth it if search quality becomes critical, but it's over-engineered for 8 episodes.

### Quick Win: Approach 4 Implementation Sketch

Minimal viable search with what we have today:

```python
# manage.py search --query "felix talking about fighter jets"

def search_transcripts(query: str):
    # 1. LLM parses query → speaker + expanded keywords
    # 2. Materialize paragraphs (or use get_episode_paragraphs)
    # 3. Filter by speaker, FTS on keywords
    # 4. Return top N with episode title + timestamps + text preview
```

This could be a `manage.py search` subcommand or an API endpoint at `/api/transcripts/search?q=...` for the web UI.
