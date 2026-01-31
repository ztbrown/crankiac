#!/usr/bin/env python3
"""
Extract host and guest names from Chapo Trap House Wikipedia page.

Scrapes the Wikipedia List of Chapo Trap House episodes page and extracts:
- Host names (known, hardcoded)
- Guest names (extracted from episode tables)

Outputs:
- data/cth_names.json: Structured JSON with hosts, guests, and all_names
- data/cth_vocabulary.txt: Simple list of all names, one per line

Usage:
    python3 scripts/extract_cth_names.py
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# Wikipedia URL for CTH episodes
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_Chapo_Trap_House_episodes"

# Default output paths
DEFAULT_JSON_PATH = Path(__file__).parent.parent / "data" / "cth_names.json"
DEFAULT_TXT_PATH = Path(__file__).parent.parent / "data" / "cth_vocabulary.txt"


def get_host_names() -> set[str]:
    """Return the set of known CTH host names."""
    return {
        "Will Menaker",
        "Matt Christman",
        "Felix Biederman",
        "Amber Frost",
        "Virgil Texas",
    }


def clean_guest_name(name: str) -> Optional[str]:
    """
    Clean a guest name by removing extra whitespace and parenthetical suffixes.

    Returns None if the name is empty, "None", "N/A", or similar.
    """
    if not name:
        return None

    # Strip whitespace
    name = name.strip()

    if not name:
        return None

    # Check for "none" or "N/A" values
    if name.lower() in ("none", "n/a", "-", "—"):
        return None

    # Skip entries with newlines (likely concatenated names)
    if "\n" in name:
        return None

    # Remove parenthetical suffixes like "(comedian)"
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name)

    # Skip entries that are too long (likely concatenated or malformed)
    if len(name) > 60:
        return None

    # Skip entries that look like references or citations
    if name.startswith("[") or name.startswith('"'):
        return None

    # Skip entries with dangling punctuation (parsing artifacts)
    if name.endswith(")") and "(" not in name:
        return None

    # Skip entries that are likely not names (single word with special chars)
    if re.match(r"^[^a-zA-Z]+$", name):
        return None

    return name.strip() if name.strip() else None


def extract_guests_from_html(html: str) -> set[str]:
    """
    Extract guest names from Wikipedia episode table HTML.

    Looks for wikitable tables with a "Guest(s)" column and extracts
    both linked and unlinked names.
    """
    soup = BeautifulSoup(html, "html.parser")
    guests: set[str] = set()

    # Find all wikitables
    tables = soup.find_all("table", class_="wikitable")

    for table in tables:
        # Find the header row to locate the guest column
        header_row = table.find("tr")
        if not header_row:
            continue

        headers = header_row.find_all("th")
        guest_col_idx = None

        for idx, th in enumerate(headers):
            text = th.get_text().strip().lower()
            if "guest" in text:
                guest_col_idx = idx
                break

        if guest_col_idx is None:
            continue

        # Process each data row
        for row in table.find_all("tr")[1:]:  # Skip header row
            cells = row.find_all(["td", "th"])
            if len(cells) <= guest_col_idx:
                continue

            guest_cell = cells[guest_col_idx]

            # Extract linked names (from <a> tags)
            for link in guest_cell.find_all("a"):
                name = clean_guest_name(link.get_text())
                if name:
                    guests.add(name)

            # Also check for unlinked text (names without wiki links)
            # Get text and split on various separators
            cell_text = guest_cell.get_text()

            # Split on commas, newlines, and common separators
            for part in re.split(r"[,\n&]|(?:\band\b)", cell_text):
                name = clean_guest_name(part)
                if name:
                    guests.add(name)

    return guests


def fetch_wikipedia_page() -> str:
    """
    Fetch the Wikipedia List of Chapo Trap House episodes page.

    Uses a proper User-Agent to comply with Wikipedia's policy.
    """
    headers = {
        "User-Agent": "CrankiacBot/1.0 (https://github.com/crankiac; contact@example.com) requests/2.x"
    }

    response = requests.get(WIKIPEDIA_URL, headers=headers)
    response.raise_for_status()

    return response.text


def build_output_data(hosts: set[str], guests: set[str]) -> dict:
    """
    Build the output data structure.

    Returns a dict with:
    - hosts: sorted list of host names
    - guests: sorted list of guest names
    - all_names: sorted list of all names combined
    """
    all_names = hosts | guests

    return {
        "hosts": sorted(hosts),
        "guests": sorted(guests),
        "all_names": sorted(all_names),
    }


def write_output_files(data: dict, json_path: str, txt_path: str) -> None:
    """
    Write output files.

    - JSON file: Full structured data
    - TXT file: One name per line (all_names)
    """
    json_path = Path(json_path)
    txt_path = Path(txt_path)

    # Ensure parent directories exist
    json_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Write vocabulary file (one name per line)
    with open(txt_path, "w", encoding="utf-8") as f:
        for name in data["all_names"]:
            f.write(f"{name}\n")


def main() -> int:
    """Main entry point."""
    print(f"Fetching Wikipedia page: {WIKIPEDIA_URL}")
    html = fetch_wikipedia_page()
    print(f"Fetched {len(html)} bytes")

    print("Extracting guest names...")
    guests = extract_guests_from_html(html)
    print(f"Found {len(guests)} unique guest names")

    hosts = get_host_names()
    print(f"Using {len(hosts)} known host names")

    data = build_output_data(hosts, guests)
    print(f"Total unique names: {len(data['all_names'])}")

    print(f"Writing output to {DEFAULT_JSON_PATH} and {DEFAULT_TXT_PATH}")
    write_output_files(data, str(DEFAULT_JSON_PATH), str(DEFAULT_TXT_PATH))

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
