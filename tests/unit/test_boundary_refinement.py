"""Tests for word-level speaker boundary refinement."""
import pytest
import numpy as np
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

from app.transcription.boundary_refinement import (
    find_boundary_words,
    refine_speaker_boundaries,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_word(start, end, speaker):
    """Create a mock word segment."""
    w = MagicMock()
    w.start_time = Decimal(str(start))
    w.end_time = Decimal(str(end))
    w.speaker = speaker
    return w


def make_embedding(dim=192, seed=0):
    """Create a deterministic normalised embedding."""
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim)
    return vec / np.linalg.norm(vec)


# ---------------------------------------------------------------------------
# find_boundary_words
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_find_boundary_words_empty():
    """Empty segment list returns empty list."""
    assert find_boundary_words([]) == []


@pytest.mark.unit
def test_find_boundary_words_single_speaker():
    """Single-speaker transcript has no transitions → no boundary words."""
    words = [
        make_word(0.0, 0.5, "Alice"),
        make_word(0.5, 1.0, "Alice"),
        make_word(1.0, 1.5, "Alice"),
    ]
    assert find_boundary_words(words) == []


@pytest.mark.unit
def test_find_boundary_words_basic_transition():
    """Words within 2s of a speaker transition are returned."""
    # Transition between word[2] (ends 3.0) and word[3] (starts 3.1)
    # Transition time ≈ 3.05.  Window: [1.05, 5.05].
    words = [
        make_word(0.0, 0.5, "Alice"),   # 0  midpoint 0.25  — outside window
        make_word(1.1, 1.6, "Alice"),   # 1  midpoint 1.35  — inside window
        make_word(2.5, 3.0, "Alice"),   # 2  midpoint 2.75  — inside window
        make_word(3.1, 3.6, "Bob"),     # 3  midpoint 3.35  — inside window
        make_word(4.5, 5.0, "Bob"),     # 4  midpoint 4.75  — inside window
        make_word(6.0, 6.5, "Bob"),     # 5  midpoint 6.25  — outside window
    ]
    result = find_boundary_words(words)
    assert 0 not in result
    assert 5 not in result
    for idx in (1, 2, 3, 4):
        assert idx in result


@pytest.mark.unit
def test_find_boundary_words_multiple_transitions():
    """Multiple transitions → boundary words from all transitions."""
    # Transition 1: between word[1] and word[2] at ~1.0
    # Transition 2: between word[3] and word[4] at ~3.0
    words = [
        make_word(0.0, 0.5, "Alice"),   # 0
        make_word(0.5, 1.0, "Alice"),   # 1
        make_word(1.0, 1.5, "Bob"),     # 2
        make_word(2.5, 3.0, "Bob"),     # 3
        make_word(3.0, 3.5, "Alice"),   # 4
        make_word(10.0, 10.5, "Alice"), # 5  far away — outside both windows
    ]
    result = find_boundary_words(words)
    # word 5 is far from both transitions
    assert 5 not in result
    # words near at least one transition should be included
    for idx in (0, 1, 2, 3, 4):
        assert idx in result


@pytest.mark.unit
def test_find_boundary_words_exactly_2s_boundary():
    """Words exactly 2s from transition are included; beyond 2s are excluded."""
    # Transition at midpoint of words[1].end (5.0) and words[2].start (5.0) → 5.0
    words = [
        make_word(2.9, 3.0, "Alice"),   # midpoint 2.95 — dist 2.05 → OUTSIDE
        make_word(3.0, 3.1, "Alice"),   # midpoint 3.05 — dist 1.95 → INSIDE
        make_word(4.9, 5.0, "Alice"),   # 2  (transition before this)
        make_word(5.0, 5.1, "Bob"),     # 3
        make_word(6.9, 7.0, "Bob"),     # midpoint 6.95 — dist 1.95 → INSIDE
        make_word(7.1, 7.2, "Bob"),     # midpoint 7.15 — dist 2.15 → OUTSIDE
    ]
    result = find_boundary_words(words)
    assert 0 not in result
    assert 1 in result
    assert 2 in result
    assert 3 in result
    assert 4 in result
    assert 5 not in result


@pytest.mark.unit
def test_find_boundary_words_returns_sorted_unique_indices():
    """Returned indices are sorted and deduplicated."""
    words = [
        make_word(0.0, 0.5, "Alice"),
        make_word(0.5, 1.0, "Bob"),
        make_word(1.0, 1.5, "Alice"),
    ]
    result = find_boundary_words(words)
    assert result == sorted(set(result))


@pytest.mark.unit
def test_find_boundary_words_unassigned_speaker_ignored():
    """Words with None speaker are treated as a transition boundary."""
    words = [
        make_word(0.0, 0.5, "Alice"),
        make_word(0.5, 1.0, None),      # unassigned — different from Alice
        make_word(1.0, 1.5, "Bob"),
    ]
    # Both transitions (Alice→None and None→Bob) exist; all words are near them
    result = find_boundary_words(words)
    assert 0 in result
    assert 1 in result
    assert 2 in result


# ---------------------------------------------------------------------------
# refine_speaker_boundaries
# ---------------------------------------------------------------------------

def _make_identifier_with_references(references: dict):
    """Return a mock SpeakerIdentifier loaded with given reference embeddings."""
    identifier = MagicMock()
    identifier.load_reference_embeddings.return_value = references
    identifier.cosine_similarity.side_effect = (
        lambda a, b: float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    )
    return identifier


@pytest.mark.unit
def test_refine_speaker_boundaries_empty_words():
    """Empty word list returns empty list unchanged."""
    identifier = _make_identifier_with_references({})
    result = refine_speaker_boundaries([], [], "audio.wav", identifier, {}, {})
    assert result == []


@pytest.mark.unit
def test_refine_speaker_boundaries_no_boundary_words():
    """Single-speaker transcript — no boundary words, nothing changes."""
    alice_emb = make_embedding(seed=1)
    identifier = _make_identifier_with_references({"Alice": alice_emb})
    identifier.model = MagicMock()  # should NOT be called

    words = [make_word(t, t + 0.5, "Alice") for t in range(5)]
    result = refine_speaker_boundaries(
        words, [], "audio.wav", identifier, {}, {}
    )
    # No embedding extractions
    identifier.model.crop.assert_not_called()
    for w in result:
        assert w.speaker == "Alice"


@pytest.mark.unit
def test_refine_speaker_boundaries_keeps_correct_assignment():
    """If current speaker has highest cosine similarity, no reassignment."""
    alice_emb = make_embedding(seed=1)
    bob_emb = make_embedding(seed=99)   # very different

    # word[0] Alice-like embedding → stays Alice
    alice_word_emb = alice_emb + make_embedding(seed=2) * 0.05
    alice_word_emb /= np.linalg.norm(alice_word_emb)
    # word[1] Bob-like embedding → stays Bob
    bob_word_emb = bob_emb + make_embedding(seed=3) * 0.05
    bob_word_emb /= np.linalg.norm(bob_word_emb)

    identifier = _make_identifier_with_references({"Alice": alice_emb, "Bob": bob_emb})
    mock_model = MagicMock()
    mock_model.crop.side_effect = [alice_word_emb, bob_word_emb]
    identifier.model = mock_model

    words = [
        make_word(0.0, 0.5, "Alice"),
        make_word(0.5, 1.0, "Bob"),
    ]
    result = refine_speaker_boundaries(
        words, [], "audio.wav", identifier,
        {"Alice": "Alice", "Bob": "Bob"},
        {"Alice": 0.9, "Bob": 0.8},
    )
    assert result[0].speaker == "Alice"
    assert result[1].speaker == "Bob"


@pytest.mark.unit
def test_refine_speaker_boundaries_reassigns_word():
    """If adjacent speaker has cosine similarity >= current + 0.05, reassign."""
    alice_emb = make_embedding(seed=1)
    bob_emb = make_embedding(seed=2)

    # The boundary word sounds clearly like Bob (close to bob_emb)
    word_emb = bob_emb + make_embedding(seed=42) * 0.02
    word_emb /= np.linalg.norm(word_emb)

    identifier = _make_identifier_with_references({"Alice": alice_emb, "Bob": bob_emb})
    mock_model = MagicMock()
    mock_model.crop.return_value = word_emb
    identifier.model = mock_model

    # word[0] assigned to Alice, but it's actually Bob's voice
    # word[1] is Bob — provides the adjacent speaker context
    words = [
        make_word(0.0, 0.5, "Alice"),
        make_word(0.5, 1.0, "Bob"),
    ]
    result = refine_speaker_boundaries(
        words, [], "audio.wav", identifier,
        {"Alice": "Alice", "Bob": "Bob"},
        {"Alice": 0.9, "Bob": 0.9},
    )
    # word[0] should be reassigned to Bob
    assert result[0].speaker == "Bob"
    # word[1] should stay as Bob
    assert result[1].speaker == "Bob"


@pytest.mark.unit
def test_refine_speaker_boundaries_below_margin_no_change():
    """If improvement is less than 0.05 margin, do NOT reassign."""
    alice_emb = make_embedding(seed=1)
    # Bob is only slightly better — less than 0.05 improvement
    word_emb = alice_emb.copy()  # identical to Alice → Alice wins

    identifier = _make_identifier_with_references({"Alice": alice_emb, "Bob": make_embedding(seed=2)})
    mock_model = MagicMock()
    mock_model.crop.return_value = word_emb
    identifier.model = mock_model

    words = [
        make_word(0.0, 0.5, "Alice"),
        make_word(0.5, 1.0, "Bob"),
    ]
    result = refine_speaker_boundaries(
        words, [], "audio.wav", identifier,
        {"Alice": "Alice", "Bob": "Bob"},
        {},
    )
    assert result[0].speaker == "Alice"


@pytest.mark.unit
def test_refine_speaker_boundaries_no_references_no_change():
    """If no reference embeddings, words are unchanged."""
    identifier = _make_identifier_with_references({})
    identifier.model = MagicMock()

    words = [
        make_word(0.0, 0.5, "Alice"),
        make_word(0.5, 1.0, "Bob"),
    ]
    result = refine_speaker_boundaries(
        words, [], "audio.wav", identifier, {}, {}
    )
    identifier.model.crop.assert_not_called()
    assert result[0].speaker == "Alice"
    assert result[1].speaker == "Bob"


@pytest.mark.unit
def test_refine_speaker_boundaries_skips_short_words():
    """Words shorter than 0.1s are skipped (not enough audio for embedding)."""
    alice_emb = make_embedding(seed=1)
    bob_emb = make_embedding(seed=2)
    identifier = _make_identifier_with_references({"Alice": alice_emb, "Bob": bob_emb})
    mock_model = MagicMock()
    # word[1] (Bob) gets processed normally — return a Bob-like embedding
    bob_word_emb = bob_emb.copy()
    mock_model.crop.return_value = bob_word_emb
    identifier.model = mock_model

    words = [
        make_word(0.0, 0.05, "Alice"),  # 50ms — too short, skip
        make_word(0.5, 1.0, "Bob"),
    ]
    result = refine_speaker_boundaries(
        words, [], "audio.wav", identifier,
        {"Alice": "Alice", "Bob": "Bob"},
        {},
    )
    # Only word[1] (Bob) should have had its embedding extracted, not word[0]
    # (crop should be called once for Bob, not twice)
    assert mock_model.crop.call_count == 1
    # Short word retains original speaker
    assert result[0].speaker == "Alice"
    # Bob stays Bob (his embedding is Bob-like)
    assert result[1].speaker == "Bob"


@pytest.mark.unit
def test_refine_speaker_boundaries_embedding_failure_graceful():
    """If embedding extraction raises, the word keeps its original speaker."""
    alice_emb = make_embedding(seed=1)
    bob_emb = make_embedding(seed=2)
    identifier = _make_identifier_with_references({"Alice": alice_emb, "Bob": bob_emb})
    mock_model = MagicMock()
    mock_model.crop.side_effect = RuntimeError("model error")
    identifier.model = mock_model

    words = [
        make_word(0.0, 0.5, "Alice"),
        make_word(0.5, 1.0, "Bob"),
    ]
    result = refine_speaker_boundaries(
        words, [], "audio.wav", identifier,
        {"Alice": "Alice", "Bob": "Bob"},
        {},
    )
    # Original speakers preserved despite error
    assert result[0].speaker == "Alice"
    assert result[1].speaker == "Bob"


@pytest.mark.unit
def test_refine_speaker_boundaries_only_checks_adjacent_speakers():
    """Only current and adjacent speakers are checked — not all speakers."""
    # Three speakers; boundary word is Alice/Bob.
    # Carol is a third speaker far away — her reference should NOT be used
    # to reassign the boundary word.
    alice_emb = make_embedding(seed=1)
    bob_emb = make_embedding(seed=2)
    carol_emb = make_embedding(seed=3)

    # word_emb is somewhat close to Carol, but Carol is not adjacent
    word_emb = carol_emb + make_embedding(seed=99) * 0.01
    word_emb /= np.linalg.norm(word_emb)

    identifier = _make_identifier_with_references(
        {"Alice": alice_emb, "Bob": bob_emb, "Carol": carol_emb}
    )
    mock_model = MagicMock()
    mock_model.crop.return_value = word_emb
    identifier.model = mock_model

    # Transcript: Alice, Alice, Bob — Carol never appears adjacent to Alice/Bob boundary
    words = [
        make_word(0.0, 0.5, "Alice"),
        make_word(0.5, 1.0, "Alice"),   # boundary word (near transition at ~1.0)
        make_word(1.0, 1.5, "Bob"),
        make_word(10.0, 10.5, "Carol"), # far away, not adjacent to boundary
    ]
    result = refine_speaker_boundaries(
        words, [], "audio.wav", identifier,
        {"Alice": "Alice", "Bob": "Bob", "Carol": "Carol"},
        {},
    )
    # Carol is not adjacent → word should NOT be reassigned to Carol
    assert result[1].speaker in ("Alice", "Bob")
