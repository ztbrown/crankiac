/**
 * Transcript Editor
 * Handles loading, rendering, and editing transcript segments
 */

class TranscriptEditor {
    constructor() {
        this.currentEpisodeId = null;
        this.segments = [];
        this.availableSpeakers = [];
        this.selectedSegments = new Set();
        this.currentPage = 1;
        this.pageSize = 100;
        this.totalPages = 1;

        this.initializeEventListeners();
        this.loadEpisodes();
    }

    initializeEventListeners() {
        // Episode selection
        document.getElementById('episode-select').addEventListener('change', (e) => {
            if (e.target.value) {
                this.loadTranscript(parseInt(e.target.value));
            }
        });

        // Select all checkbox
        document.getElementById('select-all').addEventListener('change', (e) => {
            this.handleSelectAll(e.target.checked);
        });

        // Apply speaker button
        document.getElementById('apply-speaker-btn').addEventListener('click', () => {
            this.handleBulkSpeakerUpdate();
        });

        // Pagination
        document.getElementById('prev-page').addEventListener('click', () => {
            this.handlePagination('prev');
        });

        document.getElementById('next-page').addEventListener('click', () => {
            this.handlePagination('next');
        });
    }

    async loadEpisodes() {
        try {
            const response = await fetch('/api/transcripts/episodes?limit=200');
            const data = await response.json();

            const select = document.getElementById('episode-select');
            data.episodes.forEach(episode => {
                const option = document.createElement('option');
                option.value = episode.id;
                option.textContent = `${episode.title} (${episode.word_count} words)`;
                select.appendChild(option);
            });
        } catch (error) {
            console.error('Failed to load episodes:', error);
            this.showToast('Failed to load episodes', 'error');
        }
    }

    async loadTranscript(episodeId) {
        this.currentEpisodeId = episodeId;
        this.currentPage = 1;
        this.selectedSegments.clear();

        this.showLoading(true);
        document.getElementById('editor-content').style.display = 'none';

        try {
            // Load speakers and segments in parallel
            const [speakersResponse, segmentsResponse] = await Promise.all([
                fetch(`/api/transcripts/episode/${episodeId}/speakers`),
                this.fetchSegments(episodeId, 0)
            ]);

            const speakersData = await speakersResponse.json();
            this.availableSpeakers = [
                ...speakersData.known_speakers,
                ...speakersData.episode_speakers.filter(s => !speakersData.known_speakers.includes(s))
            ];

            const segmentsData = await segmentsResponse.json();
            this.segments = segmentsData.segments || [];

            // Calculate total pages (assuming we'll implement pagination endpoint)
            this.totalPages = Math.ceil(this.segments.length / this.pageSize);

            this.renderSegments(this.segments);
            this.populateSpeakerDropdowns();
            this.updatePagination();

            this.showLoading(false);
            document.getElementById('editor-content').style.display = 'block';

            if (this.segments.length === 0) {
                document.getElementById('transcript-table').style.display = 'none';
                document.getElementById('empty-state').style.display = 'block';
            } else {
                document.getElementById('transcript-table').style.display = 'table';
                document.getElementById('empty-state').style.display = 'none';
            }
        } catch (error) {
            console.error('Failed to load transcript:', error);
            this.showToast('Failed to load transcript', 'error');
            this.showLoading(false);
        }
    }

    async fetchSegments(episodeId, offset) {
        // For now, fetch all segments from the context endpoint
        // TODO: Use proper pagination endpoint when available
        const response = await fetch(`/api/transcripts/search?q=&episode_number=&limit=500&offset=${offset}`);
        const data = await response.json();

        // Filter by episode ID (temporary until we have proper endpoint)
        // For now, return empty since we need the proper endpoint
        return { segments: [] };
    }

    renderSegments(segments) {
        const tbody = document.getElementById('transcript-body');
        tbody.innerHTML = '';

        // Paginate segments
        const startIdx = (this.currentPage - 1) * this.pageSize;
        const endIdx = startIdx + this.pageSize;
        const pageSegments = segments.slice(startIdx, endIdx);

        pageSegments.forEach((segment, idx) => {
            const row = this.createSegmentRow(segment, startIdx + idx);
            tbody.appendChild(row);
        });

        this.updateSelectionCount();
    }

    createSegmentRow(segment, index) {
        const row = document.createElement('tr');
        row.dataset.segmentId = segment.id;
        row.dataset.index = index;

        // Checkbox column
        const checkboxCell = document.createElement('td');
        checkboxCell.className = 'col-checkbox';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.dataset.segmentId = segment.id;
        checkbox.addEventListener('change', (e) => {
            this.handleSegmentSelection(segment.id, e.target.checked, e.shiftKey);
        });
        checkboxCell.appendChild(checkbox);

        // Time column
        const timeCell = document.createElement('td');
        timeCell.className = 'col-time';
        timeCell.textContent = this.formatTime(segment.start_time);

        // Speaker column
        const speakerCell = document.createElement('td');
        speakerCell.className = 'col-speaker';
        const speakerDropdown = this.createSpeakerDropdown(segment);
        speakerCell.appendChild(speakerDropdown);

        // Word column
        const wordCell = document.createElement('td');
        wordCell.className = 'col-word word-cell';
        wordCell.textContent = segment.word;

        row.appendChild(checkboxCell);
        row.appendChild(timeCell);
        row.appendChild(speakerCell);
        row.appendChild(wordCell);

        return row;
    }

    createSpeakerDropdown(segment) {
        const select = document.createElement('select');
        select.className = 'speaker-dropdown';
        select.dataset.segmentId = segment.id;

        // Add current speaker first if not in known speakers
        const currentSpeaker = segment.speaker || 'Unknown';
        if (!this.availableSpeakers.includes(currentSpeaker)) {
            const option = document.createElement('option');
            option.value = currentSpeaker;
            option.textContent = currentSpeaker;
            option.selected = true;
            select.appendChild(option);
        }

        // Add all available speakers
        this.availableSpeakers.forEach(speaker => {
            const option = document.createElement('option');
            option.value = speaker;
            option.textContent = speaker;
            if (speaker === currentSpeaker) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        // Handle individual speaker change
        select.addEventListener('change', (e) => {
            this.updateSpeaker([segment.id], e.target.value, select);
        });

        return select;
    }

    populateSpeakerDropdowns() {
        const speakerSelect = document.getElementById('speaker-select');
        speakerSelect.innerHTML = '<option value="">Select speaker...</option>';

        this.availableSpeakers.forEach(speaker => {
            const option = document.createElement('option');
            option.value = speaker;
            option.textContent = speaker;
            speakerSelect.appendChild(option);
        });
    }

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    handleSegmentSelection(segmentId, isSelected, isShiftKey) {
        if (isSelected) {
            this.selectedSegments.add(segmentId);
        } else {
            this.selectedSegments.delete(segmentId);
        }

        // Update row styling
        const row = document.querySelector(`tr[data-segment-id="${segmentId}"]`);
        if (row) {
            row.classList.toggle('selected', isSelected);
        }

        this.updateSelectionCount();

        // Enable/disable apply button
        const applyBtn = document.getElementById('apply-speaker-btn');
        applyBtn.disabled = this.selectedSegments.size === 0;
    }

    handleSelectAll(isChecked) {
        const checkboxes = document.querySelectorAll('#transcript-body input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            checkbox.checked = isChecked;
            const segmentId = parseInt(checkbox.dataset.segmentId);
            if (isChecked) {
                this.selectedSegments.add(segmentId);
            } else {
                this.selectedSegments.delete(segmentId);
            }

            const row = checkbox.closest('tr');
            row.classList.toggle('selected', isChecked);
        });

        this.updateSelectionCount();

        const applyBtn = document.getElementById('apply-speaker-btn');
        applyBtn.disabled = this.selectedSegments.size === 0;
    }

    updateSelectionCount() {
        const count = this.selectedSegments.size;
        document.getElementById('selection-count').textContent =
            `${count} segment${count !== 1 ? 's' : ''} selected`;
    }

    async updateSpeaker(segmentIds, speaker, dropdownElement = null) {
        // Show loading state
        if (dropdownElement) {
            dropdownElement.classList.add('loading');
            const row = dropdownElement.closest('tr');
            row.classList.add('saving');
        }

        try {
            const response = await fetch('/api/transcripts/segments/speaker', {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    segment_ids: segmentIds,
                    speaker: speaker
                })
            });

            if (!response.ok) {
                throw new Error('Failed to update speaker');
            }

            const data = await response.json();

            // Update segments in memory
            segmentIds.forEach(id => {
                const segment = this.segments.find(s => s.id === id);
                if (segment) {
                    segment.speaker = speaker;
                }
            });

            this.showToast(`Updated ${data.updated} segment(s)`, 'success');

        } catch (error) {
            console.error('Failed to update speaker:', error);
            this.showToast('Failed to update speaker', 'error');

            // Revert dropdown if single update
            if (dropdownElement && segmentIds.length === 1) {
                const segment = this.segments.find(s => s.id === segmentIds[0]);
                if (segment) {
                    dropdownElement.value = segment.speaker || 'Unknown';
                }
            }
        } finally {
            // Remove loading state
            if (dropdownElement) {
                dropdownElement.classList.remove('loading');
                const row = dropdownElement.closest('tr');
                row.classList.remove('saving');
            }
        }
    }

    handleBulkSpeakerUpdate() {
        const speakerSelect = document.getElementById('speaker-select');
        const speaker = speakerSelect.value;

        if (!speaker) {
            this.showToast('Please select a speaker', 'error');
            return;
        }

        if (this.selectedSegments.size === 0) {
            this.showToast('No segments selected', 'error');
            return;
        }

        const segmentIds = Array.from(this.selectedSegments);
        this.updateSpeaker(segmentIds, speaker);

        // Clear selection after update
        this.selectedSegments.clear();
        document.getElementById('select-all').checked = false;
        document.querySelectorAll('#transcript-body input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });
        document.querySelectorAll('#transcript-body tr').forEach(row => {
            row.classList.remove('selected');
        });
        this.updateSelectionCount();
        document.getElementById('apply-speaker-btn').disabled = true;
        speakerSelect.value = '';
    }

    handlePagination(direction) {
        if (direction === 'prev' && this.currentPage > 1) {
            this.currentPage--;
        } else if (direction === 'next' && this.currentPage < this.totalPages) {
            this.currentPage++;
        }

        this.renderSegments(this.segments);
        this.updatePagination();

        // Scroll to top of table
        document.querySelector('.table-container').scrollIntoView({ behavior: 'smooth' });
    }

    updatePagination() {
        document.getElementById('page-info').textContent =
            `Page ${this.currentPage} of ${this.totalPages}`;
        document.getElementById('prev-page').disabled = this.currentPage === 1;
        document.getElementById('next-page').disabled = this.currentPage === this.totalPages;
    }

    showLoading(isLoading) {
        document.getElementById('loading-indicator').style.display = isLoading ? 'block' : 'none';
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;

        container.appendChild(toast);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease-out reverse';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// Initialize editor when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.editor = new TranscriptEditor();
});
