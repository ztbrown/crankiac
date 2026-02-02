class TranscriptEditor {
    constructor() {
        this.currentEpisodeId = null;
        this.paragraphs = [];
        this.speakers = [];
        this.selectedRange = null;
        this.currentSelection = null;

        this.initializeElements();
        this.attachEventListeners();
        this.loadEpisodes();
        this.loadSpeakers();
    }

    initializeElements() {
        this.episodeSelect = document.getElementById("episode-select");
        this.episodeTitle = document.getElementById("episode-title");
        this.paragraphCount = document.getElementById("paragraph-count");
        this.transcriptContainer = document.getElementById("transcript-container");
        this.loadingContainer = document.getElementById("loading-container");
        this.errorContainer = document.getElementById("error-container");
        this.errorText = document.getElementById("error-text");
        this.errorDismiss = document.getElementById("error-dismiss");
        this.speakerDialog = document.getElementById("speaker-dialog");
        this.dialogOverlay = document.getElementById("dialog-overlay");
        this.speakerInput = document.getElementById("speaker-input");
        this.speakerSuggestions = document.getElementById("speaker-suggestions");
        this.selectedTextPreview = document.getElementById("selected-text-preview");
        this.cancelSpeakerBtn = document.getElementById("cancel-speaker-btn");
        this.assignSpeakerBtn = document.getElementById("assign-speaker-btn");
    }

    attachEventListeners() {
        this.episodeSelect.addEventListener("change", () => this.handleEpisodeChange());
        this.errorDismiss.addEventListener("click", () => this.hideError());
        this.cancelSpeakerBtn.addEventListener("click", () => this.closeSpeakerDialog());
        this.assignSpeakerBtn.addEventListener("click", () => this.handleAssignSpeaker());
        this.dialogOverlay.addEventListener("click", () => this.closeSpeakerDialog());
        this.speakerInput.addEventListener("input", () => this.handleSpeakerInput());
        this.speakerInput.addEventListener("keydown", (e) => this.handleSpeakerInputKeydown(e));

        // Handle text selection
        document.addEventListener("mouseup", () => this.handleTextSelection());
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
        container.innerHTML = "";

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.innerHTML = message;
        container.appendChild(toast);

        requestAnimationFrame(() => toast.classList.add("show"));

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
            this.showError("Failed to load episodes: " + error.message);
        } finally {
            this.hideLoading();
        }
    }

    async loadSpeakers() {
        try {
            const response = await fetch("/api/transcripts/speakers");
            if (!response.ok) {
                throw new Error("Failed to fetch speakers");
            }

            const data = await response.json();
            this.speakers = data.speakers;
        } catch (error) {
            console.error("Failed to load speakers:", error);
        }
    }

    populateEpisodeDropdown(episodes) {
        this.episodeSelect.innerHTML = '<option value="">-- Select an episode --</option>';

        episodes.forEach(episode => {
            const option = document.createElement("option");
            option.value = episode.id;
            option.textContent = episode.title;
            this.episodeSelect.appendChild(option);
        });
    }

    async handleEpisodeChange() {
        const episodeId = parseInt(this.episodeSelect.value);
        if (!episodeId) {
            this.transcriptContainer.innerHTML = "";
            this.episodeTitle.textContent = "";
            this.paragraphCount.textContent = "";
            return;
        }

        this.currentEpisodeId = episodeId;
        await this.loadTranscript(episodeId);
    }

    async loadTranscript(episodeId) {
        this.showLoading("Loading transcript...");
        try {
            const response = await fetch(`/api/transcripts/episode/${episodeId}/paragraphs`);
            if (!response.ok) {
                throw new Error("Failed to fetch transcript");
            }

            const data = await response.json();
            this.paragraphs = data.paragraphs;
            this.episodeTitle.textContent = data.episode_title;
            this.paragraphCount.textContent = `${data.total} paragraphs`;
            this.renderTranscript();
        } catch (error) {
            this.showError("Failed to load transcript: " + error.message);
        } finally {
            this.hideLoading();
        }
    }

    renderTranscript() {
        this.transcriptContainer.innerHTML = "";

        this.paragraphs.forEach((paragraph, index) => {
            const paragraphDiv = document.createElement("div");
            paragraphDiv.className = "paragraph";
            paragraphDiv.dataset.paragraphIndex = index;

            const speakerLabel = document.createElement("div");
            speakerLabel.className = "speaker-label";
            speakerLabel.textContent = `[${paragraph.speaker || "Unknown Speaker"}]`;

            const textDiv = document.createElement("div");
            textDiv.className = "paragraph-text";
            textDiv.dataset.paragraphIndex = index;

            // Split text into words and wrap each with segment IDs
            const words = paragraph.text.split(" ");
            const segmentIds = paragraph.segment_ids;

            words.forEach((word, wordIndex) => {
                const span = document.createElement("span");
                span.className = "word";
                span.contentEditable = "true";
                span.spellcheck = false;
                span.textContent = word;
                span.dataset.segmentId = segmentIds[wordIndex] || segmentIds[segmentIds.length - 1];
                span.dataset.originalWord = word;

                // Add event listeners for editing
                span.addEventListener("focus", (e) => this.handleWordFocus(e));
                span.addEventListener("blur", (e) => this.handleWordBlur(e));
                span.addEventListener("keydown", (e) => this.handleWordKeydown(e));

                textDiv.appendChild(span);

                if (wordIndex < words.length - 1) {
                    textDiv.appendChild(document.createTextNode(" "));
                }
            });

            paragraphDiv.appendChild(speakerLabel);
            paragraphDiv.appendChild(textDiv);
            this.transcriptContainer.appendChild(paragraphDiv);
        });
    }

    handleWordFocus(e) {
        const span = e.target;
        span.dataset.originalWord = span.textContent;
        span.classList.add("editing");
    }

    handleWordBlur(e) {
        const span = e.target;
        span.classList.remove("editing");

        const newWord = span.textContent.trim();
        const originalWord = span.dataset.originalWord;
        const segmentId = parseInt(span.dataset.segmentId);

        if (newWord && newWord !== originalWord) {
            this.updateWord(segmentId, newWord, span);
        } else if (!newWord) {
            // Restore original if empty
            span.textContent = originalWord;
        }
    }

    handleWordKeydown(e) {
        if (e.key === "Enter") {
            e.preventDefault();
            e.target.blur();
        } else if (e.key === "Escape") {
            e.preventDefault();
            e.target.textContent = e.target.dataset.originalWord;
            e.target.blur();
        }
    }

    async updateWord(segmentId, newWord, span) {
        span.classList.add("saving");

        try {
            const response = await fetch(`/api/transcripts/segments/${segmentId}/word`, {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ word: newWord })
            });

            if (!response.ok) {
                throw new Error("Failed to update word");
            }

            span.dataset.originalWord = newWord;
            span.classList.remove("saving");
            span.classList.add("saved");
            setTimeout(() => span.classList.remove("saved"), 2000);
        } catch (error) {
            span.classList.remove("saving");
            span.classList.add("error");
            span.textContent = span.dataset.originalWord;
            this.showToast("Failed to update word: " + error.message, "error");
            setTimeout(() => span.classList.remove("error"), 2000);
        }
    }

    handleTextSelection() {
        const selection = window.getSelection();
        if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
            return;
        }

        const range = selection.getRangeAt(0);
        const selectedText = selection.toString().trim();

        if (!selectedText || selectedText.length < 2) {
            return;
        }

        // Find the segment IDs for the selected range
        const startContainer = range.startContainer;
        const endContainer = range.endContainer;

        // Find the word spans containing the selection
        const startSpan = this.findWordSpan(startContainer);
        const endSpan = this.findWordSpan(endContainer);

        if (!startSpan || !endSpan) {
            return;
        }

        const startSegmentId = parseInt(startSpan.dataset.segmentId);
        const endSegmentId = parseInt(endSpan.dataset.segmentId);

        if (!startSegmentId || !endSegmentId) {
            return;
        }

        this.selectedRange = {
            startSegmentId,
            endSegmentId,
            text: selectedText
        };

        this.openSpeakerDialog(selectedText);
    }

    findWordSpan(node) {
        if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains("word")) {
            return node;
        }
        if (node.nodeType === Node.TEXT_NODE && node.parentElement) {
            if (node.parentElement.classList.contains("word")) {
                return node.parentElement;
            }
            // Look for sibling word spans
            const siblings = Array.from(node.parentElement.children);
            return siblings.find(s => s.classList.contains("word"));
        }
        return null;
    }

    openSpeakerDialog(selectedText) {
        const previewText = selectedText.length > 100
            ? selectedText.substring(0, 100) + "..."
            : selectedText;
        this.selectedTextPreview.textContent = `"${previewText}"`;
        this.speakerInput.value = "";
        this.speakerSuggestions.innerHTML = "";
        this.assignSpeakerBtn.disabled = true;
        this.speakerDialog.style.display = "flex";
        this.dialogOverlay.style.display = "block";
        this.speakerInput.focus();
    }

    closeSpeakerDialog() {
        this.speakerDialog.style.display = "none";
        this.dialogOverlay.style.display = "none";
        this.selectedRange = null;
        window.getSelection().removeAllRanges();
    }

    handleSpeakerInput() {
        const query = this.speakerInput.value.trim();
        this.assignSpeakerBtn.disabled = query.length === 0;

        if (query.length === 0) {
            this.speakerSuggestions.innerHTML = "";
            return;
        }

        // Filter speakers by query
        const matches = this.speakers.filter(s =>
            s.name.toLowerCase().includes(query.toLowerCase())
        );

        this.renderSuggestions(matches);
    }

    handleSpeakerInputKeydown(e) {
        if (e.key === "Enter" && !this.assignSpeakerBtn.disabled) {
            this.handleAssignSpeaker();
        } else if (e.key === "Escape") {
            this.closeSpeakerDialog();
        }
    }

    renderSuggestions(matches) {
        this.speakerSuggestions.innerHTML = "";

        if (matches.length === 0) {
            return;
        }

        matches.slice(0, 5).forEach(speaker => {
            const suggestion = document.createElement("div");
            suggestion.className = "suggestion-item";
            suggestion.textContent = speaker.name;
            suggestion.addEventListener("click", () => {
                this.speakerInput.value = speaker.name;
                this.speakerSuggestions.innerHTML = "";
                this.assignSpeakerBtn.disabled = false;
                this.currentSelection = speaker;
            });
            this.speakerSuggestions.appendChild(suggestion);
        });
    }

    async handleAssignSpeaker() {
        if (!this.selectedRange) {
            return;
        }

        const speakerName = this.speakerInput.value.trim();
        if (!speakerName) {
            return;
        }

        this.assignSpeakerBtn.disabled = true;
        this.assignSpeakerBtn.textContent = "Assigning...";

        try {
            // Check if speaker exists, if not create it
            let speaker = this.speakers.find(s => s.name === speakerName);
            if (!speaker) {
                speaker = await this.createSpeaker(speakerName);
                if (!speaker) {
                    throw new Error("Failed to create speaker");
                }
                this.speakers.push(speaker);
            }

            // Assign speaker to the selected range
            const response = await fetch("/api/transcripts/assign-speaker", {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    episode_id: this.currentEpisodeId,
                    start_segment_id: this.selectedRange.startSegmentId,
                    end_segment_id: this.selectedRange.endSegmentId,
                    speaker_id: speaker.id
                })
            });

            if (!response.ok) {
                throw new Error("Failed to assign speaker");
            }

            const result = await response.json();
            this.showToast(`Assigned "${speakerName}" to ${result.updated} segments`, "success");

            // Reload the transcript to reflect changes
            await this.loadTranscript(this.currentEpisodeId);

            this.closeSpeakerDialog();
        } catch (error) {
            this.showToast("Failed to assign speaker: " + error.message, "error");
        } finally {
            this.assignSpeakerBtn.disabled = false;
            this.assignSpeakerBtn.textContent = "Assign Speaker";
        }
    }

    async createSpeaker(name) {
        try {
            const response = await fetch("/api/transcripts/speakers", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ name })
            });

            if (!response.ok) {
                // Speaker might already exist
                if (response.status === 409) {
                    // Reload speakers and find it
                    await this.loadSpeakers();
                    return this.speakers.find(s => s.name === name);
                }
                throw new Error("Failed to create speaker");
            }

            return await response.json();
        } catch (error) {
            console.error("Failed to create speaker:", error);
            return null;
        }
    }
}

// Initialize editor when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    new TranscriptEditor();
});
