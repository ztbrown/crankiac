# Transcript Editor: TDD Breakdown

## Overview
Breaking down the transcript editor implementation into atomic, test-driven development beads organized into logical convoys.

## Convoy 1: Storage Layer (Backend Foundation)

### Bead 1.1: Update Word Text Method
**Feature:** Add `update_word_text()` method to TranscriptStorage
**TDD Approach:**
1. Write test: `test_update_word_text_success()` - verify word updates correctly
2. Write test: `test_update_word_text_nonexistent()` - verify returns False for invalid ID
3. Write test: `test_update_word_text_validation()` - verify empty word rejected
4. Implement method in `app/transcription/storage.py`
5. Verify all tests pass

**Files:**
- `tests/db/test_storage_editor.py` (create)
- `app/transcription/storage.py` (modify)

**Acceptance Criteria:**
- Method updates word text for valid segment_id
- Returns True on success, False on failure
- Validates non-empty word, max 200 chars
- Uses single transaction

---

### Bead 1.2: Bulk Speaker Update Method
**Feature:** Add `update_speakers_by_ids()` method to TranscriptStorage
**TDD Approach:**
1. Write test: `test_update_speakers_single()` - update one segment
2. Write test: `test_update_speakers_bulk()` - update 10 segments in batch
3. Write test: `test_update_speakers_empty_list()` - verify returns 0 for empty list
4. Write test: `test_update_speakers_transaction()` - verify transaction rollback on error
5. Implement method in `app/transcription/storage.py`
6. Verify all tests pass

**Files:**
- `tests/db/test_storage_editor.py` (modify)
- `app/transcription/storage.py` (modify)

**Acceptance Criteria:**
- Method updates speaker for all provided IDs
- Returns count of updated rows
- Uses `WHERE id = ANY(%s)` for batch update
- Single transaction for all updates

---

### Bead 1.3: Paginated Segments Retrieval
**Feature:** Add `get_segments_paginated()` method to TranscriptStorage
**TDD Approach:**
1. Write test: `test_get_segments_first_page()` - verify first 100 segments returned
2. Write test: `test_get_segments_second_page()` - verify offset works correctly
3. Write test: `test_get_segments_speaker_filter()` - verify speaker filtering
4. Write test: `test_get_segments_total_count()` - verify total count accurate
5. Implement method in `app/transcription/storage.py`
6. Verify all tests pass

**Files:**
- `tests/db/test_storage_editor.py` (modify)
- `app/transcription/storage.py` (modify)

**Acceptance Criteria:**
- Returns tuple: (segments, total_count)
- Segments ordered by segment_index
- Pagination works correctly (limit/offset)
- Optional speaker filter works
- Read-only query (commit=False)

---

## Convoy 2: API Layer (Backend Endpoints)

### Bead 2.1: Get Episode Segments Endpoint
**Feature:** Add GET `/api/transcripts/episode/<id>/segments` endpoint
**TDD Approach:**
1. Write test: `test_get_segments_endpoint()` - verify 200 response with segments
2. Write test: `test_get_segments_pagination()` - verify limit/offset query params
3. Write test: `test_get_segments_speaker_filter()` - verify speaker query param
4. Write test: `test_get_segments_invalid_episode()` - verify 404 for invalid ID
5. Implement endpoint in `app/api/transcript_routes.py`
6. Verify all tests pass

**Files:**
- `tests/api/test_transcript_editor.py` (create)
- `app/api/transcript_routes.py` (modify)

**Acceptance Criteria:**
- Returns JSON with segments, total, episode_title, speakers
- Supports limit (default 100), offset (default 0)
- Supports speaker filter (optional)
- Returns 404 if episode doesn't exist
- Uses `get_segments_paginated()` from storage

---

### Bead 2.2: Update Speaker Endpoint
**Feature:** Add PATCH `/api/transcripts/segments/speaker` endpoint
**TDD Approach:**
1. Write test: `test_update_speaker_single()` - update one segment
2. Write test: `test_update_speaker_bulk()` - update multiple segments
3. Write test: `test_update_speaker_validation()` - verify segment_ids and speaker required
4. Write test: `test_update_speaker_empty_list()` - verify handles empty segment_ids
5. Implement endpoint in `app/api/transcript_routes.py`
6. Verify all tests pass

**Files:**
- `tests/api/test_transcript_editor.py` (modify)
- `app/api/transcript_routes.py` (modify)

**Acceptance Criteria:**
- Accepts JSON: `{"segment_ids": [...], "speaker": "name"}`
- Returns count of updated segments
- Returns 400 if missing required fields
- Uses `update_speakers_by_ids()` from storage

---

### Bead 2.3: Update Word Endpoint
**Feature:** Add PATCH `/api/transcripts/segments/<id>/word` endpoint
**TDD Approach:**
1. Write test: `test_update_word_success()` - verify word updates
2. Write test: `test_update_word_validation()` - verify empty word rejected
3. Write test: `test_update_word_not_found()` - verify 404 for invalid segment_id
4. Write test: `test_update_word_missing_body()` - verify 400 if word missing
5. Implement endpoint in `app/api/transcript_routes.py`
6. Verify all tests pass

**Files:**
- `tests/api/test_transcript_editor.py` (modify)
- `app/api/transcript_routes.py` (modify)

**Acceptance Criteria:**
- Accepts JSON: `{"word": "corrected"}`
- Returns updated segment info
- Returns 404 if segment not found
- Returns 400 if validation fails
- Uses `update_word_text()` from storage

---

### Bead 2.4: Get Episode Speakers Endpoint
**Feature:** Add GET `/api/transcripts/episode/<id>/speakers` endpoint
**TDD Approach:**
1. Write test: `test_get_speakers_list()` - verify returns known and episode speakers
2. Write test: `test_get_speakers_invalid_episode()` - verify handles invalid episode
3. Implement endpoint in `app/api/transcript_routes.py`
4. Verify all tests pass

**Files:**
- `tests/api/test_transcript_editor.py` (modify)
- `app/api/transcript_routes.py` (modify)

**Acceptance Criteria:**
- Returns KNOWN_SPEAKERS constant
- Returns distinct speakers from episode's segments
- Returns 404 if episode doesn't exist
- JSON format: `{"known_speakers": [...], "episode_speakers": [...]}`

---

## Convoy 3: Frontend Foundation

### Bead 3.1: Editor Route and HTML
**Feature:** Add /editor route and create editor.html
**TDD Approach:**
1. Write test: `test_editor_route_exists()` - verify route returns 200
2. Write test: `test_editor_html_loads()` - verify HTML contains expected elements
3. Add route to `app/api/app.py`
4. Create `app/ui/static/editor.html` with base structure
5. Verify tests pass

**Files:**
- `tests/api/test_routes.py` (modify or create)
- `app/api/app.py` (modify)
- `app/ui/static/editor.html` (create)

**Acceptance Criteria:**
- Route `/editor` returns editor.html
- HTML includes: episode selector, toolbar, segment table, pagination
- HTML is valid and renders without errors

---

### Bead 3.2: TranscriptEditor Class Skeleton
**Feature:** Create TranscriptEditor class with constructor
**TDD Approach:**
1. Create `app/ui/static/editor.js`
2. Write JS test (or manual verification): Editor class instantiates
3. Implement constructor with instance variables
4. Verify initialization works

**Files:**
- `app/ui/static/editor.js` (create)
- `app/ui/static/editor.css` (create)

**Acceptance Criteria:**
- TranscriptEditor class defined
- Constructor initializes: currentEpisode, segments, selectedSegments, currentPage, pageSize
- No errors on page load

---

## Convoy 4: Core Editor Features

### Bead 4.1: Episode Loading
**Feature:** Load and display episode list
**TDD Approach:**
1. Implement `loadEpisodes()` method - fetch from `/api/transcripts/episodes`
2. Implement episode dropdown population
3. Manual test: Verify dropdown populates with episodes
4. Add error handling test: Verify graceful failure on API error

**Files:**
- `app/ui/static/editor.js` (modify)
- `app/ui/static/editor.html` (modify)

**Acceptance Criteria:**
- Dropdown populates with episode titles
- Episodes sorted by date (newest first)
- Loading indicator shown during fetch
- Error message shown on failure

---

### Bead 4.2: Segment Rendering
**Feature:** Load and render transcript segments
**TDD Approach:**
1. Implement `loadTranscript(episodeId)` method - fetch from `/api/transcripts/episode/<id>/segments`
2. Implement `renderSegments(segments)` method - create table rows
3. Manual test: Verify segments display in table
4. Test pagination: Verify only 100 segments load at a time

**Files:**
- `app/ui/static/editor.js` (modify)
- `app/ui/static/editor.html` (modify)
- `app/ui/static/editor.css` (modify)

**Acceptance Criteria:**
- Table rows created for each segment
- Columns: checkbox, timestamp, speaker, word
- Timestamps formatted (MM:SS)
- Loading indicator during fetch
- Empty state message if no segments

---

### Bead 4.3: Word Editing
**Feature:** Edit individual words with auto-save
**TDD Approach:**
1. Implement word input fields (inline editing)
2. Implement debounced save on blur/Enter
3. Implement `updateWord(segmentId, word)` method
4. Manual test: Edit word, verify saves after 500ms
5. Test validation: Verify empty word rejected
6. Test visual feedback: Verify yellow border → green checkmark

**Files:**
- `app/ui/static/editor.js` (modify)
- `app/ui/static/editor.css` (modify)

**Acceptance Criteria:**
- Input fields editable
- Changes debounced (500ms)
- API called on blur or Enter key
- Visual feedback: unsaved (yellow), saved (green), error (red)
- Reverts on error

---

### Bead 4.4: Individual Speaker Editing
**Feature:** Change speaker for individual words
**TDD Approach:**
1. Implement speaker dropdown per row
2. Implement speaker change handler
3. Implement `updateSpeaker([segmentId], speaker)` method
4. Manual test: Change speaker, verify updates immediately
5. Test visual feedback: Verify loading state during save

**Files:**
- `app/ui/static/editor.js` (modify)
- `app/ui/static/editor.css` (modify)

**Acceptance Criteria:**
- Dropdown shows KNOWN_SPEAKERS + episode speakers
- Change triggers immediate save
- Visual feedback during save
- Success/error toast notification
- Row updates with new speaker

---

### Bead 4.5: Range Selection
**Feature:** Select multiple words with Shift+click
**TDD Approach:**
1. Implement checkbox selection tracking
2. Implement Shift+click range selection logic
3. Implement visual highlighting for selected rows
4. Manual test: Click checkbox, Shift+click another, verify range selected
5. Test edge cases: Shift+click without first selection

**Files:**
- `app/ui/static/editor.js` (modify)
- `app/ui/static/editor.css` (modify)

**Acceptance Criteria:**
- Single click selects/deselects individual row
- Shift+click selects range between first and last
- Selected rows highlighted visually
- Selection count displayed
- "Select All" checkbox works

---

### Bead 4.6: Bulk Speaker Update
**Feature:** Change speaker for multiple selected words
**TDD Approach:**
1. Implement toolbar speaker dropdown
2. Implement "Apply" button handler
3. Implement bulk `updateSpeaker(segmentIds, speaker)` method
4. Manual test: Select range, choose speaker, click Apply
5. Test validation: Verify requires selection and speaker choice
6. Test feedback: Verify toast shows count updated

**Files:**
- `app/ui/static/editor.js` (modify)
- `app/ui/static/editor.html` (modify)
- `app/ui/static/editor.css` (modify)

**Acceptance Criteria:**
- Toolbar dropdown populated with speakers
- Apply button disabled if no selection
- Bulk update API called with all selected IDs
- Toast notification: "Updated 10 words to speaker 'Matt'"
- Selected rows update immediately
- Selection cleared after update

---

## Convoy 5: Navigation and UX

### Bead 5.1: Pagination Controls
**Feature:** Navigate between pages of segments
**TDD Approach:**
1. Implement `handlePagination(direction)` method
2. Implement next/previous button handlers
3. Implement page indicator display
4. Manual test: Navigate between pages
5. Test edge cases: First page (prev disabled), last page (next disabled)

**Files:**
- `app/ui/static/editor.js` (modify)
- `app/ui/static/editor.html` (modify)
- `app/ui/static/editor.css` (modify)

**Acceptance Criteria:**
- Next/Previous buttons work
- Page indicator: "Page 1 of 150"
- Buttons disabled at boundaries
- Selection state preserved across pages
- Loading indicator during page load

---

### Bead 5.2: Undo/Redo Functionality
**Feature:** Client-side undo/redo for recent changes
**TDD Approach:**
1. Implement undo/redo stacks
2. Implement `undo()` method - revert last change via API
3. Implement `redo()` method - reapply change via API
4. Manual test: Make change, undo, redo
5. Test stack limits: Verify max 20 actions in history

**Files:**
- `app/ui/static/editor.js` (modify)
- `app/ui/static/editor.html` (modify)

**Acceptance Criteria:**
- Undo button reverts last change
- Redo button reapplies undone change
- Buttons disabled when stacks empty
- Stack limited to 20 actions
- Toast notification for undo/redo actions

---

### Bead 5.3: Visual Feedback and Polish
**Feature:** Loading states, toasts, error messages
**TDD Approach:**
1. Implement loading spinners for API calls
2. Implement toast notifications (success/error)
3. Implement error message displays
4. Manual test: Verify all feedback mechanisms work
5. Test accessibility: Verify screen reader announcements

**Files:**
- `app/ui/static/editor.js` (modify)
- `app/ui/static/editor.css` (modify)

**Acceptance Criteria:**
- Loading spinner shows during API calls
- Toast notifications for: save success, save error, bulk update
- Toast auto-dismisses after 4 seconds
- Error messages clear and actionable
- Color-coded speakers (consistent colors)
- Responsive design (mobile-friendly table)

---

## Convoy 6: Integration and Testing

### Bead 6.1: End-to-End Integration Test
**Feature:** Complete workflow test
**TDD Approach:**
1. Write integration test script
2. Test full workflow: select episode → load segments → edit word → change speaker → verify DB
3. Verify changes persist after page reload
4. Verify changes appear in search UI

**Files:**
- `tests/integration/test_editor_workflow.py` (create)

**Acceptance Criteria:**
- Full workflow completes without errors
- Database updates verified
- Changes persist across sessions
- Search UI reflects edited data

---

### Bead 6.2: Performance Testing
**Feature:** Test with large episode (15,000 segments)
**TDD Approach:**
1. Create test episode with 15,000 segments
2. Load editor and measure performance
3. Verify pagination prevents browser freeze
4. Verify bulk update of 100+ segments completes quickly

**Files:**
- `tests/performance/test_editor_performance.py` (create)

**Acceptance Criteria:**
- Page load < 2 seconds
- Segment rendering < 1 second
- Bulk update of 100 segments < 1 second
- No browser freeze or lag
- Memory usage reasonable

---

## Summary

**Total Beads:** 19
**Total Convoys:** 6

**Estimated Effort:**
- Convoy 1 (Storage): 3 beads × 1-2 hours = 3-6 hours
- Convoy 2 (API): 4 beads × 1-2 hours = 4-8 hours
- Convoy 3 (Foundation): 2 beads × 1 hour = 2 hours
- Convoy 4 (Features): 6 beads × 2-3 hours = 12-18 hours
- Convoy 5 (UX): 3 beads × 1-2 hours = 3-6 hours
- Convoy 6 (Testing): 2 beads × 2 hours = 4 hours

**Total Estimate:** 28-44 hours

**Critical Path:**
Convoy 1 → Convoy 2 → Convoy 3 → Convoy 4 → Convoy 5 → Convoy 6

**Parallelizable Work:**
- Beads within same convoy can be worked on independently (after dependencies met)
- Frontend work (Convoy 4-5) can start after Convoy 2 completes

**TDD Emphasis:**
Every bead follows Test-Driven Development:
1. Write tests first (red)
2. Implement to pass tests (green)
3. Refactor if needed (refactor)
4. Verify all tests pass before moving to next bead
