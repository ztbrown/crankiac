import os
import time
import requests
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

DEFAULT_DOWNLOAD_DIR = "downloads/audio"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

@dataclass
class DownloadResult:
    success: bool
    file_path: Optional[str]
    error: Optional[str] = None
    file_size: int = 0

class AudioDownloader:
    """Downloads audio files from Patreon with retry support."""

    def __init__(self, session_id: str, download_dir: str = DEFAULT_DOWNLOAD_DIR):
        """
        Initialize the downloader.

        Args:
            session_id: Patreon session_id cookie for authenticated downloads.
            download_dir: Directory to save downloaded files.
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.cookies.set("session_id", session_id, domain=".patreon.com")
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })

    def get_file_path(self, episode_id: str, extension: str = "mp3") -> Path:
        """Get the local file path for an episode."""
        return self.download_dir / f"{episode_id}.{extension}"

    def is_downloaded(self, episode_id: str) -> bool:
        """Check if an episode has already been downloaded."""
        file_path = self.get_file_path(episode_id)
        return file_path.exists() and file_path.stat().st_size > 0

    def download(
        self,
        audio_url: str,
        episode_id: str,
        max_retries: int = MAX_RETRIES
    ) -> DownloadResult:
        """
        Download an audio file with retry support.

        Args:
            audio_url: URL to download from.
            episode_id: Episode ID for naming the file.
            max_retries: Maximum number of retry attempts.

        Returns:
            DownloadResult with success status and file path.
        """
        if self.is_downloaded(episode_id):
            file_path = self.get_file_path(episode_id)
            return DownloadResult(
                success=True,
                file_path=str(file_path),
                file_size=file_path.stat().st_size
            )

        file_path = self.get_file_path(episode_id)
        temp_path = file_path.with_suffix(".tmp")

        for attempt in range(max_retries):
            try:
                return self._download_with_resume(audio_url, file_path, temp_path)
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    return DownloadResult(
                        success=False,
                        file_path=None,
                        error=str(e)
                    )

        return DownloadResult(success=False, file_path=None, error="Max retries exceeded")

    def _download_with_resume(
        self,
        url: str,
        file_path: Path,
        temp_path: Path
    ) -> DownloadResult:
        """Download with resume support for partial downloads."""
        headers = {}
        mode = "wb"
        downloaded_size = 0

        # Check for partial download
        if temp_path.exists():
            downloaded_size = temp_path.stat().st_size
            headers["Range"] = f"bytes={downloaded_size}-"
            mode = "ab"

        response = self.session.get(url, headers=headers, stream=True)

        # Handle 416 (range not satisfiable) - file already complete
        if response.status_code == 416:
            if temp_path.exists():
                temp_path.rename(file_path)
                return DownloadResult(
                    success=True,
                    file_path=str(file_path),
                    file_size=file_path.stat().st_size
                )

        response.raise_for_status()

        # Get total size
        total_size = int(response.headers.get("content-length", 0)) + downloaded_size

        # Download in chunks
        with open(temp_path, mode) as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        # Rename temp file to final
        temp_path.rename(file_path)

        return DownloadResult(
            success=True,
            file_path=str(file_path),
            file_size=file_path.stat().st_size
        )

    def download_episode(self, episode) -> DownloadResult:
        """
        Download audio for an episode object.

        Args:
            episode: Episode object with id and audio_url attributes.

        Returns:
            DownloadResult with success status.
        """
        if not episode.audio_url:
            return DownloadResult(
                success=False,
                file_path=None,
                error="No audio URL available"
            )

        return self.download(episode.audio_url, episode.id)
