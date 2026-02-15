"""Tests for extract-clips manage.py command."""
import pytest
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestExtractClipsCommand:
    """Tests for extract-clips command."""

    @pytest.mark.unit
    def test_extract_clips_in_help(self):
        """Test that extract-clips command appears in help."""
        result = subprocess.run(
            [sys.executable, "manage.py", "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )
        assert "extract-clips" in result.stdout

    @pytest.mark.unit
    def test_extract_clips_help(self):
        """Test extract-clips --help works."""
        result = subprocess.run(
            [sys.executable, "manage.py", "extract-clips", "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )
        assert result.returncode == 0
        assert "--episode" in result.stdout
        assert "--episodes" in result.stdout
        assert "--speaker" in result.stdout
        assert "--max-clips" in result.stdout
        assert "--output-dir" in result.stdout
        assert "--min-duration" in result.stdout
        assert "--max-duration" in result.stdout
