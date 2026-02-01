class TranscriptEditor {
    constructor() {
        this.currentEpisodeId = null;
        this.currentPage = 1;
        this.pageSize = 100;
        this.totalSegments = 0;
        this.segments = [];
        this.selectedSegments = new Set();
        this.lastSelectedIndex = null;
        this.knownSpeakers = [];
        this.episodeSpeakers = [];
        this.speakerColors = new Map();
        this.debounceTimers = new Map();
        this.currentSpeakerFilter = null;

        this.initializeElements();
        this.attachEventListeners();
        this.loadEpisodes();
    }

    initializeElements() {
        this.episodeSelect = document.getElementById("episode-select");
        this.speakerFilter = document.getElementById("speaker-filter");
        this.episodeTitle = document.getElementById("episode-title");
        this.segmentCount = document.getElementById("segment-count");
        this.segmentsBody = document.getElementById("segments-body");
        this.selectAllCheckbox = document.getElementById("select-all");
        this.selectionCount = document.getElementById("selection-count");
        this.bulkSpeakerSelect = document.getElementById("bulk-speaker-select");
        this.applySpeakerBtn = document.getElementById("apply-speaker-btn");
        this.prevPageBtn = document.getElementById("prev-page-btn");
        this.nextPageBtn = document.getElementById("next-page-btn");
        this.pageInfo = document.getElementById("page-info");
        this.loadingContainer = document.getElementById("loading-container");
        this.errorContainer = document.getElementById("error-container");
        this.errorText = document.getElementById("error-text");
        this.errorDismiss = document.getElementById("error-dismiss");
    }

    attachEventListeners() {
        this.episodeSelect.addEventListener("change", () => this.handleEpisodeChange());
        this.speakerFilter.addEventListener("change", () => this.handleSpeakerFilterChange());
        this.selectAllCheckbox.addEventListener("change", () => this.handleSelectAll());
        this.applySpeakerBtn.addEventListener("change", () => this.updateApplyButtonState());
        this.applySpeakerBtn.addEventListener("click", () => this.handleBulkSpeakerUpdate());
        this.prevPageBtn.addEventListener("click", () => this.handlePreviousPage());
        this.nextPageBtn.addEventListener("click", () => this.handleNextPage());
        this.errorDismiss.addEventListener("click", () => this.hideError());
    }

    showLoading(message = "Loading...") {
        this.loadingContainer.querySelector(".loading-text").textContent = message;
        this.loadingContainer.style.display = "flex";
    }

    hideLoading() {
        this.loadingContainer.style.display = "none";
    }

    showError(message) {
        this.errorText.textContent = message;
        this.errorContainer.style.display = "flex";
    }

    hideError() {
        this.errorContainer.style.display = "none";
    }

    showToast(message, type = "success", duration = 4000) {
        const container = document.getElementById("toast-container");

        // Remove existing toasts
        container.innerHTML = "";

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.innerHTML = message;
        container.appendChild(toast);

        // Trigger animation
        requestAnimationFrame(() => toast.classList.add("show"));

        // Auto-dismiss
        setTimeout(() => {
            toast.classList.remove("show");
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    async loadEpisodes() {
        this.showLoading("Loading episodes...");
        try {
            const response = await fetch("/api/transcripts/episodes?limit=200");
            if (!response.ok) {
                throw new Error("Failed to fetch episodes");
            }

            const data = await response.json();
            this.populateEpisodeDropdown(data.episodes);
        } catch (error) {
            console.error("Error loading episodes:", error);
            this.showError(`Failed to load episodes: ${error.message}`);
        } finally {
            this.hideLoading();
        }
    }

    populateEpisodeDropdown(episodes) {
        // Keep the default option
        this.episodeSelect.innerHTML = '<option value="">-- Select an episode --</option>';

        episodes.forEach(ep => {
            if (ep.word_count > 0) {
                const option = document.createElement("option");
                option.value = ep.id;
                option.textContent = `${ep.title} (${ep.word_count} words)`;
                this.episodeSelect.appendChild(option);
            }
        });
    }

    async handleEpisodeChange() {
        const episodeId = parseInt(this.episodeSelect.value);
        if (!episodeId) {
            this.clearEditor();
            return;
        }

        this.currentEpisodeId = episodeId;
        this.currentPage = 1;
        this.selectedSegments.clear();
        this.currentSpeakerFilter = null;

        await this.loadSpeakers();
        await this.loadSegments();
    }

    async handleSpeakerFilterChange() {
        const speaker = this.speakerFilter.value;
        this.currentSpeakerFilter = speaker || null;
        this.currentPage = 1;
        this.selectedSegments.clear();
        await this.loadSegments();
    }

    async loadSpeakers() {
        try {
            const response = await fetch(`/api/transcripts/episode/${this.currentEpisodeId}/speakers`);
            if (!response.ok) {
                throw new Error("Failed to fetch speakers");
            }

            const data = await response.json();
            this.knownSpeakers = data.known_speakers || [];
            this.episodeSpeakers = data.episode_speakers || [];

            this.populateSpeakerDropdowns();
        } catch (error) {
            console.error("Error loading speakers:", error);
            this.showError(`Failed to load speakers: ${error.message}`);
        }
    }

    populateSpeakerDropdowns() {
        // Combine all speakers and remove duplicates
        const allSpeakers = [
            ...new Set([...this.knownSpeakers, ...this.episodeSpeakers])
        ].sort();

        // Populate speaker filter
        this.speakerFilter.innerHTML = '<option value="">All speakers</option>';
        allSpeakers.forEach(speaker => {
            const option = document.createElement("option");
            option.value = speaker;
            option.textContent = speaker;
            this.speakerFilter.appendChild(option);
        });

        // Populate bulk speaker select
        this.bulkSpeakerSelect.innerHTML = '<option value="">-- Select speaker --</option>';
        allSpeakers.forEach(speaker => {
            const option = document.createElement("option");
            option.value = speaker;
            option.textContent = speaker;
            this.bulkSpeakerSelect.appendChild(option);
        });

        // Assign colors to speakers
        this.assignSpeakerColors(allSpeakers);
    }

    assignSpeakerColors(speakers) {
        const colors = [
            "#0066cc", "#0a7d0a", "#f96854", "#9b59b6",
            "#e67e22", "#16a085", "#c0392b", "#2980b9"
        ];

        speakers.forEach((speaker, index) => {
            this.speakerColors.set(speaker, colors[index % colors.length]);
        });
    }

    async loadSegments() {
        if (!this.currentEpisodeId) return;

        const offset = (this.currentPage - 1) * this.pageSize;
        let url = `/api/transcripts/episode/${this.currentEpisodeId}/segments?limit=${this.pageSize}&offset=${offset}`;

        if (this.currentSpeakerFilter) {
            url += `&speaker=${encodeURIComponent(this.currentSpeakerFilter)}`;
        }

        this.showLoading("Loading transcript segments...");
        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error("Failed to fetch segments");
            }

            const data = await response.json();
            this.segments = data.segments;
            this.totalSegments = data.total;
            this.episodeTitle.textContent = data.episode_title;
            this.segmentCount.textContent = `(${this.totalSegments} segments)`;

            this.renderSegments();
            this.updatePaginationControls();
            this.updateSelectionCount();
        } catch (error) {
            console.error("Error loading segments:", error);
            this.showError(`Failed to load segments: ${error.message}`);
        } finally {
            this.hideLoading();
        }
    }

    renderSegments() {
        this.segmentsBody.innerHTML = "";

        if (this.segments.length === 0) {
            const row = document.createElement("tr");
            row.innerHTML = '<td colspan="5" class="empty-state">No segments found</td>';
            this.segmentsBody.appendChild(row);
            return;
        }

        this.segments.forEach((segment, index) => {
            const row = this.createSegmentRow(segment, index);
            this.segmentsBody.appendChild(row);
        });
    }

    createSegmentRow(segment, index) {
        const row = document.createElement("tr");
        row.dataset.segmentId = segment.id;
        row.dataset.index = index;

        if (this.selectedSegments.has(segment.id)) {
            row.classList.add("selected");
        }

        // Checkbox column
        const checkboxCell = document.createElement("td");
        checkboxCell.className = "col-checkbox";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "segment-checkbox";
        checkbox.checked = this.selectedSegments.has(segment.id);
        checkbox.addEventListener("change", (e) => this.handleSegmentSelect(e, segment.id, index));
        checkboxCell.appendChild(checkbox);

        // Time column
        const timeCell = document.createElement("td");
        timeCell.className = "col-time";
        timeCell.textContent = this.formatTimestamp(segment.start_time);

        // Speaker column
        const speakerCell = document.createElement("td");
        speakerCell.className = "col-speaker";
        const speakerSelect = this.createSpeakerSelect(segment);
        speakerCell.appendChild(speakerSelect);

        // Word column
        const wordCell = document.createElement("td");
        wordCell.className = "col-word";
        const wordInput = document.createElement("input");
        wordInput.type = "text";
        wordInput.className = "word-input";
        wordInput.value = segment.word;
        wordInput.dataset.originalValue = segment.word;
        wordInput.addEventListener("input", (e) => this.handleWordEdit(e, segment.id));
        wordCell.appendChild(wordInput);

        // Actions column
        const actionsCell = document.createElement("td");
        actionsCell.className = "col-actions";
        const statusSpan = document.createElement("span");
        statusSpan.className = "status-indicator";
        statusSpan.dataset.segmentId = segment.id;
        actionsCell.appendChild(statusSpan);

        row.appendChild(checkboxCell);
        row.appendChild(timeCell);
        row.appendChild(speakerCell);
        row.appendChild(wordCell);
        row.appendChild(actionsCell);

        return row;
    }

    createSpeakerSelect(segment) {
        const select = document.createElement("select");
        select.className = "speaker-select";

        const color = this.speakerColors.get(segment.speaker) || "#666";
        select.style.borderLeftColor = color;
        select.style.color = color;

        // Add all available speakers
        const allSpeakers = [...new Set([...this.knownSpeakers, ...this.episodeSpeakers])].sort();

        allSpeakers.forEach(speaker => {
            const option = document.createElement("option");
            option.value = speaker;
            option.textContent = speaker;
            option.selected = speaker === segment.speaker;
            select.appendChild(option);
        });

        select.addEventListener("change", (e) => this.handleSpeakerChange(e, segment.id));

        return select;
    }

    formatTimestamp(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, "0")}`;
    }

    handleSegmentSelect(event, segmentId, index) {
        if (event.shiftKey && this.lastSelectedIndex !== null) {
            // Range selection
            event.preventDefault();
            this.selectRange(this.lastSelectedIndex, index);
        } else {
            // Single selection
            if (event.target.checked) {
                this.selectedSegments.add(segmentId);
            } else {
                this.selectedSegments.delete(segmentId);
            }
            this.lastSelectedIndex = index;
        }

        this.updateSelectionUI();
    }

    selectRange(startIndex, endIndex) {
        const start = Math.min(startIndex, endIndex);
        const end = Math.max(startIndex, endIndex);

        for (let i = start; i <= end; i++) {
            if (i < this.segments.length) {
                this.selectedSegments.add(this.segments[i].id);
            }
        }

        this.lastSelectedIndex = endIndex;
    }

    handleSelectAll() {
        if (this.selectAllCheckbox.checked) {
            this.segments.forEach(seg => this.selectedSegments.add(seg.id));
        } else {
            this.selectedSegments.clear();
        }
        this.updateSelectionUI();
    }

    updateSelectionUI() {
        // Update checkboxes
        this.segmentsBody.querySelectorAll("tr").forEach(row => {
            const segmentId = parseInt(row.dataset.segmentId);
            if (segmentId) {
                const checkbox = row.querySelector(".segment-checkbox");
                const isSelected = this.selectedSegments.has(segmentId);
                checkbox.checked = isSelected;
                row.classList.toggle("selected", isSelected);
            }
        });

        // Update select all checkbox
        const allSelected = this.segments.length > 0 &&
                          this.segments.every(seg => this.selectedSegments.has(seg.id));
        this.selectAllCheckbox.checked = allSelected;

        this.updateSelectionCount();
        this.updateApplyButtonState();
    }

    updateSelectionCount() {
        const count = this.selectedSegments.size;
        if (count > 0) {
            this.selectionCount.textContent = `(${count} selected)`;
        } else {
            this.selectionCount.textContent = "";
        }
    }

    updateApplyButtonState() {
        const hasSelection = this.selectedSegments.size > 0;
        const hasSpeaker = this.bulkSpeakerSelect.value !== "";
        this.applySpeakerBtn.disabled = !hasSelection || !hasSpeaker;
    }

    async handleBulkSpeakerUpdate() {
        const speaker = this.bulkSpeakerSelect.value;
        if (!speaker || this.selectedSegments.size === 0) return;

        const segmentIds = Array.from(this.selectedSegments);
        const updates = segmentIds.map(id => ({ id, speaker }));

        this.showLoading("Updating speakers...");
        try {
            const response = await fetch("/api/transcripts/segments/speaker", {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ updates })
            });

            if (!response.ok) {
                throw new Error("Failed to update speakers");
            }

            const result = await response.json();
            this.showToast(`<strong>Success!</strong> Updated ${result.updated} segment(s)`, "success");

            // Update local data
            this.segments.forEach(seg => {
                if (this.selectedSegments.has(seg.id)) {
                    seg.speaker = speaker;
                }
            });

            // Re-render to show updated speakers
            this.renderSegments();
            this.selectedSegments.clear();
            this.bulkSpeakerSelect.value = "";
            this.updateSelectionUI();

        } catch (error) {
            console.error("Error updating speakers:", error);
            this.showToast(`<strong>Error:</strong> ${error.message}`, "error");
        } finally {
            this.hideLoading();
        }
    }

    async handleSpeakerChange(event, segmentId) {
        const newSpeaker = event.target.value;
        const statusIndicator = document.querySelector(`[data-segment-id="${segmentId}"]`);

        statusIndicator.textContent = "⏳";
        statusIndicator.className = "status-indicator status-loading";

        try {
            const response = await fetch("/api/transcripts/segments/speaker", {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ updates: [{ id: segmentId, speaker: newSpeaker }] })
            });

            if (!response.ok) {
                throw new Error("Failed to update speaker");
            }

            // Update local data
            const segment = this.segments.find(s => s.id === segmentId);
            if (segment) {
                segment.speaker = newSpeaker;
            }

            // Update speaker select styling
            const color = this.speakerColors.get(newSpeaker) || "#666";
            event.target.style.borderLeftColor = color;
            event.target.style.color = color;

            statusIndicator.textContent = "✓";
            statusIndicator.className = "status-indicator status-success";
            setTimeout(() => {
                statusIndicator.textContent = "";
                statusIndicator.className = "status-indicator";
            }, 2000);

        } catch (error) {
            console.error("Error updating speaker:", error);
            statusIndicator.textContent = "✗";
            statusIndicator.className = "status-indicator status-error";
            this.showToast(`<strong>Error:</strong> Failed to update speaker`, "error");
        }
    }

    handleWordEdit(event, segmentId) {
        const input = event.target;
        const newWord = input.value.trim();
        const originalWord = input.dataset.originalValue;

        // Mark as edited if different from original
        if (newWord !== originalWord) {
            input.classList.add("editing");
        } else {
            input.classList.remove("editing");
        }

        // Debounce the API call
        if (this.debounceTimers.has(segmentId)) {
            clearTimeout(this.debounceTimers.get(segmentId));
        }

        const timer = setTimeout(() => {
            if (newWord && newWord !== originalWord) {
                this.saveWordEdit(segmentId, newWord, input);
            }
        }, 500);

        this.debounceTimers.set(segmentId, timer);
    }

    async saveWordEdit(segmentId, newWord, input) {
        const statusIndicator = document.querySelector(`[data-segment-id="${segmentId}"]`);

        statusIndicator.textContent = "⏳";
        statusIndicator.className = "status-indicator status-loading";

        try {
            const response = await fetch(`/api/transcripts/segments/${segmentId}/word`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ word: newWord })
            });

            if (!response.ok) {
                throw new Error("Failed to update word");
            }

            // Update local data and input
            const segment = this.segments.find(s => s.id === segmentId);
            if (segment) {
                segment.word = newWord;
            }
            input.dataset.originalValue = newWord;
            input.classList.remove("editing");

            statusIndicator.textContent = "✓";
            statusIndicator.className = "status-indicator status-success";
            setTimeout(() => {
                statusIndicator.textContent = "";
                statusIndicator.className = "status-indicator";
            }, 2000);

        } catch (error) {
            console.error("Error updating word:", error);
            input.classList.add("error");
            statusIndicator.textContent = "✗";
            statusIndicator.className = "status-indicator status-error";
            this.showToast(`<strong>Error:</strong> Failed to save word edit`, "error");
        }
    }

    async handlePreviousPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.selectedSegments.clear();
            await this.loadSegments();
        }
    }

    async handleNextPage() {
        const totalPages = Math.ceil(this.totalSegments / this.pageSize);
        if (this.currentPage < totalPages) {
            this.currentPage++;
            this.selectedSegments.clear();
            await this.loadSegments();
        }
    }

    updatePaginationControls() {
        const totalPages = Math.ceil(this.totalSegments / this.pageSize);

        this.prevPageBtn.disabled = this.currentPage <= 1;
        this.nextPageBtn.disabled = this.currentPage >= totalPages;
        this.pageInfo.textContent = `Page ${this.currentPage} of ${totalPages}`;
    }

    clearEditor() {
        this.currentEpisodeId = null;
        this.segments = [];
        this.selectedSegments.clear();
        this.segmentsBody.innerHTML = "";
        this.episodeTitle.textContent = "";
        this.segmentCount.textContent = "";
        this.updatePaginationControls();
    }
}

// Initialize editor when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    new TranscriptEditor();
});
