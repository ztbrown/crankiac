const searchInput = document.getElementById("search-input");
const searchButton = document.getElementById("search-button");
const resultsContainer = document.getElementById("results");
const onThisDayContainer = document.getElementById("on-this-day");

async function performSearch() {
    const query = searchInput.value.trim();

    if (!query) {
        resultsContainer.innerHTML = "";
        return;
    }

    try {
        const response = await fetch(`/api/transcripts/search?q=${encodeURIComponent(query)}&limit=50`);

        if (!response.ok) {
            throw new Error("Search request failed");
        }

        const data = await response.json();
        displayResults(data.results, data.query);
    } catch (error) {
        resultsContainer.innerHTML = `<div class="error">Error: ${error.message}</div>`;
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

function getYoutubeUrlWithTimestamp(youtubeUrl, seconds) {
    const t = Math.floor(seconds);
    if (youtubeUrl.includes("?")) {
        return `${youtubeUrl}&t=${t}`;
    }
    return `${youtubeUrl}?t=${t}`;
}

function displayResults(results, query) {
    if (results.length === 0) {
        resultsContainer.innerHTML = '<div class="no-results">No results found</div>';
        return;
    }

    const html = results
        .map((item, index) => {
            const hasYoutube = !!item.youtube_url;
            const timestampUrl = hasYoutube
                ? getYoutubeUrlWithTimestamp(item.youtube_url, item.start_time)
                : getPatreonUrl(item.patreon_id);
            const linkTitle = hasYoutube
                ? `Watch on YouTube at ${formatTimestamp(item.start_time)}`
                : `Open on Patreon (skip to ${formatTimestamp(item.start_time)})`;
            const iconClass = hasYoutube ? "youtube" : "";

            return `
            <div class="result-item" data-result-index="${index}">
                <div class="result-header">
                    <a href="${timestampUrl}"
                       target="_blank"
                       rel="noopener noreferrer"
                       class="timestamp-link ${iconClass}"
                       title="${linkTitle}">
                        <span class="timestamp">${formatTimestamp(item.start_time)}</span>
                        <span class="play-icon">${hasYoutube ? "&#9654;" : "▶"}</span>
                    </a>
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

    resultsContainer.innerHTML = html;

    // Store results for later reference
    resultsContainer.dataset.query = query;
    window.currentResults = results;

    // Add click handlers to expand buttons
    document.querySelectorAll(".expand-btn").forEach(btn => {
        btn.addEventListener("click", handleExpandClick);
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
