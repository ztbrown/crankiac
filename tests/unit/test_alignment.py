"""Tests for YouTube/Patreon alignment utilities."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.youtube.alignment import (
    AnchorPoint,
    AlignmentResult,
    store_anchor_points,
)


class TestAnchorPoint:
    """Tests for AnchorPoint dataclass."""

    def test_anchor_point_required_fields(self):
        """AnchorPoint requires patreon_time and youtube_time."""
        ap = AnchorPoint(
            patreon_time=Decimal("10.5"),
            youtube_time=Decimal("12.3"),
        )
        assert ap.patreon_time == Decimal("10.5")
        assert ap.youtube_time == Decimal("12.3")
        assert ap.confidence is None
        assert ap.matched_text is None

    def test_anchor_point_all_fields(self):
        """AnchorPoint can have all optional fields."""
        ap = AnchorPoint(
            patreon_time=Decimal("100.0"),
            youtube_time=Decimal("105.5"),
            confidence=Decimal("0.95"),
            matched_text="hello world",
        )
        assert ap.confidence == Decimal("0.95")
        assert ap.matched_text == "hello world"


class TestAlignmentResult:
    """Tests for AlignmentResult dataclass."""

    def test_alignment_result_defaults(self):
        """AlignmentResult has sensible defaults."""
        result = AlignmentResult(anchor_points=[])
        assert result.anchor_points == []
        assert result.success is True
        assert result.error_message is None

    def test_alignment_result_with_error(self):
        """AlignmentResult can represent failure."""
        result = AlignmentResult(
            anchor_points=[],
            success=False,
            error_message="Audio mismatch detected",
        )
        assert result.success is False
        assert result.error_message == "Audio mismatch detected"


class TestStoreAnchorPoints:
    """Tests for store_anchor_points function."""

    @patch("app.youtube.alignment.get_cursor")
    def test_store_empty_result_returns_zero(self, mock_get_cursor):
        """Storing empty result returns 0 without database call."""
        result = AlignmentResult(anchor_points=[])
        count = store_anchor_points(episode_id=1, result=result)
        assert count == 0
        mock_get_cursor.assert_not_called()

    @patch("app.youtube.alignment.get_cursor")
    def test_store_anchor_points_deletes_existing(self, mock_get_cursor):
        """Store deletes existing anchors before inserting new ones."""
        mock_cursor = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = AlignmentResult(
            anchor_points=[
                AnchorPoint(
                    patreon_time=Decimal("10.0"),
                    youtube_time=Decimal("15.0"),
                )
            ]
        )

        count = store_anchor_points(episode_id=42, result=result)

        # Should have called execute for DELETE
        calls = mock_cursor.execute.call_args_list
        assert len(calls) == 1
        delete_call = calls[0]
        assert "DELETE FROM timestamp_anchors" in delete_call[0][0]
        assert delete_call[0][1] == (42,)

        assert count == 1

    @patch("app.youtube.alignment.get_cursor")
    def test_store_anchor_points_inserts_values(self, mock_get_cursor):
        """Store inserts all anchor points with correct values."""
        mock_cursor = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = AlignmentResult(
            anchor_points=[
                AnchorPoint(
                    patreon_time=Decimal("10.5"),
                    youtube_time=Decimal("15.2"),
                    confidence=Decimal("0.9500"),
                    matched_text="test phrase",
                ),
                AnchorPoint(
                    patreon_time=Decimal("60.0"),
                    youtube_time=Decimal("65.5"),
                ),
            ]
        )

        count = store_anchor_points(episode_id=7, result=result)

        # Should have called executemany for INSERT
        executemany_calls = mock_cursor.executemany.call_args_list
        assert len(executemany_calls) == 1
        insert_call = executemany_calls[0]
        assert "INSERT INTO timestamp_anchors" in insert_call[0][0]

        values = insert_call[0][1]
        assert len(values) == 2
        assert values[0] == (7, Decimal("10.5"), Decimal("15.2"), Decimal("0.9500"), "test phrase")
        assert values[1] == (7, Decimal("60.0"), Decimal("65.5"), None, None)

        assert count == 2

    @patch("app.youtube.alignment.get_cursor")
    def test_store_anchor_points_returns_count(self, mock_get_cursor):
        """Store returns the number of anchor points stored."""
        mock_cursor = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        anchors = [
            AnchorPoint(patreon_time=Decimal(str(i)), youtube_time=Decimal(str(i + 5)))
            for i in range(5)
        ]
        result = AlignmentResult(anchor_points=anchors)

        count = store_anchor_points(episode_id=1, result=result)
        assert count == 5
