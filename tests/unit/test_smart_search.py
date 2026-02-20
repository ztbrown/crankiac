"""Unit tests for the /api/transcripts/smart-search endpoint."""
import pytest
from unittest.mock import patch, MagicMock

from app.search.query_expander import ExpandedQuery


@pytest.fixture
def client():
    """Create a test client."""
    from app.api.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_result(episode_id=1, segment_index=0, word="hello", published_at="2024-01-01T00:00:00"):
    return {
        "word": word,
        "start_time": 1.0,
        "end_time": 1.5,
        "segment_index": segment_index,
        "speaker": "Matt",
        "episode_id": episode_id,
        "episode_title": "Episode 1",
        "patreon_id": "pat1",
        "published_at": published_at,
        "youtube_url": None,
        "youtube_start_time": None,
        "is_free": True,
        "context": "some context here",
    }


class TestSmartSearchEmptyQuery:
    def test_empty_q_returns_empty(self, client):
        resp = client.get("/api/transcripts/smart-search?q=")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["results"] == []
        assert data["total"] == 0
        assert data["expanded_query"] is None

    def test_missing_q_returns_empty(self, client):
        resp = client.get("/api/transcripts/smart-search")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["results"] == []

    def test_invalid_limit_returns_400(self, client):
        resp = client.get("/api/transcripts/smart-search?q=test&limit=abc")
        assert resp.status_code == 400
        assert "error" in resp.get_json()


class TestSmartSearchExpansion:
    def test_expanded_query_in_response(self, client):
        expanded = ExpandedQuery(
            speaker="Matt",
            keywords=["foreign", "policy"],
            topic_summary="foreign policy discussion",
            original="what does Matt say about foreign policy",
        )
        result = _make_result()

        with patch("app.api.transcript_routes._get_distinct_speakers", return_value=["Matt", "Will"]):
            with patch("app.api.transcript_routes._expand_query", return_value=expanded):
                with patch(
                    "app.api.transcript_routes.search_single_word",
                    return_value=([result], 1),
                ):
                    resp = client.get(
                        "/api/transcripts/smart-search?q=what+does+Matt+say+about+foreign+policy"
                    )

        assert resp.status_code == 200
        data = resp.get_json()
        eq = data["expanded_query"]
        assert eq["speaker"] == "Matt"
        assert eq["keywords"] == ["foreign", "policy"]
        assert eq["topic_summary"] == "foreign policy discussion"
        assert eq["original"] == "what does Matt say about foreign policy"

    def test_results_include_keyword_hits(self, client):
        expanded = ExpandedQuery(
            speaker=None,
            keywords=["climate", "change"],
            topic_summary="climate change",
            original="climate change",
        )
        # Same segment matched by both keywords
        result = _make_result(episode_id=1, segment_index=5)

        with patch("app.api.transcript_routes._get_distinct_speakers", return_value=[]):
            with patch("app.api.transcript_routes._expand_query", return_value=expanded):
                with patch(
                    "app.api.transcript_routes.search_single_word",
                    return_value=([result], 1),
                ):
                    resp = client.get("/api/transcripts/smart-search?q=climate+change")

        data = resp.get_json()
        assert data["total"] == 1
        assert data["results"][0]["keyword_hits"] == 2  # matched by both keywords

    def test_deduplication_by_episode_and_segment(self, client):
        expanded = ExpandedQuery(
            speaker=None,
            keywords=["tax", "policy"],
            topic_summary="tax policy",
            original="tax policy",
        )
        r1 = _make_result(episode_id=1, segment_index=10)
        r2 = _make_result(episode_id=1, segment_index=10)  # duplicate
        r3 = _make_result(episode_id=1, segment_index=20)  # different segment

        call_results = iter([([r1], 1), ([r2, r3], 2)])

        with patch("app.api.transcript_routes._get_distinct_speakers", return_value=[]):
            with patch("app.api.transcript_routes._expand_query", return_value=expanded):
                with patch(
                    "app.api.transcript_routes.search_single_word",
                    side_effect=lambda *a, **kw: next(call_results),
                ):
                    resp = client.get("/api/transcripts/smart-search?q=tax+policy")

        data = resp.get_json()
        # r1 and r2 are same key (ep=1, seg=10) -> 2 hits; r3 is unique -> 1 hit
        assert data["total"] == 2
        segment_indices = [r["segment_index"] for r in data["results"]]
        assert 10 in segment_indices
        assert 20 in segment_indices

    def test_ranking_by_hit_count_then_recency(self, client):
        expanded = ExpandedQuery(
            speaker=None,
            keywords=["a", "b"],
            topic_summary="test",
            original="a b",
        )
        older_result = _make_result(episode_id=1, segment_index=1, published_at="2023-01-01T00:00:00")
        newer_result = _make_result(episode_id=2, segment_index=1, published_at="2024-06-01T00:00:00")

        # older_result matched by both keywords (2 hits), newer only by first (1 hit)
        call_results = iter([
            ([older_result, newer_result], 2),
            ([older_result], 1),
        ])

        with patch("app.api.transcript_routes._get_distinct_speakers", return_value=[]):
            with patch("app.api.transcript_routes._expand_query", return_value=expanded):
                with patch(
                    "app.api.transcript_routes.search_single_word",
                    side_effect=lambda *a, **kw: next(call_results),
                ):
                    resp = client.get("/api/transcripts/smart-search?q=a+b")

        data = resp.get_json()
        assert data["total"] == 2
        # older_result has 2 hits -> first in ranking
        assert data["results"][0]["episode_id"] == 1
        assert data["results"][0]["keyword_hits"] == 2
        assert data["results"][1]["episode_id"] == 2
        assert data["results"][1]["keyword_hits"] == 1

    def test_recency_tiebreak(self, client):
        expanded = ExpandedQuery(
            speaker=None,
            keywords=["test"],
            topic_summary="test",
            original="test",
        )
        older = _make_result(episode_id=1, segment_index=1, published_at="2022-01-01T00:00:00")
        newer = _make_result(episode_id=2, segment_index=1, published_at="2024-01-01T00:00:00")

        with patch("app.api.transcript_routes._get_distinct_speakers", return_value=[]):
            with patch("app.api.transcript_routes._expand_query", return_value=expanded):
                with patch(
                    "app.api.transcript_routes.search_single_word",
                    return_value=([older, newer], 2),
                ):
                    resp = client.get("/api/transcripts/smart-search?q=test")

        data = resp.get_json()
        assert data["total"] == 2
        # Both have 1 hit; newer should come first (recency tiebreak)
        assert data["results"][0]["episode_id"] == 2
        assert data["results"][1]["episode_id"] == 1


class TestSmartSearchFallback:
    def test_fallback_on_expansion_error(self, client):
        """If QueryExpander raises, falls back to literal keyword search."""
        result = _make_result()

        with patch("app.api.transcript_routes._get_distinct_speakers", return_value=[]):
            with patch("app.api.transcript_routes._expand_query", side_effect=RuntimeError("Ollama down")):
                with patch(
                    "app.api.transcript_routes.search_single_word",
                    return_value=([result], 1),
                ):
                    resp = client.get("/api/transcripts/smart-search?q=foreign+policy")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        # Fallback expands to individual words; keywords = ["foreign", "policy"]
        eq = data["expanded_query"]
        assert eq["keywords"] == ["foreign", "policy"]
        assert eq["speaker"] is None


class TestSmartSearchFilters:
    def test_filters_forwarded_to_search(self, client):
        """EpisodeFilter parameters are passed through to search_single_word."""
        expanded = ExpandedQuery(
            speaker=None,
            keywords=["test"],
            topic_summary="test",
            original="test",
        )

        with patch("app.api.transcript_routes._get_distinct_speakers", return_value=[]):
            with patch("app.api.transcript_routes._expand_query", return_value=expanded):
                with patch(
                    "app.api.transcript_routes.search_single_word",
                    return_value=([], 0),
                ) as mock_search:
                    resp = client.get(
                        "/api/transcripts/smart-search?q=test&content_type=free&date_from=2023-01-01"
                    )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["filters"].get("content_type") == "free"
        assert data["filters"].get("date_from") == "2023-01-01"

    def test_pagination(self, client):
        expanded = ExpandedQuery(
            speaker=None,
            keywords=["test"],
            topic_summary="test",
            original="test",
        )
        results = [_make_result(segment_index=i) for i in range(5)]

        with patch("app.api.transcript_routes._get_distinct_speakers", return_value=[]):
            with patch("app.api.transcript_routes._expand_query", return_value=expanded):
                with patch(
                    "app.api.transcript_routes.search_single_word",
                    return_value=(results, 5),
                ):
                    resp = client.get("/api/transcripts/smart-search?q=test&limit=2&offset=1")

        data = resp.get_json()
        assert data["total"] == 5
        assert len(data["results"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 1
