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
        displayResults(data.results, data.query, data.filters);
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

function displayResults(results, query, activeFilters = {}) {
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

            let timestampLink;
            if (hasYoutube) {
                const timestampUrl = getYoutubeUrlWithTimestamp(item.youtube_url, item.start_time);
                timestampLink = `
                    <a href="${timestampUrl}"
                       target="_blank"
                       rel="noopener noreferrer"
                       class="timestamp-link youtube"
                       title="Watch on YouTube at ${timestamp}">
                        <span class="timestamp">${timestamp}</span>
                        <span class="play-icon">&#9654;</span>
                    </a>`;
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
                    </a>`;
            }

            return `
            <div class="result-item" data-result-index="${index}">
                <div class="result-header">
                    ${timestampLink}
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

        // Display expanded context
        contextContainer.innerHTML = `<p class="context expanded-context">${highlightMatch(data.context, query)}</p>`;
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
