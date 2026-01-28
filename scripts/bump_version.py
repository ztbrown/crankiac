#!/usr/bin/env python3
"""
Version bump utility for the refinery.

Analyzes commit messages and bumps the version in pyproject.toml accordingly.
Updates CHANGELOG.md with the changes.

Usage:
    python3 bump_version.py [patch|minor|major|auto]

    auto: Analyze commits since last tag to determine bump level
    patch/minor/major: Force a specific bump level
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Literal, Optional

BumpLevel = Literal["patch", "minor", "major"]

# Commit prefix to bump level mapping
COMMIT_BUMP_MAP: dict[str, BumpLevel] = {
    "feat": "minor",
    "fix": "patch",
    "docs": "patch",
    "refactor": "patch",
    "test": "patch",
    "chore": "patch",
    "perf": "patch",
    "style": "patch",
    "ci": "patch",
    "build": "patch",
}


def get_current_version() -> str:
    """Read current version from pyproject.toml."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject.read_text()
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    if not match:
        raise ValueError("Could not find version in pyproject.toml")
    return match.group(1)


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse version string into (major, minor, patch) tuple."""
    # Handle pre-release suffixes
    base_version = version.split("-")[0]
    parts = base_version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump_version(current: str, level: BumpLevel) -> str:
    """Bump version according to level."""
    major, minor, patch = parse_version(current)

    if level == "major":
        return f"{major + 1}.0.0"
    elif level == "minor":
        return f"{major}.{minor + 1}.0"
    else:  # patch
        return f"{major}.{minor}.{patch + 1}"


def get_commits_since_tag(tag: Optional[str] = None) -> list[str]:
    """Get commit messages since the specified tag (or all if no tag)."""
    try:
        if tag:
            result = subprocess.run(
                ["git", "log", f"{tag}..HEAD", "--pretty=format:%s"],
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            result = subprocess.run(
                ["git", "log", "--pretty=format:%s"],
                capture_output=True,
                text=True,
                check=True,
            )
        return [msg for msg in result.stdout.strip().split("\n") if msg]
    except subprocess.CalledProcessError:
        return []


def get_latest_tag() -> Optional[str]:
    """Get the latest version tag."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", "--match", "v*"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def analyze_commits(commits: list[str]) -> BumpLevel:
    """Analyze commits to determine the appropriate bump level."""
    max_level: BumpLevel = "patch"

    for commit in commits:
        commit_lower = commit.lower()

        # Check for breaking changes
        if commit_lower.startswith("breaking:") or "breaking change:" in commit_lower:
            return "major"

        # Check for conventional commit prefixes
        for prefix, level in COMMIT_BUMP_MAP.items():
            if commit_lower.startswith(f"{prefix}:") or commit_lower.startswith(f"{prefix}("):
                if level == "minor" and max_level == "patch":
                    max_level = "minor"
                break

    return max_level


def categorize_commits(commits: list[str]) -> dict[str, list[str]]:
    """Categorize commits by type for changelog."""
    categories: dict[str, list[str]] = {
        "Added": [],
        "Changed": [],
        "Fixed": [],
        "Removed": [],
        "Security": [],
        "Other": [],
    }

    for commit in commits:
        # Remove issue references like (cr-xyz)
        clean_commit = re.sub(r"\s*\(cr-\w+\)\s*$", "", commit)

        # Categorize based on prefix
        commit_lower = clean_commit.lower()
        if commit_lower.startswith("feat:") or commit_lower.startswith("feat("):
            msg = re.sub(r"^feat(\([^)]+\))?:\s*", "", clean_commit, flags=re.IGNORECASE)
            categories["Added"].append(msg)
        elif commit_lower.startswith("fix:") or commit_lower.startswith("fix("):
            msg = re.sub(r"^fix(\([^)]+\))?:\s*", "", clean_commit, flags=re.IGNORECASE)
            categories["Fixed"].append(msg)
        elif commit_lower.startswith("breaking:"):
            msg = re.sub(r"^breaking:\s*", "", clean_commit, flags=re.IGNORECASE)
            categories["Changed"].append(f"**BREAKING**: {msg}")
        elif commit_lower.startswith(("refactor:", "refactor(")):
            msg = re.sub(r"^refactor(\([^)]+\))?:\s*", "", clean_commit, flags=re.IGNORECASE)
            categories["Changed"].append(msg)
        elif commit_lower.startswith(("docs:", "docs(")):
            # Skip docs commits in changelog
            pass
        elif commit_lower.startswith(("test:", "test(", "chore:", "chore(", "ci:", "ci(")):
            # Skip test/chore/ci commits in changelog
            pass
        else:
            categories["Other"].append(clean_commit)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def update_pyproject(new_version: str) -> None:
    """Update version in pyproject.toml."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject.read_text()
    updated = re.sub(
        r'version\s*=\s*"[^"]+"',
        f'version = "{new_version}"',
        content,
    )
    pyproject.write_text(updated)
    print(f"Updated pyproject.toml to version {new_version}")


def update_changelog(new_version: str, categories: dict[str, list[str]]) -> None:
    """Update CHANGELOG.md with new version entry."""
    changelog = Path(__file__).parent.parent / "CHANGELOG.md"

    if not changelog.exists():
        print("Warning: CHANGELOG.md not found, skipping update")
        return

    content = changelog.read_text()
    today = date.today().isoformat()

    # Build new version section
    new_section_lines = [f"\n## [{new_version}] - {today}\n"]

    for category, items in categories.items():
        if items:
            new_section_lines.append(f"\n### {category}\n")
            for item in items:
                new_section_lines.append(f"- {item}\n")

    new_section = "".join(new_section_lines)

    # Insert after [Unreleased] section
    unreleased_pattern = r"(## \[Unreleased\].*?)(\n## \[)"
    match = re.search(unreleased_pattern, content, re.DOTALL)

    if match:
        # Clear unreleased section and add new version
        unreleased_header = "## [Unreleased]\n"
        insert_pos = match.start(2)
        content = content[:match.start(1)] + unreleased_header + new_section + content[insert_pos:]
    else:
        # No existing version sections, add after Unreleased
        unreleased_pos = content.find("## [Unreleased]")
        if unreleased_pos != -1:
            # Find end of unreleased section
            next_section = content.find("\n## [", unreleased_pos + 1)
            if next_section == -1:
                content = content.rstrip() + new_section
            else:
                content = content[:next_section] + new_section + content[next_section:]

    changelog.write_text(content)
    print(f"Updated CHANGELOG.md with version {new_version}")


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        level_arg = "auto"
    else:
        level_arg = sys.argv[1].lower()

    if level_arg not in ("patch", "minor", "major", "auto"):
        print(f"Usage: {sys.argv[0]} [patch|minor|major|auto]")
        return 1

    current_version = get_current_version()
    print(f"Current version: {current_version}")

    # Determine bump level
    if level_arg == "auto":
        latest_tag = get_latest_tag()
        commits = get_commits_since_tag(latest_tag)

        if not commits:
            print("No commits found since last tag, nothing to bump")
            return 0

        level = analyze_commits(commits)
        print(f"Analyzed {len(commits)} commits, determined bump level: {level}")
    else:
        level = level_arg  # type: ignore
        latest_tag = get_latest_tag()
        commits = get_commits_since_tag(latest_tag)

    # Calculate new version
    new_version = bump_version(current_version, level)
    print(f"Bumping to version: {new_version}")

    # Update files
    update_pyproject(new_version)

    if commits:
        categories = categorize_commits(commits)
        update_changelog(new_version, categories)

    print(f"\nVersion bumped: {current_version} -> {new_version}")
    print("Don't forget to commit and tag:")
    print(f"  git add pyproject.toml CHANGELOG.md")
    print(f"  git commit -m 'chore: Bump version to {new_version}'")
    print(f"  git tag v{new_version}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
