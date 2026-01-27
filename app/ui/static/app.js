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
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);

        if (!response.ok) {
            throw new Error("Search request failed");
        }

        const data = await response.json();
        displayResults(data.results);
    } catch (error) {
        resultsContainer.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

function displayResults(results) {
    if (results.length === 0) {
        resultsContainer.innerHTML = '<div class="no-results">No results found</div>';
        return;
    }

    const html = results
        .map(
            (item) => `
            <div class="result-item">
                <h3>${escapeHtml(item.name)}</h3>
                <p>${escapeHtml(item.description || "")}</p>
            </div>
        `
        )
        .join("");

    resultsContainer.innerHTML = html;
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
