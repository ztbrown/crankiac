"""Unit tests for the version bump script."""

import pytest
import sys
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from bump_version import (
    parse_version,
    bump_version,
    analyze_commits,
    categorize_commits,
)


@pytest.mark.unit
class TestParseVersion:
    """Tests for version parsing."""

    def test_parse_standard_version(self):
        assert parse_version("1.2.3") == (1, 2, 3)

    def test_parse_zero_version(self):
        assert parse_version("0.0.0") == (0, 0, 0)

    def test_parse_version_with_prerelease(self):
        assert parse_version("1.0.0-alpha.1") == (1, 0, 0)

    def test_parse_invalid_version_raises(self):
        with pytest.raises(ValueError):
            parse_version("1.2")


@pytest.mark.unit
class TestBumpVersion:
    """Tests for version bumping."""

    def test_bump_patch(self):
        assert bump_version("1.2.3", "patch") == "1.2.4"

    def test_bump_minor(self):
        assert bump_version("1.2.3", "minor") == "1.3.0"

    def test_bump_major(self):
        assert bump_version("1.2.3", "major") == "2.0.0"

    def test_bump_patch_from_zero(self):
        assert bump_version("0.1.0", "patch") == "0.1.1"

    def test_bump_minor_from_zero(self):
        assert bump_version("0.1.0", "minor") == "0.2.0"

    def test_bump_major_from_zero(self):
        assert bump_version("0.1.0", "major") == "1.0.0"


@pytest.mark.unit
class TestAnalyzeCommits:
    """Tests for commit analysis."""

    def test_breaking_change_returns_major(self):
        commits = ["BREAKING: Remove deprecated API"]
        assert analyze_commits(commits) == "major"

    def test_breaking_in_body_returns_major(self):
        commits = ["feat: New API\n\nBREAKING CHANGE: old API removed"]
        assert analyze_commits(commits) == "major"

    def test_feat_returns_minor(self):
        commits = ["feat: Add new feature"]
        assert analyze_commits(commits) == "minor"

    def test_fix_returns_patch(self):
        commits = ["fix: Fix the bug"]
        assert analyze_commits(commits) == "patch"

    def test_mixed_commits_returns_highest(self):
        commits = [
            "fix: Fix something",
            "feat: Add feature",
            "docs: Update docs",
        ]
        assert analyze_commits(commits) == "minor"

    def test_only_patches_returns_patch(self):
        commits = [
            "fix: Bug 1",
            "docs: Update readme",
            "chore: Update deps",
        ]
        assert analyze_commits(commits) == "patch"

    def test_empty_commits_returns_patch(self):
        assert analyze_commits([]) == "patch"


@pytest.mark.unit
class TestCategorizeCommits:
    """Tests for commit categorization."""

    def test_feat_categorized_as_added(self):
        commits = ["feat: Add new feature"]
        result = categorize_commits(commits)
        assert "Added" in result
        assert "Add new feature" in result["Added"]

    def test_fix_categorized_as_fixed(self):
        commits = ["fix: Fix the bug"]
        result = categorize_commits(commits)
        assert "Fixed" in result
        assert "Fix the bug" in result["Fixed"]

    def test_breaking_categorized_as_changed(self):
        commits = ["BREAKING: Remove old API"]
        result = categorize_commits(commits)
        assert "Changed" in result
        assert any("BREAKING" in item for item in result["Changed"])

    def test_docs_not_included(self):
        commits = ["docs: Update readme"]
        result = categorize_commits(commits)
        assert "Added" not in result
        assert "Fixed" not in result

    def test_removes_issue_references(self):
        commits = ["feat: Add feature (cr-abc1)"]
        result = categorize_commits(commits)
        assert "Added" in result
        # Issue reference should be stripped from categorization
        assert "Add feature" in result["Added"]

    def test_scoped_prefix_handled(self):
        commits = ["feat(api): Add endpoint"]
        result = categorize_commits(commits)
        assert "Added" in result
        assert "Add endpoint" in result["Added"]
