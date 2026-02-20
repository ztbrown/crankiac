"""Tests for QueryExpander."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.search.query_expander import ExpandedQuery, QueryExpander


def _mock_ollama_response(payload: dict):
    """Return a mock requests.Response for Ollama /api/generate."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": json.dumps(payload)}
    return mock_resp


class TestQueryExpanderExpand:
    def test_returns_expanded_query_on_success(self):
        expander = QueryExpander(known_speakers=["Matt Christman", "Chris Leyden"])
        payload = {
            "speaker": "Matt Christman",
            "keywords": ["healthcare", "policy"],
            "topic_summary": "healthcare policy discussion",
        }
        with patch("app.search.query_expander.requests.post", return_value=_mock_ollama_response(payload)):
            result = expander.expand("what did Matt say about healthcare?")

        assert isinstance(result, ExpandedQuery)
        assert result.speaker == "Matt Christman"
        assert result.keywords == ["healthcare", "policy"]
        assert result.topic_summary == "healthcare policy discussion"
        assert result.original == "what did Matt say about healthcare?"

    def test_fallback_on_connection_error(self):
        expander = QueryExpander()
        with patch("app.search.query_expander.requests.post", side_effect=ConnectionError("refused")):
            result = expander.expand("some query about housing")

        assert result.original == "some query about housing"
        assert result.speaker is None
        assert result.keywords == ["some", "query", "about", "housing"]
        assert result.topic_summary == "some query about housing"

    def test_fallback_on_bad_json(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": "not valid json {{{"}
        expander = QueryExpander()
        with patch("app.search.query_expander.requests.post", return_value=mock_resp):
            result = expander.expand("bad json query")

        assert result.original == "bad json query"
        assert result.speaker is None

    def test_fallback_on_http_error(self):
        import requests as req_lib
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_lib.exceptions.HTTPError("500")
        expander = QueryExpander()
        with patch("app.search.query_expander.requests.post", return_value=mock_resp):
            result = expander.expand("http error query")

        assert result.original == "http error query"

    def test_speaker_resolved_from_known_speakers(self):
        expander = QueryExpander(known_speakers=["Chris Leyden", "Matt Christman"])
        payload = {
            "speaker": "chris",
            "keywords": ["immigration"],
            "topic_summary": "immigration topic",
        }
        with patch("app.search.query_expander.requests.post", return_value=_mock_ollama_response(payload)):
            result = expander.expand("what did chris say about immigration")

        assert result.speaker == "Chris Leyden"

    def test_null_speaker_stays_none(self):
        expander = QueryExpander(known_speakers=["Matt Christman"])
        payload = {
            "speaker": None,
            "keywords": ["economy"],
            "topic_summary": "economy discussion",
        }
        with patch("app.search.query_expander.requests.post", return_value=_mock_ollama_response(payload)):
            result = expander.expand("talk about the economy")

        assert result.speaker is None

    def test_no_known_speakers_accepts_any_speaker(self):
        expander = QueryExpander()
        payload = {
            "speaker": "Unknown Person",
            "keywords": ["topic"],
            "topic_summary": "some topic",
        }
        with patch("app.search.query_expander.requests.post", return_value=_mock_ollama_response(payload)):
            result = expander.expand("what did unknown person say")

        assert result.speaker == "Unknown Person"

    def test_keywords_defaults_to_empty_list_when_missing(self):
        expander = QueryExpander()
        payload = {"speaker": None, "topic_summary": "summary only"}
        with patch("app.search.query_expander.requests.post", return_value=_mock_ollama_response(payload)):
            result = expander.expand("query without keywords field")

        assert result.keywords == []

    def test_keywords_coerced_to_list_when_not_list(self):
        expander = QueryExpander()
        payload = {"speaker": None, "keywords": "single string", "topic_summary": "x"}
        with patch("app.search.query_expander.requests.post", return_value=_mock_ollama_response(payload)):
            result = expander.expand("query")

        assert result.keywords == []
