const searchInput = document.getElementById("search-input");
const searchButton = document.getElementById("search-button");
const resultsContainer = document.getElementById("results");
const onThisDayContainer = document.getElementById("on-this-day");

const filterDateFrom = document.getElementById("filter-date-from");
const filterDateTo = document.getElementById("filter-date-to");
const filterEpisode = document.getElementById("filter-episode");
const filterContentType = document.getElementById("filter-content-type");
const clearFiltersBtn = document.getElementById("clear-filters");

function getFilters() {
    const filters = {};
    if (filterDateFrom.value) filters.date_from = filterDateFrom.value;
    if (filterDateTo.value) filters.date_to = filterDateTo.value;
    if (filterEpisode.value) filters.episode_number = filterEpisode.value;
    if (filterContentType.value !== "all") filters.content_type = filterContentType.value;
    return filters;
}

function buildSearchUrl(query) {
    const params = new URLSearchParams({ q: query, limit: "50" });
    const filters = getFilters();
    for (const [key, value] of Object.entries(filters)) {
        params.append(key, value);
    }
    // Fuzzy search is always enabled for better typo tolerance
    params.append("fuzzy", "true");
    return `/api/transcripts/search?${params.toString()}`;
}

async function performSearch() {
    const query = searchInput.value.trim();

    if (!query) {
        resultsContainer.innerHTML = "";
        return;
    }

    try {
        const url = buildSearchUrl(query);
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error("Search request failed");
        }

        const data = await response.json();
        displayResults(data.results, data.query, data.filters, data.fuzzy);
    } catch (error) {
        resultsContainer.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

function clearFilters() {
    filterDateFrom.value = "";
    filterDateTo.value = "";
    filterEpisode.value = "";
    filterContentType.value = "all";
    if (searchInput.value.trim()) {
        performSearch();
    }
}

function formatTimestamp(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function getPatreonUrl(patreonId) {
    return `https://www.patreon.com/posts/${patreonId}`;
}

function copyToClipboard(text) {
    return navigator.clipboard.writeText(text).catch(() => {
        // Fallback for older browsers
        const textarea = document.createElement("textarea");
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
    });
}

function showToast(message, duration = 4000) {
    const existing = document.querySelector(".toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = message;
    document.body.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => toast.classList.add("show"));

    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

async function handlePatreonClick(event, patreonId, timestamp) {
    event.preventDefault();

    await copyToClipboard(timestamp);
    showToast(`<strong>${timestamp}</strong> copied!<br>Use the audio player's seek bar to navigate to this time.`);

    // Open Patreon after a short delay so user sees the toast
    setTimeout(() => {
        window.open(getPatreonUrl(patreonId), "_blank", "noopener,noreferrer");
    }, 500);
}

function getYoutubeUrlWithTimestamp(youtubeUrl, seconds) {
    const t = Math.floor(seconds);
    if (youtubeUrl.includes("?")) {
        return `${youtubeUrl}&t=${t}`;
    }
    return `${youtubeUrl}?t=${t}`;
}

function extractYoutubeVideoId(url) {
    // Handle various YouTube URL formats:
    // - https://www.youtube.com/watch?v=VIDEO_ID
    // - https://youtu.be/VIDEO_ID
    // - https://www.youtube.com/embed/VIDEO_ID
    const patterns = [
        /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/,
    ];
    for (const pattern of patterns) {
        const match = url.match(pattern);
        if (match) {
            return match[1];
        }
    }
    return null;
}

function getYoutubeEmbedUrl(videoId, startSeconds) {
    const start = Math.floor(startSeconds);
    return `https://www.youtube.com/embed/${videoId}?start=${start}&autoplay=1`;
}

function toggleYoutubeEmbed(event) {
    const btn = event.currentTarget;
    const resultItem = btn.closest(".result-item");
    const contextContainer = resultItem.querySelector(".context-container");
    const embedContainer = resultItem.querySelector(".youtube-embed-container");

    if (embedContainer) {
        // Close embed
        embedContainer.remove();
        btn.classList.remove("active");
        btn.title = "Watch inline";
        return;
    }

    // Create embed using pre-computed URL from API (includes ?start= and autoplay)
    const embedUrl = btn.dataset.embedUrl;
    // Add autoplay parameter if not present
    const embedUrlWithAutoplay = embedUrl.includes("autoplay=") ? embedUrl : `${embedUrl}&autoplay=1`;

    const container = document.createElement("div");
    container.className = "youtube-embed-container";
    container.innerHTML = `
        <iframe
            src="${embedUrlWithAutoplay}"
            frameborder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen>
        </iframe>
    `;

    contextContainer.insertAdjacentElement("afterend", container);
    btn.classList.add("active");
    btn.title = "Close video";
}

function toggleAudioPlayer(event) {
    const btn = event.currentTarget;
    const resultItem = btn.closest(".result-item");
    const contextContainer = resultItem.querySelector(".context-container");
    const playerContainer = resultItem.querySelector(".audio-player-container");

    if (playerContainer) {
        // Close player
        const audio = playerContainer.querySelector("audio");
        if (audio) {
            audio.pause();
        }
        playerContainer.remove();
        btn.classList.remove("active");
        btn.title = "Play audio";
        return;
    }

    // Create audio player
    const patreonId = btn.dataset.patreonId;
    const startTime = parseFloat(btn.dataset.startTime);
    const streamUrl = `/api/audio/stream/${patreonId}`;

    const container = document.createElement("div");
    container.className = "audio-player-container";
    container.innerHTML = `
        <div class="audio-player-wrapper">
            <audio controls preload="metadata">
                <source src="${streamUrl}" type="audio/mpeg">
                Your browser does not support the audio element.
            </audio>
            <div class="audio-seek-info">
                Seeking to ${formatTimestamp(startTime)}...
            </div>
        </div>
    `;

    contextContainer.insertAdjacentElement("afterend", container);

    const audio = container.querySelector("audio");
    const seekInfo = container.querySelector(".audio-seek-info");

    // When metadata is loaded, seek to the start time
    audio.addEventListener("loadedmetadata", () => {
        audio.currentTime = startTime;
        seekInfo.textContent = `Playing from ${formatTimestamp(startTime)}`;
        audio.play().catch(e => {
            // Autoplay might be blocked
            seekInfo.textContent = `Ready at ${formatTimestamp(startTime)} - click play`;
        });
    });

    // Update seek info while playing
    audio.addEventListener("timeupdate", () => {
        seekInfo.textContent = `${formatTimestamp(audio.currentTime)} / ${formatTimestamp(audio.duration || 0)}`;
    });

    // Handle errors
    audio.addEventListener("error", () => {
        seekInfo.textContent = "Audio not available";
        seekInfo.classList.add("error");
    });

    btn.classList.add("active");
    btn.title = "Close audio";
}

function getMatchTypeBadge(item) {
    // If no similarity field, it's an exact match (non-fuzzy search)
    if (item.similarity === undefined) {
        return '<span class="match-badge exact">exact</span>';
    }
    // Similarity of 1.0 means exact match
    if (item.similarity >= 0.99) {
        return '<span class="match-badge exact">exact</span>';
    }
    // Lower similarity means fuzzy match (trigram-based)
    return `<span class="match-badge fuzzy">fuzzy ${Math.round(item.similarity * 100)}%</span>`;
}

function displayResults(results, query, activeFilters = {}, fuzzyEnabled = true) {
    if (results.length === 0) {
        const filterInfo = Object.keys(activeFilters).length > 0
            ? " with current filters"
            : "";
        resultsContainer.innerHTML = `<div class="no-results">No results found${filterInfo}</div>`;
        return;
    }

    // Show active filters summary
    let filterSummary = "";
    if (Object.keys(activeFilters).length > 0) {
        const filterParts = [];
        if (activeFilters.date_from || activeFilters.date_to) {
            const from = activeFilters.date_from || "any";
            const to = activeFilters.date_to || "any";
            filterParts.push(`dates: ${from} to ${to}`);
        }
        if (activeFilters.episode_number) {
            filterParts.push(`episode #${activeFilters.episode_number}`);
        }
        if (activeFilters.content_type) {
            filterParts.push(activeFilters.content_type === "free" ? "free episodes" : "premium episodes");
        }
        filterSummary = `<div class="filter-summary">Filtered by: ${filterParts.join(", ")}</div>`;
    }

    const html = results
        .map((item, index) => {
            const hasYoutube = !!item.youtube_url;
            const timestamp = formatTimestamp(item.start_time);
            const iconClass = hasYoutube ? "youtube" : "patreon";
            const matchBadge = fuzzyEnabled ? getMatchTypeBadge(item) : "";

            let timestampLink;
            if (hasYoutube) {
                const timestampUrl = getYoutubeUrlWithTimestamp(item.youtube_url, item.start_time);
                // Use youtube_embed_url from API if available, otherwise fallback to constructing it
                const embedUrl = item.youtube_embed_url || getYoutubeEmbedUrl(extractYoutubeVideoId(item.youtube_url), item.start_time);
                timestampLink = `
                    <a href="${timestampUrl}"
                       target="_blank"
                       rel="noopener noreferrer"
                       class="timestamp-link youtube"
                       title="Watch on YouTube at ${timestamp}">
                        <span class="timestamp">${timestamp}</span>
                        <span class="play-icon">&#9654;</span>
                    </a>
                    <button class="embed-btn"
                            data-embed-url="${escapeHtml(embedUrl)}"
                            title="Watch inline">
                        <span class="embed-icon">&#9632;</span>
                    </button>`;
            } else {
                timestampLink = `
                    <a href="${getPatreonUrl(item.patreon_id)}"
                       class="timestamp-link patreon"
                       title="Copy timestamp and open on Patreon"
                       data-patreon-id="${item.patreon_id}"
                       data-timestamp="${timestamp}">
                        <span class="timestamp">${timestamp}</span>
                        <span class="play-icon">▶</span>
                        <span class="copy-hint">📋</span>
                    </a>
                    <button class="audio-btn"
                            data-patreon-id="${item.patreon_id}"
                            data-start-time="${item.start_time}"
                            title="Play audio">
                        <span class="audio-icon">🔊</span>
                    </button>`;
            }

            const speakerSpan = item.speaker
                ? `<span class="speaker">${escapeHtml(item.speaker)}</span>`
                : "";

            return `
            <div class="result-item" data-result-index="${index}">
                <div class="result-header">
                    ${timestampLink}
                    ${matchBadge}
                    ${speakerSpan}
                    <a href="${hasYoutube ? item.youtube_url : getPatreonUrl(item.patreon_id)}"
                       target="_blank"
                       rel="noopener noreferrer"
                       class="episode-link">
                        ${escapeHtml(item.episode_title)}
                    </a>
                    ${hasYoutube ? '<span class="yt-badge">YT</span>' : ""}
                    <button class="expand-btn"
                            data-episode-id="${item.episode_id}"
                            data-segment-index="${item.segment_index}"
                            title="Show more context">
                        <span class="expand-icon">⋯</span>
                    </button>
                </div>
                <div class="context-container">
                    <p class="context">${highlightMatch(item.context || item.word || item.phrase, query)}</p>
                </div>
            </div>
        `;
        })
        .join("");

    resultsContainer.innerHTML = filterSummary + html;

    // Store results for later reference
    resultsContainer.dataset.query = query;
    window.currentResults = results;

    // Add click handlers to expand buttons
    document.querySelectorAll(".expand-btn").forEach(btn => {
        btn.addEventListener("click", handleExpandClick);
    });

    // Add click handlers to Patreon timestamp links
    document.querySelectorAll(".timestamp-link.patreon").forEach(link => {
        link.addEventListener("click", (e) => {
            handlePatreonClick(e, link.dataset.patreonId, link.dataset.timestamp);
        });
    });

    // Add click handlers to YouTube embed buttons
    document.querySelectorAll(".embed-btn").forEach(btn => {
        btn.addEventListener("click", toggleYoutubeEmbed);
    });

    // Add click handlers to audio play buttons
    document.querySelectorAll(".audio-btn").forEach(btn => {
        btn.addEventListener("click", toggleAudioPlayer);
    });
}

async function handleExpandClick(event) {
    const btn = event.currentTarget;
    const resultItem = btn.closest(".result-item");
    const contextContainer = resultItem.querySelector(".context-container");
    const episodeId = btn.dataset.episodeId;
    const segmentIndex = btn.dataset.segmentIndex;
    const query = resultsContainer.dataset.query;

    // Check if already expanded
    if (resultItem.classList.contains("expanded")) {
        // Collapse: restore original context
        const resultIndex = parseInt(resultItem.dataset.resultIndex);
        const originalItem = window.currentResults[resultIndex];
        contextContainer.innerHTML = `<p class="context">${highlightMatch(originalItem.context || originalItem.word, query)}</p>`;
        resultItem.classList.remove("expanded");
        btn.querySelector(".expand-icon").textContent = "⋯";
        btn.title = "Show more context";
        return;
    }

    // Show loading state
    btn.disabled = true;
    btn.querySelector(".expand-icon").textContent = "⏳";

    try {
        const response = await fetch(
            `/api/transcripts/context?episode_id=${episodeId}&segment_index=${segmentIndex}&radius=50`
        );

        if (!response.ok) {
            throw new Error("Failed to fetch context");
        }

        const data = await response.json();

        // Display expanded context as script format if speaker_turns available
        let contextHtml;
        if (data.speaker_turns && data.speaker_turns.length > 0) {
            contextHtml = '<div class="context expanded-context script-format">';
            for (const turn of data.speaker_turns) {
                const speakerLabel = turn.speaker || "Unknown";
                const text = highlightMatch(turn.text, query);
                contextHtml += `<div class="speaker-turn"><span class="speaker-label">${escapeHtml(speakerLabel)}:</span> ${text}</div>`;
            }
            contextHtml += '</div>';
        } else {
            contextHtml = `<p class="context expanded-context">${highlightMatch(data.context, query)}</p>`;
        }
        contextContainer.innerHTML = contextHtml;
        resultItem.classList.add("expanded");
        btn.querySelector(".expand-icon").textContent = "−";
        btn.title = "Show less context";
    } catch (error) {
        console.error("Error fetching context:", error);
        btn.querySelector(".expand-icon").textContent = "!";
    } finally {
        btn.disabled = false;
    }
}

function highlightMatch(text, query) {
    const escaped = escapeHtml(text);
    const regex = new RegExp(`(${escapeRegex(query)})`, "gi");
    return escaped.replace(regex, '<mark>$1</mark>');
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

searchButton.addEventListener("click", performSearch);

searchInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
        performSearch();
    }
});

async function loadOnThisDay() {
    try {
        const response = await fetch("/api/transcripts/on-this-day");

        if (!response.ok) {
            throw new Error("Failed to fetch On This Day");
        }

        const data = await response.json();
        displayOnThisDay(data);
    } catch (error) {
        console.error("Error loading On This Day:", error);
    }
}

function displayOnThisDay(data) {
    if (!data.episodes || data.episodes.length === 0) {
        onThisDayContainer.innerHTML = "";
        return;
    }

    const monthNames = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ];

    const dateStr = `${monthNames[data.date.month - 1]} ${data.date.day}`;

    const episodesHtml = data.episodes
        .map((ep, index) => {
            const yearsAgo = data.years_ago[index];
            const yearLabel = yearsAgo === 1 ? "1 year ago" : `${yearsAgo} years ago`;
            const linkUrl = ep.youtube_url || getPatreonUrl(ep.patreon_id);
            const hasYoutube = !!ep.youtube_url;

            return `
                <div class="otd-episode">
                    <span class="otd-years-ago">${yearLabel}</span>
                    <a href="${linkUrl}"
                       target="_blank"
                       rel="noopener noreferrer"
                       class="otd-episode-link">
                        ${escapeHtml(ep.title)}
                    </a>
                    ${hasYoutube ? '<span class="yt-badge">YT</span>' : ""}
                </div>
            `;
        })
        .join("");

    onThisDayContainer.innerHTML = `
        <div class="otd-header">
            <h2>On This Day (${dateStr})</h2>
        </div>
        <div class="otd-episodes">
            ${episodesHtml}
        </div>
    `;
}

// Load On This Day content when page loads
loadOnThisDay();

clearFiltersBtn.addEventListener("click", clearFilters);

// Re-search when filters change
[filterDateFrom, filterDateTo, filterEpisode, filterContentType].forEach(el => {
    el.addEventListener("change", () => {
        if (searchInput.value.trim()) {
            performSearch();
        }
    });
});
