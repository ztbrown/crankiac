# LLM Post-Processing Design for Crankiac Transcription System

## 1. Architecture Overview

After Whisper transcribes and pyannote diarizes an episode, run a cheap LLM (Claude Haiku) over low-confidence sections to fix transcription errors. The LLM gets surrounding context and uses language understanding to correct words that Whisper was acoustically unsure about.

```
                           EXISTING PIPELINE
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  FETCH   │───>│ DOWNLOAD │───>│ WHISPER  │───>│ DIARIZE  │───>│  STORE   │
│ Episodes │    │  Audio   │    │(+confid.)│    │(pyannote)│    │ Segments │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                                      │
                                                                      ▼
                                                               ┌──────────┐
                                                               │ CORRECT  │
                                                               │(dict map)│
                                                               └──────────┘
                                                                      │
                                                                      ▼
                                                    ┌─────────────────────────┐
                                                    │   NEW: LLM POST-PROC   │
                                                    │  1. Load segments       │
                                                    │  2. Find low-conf      │
                                                    │  3. Build chunks        │
                                                    │  4. Call LLM            │
                                                    │  5. Apply fixes         │
                                                    │  6. Log to edit_history │
                                                    └─────────────────────────┘
```

## 2. When Does This Run?

**Both** as a standalone `manage.py` command and optionally in the pipeline.

### Standalone command (primary interface)

```bash
# Single episode
python manage.py llm-correct --episode 11

# Batch: unprocessed episodes
python manage.py llm-correct --limit 10

# Dry run
python manage.py llm-correct --episode 11 --dry-run

# Adjust threshold
python manage.py llm-correct --episode 11 --threshold 0.6

# Force re-run
python manage.py llm-correct --episode 11 --force
```

### Pipeline integration (optional, disabled by default)

When `enable_llm_correction=True`, runs after correction dictionary and before storage.

### Prerequisite: word_confidence data

Only 1 of 68 transcribed episodes currently has `word_confidence`. Episodes without it are skipped with a warning suggesting `backfill-word-confidence`.

## 3. What Gets Sent to the LLM?

### Threshold: 0.7 (configurable)

Based on episode 11 data (15,540 words):

| Threshold | Words Below | % of Episode | Est. Chunks |
|-----------|-------------|--------------|-------------|
| 0.5       | 322         | 2.1%         | ~3          |
| 0.6       | 480         | 3.1%         | ~4          |
| **0.7**   | **735**     | **4.7%**     | **~6**      |
| 0.8       | 1,092       | 7.0%         | ~7          |

### Chunking strategy

1. **Find low-confidence regions**: contiguous runs where any word has confidence < threshold. Group words within 15 indices of each other.
2. **Expand with context**: ±50 words of high-confidence text around each region.
3. **Merge overlapping chunks**.
4. **Cap at ~2,000 words per chunk**. Split at speaker boundaries if needed.

Result: ~6-8 chunks per episode, each ~150-300 words with a few flagged words marked.

## 4. Prompt Design

### System prompt

```
You are a transcript correction assistant for "Chapo Trap House," a political
comedy podcast. You are reviewing sections of an automated transcript (produced
by Whisper) where the speech-to-text model was uncertain about specific words.

The podcast's regular hosts are Will Menaker, Matt Christman, Felix Biederman,
Amber A'Lee Frost, and Virgil Texas. Common guests include Derek Davison,
Brendan James, and Chris Wade. The show discusses US politics, foreign policy,
media criticism, and internet culture with heavy use of irony and satire.

Words marked with [?word?] are low-confidence transcriptions that may be wrong.
Your job is to examine the surrounding context and determine whether each flagged
word is correct or should be replaced.

Common Whisper errors on this podcast:
- "Choppo" or "chop" instead of "Chapo"
- Names of politicians, pundits, and public figures mangled
- Filler words inserted or omitted ("um," "uh," "like")
- Homophones confused ("their/there/they're," "your/you're")
- Podcast-specific vocabulary: "failson," "poster," "reply guy," "the bit"

Rules:
1. Only suggest corrections for words marked with [?word?].
2. If a flagged word appears correct in context, include it with corrected=null.
3. Preserve the original punctuation style.
4. Do not add or remove words — only replace existing ones.
5. For proper nouns you are unsure about, include your best guess with a note.
6. Respond with ONLY a JSON object.

Response format:
{
  "corrections": [
    {"index": <segment_index>, "original": "<flagged word>",
     "corrected": "<fixed word or null>", "reason": "<brief explanation>"}
  ]
}
```

### User prompt template

```
Episode: "{episode_title}"

Transcript section (words marked [?word?] have low confidence):

{formatted_chunk}

Review each flagged word and return corrections as JSON.
```

### Formatted chunk example

```
[Will Menaker]
some sort of i don't know non [?insanity?](0.015) as [?part?](0.448) of your
public facing persona and like [?the?](0.382) [?felix?](0.709) the thing

[Felix Biederman]
yeah well that's [?choppo,?](0.531) everyone. [?Obviously,?](0.603) we've got
a lot to talk about
```

## 5. How Corrections Are Applied

### Database updates

```sql
-- Update the word
UPDATE transcript_segments SET word = 'Chapo,' WHERE id = 12345;

-- Log with distinct field type
INSERT INTO edit_history (episode_id, segment_id, field, old_value, new_value)
VALUES (11, 12345, 'llm_word', 'choppo,', 'Chapo,');
```

Using `field = 'llm_word'` means:
- LLM corrections are distinguishable from human corrections
- `mine_corrections` (filters on `field='word'`) won't pick up LLM corrections — intentional, since humans are ground truth
- Easy to query: `SELECT * FROM edit_history WHERE field = 'llm_word'`

### Word confidence after correction

Set `word_confidence = NULL` for LLM-corrected words. The original Whisper confidence no longer applies, and NULL signals "externally corrected."

### Tracking corrected episodes

New migration:

```sql
-- 014_add_llm_corrected.sql
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS llm_corrected BOOLEAN DEFAULT FALSE;
```

## 6. Cost Analysis

Based on episode 11 (15,540 words, 735 low-confidence at 0.7 threshold):
- ~6 chunks, ~19,200 input tokens, ~1,200 output tokens per episode

| Model | Per Episode | 68 Episodes | 1,000 Episodes |
|-------|-------------|-------------|----------------|
| **Haiku 3.5** | $0.02 | $1.37 | $20 |
| Haiku 3.5 + Batch API | $0.01 | $0.69 | $10 |
| Sonnet 4.5 | $0.08 | $5.14 | $76 |

**Recommendation**: Haiku 3.5. At $20 for the full catalog, it's essentially free. The task is narrow and well-suited to a small model. Use Batch API for large backfill runs.

## 7. Speaker Diarization Corrections

**Out of scope for this design.** Speaker attribution correction is a different problem (different threshold, different prompt, more subjective). Noted as a future extension with an optional `--check-speakers` flag.

## 8. New Files

| File | Purpose |
|------|---------|
| `app/transcription/llm_corrector.py` | Core logic: chunking, prompting, applying corrections |
| `app/transcription/llm_prompts.py` | Prompt templates |
| `db/migrations/014_add_llm_corrected.sql` | New column on episodes |

### Modifications to existing files

| File | Change |
|------|--------|
| `manage.py` | Add `llm-correct` subcommand |
| `app/pipeline.py` | Optional `enable_llm_correction` parameter |
| `requirements.txt` | Add `anthropic>=0.40.0` |

## 9. Edge Cases

- **Invalid JSON from LLM**: Retry once, then skip chunk and log. Don't mark episode as corrected.
- **LLM suggests adding/removing words**: Reject. Only 1:1 replacements.
- **LLM suggests changing unmarked words**: Reject.
- **No low-confidence words**: Skip and mark corrected (nothing to fix is valid).
- **No word_confidence data**: Skip with warning.
- **Rate limiting**: Configurable delay between calls, exponential backoff on 429.
- **Concurrent runs**: Use `UPDATE ... WHERE llm_corrected = FALSE RETURNING id` as advisory lock.

## 10. What This Does NOT Do

- Re-transcribe audio (operates on existing Whisper output only)
- Correct speaker labels (future feature)
- Handle word insertions or deletions (only 1:1 replacements)
- Replace manual review (reduces errors found during review)
- Update the correction dictionary (LLM edits logged separately as `llm_word`)
- Use Batch API by default (recommended for backfill, separate implementation phase)

## 11. Implementation Sequence

1. Add `anthropic` to `requirements.txt`
2. Create migration `014_add_llm_corrected.sql`
3. Create `app/transcription/llm_prompts.py` (pure data)
4. Create `app/transcription/llm_corrector.py` (core logic)
5. Add `llm-correct` command to `manage.py`
6. Add optional pipeline integration to `app/pipeline.py`
7. Tests: unit tests for chunking/formatting (mock Anthropic API)
