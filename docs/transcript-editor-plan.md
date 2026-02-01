# Transcript Editor Implementation Plan

## Overview
Build a web-based transcript editor that allows editing speaker labels and correcting transcribed words. The tool will integrate with the existing Flask API and use word-level editing with range selection for bulk speaker changes.

## Requirements
- Edit speaker labels for individual words or ranges of words
- Correct improperly transcribed words
- Range selection (Shift+click) for bulk speaker assignment
- Word-level editing only (preserve timestamps)
- Web-based interface integrated with existing Flask app

## Architecture

### Backend: New API Endpoints
Add 4 new endpoints to `/app/api/transcript_routes.py`:

1. **GET `/api/transcripts/episode/<episode_id>/segments`** - Load transcript for editing
   - Query params: `limit` (default 100), `offset` (default 0), `speaker` (optional filter)
   - Returns: paginated segments with episode info and available speakers
   - Response includes: segments list, total count, episode title, speakers list

2. **PATCH `/api/transcripts/segments/speaker`** - Update speaker for multiple segments
   - Request body: `{"segment_ids": [1, 2, 3], "speaker": "Matt"}`
   - Returns: `{"updated": 3, "segment_ids": [1, 2, 3], "speaker": "Matt"}`
   - Uses batch UPDATE in single transaction

3. **PATCH `/api/transcripts/segments/<segment_id>/word`** - Edit word text
   - Request body: `{"word": "corrected_word"}`
   - Returns: `{"id": 123, "word": "corrected_word", "updated": true}`

4. **GET `/api/transcripts/episode/<episode_id>/speakers`** - Get available speakers
   - Returns: KNOWN_SPEAKERS + distinct speakers from episode
   - Response: `{"known_speakers": [...], "episode_speakers": [...]}`

### Backend: New Storage Methods
Add 3 methods to `TranscriptStorage` class in `/app/transcription/storage.py`:

1. **`update_word_text(segment_id: int, new_word: str) -> bool`**
   - Single UPDATE query with validation
   - Returns True if segment was found and updated

2. **`update_speakers_by_ids(segment_ids: list[int], speaker: str) -> int`**
   - Batch UPDATE using `WHERE id = ANY(%s)`
   - Returns count of updated rows
   - Single transaction for all updates

3. **`get_segments_paginated(episode_id: int, limit: int, offset: int, speaker: Optional[str]) -> tuple[list[TranscriptSegment], int]`**
   - Get page of segments ordered by segment_index
   - Returns (segments, total_count) tuple
   - Optional speaker filter

### Frontend: New Editor Interface
Create new files in `/app/ui/static/`:

**1. `editor.html`** - Editor page structure
- Episode selector dropdown
- Toolbar with speaker dropdown and apply button
- Segment table with columns: checkbox, time, speaker, word, actions
- Pagination controls
- "Select All" checkbox
- Save/undo/redo buttons (client-side undo)

**2. `editor.js`** - Editor JavaScript logic
- `TranscriptEditor` class with methods:
  - `loadEpisodes()` - populate episode dropdown
  - `loadTranscript(episodeId)` - fetch and render segments
  - `renderSegments(segments)` - create table rows
  - `handleRangeSelection(start, end)` - Shift+click support
  - `updateSpeaker(segmentIds, speaker)` - bulk speaker update
  - `updateWord(segmentId, word)` - single word update
  - `handlePagination(direction)` - next/previous pages
  - `undo()/redo()` - client-side undo stack
- Debounced word editing (500ms delay before save)
- Visual feedback: loading spinners, success/error toasts
- Range selection: click first checkbox, Shift+click last checkbox

**3. `editor.css`** - Editor styles
- Table layout with fixed header
- Color-coded speakers (consistent colors per speaker)
- Visual indicators: selected rows, edited words, loading states
- Responsive design for table overflow

### Frontend: Route Integration
Modify `/app/api/app.py` to add editor route:
```python
@app.route("/editor")
def editor():
    return app.send_static_file("editor.html")
```

Optional: Add "Editor" link to existing search UI (`/app/ui/static/index.html`)

## User Flow

1. User navigates to `/editor`
2. Select episode from dropdown (populated from `/api/transcripts/episodes`)
3. Editor loads first 100 segments and available speakers
4. User can:
   - Edit individual words by typing in input fields (auto-saves on blur)
   - Select word ranges with Shift+click
   - Change speaker for selected words using toolbar
   - Navigate pages with prev/next buttons
   - Filter by speaker using dropdown
5. Changes save immediately with visual feedback
6. Undo/redo available for recent changes (client-side)

## Implementation Details

### Pagination Strategy
- Load 100 segments per page (15,000 segments = 150 pages)
- Lazy loading to prevent browser freeze
- Preserve selection state across page changes
- Page indicator: "Page 1 of 150"

### Range Selection
- Click checkbox on first word
- Shift+click checkbox on last word
- JavaScript selects all segments between indices
- Highlight selected rows visually
- Bulk speaker update applies to all selected

### Word Editing
- Inline `<input>` fields for each word
- Debounce API calls (500ms after typing stops)
- Yellow border for unsaved changes
- Green checkmark on successful save
- Red X on error with revert

### Speaker Editing
- Dropdown next to each word (individual changes)
- Toolbar dropdown + "Apply" button (bulk changes)
- Speaker options: KNOWN_SPEAKERS + any existing speakers in episode
- Allow custom speaker names for guests

### Performance
- Pagination prevents rendering 15,000 rows
- Batch updates in single transaction
- Database indexes already exist on episode_id and speaker
- Debounced API calls reduce server load

### Validation
- Speaker: Allow any non-empty string
- Word: Non-empty, max 200 chars, trim whitespace
- Segment ID: Must exist in database

### Error Handling
- Network errors: Show toast notification
- Invalid inputs: Show inline error messages
- Transaction failures: Rollback database changes
- Retry logic: Exponential backoff for network errors

## Edge Cases

1. **Concurrent editing**: Episode lock mechanism (future enhancement)
2. **Re-processing conflict**: Add `editing_locked` boolean to episodes table (future)
3. **Empty episodes**: Show "No segments found" message
4. **Null speakers**: Allow editing from null to valid speaker
5. **Special characters**: Escape HTML in word display
6. **Browser compatibility**: Test in Chrome, Firefox, Safari

## Critical Files

### Backend (Modify)
- `/app/api/transcript_routes.py` - Add 4 new endpoints
- `/app/transcription/storage.py` - Add 3 new methods
- `/app/api/app.py` - Add `/editor` route

### Frontend (Create)
- `/app/ui/static/editor.html` - Editor page HTML
- `/app/ui/static/editor.js` - Editor JavaScript
- `/app/ui/static/editor.css` - Editor styles

### Frontend (Modify - Optional)
- `/app/ui/static/index.html` - Add link to editor

## Testing & Verification

### Backend Tests
1. Test GET segments endpoint with pagination and filters
2. Test PATCH speaker update with single and multiple IDs
3. Test PATCH word update with validation
4. Test transaction rollback on errors
5. Test with episode containing 15,000 segments

### Frontend Tests
1. Load editor with large episode (15,000 segments)
2. Test pagination (next/prev)
3. Test range selection with Shift+click
4. Test bulk speaker update
5. Test individual word editing with auto-save
6. Test undo/redo functionality
7. Test speaker filter

### Integration Test
1. Select episode from dropdown
2. Edit multiple words
3. Select range of 10 words with Shift+click
4. Change speaker to "Matt"
5. Verify database updates correctly
6. Reload page and verify changes persisted

### End-to-End Verification
1. Navigate to `/editor`
2. Select an episode
3. Make edits to words and speakers
4. Verify changes in database: `SELECT * FROM transcript_segments WHERE episode_id = X ORDER BY segment_index LIMIT 10`
5. Verify changes appear in search UI
6. Test undo/redo
7. Test pagination across 150 pages

## Future Enhancements
- Virtual scrolling for better performance
- Episode locking to prevent concurrent edits
- Edit history tracking in database
- Merge/split words functionality
- YouTube player integration for playback during editing
- Mobile-optimized UI
- Bulk find/replace for speakers
- Export edited transcript to SRT/VTT format
