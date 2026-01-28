const searchInput = document.getElementById("search-input");
const searchButton = document.getElementById("search-button");
const resultsContainer = document.getElementById("results");

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

function displayResults(results, query) {
    if (results.length === 0) {
        resultsContainer.innerHTML = '<div class="no-results">No results found</div>';
        return;
    }

    const html = results
        .map(
            (item) => `
            <div class="result-item">
                <div class="result-header">
                    <a href="${getPatreonUrl(item.patreon_id)}"
                       target="_blank"
                       rel="noopener noreferrer"
                       class="timestamp-link"
                       title="Open on Patreon (skip to ${formatTimestamp(item.start_time)})">
                        <span class="timestamp">${formatTimestamp(item.start_time)}</span>
                        <span class="play-icon">▶</span>
                    </a>
                    <a href="${getPatreonUrl(item.patreon_id)}"
                       target="_blank"
                       rel="noopener noreferrer"
                       class="episode-link">
                        ${escapeHtml(item.episode_title)}
                    </a>
                </div>
                <p class="context">${highlightMatch(item.context || item.word, query)}</p>
            </div>
        `
        )
        .join("");

    resultsContainer.innerHTML = html;
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
