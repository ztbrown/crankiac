"""Unit tests for transcript alignment algorithm."""
import pytest
from decimal import Decimal
from app.youtube.alignment import (
    normalize_text,
    extract_words,
    align_transcripts,
    AnchorPoint,
    AlignmentResult,
)


class TestNormalizeText:
    """Tests for text normalization."""

    def test_lowercase(self):
        assert normalize_text("Hello World") == "hello world"

    def test_remove_punctuation(self):
        assert normalize_text("Hello, world!") == "hello world"

    def test_preserve_apostrophes(self):
        assert normalize_text("don't") == "don't"

    def test_collapse_whitespace(self):
        assert normalize_text("hello    world") == "hello world"

    def test_strip_edges(self):
        assert normalize_text("  hello  ") == "hello"

    def test_combined(self):
        assert normalize_text("  Hello,  World!  ") == "hello world"


class TestExtractWords:
    """Tests for word extraction."""

    def test_simple(self):
        assert extract_words("hello world") == ["hello", "world"]

    def test_with_punctuation(self):
        assert extract_words("Hello, World!") == ["hello", "world"]

    def test_contractions(self):
        assert extract_words("don't stop") == ["don't", "stop"]

    def test_empty(self):
        assert extract_words("") == []


class TestAlignTranscripts:
    """Tests for the main alignment algorithm."""

    def test_empty_inputs(self):
        """Empty inputs should return empty result."""
        result = align_transcripts([], [])
        assert result.anchor_points == []
        assert result.coverage == 0.0

    def test_empty_patreon(self):
        """Empty Patreon transcript should return empty result."""
        youtube = [
            {"text": "hello world", "start_time": 0, "duration": 2}
        ]
        result = align_transcripts([], youtube)
        assert result.anchor_points == []
        assert result.patreon_word_count == 0

    def test_empty_youtube(self):
        """Empty YouTube transcript should return empty result."""
        patreon = [
            {"word": "hello", "start_time": 0, "end_time": 0.5},
            {"word": "world", "start_time": 0.5, "end_time": 1.0},
        ]
        result = align_transcripts(patreon, [])
        assert result.anchor_points == []
        assert result.youtube_word_count == 0

    def test_exact_match(self):
        """Exact matching text should produce anchors."""
        # Create a sequence long enough to match (min 5 words)
        words = ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]

        patreon = [
            {"word": w, "start_time": i * 0.5, "end_time": (i + 1) * 0.5}
            for i, w in enumerate(words)
        ]

        youtube = [
            {"text": " ".join(words), "start_time": 0, "duration": 4.5}
        ]

        result = align_transcripts(patreon, youtube)
        assert len(result.anchor_points) >= 1
        assert result.coverage > 0.5

    def test_partial_match(self):
        """Partial overlap should still produce anchors."""
        patreon = [
            {"word": "hello", "start_time": 0, "end_time": 0.5},
            {"word": "there", "start_time": 0.5, "end_time": 1.0},
            {"word": "how", "start_time": 1.0, "end_time": 1.5},
            {"word": "are", "start_time": 1.5, "end_time": 2.0},
            {"word": "you", "start_time": 2.0, "end_time": 2.5},
            {"word": "doing", "start_time": 2.5, "end_time": 3.0},
            {"word": "today", "start_time": 3.0, "end_time": 3.5},
        ]

        # YouTube has same words but different order at start
        youtube = [
            {"text": "intro music there how are you doing today", "start_time": 5, "duration": 4}
        ]

        result = align_transcripts(patreon, youtube, min_match_length=4)
        # Should find match for "there how are you doing today"
        assert len(result.anchor_points) >= 1

    def test_time_offset(self):
        """Matched anchors should reflect time offset between sources."""
        words = ["one", "two", "three", "four", "five", "six"]

        # Patreon starts at 0
        patreon = [
            {"word": w, "start_time": i * 1.0, "end_time": (i + 1) * 1.0}
            for i, w in enumerate(words)
        ]

        # YouTube starts at 10 seconds
        youtube = [
            {"text": " ".join(words), "start_time": 10, "duration": 6}
        ]

        result = align_transcripts(patreon, youtube, min_match_length=5)
        assert len(result.anchor_points) >= 1

        # First anchor should show ~10 second offset
        first = result.anchor_points[0]
        offset = first.youtube_time - first.patreon_time
        assert abs(offset - Decimal('10')) < Decimal('2')  # Allow some variance

    def test_confidence_increases_with_length(self):
        """Longer matches should have higher confidence."""
        # Short match (5 words)
        short_words = ["one", "two", "three", "four", "five"]
        short_patreon = [
            {"word": w, "start_time": i, "end_time": i + 1}
            for i, w in enumerate(short_words)
        ]
        short_youtube = [{"text": " ".join(short_words), "start_time": 0, "duration": 5}]
        short_result = align_transcripts(short_patreon, short_youtube, min_match_length=5)

        # Long match (10 words)
        long_words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        long_patreon = [
            {"word": w, "start_time": i, "end_time": i + 1}
            for i, w in enumerate(long_words)
        ]
        long_youtube = [{"text": " ".join(long_words), "start_time": 0, "duration": 10}]
        long_result = align_transcripts(long_patreon, long_youtube, min_match_length=5)

        if short_result.anchor_points and long_result.anchor_points:
            assert long_result.anchor_points[0].confidence >= short_result.anchor_points[0].confidence


class TestAlignmentResult:
    """Tests for AlignmentResult interpolation."""

    def test_interpolate_no_anchors(self):
        """Interpolation without anchors returns None."""
        result = AlignmentResult(
            anchor_points=[],
            patreon_word_count=100,
            youtube_word_count=100,
            coverage=0.0,
        )
        assert result.interpolate(Decimal('50')) is None

    def test_interpolate_single_anchor(self):
        """Single anchor applies constant offset."""
        result = AlignmentResult(
            anchor_points=[
                AnchorPoint(
                    patreon_time=Decimal('10'),
                    youtube_time=Decimal('15'),
                    confidence=1.0,
                    matched_text="test",
                )
            ],
            patreon_word_count=100,
            youtube_word_count=100,
            coverage=0.5,
        )
        # Offset is +5, should apply to any time
        assert result.interpolate(Decimal('20')) == Decimal('25')
        assert result.interpolate(Decimal('5')) == Decimal('10')

    def test_interpolate_between_anchors(self):
        """Interpolation between anchors uses linear interpolation."""
        result = AlignmentResult(
            anchor_points=[
                AnchorPoint(
                    patreon_time=Decimal('0'),
                    youtube_time=Decimal('10'),
                    confidence=1.0,
                    matched_text="start",
                ),
                AnchorPoint(
                    patreon_time=Decimal('100'),
                    youtube_time=Decimal('110'),
                    confidence=1.0,
                    matched_text="end",
                ),
            ],
            patreon_word_count=1000,
            youtube_word_count=1000,
            coverage=0.8,
        )
        # Midpoint should interpolate
        yt_time = result.interpolate(Decimal('50'))
        assert yt_time == Decimal('60')

    def test_interpolate_before_first_anchor(self):
        """Time before first anchor uses first anchor's offset."""
        result = AlignmentResult(
            anchor_points=[
                AnchorPoint(
                    patreon_time=Decimal('10'),
                    youtube_time=Decimal('20'),
                    confidence=1.0,
                    matched_text="test",
                ),
            ],
            patreon_word_count=100,
            youtube_word_count=100,
            coverage=0.5,
        )
        # Offset is +10
        assert result.interpolate(Decimal('5')) == Decimal('15')

    def test_interpolate_after_last_anchor(self):
        """Time after last anchor uses last anchor's offset."""
        result = AlignmentResult(
            anchor_points=[
                AnchorPoint(
                    patreon_time=Decimal('10'),
                    youtube_time=Decimal('20'),
                    confidence=1.0,
                    matched_text="test",
                ),
            ],
            patreon_word_count=100,
            youtube_word_count=100,
            coverage=0.5,
        )
        # Offset is +10
        assert result.interpolate(Decimal('50')) == Decimal('60')

    def test_interpolate_variable_drift(self):
        """Handles varying time drift between anchors."""
        # Simulate YouTube starting 10s later but Patreon being 10% faster
        result = AlignmentResult(
            anchor_points=[
                AnchorPoint(
                    patreon_time=Decimal('0'),
                    youtube_time=Decimal('10'),
                    confidence=1.0,
                    matched_text="start",
                ),
                AnchorPoint(
                    patreon_time=Decimal('100'),
                    youtube_time=Decimal('120'),  # 10s offset + 10% slower
                    confidence=1.0,
                    matched_text="end",
                ),
            ],
            patreon_word_count=1000,
            youtube_word_count=1000,
            coverage=0.8,
        )
        # At Patreon 50, should be at YouTube 65 (linear interp)
        yt_time = result.interpolate(Decimal('50'))
        assert yt_time == Decimal('65')


class TestAnchorPoint:
    """Tests for AnchorPoint dataclass."""

    def test_creation(self):
        anchor = AnchorPoint(
            patreon_time=Decimal('10.5'),
            youtube_time=Decimal('15.3'),
            confidence=0.9,
            matched_text="hello world",
        )
        assert anchor.patreon_time == Decimal('10.5')
        assert anchor.youtube_time == Decimal('15.3')
        assert anchor.confidence == 0.9
        assert anchor.matched_text == "hello world"
