class TranscriptEditor {
    constructor() {
        this.currentEpisodeId = null;
        this.paragraphs = [];
        this.speakers = [];
        this.selectedRange = null;
        this.currentSelection = null;
        this.mode = "speaker"; // "speaker" or "edit"

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
        this.modeSpeakerBtn = document.getElementById("mode-speaker");
        this.modeEditBtn = document.getElementById("mode-edit");
    }

    attachEventListeners() {
        this.episodeSelect.addEventListener("change", () => this.handleEpisodeChange());
        this.errorDismiss.addEventListener("click", () => this.hideError());
        this.cancelSpeakerBtn.addEventListener("click", () => this.closeSpeakerDialog());
        this.assignSpeakerBtn.addEventListener("click", () => this.handleAssignSpeaker());
        this.dialogOverlay.addEventListener("click", () => this.closeSpeakerDialog());
        this.speakerInput.addEventListener("input", () => this.handleSpeakerInput());
        this.speakerInput.addEventListener("keydown", (e) => this.handleSpeakerInputKeydown(e));
        this.modeSpeakerBtn.addEventListener("click", () => this.setMode("speaker"));
        this.modeEditBtn.addEventListener("click", () => this.setMode("edit"));

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

    setMode(mode) {
        this.mode = mode;

        // Update button states
        this.modeSpeakerBtn.classList.toggle("active", mode === "speaker");
        this.modeEditBtn.classList.toggle("active", mode === "edit");

        // Update container class for styling
        this.transcriptContainer.dataset.mode = mode;

        // Re-render if we have a transcript loaded
        if (this.currentEpisodeId) {
            this.renderTranscript();
        }
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
        this.transcriptContainer.dataset.mode = this.mode;

        this.paragraphs.forEach((paragraph, index) => {
            const paragraphDiv = document.createElement("div");
            paragraphDiv.className = "paragraph";
            paragraphDiv.dataset.paragraphIndex = index;

            const speakerLabel = document.createElement("div");
            speakerLabel.className = "speaker-label";
            const speakerName = paragraph.speaker || "Unknown Speaker";
            const confidence = paragraph.speaker_confidence;
            if (confidence !== null && confidence !== undefined) {
                const pct = Math.round(confidence * 100);
                speakerLabel.textContent = `[${speakerName}] ${pct}%`;
                if (confidence < 0.5) {
                    speakerLabel.classList.add("low-confidence");
                } else if (confidence < 0.7) {
                    speakerLabel.classList.add("medium-confidence");
                }
            } else {
                speakerLabel.textContent = `[${speakerName}]`;
            }

            const textDiv = document.createElement("div");
            textDiv.className = "paragraph-text";
            textDiv.dataset.paragraphIndex = index;

            if (this.mode === "edit") {
                // Edit mode: make entire paragraph editable
                textDiv.contentEditable = "true";
                textDiv.spellcheck = false;
                textDiv.textContent = paragraph.text;
                textDiv.dataset.originalText = paragraph.text;
                textDiv.dataset.segmentIds = JSON.stringify(paragraph.segment_ids);

                // Add event listeners for paragraph editing
                textDiv.addEventListener("blur", (e) => this.handleParagraphBlur(e, paragraph));
                textDiv.addEventListener("keydown", (e) => {
                    if (e.key === "Escape") {
                        e.preventDefault();
                        e.target.textContent = e.target.dataset.originalText;
                        e.target.blur();
                    }
                });
            } else {
                // Speaker mode: wrap words in spans for selection
                const words = paragraph.text.split(" ");
                const segmentIds = paragraph.segment_ids;

                words.forEach((word, wordIndex) => {
                    const span = document.createElement("span");
                    span.className = "word";
                    span.textContent = word;
                    span.dataset.segmentId = segmentIds[wordIndex] || segmentIds[segmentIds.length - 1];
                    textDiv.appendChild(span);

                    if (wordIndex < words.length - 1) {
                        textDiv.appendChild(document.createTextNode(" "));
                    }
                });
            }

            paragraphDiv.appendChild(speakerLabel);
            paragraphDiv.appendChild(textDiv);
            this.transcriptContainer.appendChild(paragraphDiv);
        });
    }

    async handleParagraphBlur(e, paragraph) {
        const textDiv = e.target;
        const newText = textDiv.textContent.trim();
        const originalText = textDiv.dataset.originalText;

        if (newText === originalText) {
            return;
        }

        textDiv.classList.add("saving");

        try {
            const segmentIds = JSON.parse(textDiv.dataset.segmentIds);

            if (!newText) {
                // Full paragraph deletion: delete all segments
                for (const segmentId of segmentIds) {
                    const response = await fetch(`/api/transcripts/segments/${segmentId}`, {
                        method: "DELETE"
                    });
                    if (!response.ok && response.status !== 404) {
                        throw new Error(`Failed to delete segment ${segmentId}`);
                    }
                }

                textDiv.classList.remove("saving");
                this.showToast(`Deleted ${segmentIds.length} segments`, "success");
                await this.loadTranscript(this.currentEpisodeId);
                return;
            }

            // Split new text into words
            const newWords = newText.split(/\s+/);

            // Update words that still exist
            const updates = [];
            for (let i = 0; i < Math.min(newWords.length, segmentIds.length); i++) {
                const segmentId = segmentIds[i];
                const newWord = newWords[i];

                const response = await fetch(`/api/transcripts/segments/${segmentId}/word`, {
                    method: "PATCH",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ word: newWord })
                });

                if (!response.ok) {
                    throw new Error(`Failed to update word at position ${i}`);
                }
                updates.push({ segmentId, word: newWord });
            }

            // Delete excess segments (words removed by user)
            const deleted = [];
            for (let i = newWords.length; i < segmentIds.length; i++) {
                const segmentId = segmentIds[i];
                const response = await fetch(`/api/transcripts/segments/${segmentId}`, {
                    method: "DELETE"
                });
                if (!response.ok && response.status !== 404) {
                    throw new Error(`Failed to delete segment ${segmentId}`);
                }
                deleted.push(segmentId);
            }

            textDiv.dataset.originalText = newText;
            textDiv.classList.remove("saving");
            textDiv.classList.add("saved");
            setTimeout(() => textDiv.classList.remove("saved"), 2000);

            const parts = [];
            if (updates.length > 0) parts.push(`${updates.length} updated`);
            if (deleted.length > 0) parts.push(`${deleted.length} deleted`);
            this.showToast(parts.join(", "), "success");

            // Reload transcript to reflect changes
            await this.loadTranscript(this.currentEpisodeId);

        } catch (error) {
            textDiv.classList.remove("saving");
            textDiv.classList.add("error");
            textDiv.textContent = originalText;
            this.showToast("Failed to update text: " + error.message, "error");
            setTimeout(() => textDiv.classList.remove("error"), 2000);
        }
    }

    handleTextSelection() {
        // Only handle text selection in speaker mode
        if (this.mode !== "speaker") {
            return;
        }

        const selection = window.getSelection();
        if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
            return;
        }

        const range = selection.getRangeAt(0);
        const selectedText = selection.toString().trim();

        if (!selectedText || selectedText.length < 1) {
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
