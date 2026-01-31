"""Unit tests for the CTH name extractor script."""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


# Sample HTML that mimics the Wikipedia episode table structure
SAMPLE_EPISODE_HTML = """
<html>
<body>
<h2><span id="2017">2017</span></h2>
<table class="wikitable">
<tr>
<th>No.</th>
<th>Title</th>
<th>Guest(s)</th>
<th>Release date</th>
</tr>
<tr>
<td>1</td>
<td>"Pilot Episode"</td>
<td>None</td>
<td>March 13, 2017</td>
</tr>
<tr>
<td>2</td>
<td>"Second Episode"</td>
<td><a href="/wiki/Adam_Curtis">Adam Curtis</a></td>
<td>March 20, 2017</td>
</tr>
<tr>
<td>3</td>
<td>"Third Episode"</td>
<td><a href="/wiki/Naomi_Klein">Naomi Klein</a>, <a href="/wiki/Slavoj_Zizek">Slavoj Zizek</a></td>
<td>March 27, 2017</td>
</tr>
<tr>
<td>4</td>
<td>"Fourth Episode"</td>
<td>John Smith (comedian)</td>
<td>April 3, 2017</td>
</tr>
</table>

<h2><span id="2018">2018</span></h2>
<table class="wikitable">
<tr>
<th>No.</th>
<th>Title</th>
<th>Guest(s)</th>
<th>Release date</th>
</tr>
<tr>
<td>100</td>
<td>"Centennial"</td>
<td><a href="/wiki/Noam_Chomsky">Noam Chomsky</a></td>
<td>January 5, 2018</td>
</tr>
</table>
</body>
</html>
"""

# HTML without guest column
SAMPLE_HTML_NO_GUESTS = """
<html>
<body>
<table class="wikitable">
<tr>
<th>No.</th>
<th>Title</th>
<th>Release date</th>
</tr>
<tr>
<td>1</td>
<td>"Pilot"</td>
<td>March 13, 2017</td>
</tr>
</table>
</body>
</html>
"""


@pytest.mark.unit
class TestExtractGuestsFromHtml:
    """Tests for extracting guest names from HTML."""

    def test_extracts_linked_guest_names(self):
        from extract_cth_names import extract_guests_from_html

        guests = extract_guests_from_html(SAMPLE_EPISODE_HTML)

        assert "Adam Curtis" in guests
        assert "Naomi Klein" in guests
        assert "Slavoj Zizek" in guests
        assert "Noam Chomsky" in guests

    def test_extracts_unlinked_guest_names(self):
        from extract_cth_names import extract_guests_from_html

        guests = extract_guests_from_html(SAMPLE_EPISODE_HTML)

        # Unlinked names with parenthetical descriptions
        assert "John Smith" in guests

    def test_excludes_none_guests(self):
        from extract_cth_names import extract_guests_from_html

        guests = extract_guests_from_html(SAMPLE_EPISODE_HTML)

        assert "None" not in guests

    def test_returns_set_of_unique_names(self):
        from extract_cth_names import extract_guests_from_html

        guests = extract_guests_from_html(SAMPLE_EPISODE_HTML)

        assert isinstance(guests, set)

    def test_handles_html_without_guest_column(self):
        from extract_cth_names import extract_guests_from_html

        guests = extract_guests_from_html(SAMPLE_HTML_NO_GUESTS)

        assert isinstance(guests, set)
        assert len(guests) == 0


@pytest.mark.unit
class TestGetHostNames:
    """Tests for getting host names."""

    def test_returns_known_hosts(self):
        from extract_cth_names import get_host_names

        hosts = get_host_names()

        assert "Will Menaker" in hosts
        assert "Matt Christman" in hosts
        assert "Felix Biederman" in hosts
        assert "Amber Frost" in hosts
        assert "Virgil Texas" in hosts

    def test_returns_set(self):
        from extract_cth_names import get_host_names

        hosts = get_host_names()

        assert isinstance(hosts, set)


@pytest.mark.unit
class TestBuildOutputData:
    """Tests for building output data structure."""

    def test_includes_hosts_and_guests(self):
        from extract_cth_names import build_output_data

        hosts = {"Will Menaker", "Felix Biederman"}
        guests = {"Adam Curtis", "Naomi Klein"}

        data = build_output_data(hosts, guests)

        assert "hosts" in data
        assert "guests" in data
        assert set(data["hosts"]) == hosts
        assert set(data["guests"]) == guests

    def test_includes_combined_all_names(self):
        from extract_cth_names import build_output_data

        hosts = {"Will Menaker"}
        guests = {"Adam Curtis"}

        data = build_output_data(hosts, guests)

        assert "all_names" in data
        assert "Will Menaker" in data["all_names"]
        assert "Adam Curtis" in data["all_names"]

    def test_lists_are_sorted(self):
        from extract_cth_names import build_output_data

        hosts = {"Will Menaker", "Amber Frost"}
        guests = {"Zizek", "Adam Curtis"}

        data = build_output_data(hosts, guests)

        assert data["hosts"] == sorted(hosts)
        assert data["guests"] == sorted(guests)


@pytest.mark.unit
class TestWriteOutputFiles:
    """Tests for writing output files."""

    def test_writes_json_file(self, tmp_path):
        from extract_cth_names import write_output_files

        json_path = tmp_path / "names.json"
        txt_path = tmp_path / "vocab.txt"
        data = {
            "hosts": ["Will Menaker"],
            "guests": ["Adam Curtis"],
            "all_names": ["Adam Curtis", "Will Menaker"]
        }

        write_output_files(data, str(json_path), str(txt_path))

        assert json_path.exists()
        loaded = json.loads(json_path.read_text())
        assert loaded == data

    def test_writes_vocabulary_file(self, tmp_path):
        from extract_cth_names import write_output_files

        json_path = tmp_path / "names.json"
        txt_path = tmp_path / "vocab.txt"
        data = {
            "hosts": ["Will Menaker"],
            "guests": ["Adam Curtis"],
            "all_names": ["Adam Curtis", "Will Menaker"]
        }

        write_output_files(data, str(json_path), str(txt_path))

        assert txt_path.exists()
        lines = txt_path.read_text().strip().split("\n")
        assert "Adam Curtis" in lines
        assert "Will Menaker" in lines

    def test_vocabulary_file_has_one_name_per_line(self, tmp_path):
        from extract_cth_names import write_output_files

        json_path = tmp_path / "names.json"
        txt_path = tmp_path / "vocab.txt"
        data = {
            "hosts": ["Will Menaker", "Felix Biederman"],
            "guests": ["Adam Curtis"],
            "all_names": ["Adam Curtis", "Felix Biederman", "Will Menaker"]
        }

        write_output_files(data, str(json_path), str(txt_path))

        lines = txt_path.read_text().strip().split("\n")
        assert len(lines) == 3


@pytest.mark.unit
class TestFetchWikipediaPage:
    """Tests for fetching the Wikipedia page."""

    def test_fetches_with_user_agent(self):
        from extract_cth_names import fetch_wikipedia_page

        with patch("extract_cth_names.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = "<html></html>"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            fetch_wikipedia_page()

            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args[1]
            assert "headers" in call_kwargs
            assert "User-Agent" in call_kwargs["headers"]

    def test_returns_html_content(self):
        from extract_cth_names import fetch_wikipedia_page

        with patch("extract_cth_names.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = "<html>test content</html>"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = fetch_wikipedia_page()

            assert result == "<html>test content</html>"


@pytest.mark.unit
class TestCleanGuestName:
    """Tests for cleaning guest names."""

    def test_strips_whitespace(self):
        from extract_cth_names import clean_guest_name

        assert clean_guest_name("  Adam Curtis  ") == "Adam Curtis"

    def test_removes_parenthetical_suffix(self):
        from extract_cth_names import clean_guest_name

        assert clean_guest_name("John Smith (comedian)") == "John Smith"

    def test_returns_none_for_empty_string(self):
        from extract_cth_names import clean_guest_name

        assert clean_guest_name("") is None
        assert clean_guest_name("   ") is None

    def test_returns_none_for_none_value(self):
        from extract_cth_names import clean_guest_name

        assert clean_guest_name("None") is None
        assert clean_guest_name("none") is None
        assert clean_guest_name("N/A") is None

    def test_preserves_names_with_punctuation(self):
        from extract_cth_names import clean_guest_name

        assert clean_guest_name("Slavoj Zizek") == "Slavoj Zizek"
