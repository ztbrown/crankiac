# Fix edit recording: semantic diffs instead of positional word-by-word

## Context

When a user edits a transcript paragraph, the frontend sends one API call per word (positional: word 1→word 1, word 2→word 2, etc.). This creates garbage in `edit_history` — e.g. changing "all right with" → "alright with me" logs `right→with` and `with→me` as "corrections". The `mine_corrections` query then returns nonsense like `'the'→'of'`.

**Fix**: Replace the N individual API calls with a single batch endpoint that uses `difflib.SequenceMatcher` to compute a semantic diff, then only logs actual corrections.

## Changes

### 1. `app/transcription/storage.py` — add `edit_paragraph()` method

New method after `delete_segment` (~line 434):

- Takes `segment_ids: list[int]` and `new_text: str`
- Fetches all segments in one query
- Builds old word list, splits new text into words
- Uses `difflib.SequenceMatcher.get_opcodes()` to get semantic diff
- Processes opcodes (right-to-left to avoid index shift issues):
  - `equal` → skip
  - `replace` → update/insert/delete segments as needed, log **one** `field='word'` entry with `old_value=" ".join(old_words)`, `new_value=" ".join(new_words)`
  - `insert` → insert new segments, log `field='insert'`
  - `delete` → delete segments, log `field='delete'`
- All in one transaction
- Returns `{"updated": N, "inserted": N, "deleted": N}`

### 2. `app/api/transcript_routes.py` — add batch edit route

`POST /api/transcripts/paragraphs/edit`

Request: `{"segment_ids": [1,2,3], "new_text": "corrected text"}`
Response: `{"updated": N, "inserted": N, "deleted": N}`

Validation: segment_ids non-empty list of ints, new_text is string.

### 3. `app/ui/static/editor.js` — simplify `handleParagraphBlur` (lines 800-905)

Replace the loop of N individual PATCH/POST/DELETE calls with a single `POST /api/transcripts/paragraphs/edit` request. Same error handling and UI feedback, just one fetch call.

### 4. Tests — `tests/unit/test_edit_history.py`

Add tests for `edit_paragraph`:
- No-change edit → no edit_history entries
- Single word correction → one `field='word'` entry
- Multi-word→single-word replacement → one entry with joined old_value
- Word insertion → `field='insert'` entry
- Word deletion → `field='delete'` entry
- Complex edit → only semantic corrections logged, no positional noise

### Not changed

- `mine_corrections` — works as-is; will now get clean data
- Existing PATCH/DELETE/insert-after endpoints — kept for other uses
- `edit_history` schema — no migration needed, columns are already TEXT

## Verification

1. `python3 -m pytest tests/unit/test_edit_history.py -v`
2. Manual: start API, edit a paragraph in the UI, check `edit_history` table for clean entries
3. `python3 manage.py mine-corrections --dry-run` — should no longer produce nonsense
