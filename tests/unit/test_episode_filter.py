"""Tests for the EpisodeFilter module."""

import pytest
from app.filters.episode_filter import EpisodeFilter


@pytest.mark.unit
class TestEpisodeFilterBuilder:
    """Test the builder pattern methods."""

    def test_empty_filter_builds_empty_conditions(self):
        """Test that empty filter produces no conditions."""
        filter = EpisodeFilter()
        sql, params = filter.build()
        assert sql == ""
        assert params == []

    def test_with_date_from(self):
        """Test date_from filter builds correct condition."""
        filter = EpisodeFilter().with_date_from("2023-01-01")
        sql, params = filter.build()
        assert sql == "e.published_at >= %s"
        assert params == ["2023-01-01"]

    def test_with_date_to(self):
        """Test date_to filter appends end-of-day time."""
        filter = EpisodeFilter().with_date_to("2023-12-31")
        sql, params = filter.build()
        assert sql == "e.published_at <= %s"
        assert params == ["2023-12-31 23:59:59"]

    def test_with_date_range(self):
        """Test date range sets both dates."""
        filter = EpisodeFilter().with_date_range("2023-01-01", "2023-12-31")
        sql, params = filter.build()
        assert "e.published_at >= %s" in sql
        assert "e.published_at <= %s" in sql
        assert params == ["2023-01-01", "2023-12-31 23:59:59"]

    def test_with_episode_number(self):
        """Test episode_number filter builds regex pattern."""
        filter = EpisodeFilter().with_episode_number(42)
        sql, params = filter.build()
        assert sql == "e.title ~ %s"
        assert params == ["^0*42 - "]

    def test_with_episode_number_zero(self):
        """Test episode_number filter handles zero."""
        filter = EpisodeFilter().with_episode_number(0)
        sql, params = filter.build()
        assert sql == "e.title ~ %s"
        assert params == ["^0*0 - "]

    def test_with_content_type_free(self):
        """Test content_type=free builds correct condition."""
        filter = EpisodeFilter().with_content_type("free")
        sql, params = filter.build()
        assert sql == "e.is_free = true"
        assert params == []

    def test_with_content_type_premium(self):
        """Test content_type=premium builds correct condition."""
        filter = EpisodeFilter().with_content_type("premium")
        sql, params = filter.build()
        assert sql == "e.is_free = false"
        assert params == []

    def test_with_content_type_all_ignored(self):
        """Test content_type=all produces no condition."""
        filter = EpisodeFilter().with_content_type("all")
        sql, params = filter.build()
        assert sql == ""
        assert params == []

    def test_with_content_type_invalid_ignored(self):
        """Test invalid content_type produces no condition."""
        filter = EpisodeFilter().with_content_type("invalid")
        sql, params = filter.build()
        assert sql == ""
        assert params == []

    def test_chained_builder_methods(self):
        """Test fluent builder pattern with chained methods."""
        filter = (
            EpisodeFilter()
            .with_date_from("2023-01-01")
            .with_date_to("2023-12-31")
            .with_episode_number(100)
            .with_content_type("free")
        )
        sql, params = filter.build()
        assert "e.published_at >= %s" in sql
        assert "e.published_at <= %s" in sql
        assert "e.title ~ %s" in sql
        assert "e.is_free = true" in sql
        assert params == ["2023-01-01", "2023-12-31 23:59:59", "^0*100 - "]


@pytest.mark.unit
class TestEpisodeFilterFromDict:
    """Test the from_dict factory method."""

    def test_from_dict_empty(self):
        """Test from_dict with empty dictionary."""
        filter = EpisodeFilter.from_dict({})
        assert filter.is_empty()

    def test_from_dict_all_fields(self):
        """Test from_dict with all fields populated."""
        filters = {
            "date_from": "2023-01-01",
            "date_to": "2023-12-31",
            "episode_number": 42,
            "content_type": "free",
        }
        filter = EpisodeFilter.from_dict(filters)
        assert filter.date_from == "2023-01-01"
        assert filter.date_to == "2023-12-31"
        assert filter.episode_number == 42
        assert filter.content_type == "free"

    def test_from_dict_partial_fields(self):
        """Test from_dict with only some fields."""
        filters = {"date_from": "2023-06-01", "content_type": "premium"}
        filter = EpisodeFilter.from_dict(filters)
        assert filter.date_from == "2023-06-01"
        assert filter.date_to is None
        assert filter.episode_number is None
        assert filter.content_type == "premium"

    def test_from_dict_none_values(self):
        """Test from_dict handles None values correctly."""
        filters = {"date_from": None, "content_type": None}
        filter = EpisodeFilter.from_dict(filters)
        assert filter.date_from is None
        assert filter.content_type is None


@pytest.mark.unit
class TestEpisodeFilterBuildClause:
    """Test the build_clause method."""

    def test_build_clause_empty(self):
        """Test build_clause with no filters returns empty string."""
        filter = EpisodeFilter()
        clause, params = filter.build_clause()
        assert clause == ""
        assert params == []

    def test_build_clause_with_filters(self):
        """Test build_clause prepends AND."""
        filter = EpisodeFilter().with_content_type("free")
        clause, params = filter.build_clause()
        assert clause == " AND e.is_free = true"
        assert params == []

    def test_build_clause_multiple_filters(self):
        """Test build_clause with multiple conditions."""
        filter = EpisodeFilter().with_date_from("2023-01-01").with_content_type("free")
        clause, params = filter.build_clause()
        assert clause.startswith(" AND ")
        assert "e.published_at >= %s" in clause
        assert "e.is_free = true" in clause


@pytest.mark.unit
class TestEpisodeFilterToDict:
    """Test the to_dict method."""

    def test_to_dict_empty(self):
        """Test to_dict with no filters returns empty dict."""
        filter = EpisodeFilter()
        assert filter.to_dict() == {}

    def test_to_dict_excludes_none_values(self):
        """Test to_dict only includes non-None values."""
        filter = EpisodeFilter().with_date_from("2023-01-01")
        result = filter.to_dict()
        assert result == {"date_from": "2023-01-01"}
        assert "date_to" not in result
        assert "episode_number" not in result

    def test_to_dict_all_filters(self):
        """Test to_dict with all filters set."""
        filter = (
            EpisodeFilter()
            .with_date_from("2023-01-01")
            .with_date_to("2023-12-31")
            .with_episode_number(42)
            .with_content_type("free")
        )
        result = filter.to_dict()
        assert result == {
            "date_from": "2023-01-01",
            "date_to": "2023-12-31",
            "episode_number": 42,
            "content_type": "free",
        }

    def test_to_dict_episode_number_zero(self):
        """Test to_dict includes episode_number even when zero."""
        filter = EpisodeFilter().with_episode_number(0)
        result = filter.to_dict()
        assert result == {"episode_number": 0}


@pytest.mark.unit
class TestEpisodeFilterIsEmpty:
    """Test the is_empty method."""

    def test_is_empty_true_for_new_filter(self):
        """Test new filter is empty."""
        filter = EpisodeFilter()
        assert filter.is_empty()

    def test_is_empty_false_with_date_from(self):
        """Test filter with date_from is not empty."""
        filter = EpisodeFilter().with_date_from("2023-01-01")
        assert not filter.is_empty()

    def test_is_empty_false_with_episode_number_zero(self):
        """Test filter with episode_number=0 is not empty."""
        filter = EpisodeFilter().with_episode_number(0)
        assert not filter.is_empty()

    def test_is_empty_false_with_content_type(self):
        """Test filter with content_type is not empty."""
        filter = EpisodeFilter().with_content_type("free")
        assert not filter.is_empty()


@pytest.mark.unit
class TestEpisodeFilterSQLGeneration:
    """Test SQL generation for edge cases."""

    def test_conditions_joined_with_and(self):
        """Test multiple conditions are joined with AND."""
        filter = (
            EpisodeFilter()
            .with_date_from("2023-01-01")
            .with_date_to("2023-12-31")
        )
        sql, params = filter.build()
        assert " AND " in sql
        parts = sql.split(" AND ")
        assert len(parts) == 2

    def test_parameter_order_matches_conditions(self):
        """Test parameters are in same order as conditions."""
        filter = (
            EpisodeFilter()
            .with_date_from("2023-01-01")
            .with_date_to("2023-12-31")
            .with_episode_number(42)
        )
        sql, params = filter.build()
        # Parameters should be: date_from, date_to (with time), episode pattern
        assert params[0] == "2023-01-01"
        assert params[1] == "2023-12-31 23:59:59"
        assert params[2] == "^0*42 - "

    def test_episode_number_regex_handles_leading_zeros(self):
        """Test episode regex matches with or without leading zeros."""
        filter = EpisodeFilter().with_episode_number(1)
        sql, params = filter.build()
        # Pattern should match "1 - ", "01 - ", "001 - ", "0001 - ", etc.
        assert params[0] == "^0*1 - "

    def test_content_type_no_parameter_needed(self):
        """Test content_type conditions don't add parameters."""
        filter_free = EpisodeFilter().with_content_type("free")
        _, params_free = filter_free.build()
        assert params_free == []

        filter_premium = EpisodeFilter().with_content_type("premium")
        _, params_premium = filter_premium.build()
        assert params_premium == []
