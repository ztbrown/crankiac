"""Ollama-powered query expansion for natural language search."""
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")


@dataclass
class ExpandedQuery:
    speaker: Optional[str]
    keywords: list[str]
    topic_summary: str
    original: str


class QueryExpander:
    """Decomposes natural language queries into structured search filters using Ollama."""

    def __init__(self, known_speakers: Optional[list[str]] = None):
        self.known_speakers = known_speakers or []
        self.ollama_url = OLLAMA_URL
        self.model = OLLAMA_MODEL
        self.last_prompt: Optional[str] = None
        self.last_raw_response: Optional[str] = None

    def expand(self, query: str) -> ExpandedQuery:
        """Expand a natural language query into structured filters.

        Falls back to original query if Ollama is unreachable or returns bad JSON.
        """
        try:
            expanded = self._call_ollama(query)
            if expanded is not None:
                return expanded
        except Exception as exc:
            logger.warning("QueryExpander fallback for %r: %s", query, exc)

        return self._fallback(query)

    def _call_ollama(self, query: str) -> Optional[ExpandedQuery]:
        speakers_hint = (
            f"Known speakers: {', '.join(self.known_speakers)}. "
            if self.known_speakers
            else ""
        )
        prompt = (
            f"You are a search query analyzer. Given a natural language search query, "
            f"extract structured search filters as JSON.\n\n"
            f"{speakers_hint}"
            f"Query: {query}\n\n"
            f"Respond with a JSON object with these fields:\n"
            f"  speaker: string or null — the speaker name if mentioned (match to known speakers if possible)\n"
            f"  keywords: array of strings — key search terms\n"
            f"  topic_summary: string — brief summary of what is being searched\n\n"
            f"Return only valid JSON, nothing else."
        )

        self.last_prompt = prompt

        response = requests.post(
            f"{self.ollama_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "format": "json", "stream": False},
            timeout=15,
        )
        response.raise_for_status()

        data = response.json()
        raw = data.get("response", "")
        self.last_raw_response = raw
        parsed = json.loads(raw)

        speaker = parsed.get("speaker") or None
        if speaker and self.known_speakers:
            speaker = self._resolve_speaker(speaker)

        keywords = parsed.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []

        topic_summary = parsed.get("topic_summary", "") or ""

        return ExpandedQuery(
            speaker=speaker,
            keywords=keywords,
            topic_summary=topic_summary,
            original=query,
        )

    def _resolve_speaker(self, name: str) -> Optional[str]:
        """Match extracted speaker name to known speakers list (case-insensitive)."""
        name_lower = name.lower()
        for known in self.known_speakers:
            if known.lower() == name_lower or name_lower in known.lower():
                return known
        return name

    def _fallback(self, query: str) -> ExpandedQuery:
        return ExpandedQuery(
            speaker=None,
            keywords=query.split(),
            topic_summary=query,
            original=query,
        )
