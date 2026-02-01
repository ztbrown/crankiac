/**
 * TranscriptEditor - Main class for editing episode transcripts
 */
class TranscriptEditor {
    constructor() {
        // Episode and segment data
        this.currentEpisode = null;
        this.segments = [];
        this.selectedSegments = new Set();

        // Pagination state
        this.currentPage = 1;
        this.pageSize = 100;
        this.totalSegments = 0;

        // UI elements
        this.episodeSelect = document.getElementById('episode-select');
        this.loadingIndicator = document.getElementById('loading-indicator');
        this.errorMessage = document.getElementById('error-message');
        this.segmentTableBody = document.getElementById('segment-table-body');
        this.pageInfo = document.getElementById('page-info');
        this.prevPageBtn = document.getElementById('prev-page-btn');
        this.nextPageBtn = document.getElementById('next-page-btn');
        this.pageSizeSelect = document.getElementById('page-size');
        this.speakerFilter = document.getElementById('speaker-filter');
        this.segmentCount = document.getElementById('segment-count');

        // Initialize event listeners
        this.initializeEventListeners();

        // Load episodes on initialization
        this.loadEpisodes();
    }

    /**
     * Initialize event listeners for UI elements
     */
    initializeEventListeners() {
        // Episode selection
        if (this.episodeSelect) {
            this.episodeSelect.addEventListener('change', (e) => {
                this.onEpisodeSelected(e.target.value);
            });
        }

        // Pagination controls
        if (this.prevPageBtn) {
            this.prevPageBtn.addEventListener('click', () => this.previousPage());
        }

        if (this.nextPageBtn) {
            this.nextPageBtn.addEventListener('click', () => this.nextPage());
        }

        if (this.pageSizeSelect) {
            this.pageSizeSelect.addEventListener('change', (e) => {
                this.pageSize = parseInt(e.target.value, 10);
                this.currentPage = 1;
                this.loadSegments();
            });
        }

        // Speaker filter
        if (this.speakerFilter) {
            this.speakerFilter.addEventListener('change', () => {
                this.currentPage = 1;
                this.loadSegments();
            });
        }
    }

    /**
     * Handle episode selection
     * @param {string} episodeId - Selected episode ID
     */
    onEpisodeSelected(episodeId) {
        if (!episodeId) {
            this.currentEpisode = null;
            this.clearSegments();
            return;
        }

        this.currentEpisode = parseInt(episodeId, 10);
        this.currentPage = 1;
        this.loadSegments();
    }

    /**
     * Clear segment display
     */
    clearSegments() {
        if (this.segmentTableBody) {
            this.segmentTableBody.innerHTML = `
                <tr class="empty-state">
                    <td colspan="5">Select an episode to begin editing</td>
                </tr>
            `;
        }
    }

    /**
     * Navigate to previous page
     */
    previousPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.loadSegments();
        }
    }

    /**
     * Navigate to next page
     */
    nextPage() {
        const totalPages = Math.ceil(this.totalSegments / this.pageSize);
        if (this.currentPage < totalPages) {
            this.currentPage++;
            this.loadSegments();
        }
    }

    /**
     * Update pagination UI
     */
    updatePaginationUI() {
        const totalPages = Math.ceil(this.totalSegments / this.pageSize);

        if (this.pageInfo) {
            this.pageInfo.textContent = `Page ${this.currentPage} of ${totalPages || 1}`;
        }

        if (this.prevPageBtn) {
            this.prevPageBtn.disabled = this.currentPage <= 1;
        }

        if (this.nextPageBtn) {
            this.nextPageBtn.disabled = this.currentPage >= totalPages;
        }

        if (this.segmentCount) {
            this.segmentCount.textContent = `${this.totalSegments} segments`;
        }
    }

    /**
     * Show loading indicator
     */
    showLoading() {
        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'inline';
        }
    }

    /**
     * Hide loading indicator
     */
    hideLoading() {
        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'none';
        }
    }

    /**
     * Show error message
     * @param {string} message - Error message to display
     */
    showError(message) {
        if (this.errorMessage) {
            this.errorMessage.textContent = message;
            this.errorMessage.style.display = 'inline';
        }
    }

    /**
     * Hide error message
     */
    hideError() {
        if (this.errorMessage) {
            this.errorMessage.style.display = 'none';
            this.errorMessage.textContent = '';
        }
    }

    /**
     * Load episodes from API and populate dropdown
     */
    async loadEpisodes() {
        this.showLoading();
        this.hideError();

        try {
            const response = await fetch('/api/transcripts/episodes?limit=200');

            if (!response.ok) {
                throw new Error(`Failed to load episodes: ${response.statusText}`);
            }

            const data = await response.json();

            // Populate dropdown with episodes
            if (this.episodeSelect) {
                // Clear existing options except the first one
                this.episodeSelect.innerHTML = '<option value="">Select an episode...</option>';

                // Episodes are already sorted by published_at DESC from the API
                data.episodes.forEach(episode => {
                    const option = document.createElement('option');
                    option.value = episode.id;
                    option.textContent = episode.title;
                    this.episodeSelect.appendChild(option);
                });
            }

            this.hideLoading();
        } catch (error) {
            console.error('Error loading episodes:', error);
            this.showError('Failed to load episodes. Please try refreshing the page.');
            this.hideLoading();
        }
    }

    /**
     * Load segments for current episode
     */
    async loadSegments() {
        if (!this.currentEpisode) {
            this.clearSegments();
            return;
        }

        this.showLoading();
        this.hideError();

        try {
            const offset = (this.currentPage - 1) * this.pageSize;
            const speaker = this.speakerFilter?.value || '';
            let url = `/api/transcripts/episode/${this.currentEpisode}/segments?limit=${this.pageSize}&offset=${offset}`;

            if (speaker) {
                url += `&speaker=${encodeURIComponent(speaker)}`;
            }

            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`Failed to load segments: ${response.statusText}`);
            }

            const data = await response.json();

            this.segments = data.segments;
            this.totalSegments = data.total;

            // Update speaker filter options
            this.updateSpeakerFilter(data.speakers);

            // Render segments in table
            this.renderSegments();

            // Update pagination UI
            this.updatePaginationUI();

            this.hideLoading();
        } catch (error) {
            console.error('Error loading segments:', error);
            this.showError('Failed to load segments. Please try again.');
            this.clearSegments();
            this.hideLoading();
        }
    }

    /**
     * Update speaker filter dropdown
     * @param {Array<string>} speakers - List of speaker names
     */
    updateSpeakerFilter(speakers) {
        if (!this.speakerFilter) return;

        const currentValue = this.speakerFilter.value;
        this.speakerFilter.innerHTML = '<option value="">All speakers</option>';

        speakers.forEach(speaker => {
            if (speaker) {
                const option = document.createElement('option');
                option.value = speaker;
                option.textContent = speaker;
                this.speakerFilter.appendChild(option);
            }
        });

        // Restore previous selection if still valid
        if (currentValue && speakers.includes(currentValue)) {
            this.speakerFilter.value = currentValue;
        }
    }

    /**
     * Render segments in the table
     */
    renderSegments() {
        if (!this.segmentTableBody) return;

        if (this.segments.length === 0) {
            this.segmentTableBody.innerHTML = `
                <tr class="empty-state">
                    <td colspan="5">No segments found</td>
                </tr>
            `;
            return;
        }

        this.segmentTableBody.innerHTML = '';

        this.segments.forEach(segment => {
            const row = document.createElement('tr');

            // Format time
            const startTime = this.formatTime(segment.start_time);

            row.innerHTML = `
                <td>
                    <input type="checkbox" data-segment-id="${segment.id}">
                </td>
                <td>${startTime}</td>
                <td>${segment.speaker || '—'}</td>
                <td>${this.escapeHtml(segment.word)}</td>
                <td>
                    <button class="edit-btn" data-segment-id="${segment.id}">Edit</button>
                </td>
            `;

            this.segmentTableBody.appendChild(row);
        });
    }

    /**
     * Format time in seconds to MM:SS format
     * @param {number} seconds - Time in seconds
     * @returns {string} Formatted time string
     */
    formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
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
}

// Initialize the editor when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.editor = new TranscriptEditor();
    console.log('TranscriptEditor initialized');
});
