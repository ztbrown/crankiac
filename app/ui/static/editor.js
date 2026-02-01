/**
 * TranscriptEditor - Interactive transcript editing interface
 *
 * Provides word-level editing of transcripts with features:
 * - Speaker label editing (individual and bulk)
 * - Word text correction
 * - Range selection with Shift+click
 * - Pagination for large transcripts
 * - Undo/redo functionality
 * - Auto-save with debouncing
 */
class TranscriptEditor {
    constructor() {
        // DOM element references
        this.episodeSelector = null;
        this.speakerDropdown = null;
        this.applyButton = null;
        this.segmentTable = null;
        this.segmentTableBody = null;
        this.selectAllCheckbox = null;
        this.prevPageButton = null;
        this.nextPageButton = null;
        this.pageIndicator = null;
        this.undoButton = null;
        this.redoButton = null;
        this.speakerFilter = null;

        // State management
        this.currentEpisodeId = null;
        this.currentPage = 0;
        this.pageSize = 100;
        this.totalSegments = 0;
        this.segments = [];
        this.selectedSegmentIds = new Set();
        this.availableSpeakers = [];
        this.lastSelectedIndex = null; // For range selection

        // Undo/redo stacks
        this.undoStack = [];
        this.redoStack = [];
        this.maxUndoSize = 50;

        // Debounce timers
        this.wordEditTimers = new Map(); // segmentId -> timerId
        this.debounceDelay = 500;

        // Loading state
        this.isLoading = false;
    }

    /**
     * Initialize the editor - bind DOM elements and attach event listeners
     */
    init() {
        this.bindDomElements();
        this.attachEventListeners();
        this.loadEpisodes();
    }

    /**
     * Bind DOM element references
     */
    bindDomElements() {
        // TODO: Query and assign all necessary DOM elements
    }

    /**
     * Attach event listeners to interactive elements
     */
    attachEventListeners() {
        // TODO: Add listeners for episode selection, pagination, buttons, etc.
    }

    /**
     * Load available episodes and populate the episode selector dropdown
     */
    async loadEpisodes() {
        // TODO: Fetch episodes from /api/transcripts/episodes
        // TODO: Populate episode selector dropdown
        // TODO: Handle errors with toast notification
    }

    /**
     * Load transcript segments for a specific episode
     * @param {number} episodeId - The episode ID to load
     */
    async loadTranscript(episodeId) {
        // TODO: Validate episodeId
        // TODO: Show loading state
        // TODO: Fetch segments from /api/transcripts/episode/<id>/segments
        // TODO: Fetch available speakers from /api/transcripts/episode/<id>/speakers
        // TODO: Update state (currentEpisodeId, segments, totalSegments, availableSpeakers)
        // TODO: Reset pagination to page 0
        // TODO: Clear selections
        // TODO: Render segments
        // TODO: Update pagination controls
        // TODO: Handle errors
    }

    /**
     * Render segments in the table
     * @param {Array} segments - Array of segment objects to render
     */
    renderSegments(segments) {
        // TODO: Clear existing table rows
        // TODO: Create table row for each segment with:
        //       - Checkbox for selection
        //       - Timestamp display
        //       - Speaker dropdown
        //       - Word input field (editable)
        //       - Action buttons if needed
        // TODO: Attach event listeners to checkboxes, inputs, dropdowns
        // TODO: Apply visual indicators (selected, edited, etc.)
    }

    /**
     * Handle range selection between two segment indices
     * Supports Shift+click for bulk selection
     * @param {number} startIndex - Starting segment index
     * @param {number} endIndex - Ending segment index
     */
    handleRangeSelection(startIndex, endIndex) {
        // TODO: Determine range (min to max of start/end)
        // TODO: Select all segments in range
        // TODO: Update selectedSegmentIds Set
        // TODO: Update checkbox states visually
        // TODO: Update "Select All" checkbox state
    }

    /**
     * Handle individual segment checkbox click
     * @param {number} segmentIndex - Index of clicked segment
     * @param {boolean} shiftKey - Whether Shift key was pressed
     */
    handleSegmentSelection(segmentIndex, shiftKey) {
        // TODO: If shift key and lastSelectedIndex exists, do range selection
        // TODO: Otherwise, toggle single segment selection
        // TODO: Update lastSelectedIndex
        // TODO: Update UI state
    }

    /**
     * Update speaker for multiple segments (bulk operation)
     * @param {Array<number>} segmentIds - Array of segment IDs to update
     * @param {string} speaker - New speaker name
     */
    async updateSpeaker(segmentIds, speaker) {
        // TODO: Validate inputs
        // TODO: Show loading state
        // TODO: Save current state to undo stack
        // TODO: Send PATCH request to /api/transcripts/segments/speaker
        // TODO: Update local segment data
        // TODO: Update UI to reflect changes
        // TODO: Show success toast
        // TODO: Handle errors with toast and revert if needed
    }

    /**
     * Update word text for a single segment
     * @param {number} segmentId - Segment ID to update
     * @param {string} word - New word text
     */
    async updateWord(segmentId, word) {
        // TODO: Validate inputs (non-empty, max length)
        // TODO: Show loading indicator on the word input
        // TODO: Save current state to undo stack
        // TODO: Send PATCH request to /api/transcripts/segments/<id>/word
        // TODO: Update local segment data
        // TODO: Show success indicator (green checkmark)
        // TODO: Handle errors (show red X, revert text)
    }

    /**
     * Debounced word edit handler - delays API call until user stops typing
     * @param {number} segmentId - Segment ID being edited
     * @param {string} newWord - New word text
     */
    handleWordEdit(segmentId, newWord) {
        // TODO: Clear existing timer for this segment
        // TODO: Set visual indicator (yellow border for unsaved)
        // TODO: Create new timer that calls updateWord after debounceDelay
        // TODO: Store timer in wordEditTimers Map
    }

    /**
     * Handle pagination - load next or previous page
     * @param {string} direction - 'next' or 'prev'
     */
    async handlePagination(direction) {
        // TODO: Calculate new page number based on direction
        // TODO: Validate page bounds (0 to maxPages)
        // TODO: Update currentPage
        // TODO: Load segments for new page
        // TODO: Preserve selection state if needed
        // TODO: Update page indicator
        // TODO: Enable/disable prev/next buttons appropriately
    }

    /**
     * Load segments for the current page
     */
    async loadCurrentPage() {
        // TODO: Calculate offset from currentPage and pageSize
        // TODO: Fetch segments with pagination params
        // TODO: Apply speaker filter if active
        // TODO: Render fetched segments
        // TODO: Update pagination controls
    }

    /**
     * Handle speaker filter change
     * @param {string} speaker - Speaker to filter by (or 'all')
     */
    async handleSpeakerFilter(speaker) {
        // TODO: Update filter state
        // TODO: Reset to page 0
        // TODO: Load segments with filter applied
        // TODO: Update UI
    }

    /**
     * Handle "Select All" checkbox toggle
     * @param {boolean} checked - New checked state
     */
    handleSelectAll(checked) {
        // TODO: If checked, select all visible segments
        // TODO: If unchecked, clear all selections
        // TODO: Update selectedSegmentIds Set
        // TODO: Update individual checkboxes
    }

    /**
     * Handle bulk speaker update from toolbar
     */
    async handleBulkSpeakerUpdate() {
        // TODO: Get selected speaker from dropdown
        // TODO: Get array of selected segment IDs
        // TODO: Validate selection is not empty
        // TODO: Call updateSpeaker with selected IDs
        // TODO: Clear selection after successful update
    }

    /**
     * Undo the last change
     */
    undo() {
        // TODO: Pop from undo stack
        // TODO: Save current state to redo stack
        // TODO: Apply previous state
        // TODO: Update UI to reflect reverted state
        // TODO: Send API request to restore previous values
        // TODO: Disable undo button if stack is empty
    }

    /**
     * Redo the last undone change
     */
    redo() {
        // TODO: Pop from redo stack
        // TODO: Save current state to undo stack
        // TODO: Apply redone state
        // TODO: Update UI
        // TODO: Send API request to restore redone values
        // TODO: Disable redo button if stack is empty
    }

    /**
     * Save current state to undo stack
     * @param {Object} state - State object to save
     */
    saveToUndoStack(state) {
        // TODO: Push state to undo stack
        // TODO: Limit stack size to maxUndoSize
        // TODO: Clear redo stack (can't redo after new change)
        // TODO: Update undo/redo button states
    }

    /**
     * Create state snapshot for undo/redo
     * @param {string} action - Type of action (e.g., 'update_speaker', 'update_word')
     * @param {Object} data - Action-specific data
     * @returns {Object} State snapshot
     */
    createStateSnapshot(action, data) {
        // TODO: Return object with:
        //       - action type
        //       - timestamp
        //       - affected segment IDs
        //       - previous values
        //       - new values
    }

    /**
     * Show loading spinner/overlay
     */
    showLoading() {
        // TODO: Set isLoading flag
        // TODO: Show visual loading indicator
        // TODO: Disable interactive elements
    }

    /**
     * Hide loading spinner/overlay
     */
    hideLoading() {
        // TODO: Clear isLoading flag
        // TODO: Hide visual loading indicator
        // TODO: Re-enable interactive elements
    }

    /**
     * Show toast notification
     * @param {string} message - Message to display
     * @param {string} type - Toast type: 'success', 'error', 'info'
     * @param {number} duration - Display duration in ms
     */
    showToast(message, type = 'info', duration = 4000) {
        // TODO: Create toast element
        // TODO: Style based on type
        // TODO: Add to DOM with animation
        // TODO: Auto-remove after duration
    }

    /**
     * Update pagination controls (buttons, page indicator)
     */
    updatePaginationControls() {
        // TODO: Calculate total pages
        // TODO: Update page indicator text (e.g., "Page 1 of 150")
        // TODO: Enable/disable prev button (disabled on page 0)
        // TODO: Enable/disable next button (disabled on last page)
    }

    /**
     * Update undo/redo button states based on stack availability
     */
    updateUndoRedoButtons() {
        // TODO: Enable undo button if undo stack has items
        // TODO: Enable redo button if redo stack has items
        // TODO: Disable if respective stacks are empty
    }

    /**
     * Populate speaker dropdown with available speakers
     */
    populateSpeakerDropdowns() {
        // TODO: Get list of available speakers (KNOWN_SPEAKERS + episode speakers)
        // TODO: Clear existing options
        // TODO: Add option for each speaker
        // TODO: Add option for custom speaker input
    }

    /**
     * Format timestamp for display
     * @param {number} seconds - Time in seconds
     * @returns {string} Formatted timestamp (MM:SS)
     */
    formatTimestamp(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    /**
     * Escape HTML to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Validate word input
     * @param {string} word - Word to validate
     * @returns {Object} Validation result {valid: boolean, error: string}
     */
    validateWord(word) {
        // TODO: Check non-empty
        // TODO: Check max length (200 chars)
        // TODO: Trim whitespace
        // TODO: Return validation result
    }

    /**
     * Handle API errors consistently
     * @param {Error} error - Error object
     * @param {string} action - Action that failed (for error message)
     */
    handleError(error, action) {
        // TODO: Log error to console
        // TODO: Show user-friendly toast notification
        // TODO: Hide loading states
        // TODO: Implement retry logic for network errors if appropriate
    }

    /**
     * Clear all selections
     */
    clearSelections() {
        // TODO: Clear selectedSegmentIds Set
        // TODO: Uncheck all checkboxes
        // TODO: Uncheck "Select All" checkbox
        // TODO: Reset lastSelectedIndex
    }

    /**
     * Get segment by ID from current segments array
     * @param {number} segmentId - Segment ID to find
     * @returns {Object|null} Segment object or null if not found
     */
    getSegmentById(segmentId) {
        // TODO: Find and return segment from this.segments
    }

    /**
     * Update local segment data after successful API call
     * @param {number} segmentId - Segment ID to update
     * @param {Object} updates - Object with fields to update
     */
    updateLocalSegment(segmentId, updates) {
        // TODO: Find segment in this.segments
        // TODO: Apply updates to segment object
        // TODO: Update DOM if segment is currently visible
    }
}

// Initialize editor when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const editor = new TranscriptEditor();
    editor.init();
});
