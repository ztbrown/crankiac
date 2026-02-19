import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    """Create a test client with mocked database."""
    with patch("app.data.database.init_db"):
        from app.api.app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

@pytest.mark.unit
def test_health_endpoint(client):
    """Test health endpoint returns ok with database status."""
    with patch("app.api.routes.get_connection") as mock_conn:
        mock_ctx = MagicMock()
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json == {"status": "ok", "database": "ok"}


@pytest.mark.unit
def test_health_endpoint_db_error(client):
    """Test health endpoint returns degraded when database fails."""
    with patch("app.api.routes.get_connection") as mock_conn:
        mock_conn.return_value.__enter__ = MagicMock(side_effect=Exception("DB error"))

        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json == {"status": "degraded", "database": "error"}

@pytest.mark.unit
def test_search_empty_query(client):
    """Test search with empty query returns empty results."""
    response = client.get("/api/search?q=")
    assert response.status_code == 200
    assert response.json == {"results": [], "query": ""}

@pytest.mark.unit
def test_search_no_query_param(client):
    """Test search with no query param returns empty results."""
    response = client.get("/api/search")
    assert response.status_code == 200
    assert response.json == {"results": [], "query": ""}

@pytest.mark.unit
def test_search_with_query(client):
    """Test search with query calls search_items and returns results."""
    mock_results = [{"id": 1, "name": "Test", "description": "Test item"}]

    with patch("app.api.routes.search_items", return_value=mock_results):
        response = client.get("/api/search?q=test")
        assert response.status_code == 200
        assert response.json["query"] == "test"
        assert response.json["results"] == mock_results

@pytest.mark.unit
def test_search_response_format(client):
    """Test search response has correct format."""
    with patch("app.api.routes.search_items", return_value=[]):
        response = client.get("/api/search?q=anything")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "query" in data
        assert isinstance(data["results"], list)

@pytest.mark.unit
def test_context_endpoint_missing_params(client):
    """Test context endpoint requires episode_id and segment_index."""
    response = client.get("/api/transcripts/context")
    assert response.status_code == 400
    assert "error" in response.json

@pytest.mark.unit
def test_context_endpoint_missing_segment_index(client):
    """Test context endpoint requires segment_index."""
    response = client.get("/api/transcripts/context?episode_id=1")
    assert response.status_code == 400
    assert "error" in response.json


@pytest.mark.unit
def test_speakers_endpoint(client):
    """Test speakers endpoint returns list of speakers."""
    mock_rows = [
        {"id": 1, "name": "SPEAKER_01", "created_at": None},
        {"id": 2, "name": "SPEAKER_02", "created_at": None},
    ]

    with patch("app.transcription.storage.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/speakers")
        assert response.status_code == 200
        data = response.json
        assert "speakers" in data
        assert isinstance(data["speakers"], list)


@pytest.mark.unit
def test_search_by_speaker_missing_param(client):
    """Test search by speaker requires speaker param."""
    response = client.get("/api/transcripts/search/speaker?q=test")
    assert response.status_code == 400
    assert "error" in response.json
    assert "speaker" in response.json["error"]


@pytest.mark.unit
def test_search_by_speaker_with_params(client):
    """Test search by speaker with valid params."""
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "Test Episode",
            "patreon_id": "123",
            "published_at": None,
            "youtube_url": None,
            "is_free": True,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search/speaker?speaker=SPEAKER_01&q=test")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "speaker" in data
        assert data["speaker"] == "SPEAKER_01"


@pytest.mark.unit
def test_search_with_date_filter(client):
    """Test search with date_from and date_to filters."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Test Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": "https://youtube.com/watch?v=123",
            "is_free": True,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor, \
         patch("app.youtube.alignment.get_youtube_time", return_value=10.0):
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&date_from=2023-01-01&date_to=2023-12-31")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["date_from"] == "2023-01-01"
        assert data["filters"]["date_to"] == "2023-12-31"


@pytest.mark.unit
def test_search_with_episode_number_filter(client):
    """Test search with episode_number filter."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0042 - Test Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": None,
            "is_free": False,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&episode_number=42")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["episode_number"] == 42


@pytest.mark.unit
def test_search_with_content_type_free(client):
    """Test search with content_type=free filter."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Free Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": "https://youtube.com/watch?v=123",
            "is_free": True,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor, \
         patch("app.youtube.alignment.get_youtube_time", return_value=10.0):
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&content_type=free")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["content_type"] == "free"
        assert data["results"][0]["is_free"] is True


@pytest.mark.unit
def test_search_with_content_type_premium(client):
    """Test search with content_type=premium filter."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Premium Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": None,
            "is_free": False,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&content_type=premium")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["content_type"] == "premium"
        assert data["results"][0]["is_free"] is False


@pytest.mark.unit
def test_search_with_multiple_filters(client):
    """Test search with multiple filters combined."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0042 - Test Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": "https://youtube.com/watch?v=123",
            "is_free": True,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor, \
         patch("app.youtube.alignment.get_youtube_time", return_value=10.0):
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&date_from=2023-01-01&date_to=2023-12-31&episode_number=42&content_type=free")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert "filters" in data
        assert data["filters"]["date_from"] == "2023-01-01"
        assert data["filters"]["date_to"] == "2023-12-31"
        assert data["filters"]["episode_number"] == 42
        assert data["filters"]["content_type"] == "free"


@pytest.mark.unit
def test_search_with_invalid_content_type_defaults_to_all(client):
    """Test search with invalid content_type defaults to no filter."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Test Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": None,
            "is_free": False,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test&content_type=invalid")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        # Invalid content_type should be excluded from filters
        assert "content_type" not in data.get("filters", {})


@pytest.mark.unit
def test_search_results_include_youtube_url_and_is_free(client):
    """Test search results include youtube_url and is_free fields."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Test Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": "https://youtube.com/watch?v=abc123",
            "is_free": True,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor, \
         patch("app.youtube.alignment.get_youtube_time", return_value=10.0):
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert "youtube_url" in result
        assert result["youtube_url"] == "https://youtube.com/watch?v=abc123"
        assert "is_free" in result
        assert result["is_free"] is True


@pytest.mark.unit
def test_search_results_youtube_url_can_be_null(client):
    """Test search results handle null youtube_url correctly."""
    from datetime import datetime
    mock_rows = [
        {
            "word": "test",
            "start_time": 1.5,
            "end_time": 2.0,
            "segment_index": 10,
            "speaker": "SPEAKER_01",
            "episode_id": 1,
            "episode_title": "0001 - Premium Episode",
            "patreon_id": "123",
            "published_at": datetime(2023, 6, 15),
            "youtube_url": None,
            "is_free": False,
            "context": "this is a test context"
        }
    ]

    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.fetchone.return_value = {"total": 1}
        mock_ctx.fetchall.return_value = mock_rows

        response = client.get("/api/transcripts/search?q=test")
        assert response.status_code == 200
        data = response.json
        assert "results" in data
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert "youtube_url" in result
        assert result["youtube_url"] is None
        assert "is_free" in result
        assert result["is_free"] is False


@pytest.mark.unit
def test_list_episodes_invalid_limit_returns_400(client):
    """Test that invalid limit parameter returns 400 instead of raising ValueError."""
    response = client.get("/api/transcripts/episodes?limit=abc")
    assert response.status_code == 400
    assert response.json == {"error": "limit and offset must be integers"}


@pytest.mark.unit
def test_list_episodes_invalid_offset_returns_400(client):
    """Test that invalid offset parameter returns 400 instead of raising ValueError."""
    response = client.get("/api/transcripts/episodes?offset=xyz")
    assert response.status_code == 400
    assert response.json == {"error": "limit and offset must be integers"}


@pytest.mark.unit
def test_transcript_search_invalid_limit_returns_400(client):
    """Test that invalid limit parameter in search returns 400 instead of raising ValueError."""
    response = client.get("/api/transcripts/search?q=test&limit=abc")
    assert response.status_code == 400
    assert response.json == {"error": "limit and offset must be integers"}


@pytest.mark.unit
def test_transcript_search_invalid_offset_returns_400(client):
    """Test that invalid offset parameter in search returns 400 instead of raising ValueError."""
    response = client.get("/api/transcripts/search?q=test&offset=xyz")
    assert response.status_code == 400
    assert response.json == {"error": "limit and offset must be integers"}


@pytest.mark.unit
def test_context_invalid_radius_returns_400(client):
    """Test that invalid radius parameter returns 400 instead of raising ValueError."""
    response = client.get("/api/transcripts/context?episode_id=1&segment_index=0&radius=abc")
    assert response.status_code == 400
    assert response.json == {"error": "radius must be an integer"}


@pytest.mark.unit
def test_on_this_day_invalid_limit_returns_400(client):
    """Test that invalid limit parameter returns 400 instead of raising ValueError."""
    response = client.get("/api/transcripts/on-this-day?limit=abc")
    assert response.status_code == 400
    assert response.json == {"error": "limit must be an integer"}


@pytest.mark.unit
def test_search_by_speaker_invalid_limit_returns_400(client):
    """Test that invalid limit parameter returns 400 instead of raising ValueError."""
    response = client.get("/api/transcripts/search/speaker?speaker=test&limit=abc")
    assert response.status_code == 400
    assert response.json == {"error": "limit and offset must be integers"}


@pytest.mark.unit
def test_search_by_speaker_invalid_offset_returns_400(client):
    """Test that invalid offset parameter returns 400 instead of raising ValueError."""
    response = client.get("/api/transcripts/search/speaker?speaker=test&offset=xyz")
    assert response.status_code == 400
    assert response.json == {"error": "limit and offset must be integers"}


# Tests for map_speaker_to_name function
@pytest.mark.unit
def test_map_speaker_to_name_none_returns_none():
    """Test that None input returns None."""
    from app.api.transcript_routes import map_speaker_to_name
    assert map_speaker_to_name(None) is None


@pytest.mark.unit
def test_map_speaker_to_name_known_speaker_unchanged():
    """Test that already known speaker names are returned unchanged."""
    from app.api.transcript_routes import map_speaker_to_name
    assert map_speaker_to_name("Matt") == "Matt"
    assert map_speaker_to_name("Will") == "Will"
    assert map_speaker_to_name("Felix") == "Felix"
    assert map_speaker_to_name("Amber") == "Amber"
    assert map_speaker_to_name("Virgil") == "Virgil"


@pytest.mark.unit
def test_map_speaker_to_name_speaker_xx_mapped():
    """Test that SPEAKER_XX format is mapped to known speakers by index."""
    from app.api.transcript_routes import map_speaker_to_name
    assert map_speaker_to_name("SPEAKER_00") == "Matt"
    assert map_speaker_to_name("SPEAKER_01") == "Will"
    assert map_speaker_to_name("SPEAKER_02") == "Felix"
    assert map_speaker_to_name("SPEAKER_03") == "Amber"
    assert map_speaker_to_name("SPEAKER_04") == "Virgil"


@pytest.mark.unit
def test_map_speaker_to_name_out_of_range_unchanged():
    """Test that SPEAKER_XX with index >= len(KNOWN_SPEAKERS) returns original."""
    from app.api.transcript_routes import map_speaker_to_name
    assert map_speaker_to_name("SPEAKER_05") == "Derek Davison"
    assert map_speaker_to_name("SPEAKER_99") == "SPEAKER_99"


@pytest.mark.unit
def test_map_speaker_to_name_unknown_format_unchanged():
    """Test that unknown speaker formats are returned unchanged."""
    from app.api.transcript_routes import map_speaker_to_name
    assert map_speaker_to_name("UNKNOWN") == "UNKNOWN"
    assert map_speaker_to_name("Speaker_00") == "Speaker_00"  # Wrong case
    assert map_speaker_to_name("SPEAKER_A") == "SPEAKER_A"  # Non-numeric
    assert map_speaker_to_name("") == ""


# Tests for PATCH /api/transcripts/segments/speaker endpoint
@pytest.mark.unit
def test_update_segment_speakers_missing_updates_field(client):
    """Test that missing updates field returns 400."""
    response = client.patch("/api/transcripts/segments/speaker", json={})
    assert response.status_code == 400
    assert "error" in response.json
    assert "updates" in response.json["error"]


@pytest.mark.unit
def test_update_segment_speakers_updates_not_array(client):
    """Test that non-array updates field returns 400."""
    response = client.patch("/api/transcripts/segments/speaker", json={"updates": "not an array"})
    assert response.status_code == 400
    assert "error" in response.json
    assert "array" in response.json["error"]


@pytest.mark.unit
def test_update_segment_speakers_empty_array(client):
    """Test that empty updates array returns 400."""
    response = client.patch("/api/transcripts/segments/speaker", json={"updates": []})
    assert response.status_code == 400
    assert "error" in response.json
    assert "empty" in response.json["error"]


@pytest.mark.unit
def test_update_segment_speakers_missing_id(client):
    """Test that update without id field returns 400."""
    response = client.patch("/api/transcripts/segments/speaker", json={
        "updates": [{"speaker": "Matt"}]
    })
    assert response.status_code == 400
    assert "error" in response.json
    assert "id" in response.json["error"]


@pytest.mark.unit
def test_update_segment_speakers_missing_speaker(client):
    """Test that update without speaker field returns 400."""
    response = client.patch("/api/transcripts/segments/speaker", json={
        "updates": [{"id": 123}]
    })
    assert response.status_code == 400
    assert "error" in response.json
    assert "speaker" in response.json["error"]


@pytest.mark.unit
def test_update_segment_speakers_invalid_id_type(client):
    """Test that non-integer id returns 400."""
    response = client.patch("/api/transcripts/segments/speaker", json={
        "updates": [{"id": "not an integer", "speaker": "Matt"}]
    })
    assert response.status_code == 400
    assert "error" in response.json
    assert "id" in response.json["error"]
    assert "integer" in response.json["error"]


@pytest.mark.unit
def test_update_segment_speakers_invalid_speaker_type(client):
    """Test that non-string speaker returns 400."""
    response = client.patch("/api/transcripts/segments/speaker", json={
        "updates": [{"id": 123, "speaker": 456}]
    })
    assert response.status_code == 400
    assert "error" in response.json
    assert "speaker" in response.json["error"]
    assert "string" in response.json["error"]


@pytest.mark.unit
def test_update_segment_speakers_success(client):
    """Test successful speaker update."""
    with patch("app.transcription.storage.TranscriptStorage") as mock_storage_class:
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.update_speaker_labels.return_value = 2

        response = client.patch("/api/transcripts/segments/speaker", json={
            "updates": [
                {"id": 123, "speaker": "Matt"},
                {"id": 124, "speaker": "Trey"}
            ]
        })

        assert response.status_code == 200
        data = response.json
        assert "updated" in data
        assert data["updated"] == 2
        assert "requested" in data
        assert data["requested"] == 2

        # Verify the storage method was called
        assert mock_storage.update_speaker_labels.called
        call_args = mock_storage.update_speaker_labels.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0].id == 123
        assert call_args[0].speaker == "Matt"
        assert call_args[1].id == 124
        assert call_args[1].speaker == "Trey"


@pytest.mark.unit
def test_update_segment_speakers_partial_success(client):
    """Test that partial success returns correct counts."""
    with patch("app.transcription.storage.TranscriptStorage") as mock_storage_class:
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        # Only 1 segment was actually updated (e.g., other didn't exist)
        mock_storage.update_speaker_labels.return_value = 1

        response = client.patch("/api/transcripts/segments/speaker", json={
            "updates": [
                {"id": 123, "speaker": "Matt"},
                {"id": 999, "speaker": "Unknown"}  # Doesn't exist
            ]
        })

        assert response.status_code == 200
        data = response.json
        assert data["updated"] == 1
        assert data["requested"] == 2


@pytest.mark.unit
def test_update_segment_speakers_no_json_body(client):
    """Test that request with no JSON body returns 415."""
    response = client.patch("/api/transcripts/segments/speaker")
    # Flask returns 415 (Unsupported Media Type) for missing content-type
    assert response.status_code == 415


@pytest.mark.unit
def test_update_segment_speakers_update_not_object(client):
    """Test that non-object update item returns 400."""
    response = client.patch("/api/transcripts/segments/speaker", json={
        "updates": ["not an object"]
    })
    assert response.status_code == 400
    assert "error" in response.json
    assert "object" in response.json["error"]


# Tests for PATCH /api/transcripts/segments/<id>/word endpoint
@pytest.mark.unit
def test_update_segment_word_success(client):
    """Test successful word update."""
    with patch("app.transcription.storage.TranscriptStorage") as mock_storage_class:
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.update_word_text.return_value = True

        response = client.patch(
            "/api/transcripts/segments/123/word",
            json={"word": "corrected"}
        )
        assert response.status_code == 200
        data = response.json
        assert data["id"] == 123
        assert data["word"] == "corrected"
        assert data["updated"] is True


@pytest.mark.unit
def test_update_segment_word_missing_json_body(client):
    """Test that missing JSON body returns 415 (Unsupported Media Type)."""
    response = client.patch("/api/transcripts/segments/123/word")
    # Flask returns 415 when no content-type header or missing body
    assert response.status_code == 415


@pytest.mark.unit
def test_update_segment_word_missing_word_field(client):
    """Test that missing word field returns 400."""
    response = client.patch(
        "/api/transcripts/segments/123/word",
        json={"other": "value"}
    )
    assert response.status_code == 400
    assert "error" in response.json
    assert "word field required" in response.json["error"]


@pytest.mark.unit
def test_update_segment_word_not_string(client):
    """Test that non-string word value returns 400."""
    response = client.patch(
        "/api/transcripts/segments/123/word",
        json={"word": 123}
    )
    assert response.status_code == 400
    assert "error" in response.json
    assert "word must be a string" in response.json["error"]


@pytest.mark.unit
def test_update_segment_word_empty_string(client):
    """Test that empty string word value returns 400."""
    response = client.patch(
        "/api/transcripts/segments/123/word",
        json={"word": ""}
    )
    assert response.status_code == 400
    assert "error" in response.json
    assert "word cannot be empty" in response.json["error"]


@pytest.mark.unit
def test_update_segment_word_whitespace_only(client):
    """Test that whitespace-only word value returns 400."""
    response = client.patch(
        "/api/transcripts/segments/123/word",
        json={"word": "   "}
    )
    assert response.status_code == 400
    assert "error" in response.json
    assert "word cannot be empty" in response.json["error"]


@pytest.mark.unit
def test_update_segment_word_not_found(client):
    """Test that non-existent segment returns 404."""
    with patch("app.transcription.storage.TranscriptStorage") as mock_storage_class:
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.update_word_text.return_value = False

        response = client.patch(
            "/api/transcripts/segments/999/word",
            json={"word": "corrected"}
        )
        assert response.status_code == 404
        assert "error" in response.json
        assert "not found" in response.json["error"].lower()


# Tests for DELETE /api/transcripts/segments/<id> endpoint
@pytest.mark.unit
def test_delete_segment_success(client):
    """Test successful segment deletion."""
    with patch("app.transcription.storage.TranscriptStorage") as mock_storage_class:
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.delete_segment.return_value = True

        response = client.delete("/api/transcripts/segments/123")
        assert response.status_code == 200
        data = response.json
        assert data["id"] == 123
        assert data["deleted"] is True


@pytest.mark.unit
def test_delete_segment_not_found(client):
    """Test that deleting a non-existent segment returns 404."""
    with patch("app.transcription.storage.TranscriptStorage") as mock_storage_class:
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.delete_segment.return_value = False

        response = client.delete("/api/transcripts/segments/999")
        assert response.status_code == 404
        assert "error" in response.json
        assert "not found" in response.json["error"].lower()


# Tests for GET /api/transcripts/episode/<id>/speakers endpoint
@pytest.mark.unit
def test_get_episode_speakers_success(client):
    """Test getting speakers for a specific episode."""
    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Mock fetchone for episode check returns the episode
        mock_ctx.fetchone.return_value = {"id": 1}
        # Mock fetchall for distinct speakers
        mock_ctx.fetchall.return_value = [
            {"speaker": "Matt"},
            {"speaker": "Will"},
            {"speaker": "Felix"}
        ]

        response = client.get("/api/transcripts/episode/1/speakers")
        assert response.status_code == 200
        data = response.json

        # Check response format matches current API
        assert "known_speakers" in data
        assert "episode_speakers" in data
        assert data["episode_speakers"] == ["Matt", "Will", "Felix"]


@pytest.mark.unit
def test_get_episode_speakers_not_found(client):
    """Test getting speakers for non-existent episode returns 404."""
    with patch("app.api.transcript_routes.get_cursor") as mock_cursor:
        mock_ctx = MagicMock()
        mock_cursor.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Mock fetchone returns None (episode not found)
        mock_ctx.fetchone.return_value = None

        response = client.get("/api/transcripts/episode/999/speakers")
        assert response.status_code == 404
        assert "error" in response.json
        assert response.json["error"] == "Episode not found"
