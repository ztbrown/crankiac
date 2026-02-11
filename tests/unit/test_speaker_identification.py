import pytest
import numpy as np
from decimal import Decimal
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.transcription.speaker_identification import SpeakerIdentifier
from app.transcription.diarization import SpeakerSegment


def make_embedding(dim=192, seed=0):
    """Create a deterministic embedding vector."""
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim)
    return vec / np.linalg.norm(vec)  # Normalize


@pytest.mark.unit
def test_cosine_similarity_identical():
    """Identical vectors have similarity 1.0."""
    vec = make_embedding(seed=1)
    assert SpeakerIdentifier.cosine_similarity(vec, vec) == pytest.approx(1.0)


@pytest.mark.unit
def test_cosine_similarity_orthogonal():
    """Orthogonal vectors have similarity 0.0."""
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert SpeakerIdentifier.cosine_similarity(a, b) == pytest.approx(0.0)


@pytest.mark.unit
def test_cosine_similarity_opposite():
    """Opposite vectors have similarity -1.0."""
    vec = make_embedding(seed=1)
    assert SpeakerIdentifier.cosine_similarity(vec, -vec) == pytest.approx(-1.0)


@pytest.mark.unit
def test_cosine_similarity_zero_vector():
    """Zero vector returns 0.0 similarity."""
    vec = make_embedding(seed=1)
    zero = np.zeros_like(vec)
    assert SpeakerIdentifier.cosine_similarity(vec, zero) == 0.0


@pytest.mark.unit
def test_match_speaker_above_threshold():
    """Speaker is matched when similarity exceeds threshold."""
    identifier = SpeakerIdentifier(match_threshold=0.70)
    cluster_emb = make_embedding(seed=1)
    # Make a reference close to the cluster embedding
    ref_emb = cluster_emb + make_embedding(seed=2) * 0.1
    references = {"Matt": ref_emb}

    name, score = identifier.match_speaker(cluster_emb, references)
    assert name == "Matt"
    assert score > 0.70


@pytest.mark.unit
def test_match_speaker_below_threshold():
    """No match when similarity is below threshold."""
    identifier = SpeakerIdentifier(match_threshold=0.95)
    # Use very different embeddings
    cluster_emb = make_embedding(seed=1)
    ref_emb = make_embedding(seed=100)
    references = {"Matt": ref_emb}

    name, score = identifier.match_speaker(cluster_emb, references)
    assert name is None


@pytest.mark.unit
def test_match_speaker_empty_references():
    """No match with empty references."""
    identifier = SpeakerIdentifier()
    cluster_emb = make_embedding(seed=1)

    name, score = identifier.match_speaker(cluster_emb, {})
    assert name is None
    assert score == 0.0


@pytest.mark.unit
def test_match_speaker_best_of_multiple():
    """Returns the best matching speaker from multiple references."""
    identifier = SpeakerIdentifier(match_threshold=0.50)
    cluster_emb = make_embedding(seed=1)

    # One close reference, one far reference
    close_ref = cluster_emb + make_embedding(seed=2) * 0.05
    far_ref = make_embedding(seed=50)

    references = {"Matt": close_ref, "Will": far_ref}
    name, score = identifier.match_speaker(cluster_emb, references)
    assert name == "Matt"


@pytest.mark.unit
def test_load_reference_embeddings(tmp_path):
    """Reference embeddings are loaded from .npy files."""
    # Create some fake .npy files
    emb_matt = make_embedding(seed=1)
    emb_will = make_embedding(seed=2)
    np.save(tmp_path / "Matt.npy", emb_matt)
    np.save(tmp_path / "Will.npy", emb_will)

    identifier = SpeakerIdentifier(embeddings_dir=str(tmp_path))
    refs = identifier.load_reference_embeddings()

    assert len(refs) == 2
    assert "Matt" in refs
    assert "Will" in refs
    np.testing.assert_array_equal(refs["Matt"], emb_matt)
    np.testing.assert_array_equal(refs["Will"], emb_will)


@pytest.mark.unit
def test_load_reference_embeddings_missing_dir():
    """Missing embeddings directory returns empty dict."""
    identifier = SpeakerIdentifier(embeddings_dir="/nonexistent/path")
    refs = identifier.load_reference_embeddings()
    assert refs == {}


@pytest.mark.unit
def test_load_reference_embeddings_caching(tmp_path):
    """Reference embeddings are cached after first load."""
    np.save(tmp_path / "Matt.npy", make_embedding(seed=1))

    identifier = SpeakerIdentifier(embeddings_dir=str(tmp_path))
    refs1 = identifier.load_reference_embeddings()
    refs2 = identifier.load_reference_embeddings()
    assert refs1 is refs2  # Same object — cached


@pytest.mark.unit
def test_relabel_segments():
    """Segments are relabeled according to the label map."""
    segments = [
        SpeakerSegment(speaker="SPEAKER_00", start_time=Decimal("0.0"), end_time=Decimal("1.0")),
        SpeakerSegment(speaker="SPEAKER_01", start_time=Decimal("1.0"), end_time=Decimal("2.0")),
        SpeakerSegment(speaker="SPEAKER_00", start_time=Decimal("2.0"), end_time=Decimal("3.0")),
    ]

    identifier = SpeakerIdentifier()
    label_map = {"SPEAKER_00": "Matt", "SPEAKER_01": "Will"}
    result = identifier.relabel_segments(segments, label_map)

    assert result[0].speaker == "Matt"
    assert result[1].speaker == "Will"
    assert result[2].speaker == "Matt"


@pytest.mark.unit
def test_relabel_segments_partial_map():
    """Segments without a mapping keep their original label."""
    segments = [
        SpeakerSegment(speaker="SPEAKER_00", start_time=Decimal("0.0"), end_time=Decimal("1.0")),
        SpeakerSegment(speaker="SPEAKER_01", start_time=Decimal("1.0"), end_time=Decimal("2.0")),
    ]

    identifier = SpeakerIdentifier()
    label_map = {"SPEAKER_00": "Matt"}
    result = identifier.relabel_segments(segments, label_map)

    assert result[0].speaker == "Matt"
    assert result[1].speaker == "SPEAKER_01"


@pytest.mark.unit
def test_identify_greedy_assignment(tmp_path):
    """Greedy assignment prevents two clusters from mapping to the same speaker."""
    # Create reference embeddings
    emb_matt = make_embedding(seed=10)
    emb_will = make_embedding(seed=20)
    np.save(tmp_path / "Matt.npy", emb_matt)
    np.save(tmp_path / "Will.npy", emb_will)

    # Create segments for two speakers
    segments = [
        SpeakerSegment(speaker="SPEAKER_00", start_time=Decimal("0.0"), end_time=Decimal("5.0")),
        SpeakerSegment(speaker="SPEAKER_01", start_time=Decimal("5.0"), end_time=Decimal("10.0")),
    ]

    identifier = SpeakerIdentifier(
        embeddings_dir=str(tmp_path),
        match_threshold=0.50,
    )

    # Mock the extract_cluster_embedding to return known embeddings
    with patch.object(identifier, 'extract_cluster_embedding') as mock_extract:
        # SPEAKER_00 is closer to Matt, SPEAKER_01 is closer to Will
        mock_extract.side_effect = lambda audio, segs, label: (
            emb_matt + make_embedding(seed=99) * 0.01 if label == "SPEAKER_00"
            else emb_will + make_embedding(seed=98) * 0.01
        )

        label_map = identifier.identify("/fake/audio.mp3", segments)

    assert label_map["SPEAKER_00"] == "Matt"
    assert label_map["SPEAKER_01"] == "Will"


@pytest.mark.unit
def test_identify_unknown_speakers(tmp_path):
    """Unmatched clusters get Unknown_N labels."""
    # Only one reference
    emb_matt = make_embedding(seed=10)
    np.save(tmp_path / "Matt.npy", emb_matt)

    segments = [
        SpeakerSegment(speaker="SPEAKER_00", start_time=Decimal("0.0"), end_time=Decimal("5.0")),
        SpeakerSegment(speaker="SPEAKER_01", start_time=Decimal("5.0"), end_time=Decimal("10.0")),
        SpeakerSegment(speaker="SPEAKER_02", start_time=Decimal("10.0"), end_time=Decimal("15.0")),
    ]

    identifier = SpeakerIdentifier(
        embeddings_dir=str(tmp_path),
        match_threshold=0.90,
    )

    with patch.object(identifier, 'extract_cluster_embedding') as mock_extract:
        # Only SPEAKER_00 is close to Matt, others are far
        def fake_extract(audio, segs, label):
            if label == "SPEAKER_00":
                return emb_matt + make_embedding(seed=99) * 0.01
            return make_embedding(seed=hash(label) % 1000)
        mock_extract.side_effect = fake_extract

        label_map = identifier.identify("/fake/audio.mp3", segments)

    assert label_map["SPEAKER_00"] == "Matt"
    assert label_map["SPEAKER_01"] == "Unknown_1"
    assert label_map["SPEAKER_02"] == "Unknown_2"


@pytest.mark.unit
def test_identify_no_references(tmp_path):
    """Empty reference dir returns empty label map."""
    # Create empty embeddings dir
    (tmp_path / "embeddings").mkdir()

    segments = [
        SpeakerSegment(speaker="SPEAKER_00", start_time=Decimal("0.0"), end_time=Decimal("5.0")),
    ]

    identifier = SpeakerIdentifier(embeddings_dir=str(tmp_path / "embeddings"))
    label_map = identifier.identify("/fake/audio.mp3", segments)
    assert label_map == {}


@pytest.mark.unit
def test_identify_no_segments(tmp_path):
    """Empty segments returns empty label map."""
    np.save(tmp_path / "Matt.npy", make_embedding(seed=1))

    identifier = SpeakerIdentifier(embeddings_dir=str(tmp_path))
    label_map = identifier.identify("/fake/audio.mp3", [])
    assert label_map == {}
