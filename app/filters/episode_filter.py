"""
Episode filter module for building SQL filter conditions.

Provides a fluent builder pattern for constructing episode filters
that can be applied to transcript search queries.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EpisodeFilter:
    """
    Builder class for constructing episode filter SQL conditions.

    Supports filtering by:
    - Date range (date_from, date_to)
    - Episode number (parsed from title format "NNNN - Title")
    - Content type (free, premium, or all)

    Example usage:
        filter = EpisodeFilter()
        filter.with_date_from("2023-01-01")
        filter.with_content_type("free")
        sql, params = filter.build()
    """

    date_from: Optional[str] = None
    date_to: Optional[str] = None
    episode_number: Optional[int] = None
    content_type: Optional[str] = None

    _conditions: list = field(default_factory=list, repr=False)
    _params: list = field(default_factory=list, repr=False)

    @classmethod
    def from_dict(cls, filters: dict) -> "EpisodeFilter":
        """
        Create an EpisodeFilter from a dictionary of filter values.

        Args:
            filters: Dictionary with keys: date_from, date_to,
                     episode_number, content_type

        Returns:
            Configured EpisodeFilter instance.
        """
        return cls(
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
            episode_number=filters.get("episode_number"),
            content_type=filters.get("content_type"),
        )

    def with_date_from(self, date_from: Optional[str]) -> "EpisodeFilter":
        """Set the start date filter (ISO format: YYYY-MM-DD)."""
        self.date_from = date_from
        return self

    def with_date_to(self, date_to: Optional[str]) -> "EpisodeFilter":
        """Set the end date filter (ISO format: YYYY-MM-DD)."""
        self.date_to = date_to
        return self

    def with_date_range(
        self, date_from: Optional[str], date_to: Optional[str]
    ) -> "EpisodeFilter":
        """Set both start and end date filters."""
        self.date_from = date_from
        self.date_to = date_to
        return self

    def with_episode_number(self, episode_number: Optional[int]) -> "EpisodeFilter":
        """Set the episode number filter."""
        self.episode_number = episode_number
        return self

    def with_content_type(self, content_type: Optional[str]) -> "EpisodeFilter":
        """
        Set the content type filter.

        Args:
            content_type: One of "free", "premium", or None for all.
        """
        if content_type in ("free", "premium"):
            self.content_type = content_type
        else:
            self.content_type = None
        return self

    def build(self) -> tuple[str, list]:
        """
        Build SQL WHERE conditions and parameters from configured filters.

        Returns:
            Tuple of (sql_conditions, params) where sql_conditions is a string
            suitable for appending to a WHERE clause (without leading AND),
            and params is a list of parameter values.

        Example:
            filter = EpisodeFilter().with_date_from("2023-01-01")
            sql, params = filter.build()
            # sql = "e.published_at >= %s"
            # params = ["2023-01-01"]
        """
        conditions = []
        params = []

        if self.date_from:
            conditions.append("e.published_at >= %s")
            params.append(self.date_from)

        if self.date_to:
            conditions.append("e.published_at <= %s")
            params.append(self.date_to + " 23:59:59")

        if self.episode_number is not None:
            # Episode titles have format "NNNN - Title", extract and match the number
            conditions.append("e.title ~ %s")
            params.append(f"^0*{self.episode_number} - ")

        if self.content_type == "free":
            conditions.append("e.is_free = true")
        elif self.content_type == "premium":
            conditions.append("e.is_free = false")

        return " AND ".join(conditions), params

    def build_clause(self) -> tuple[str, list]:
        """
        Build SQL clause with leading AND if conditions exist.

        Returns:
            Tuple of (sql_clause, params) where sql_clause includes
            " AND " prefix if there are conditions, empty string otherwise.

        Example:
            filter = EpisodeFilter().with_content_type("free")
            clause, params = filter.build_clause()
            # clause = " AND e.is_free = true"
            # params = []
        """
        conditions, params = self.build()
        if conditions:
            return f" AND {conditions}", params
        return "", params

    def to_dict(self) -> dict:
        """
        Convert active filters to a dictionary for API response.

        Returns only filters that have non-None values.
        """
        result = {}
        if self.date_from:
            result["date_from"] = self.date_from
        if self.date_to:
            result["date_to"] = self.date_to
        if self.episode_number is not None:
            result["episode_number"] = self.episode_number
        if self.content_type:
            result["content_type"] = self.content_type
        return result

    def is_empty(self) -> bool:
        """Check if no filters are configured."""
        return not any([
            self.date_from,
            self.date_to,
            self.episode_number is not None,
            self.content_type,
        ])
