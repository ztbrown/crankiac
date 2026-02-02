const FRONTEND_VERSION = "0.2.0";

async function fetchBackendVersion() {
    try {
        const response = await fetch("/api/version");
        if (!response.ok) {
            throw new Error("Failed to fetch version");
        }
        const data = await response.json();
        return data.version;
    } catch (error) {
        console.error("Error fetching backend version:", error);
        return null;
    }
}

async function displayVersion() {
    const versionElement = document.getElementById("version-info");
    if (!versionElement) return;

    const backendVersion = await fetchBackendVersion();

    if (backendVersion && backendVersion !== FRONTEND_VERSION) {
        versionElement.textContent = `v${FRONTEND_VERSION} (backend v${backendVersion})`;
    } else {
        versionElement.textContent = `v${FRONTEND_VERSION}`;
    }
}

document.addEventListener("DOMContentLoaded", displayVersion);
