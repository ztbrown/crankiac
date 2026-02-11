import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.transcription.enroll import (
    compute_speaker_embedding,
    enroll_speaker,
    enroll_all_speakers,
)


def make_fake_embedding(dim=192):
    """Create a fake normalized embedding."""
    vec = np.random.randn(dim)
    return vec / np.linalg.norm(vec)


@pytest.fixture
def mock_inference():
    """Mock pyannote Model and Inference."""
    with patch("pyannote.audio.Model") as mock_model, \
         patch("pyannote.audio.Inference") as mock_inference_cls:

        fake_embedding = make_fake_embedding()
        mock_inference_instance = MagicMock()
        mock_inference_instance.return_value = fake_embedding
        mock_inference_cls.return_value = mock_inference_instance

        yield mock_inference_instance, fake_embedding


@pytest.mark.unit
def test_compute_speaker_embedding(tmp_path, mock_inference):
    """Compute embedding from reference audio clips."""
    mock_inf, expected_emb = mock_inference

    # Create fake audio files
    clip1 = tmp_path / "clip1.wav"
    clip2 = tmp_path / "clip2.wav"
    clip1.write_bytes(b"fake audio 1")
    clip2.write_bytes(b"fake audio 2")

    result = compute_speaker_embedding(
        [str(clip1), str(clip2)],
        hf_token="test-token",
    )

    assert mock_inf.call_count == 2
    assert result.shape == expected_emb.shape


@pytest.mark.unit
def test_compute_speaker_embedding_skips_missing(tmp_path, mock_inference):
    """Missing files are skipped with a warning."""
    mock_inf, _ = mock_inference

    clip1 = tmp_path / "clip1.wav"
    clip1.write_bytes(b"fake audio")

    result = compute_speaker_embedding(
        [str(clip1), "/nonexistent/clip.wav"],
        hf_token="test-token",
    )

    # Only the existing file was processed
    assert mock_inf.call_count == 1


@pytest.mark.unit
def test_compute_speaker_embedding_no_valid_files():
    """Raises when no embeddings can be extracted."""
    with patch("pyannote.audio.Model"), \
         patch("pyannote.audio.Inference"):
        with pytest.raises(ValueError, match="Could not extract any embeddings"):
            compute_speaker_embedding(
                ["/nonexistent/a.wav", "/nonexistent/b.wav"],
                hf_token="test-token",
            )


@pytest.mark.unit
def test_compute_speaker_embedding_requires_token():
    """Raises without HF token."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="HuggingFace token required"):
            compute_speaker_embedding(["/some/file.wav"])


@pytest.mark.unit
def test_enroll_speaker(tmp_path, mock_inference):
    """Enroll a single speaker and save embedding to disk."""
    mock_inf, expected_emb = mock_inference

    # Set up speaker directory with audio files
    speaker_dir = tmp_path / "reference" / "Matt"
    speaker_dir.mkdir(parents=True)
    (speaker_dir / "clip1.wav").write_bytes(b"audio1")
    (speaker_dir / "clip2.wav").write_bytes(b"audio2")

    output_dir = tmp_path / "embeddings"

    result_path = enroll_speaker(
        name="Matt",
        audio_dir=str(tmp_path / "reference"),
        output_dir=str(output_dir),
        hf_token="test-token",
    )

    assert result_path.exists()
    assert result_path.name == "Matt.npy"

    # Load and verify
    loaded = np.load(result_path)
    assert loaded.shape == expected_emb.shape


@pytest.mark.unit
def test_enroll_speaker_missing_dir():
    """Raises when speaker directory doesn't exist."""
    with pytest.raises(FileNotFoundError, match="Speaker directory not found"):
        enroll_speaker(
            name="NonexistentSpeaker",
            audio_dir="/nonexistent/audio",
        )


@pytest.mark.unit
def test_enroll_speaker_no_audio_files(tmp_path):
    """Raises when speaker directory has no audio files."""
    speaker_dir = tmp_path / "Matt"
    speaker_dir.mkdir()
    (speaker_dir / "readme.txt").write_text("not audio")

    with pytest.raises(FileNotFoundError, match="No audio files found"):
        enroll_speaker(
            name="Matt",
            audio_dir=str(tmp_path),
        )


@pytest.mark.unit
def test_enroll_speaker_creates_output_dir(tmp_path, mock_inference):
    """Output directory is created if it doesn't exist."""
    speaker_dir = tmp_path / "reference" / "Matt"
    speaker_dir.mkdir(parents=True)
    (speaker_dir / "clip.wav").write_bytes(b"audio")

    output_dir = tmp_path / "new" / "nested" / "dir"
    assert not output_dir.exists()

    enroll_speaker(
        name="Matt",
        audio_dir=str(tmp_path / "reference"),
        output_dir=str(output_dir),
        hf_token="test-token",
    )

    assert output_dir.exists()
    assert (output_dir / "Matt.npy").exists()


@pytest.mark.unit
def test_enroll_all_speakers(tmp_path, mock_inference):
    """Batch enroll all speakers in a directory."""
    # Create multiple speaker directories
    for name in ["Matt", "Will", "Felix"]:
        d = tmp_path / "reference" / name
        d.mkdir(parents=True)
        (d / "clip.wav").write_bytes(b"audio")

    output_dir = tmp_path / "embeddings"

    enrolled = enroll_all_speakers(
        audio_dir=str(tmp_path / "reference"),
        output_dir=str(output_dir),
        hf_token="test-token",
    )

    assert set(enrolled) == {"Felix", "Matt", "Will"}
    assert len(list(output_dir.glob("*.npy"))) == 3


@pytest.mark.unit
def test_enroll_all_speakers_missing_dir():
    """Raises when reference audio directory doesn't exist."""
    with pytest.raises(FileNotFoundError, match="Reference audio directory not found"):
        enroll_all_speakers(audio_dir="/nonexistent/path")


@pytest.mark.unit
def test_enroll_all_speakers_no_subdirs(tmp_path):
    """Raises when no speaker directories are found."""
    (tmp_path / "readme.txt").write_text("not a speaker dir")

    with pytest.raises(FileNotFoundError, match="No speaker directories found"):
        enroll_all_speakers(audio_dir=str(tmp_path))


@pytest.mark.unit
def test_enroll_all_speakers_partial_failure(tmp_path, mock_inference):
    """Successfully enrolled speakers are returned even if some fail."""
    mock_inf, _ = mock_inference

    # Matt has audio, Will has no audio files
    matt_dir = tmp_path / "reference" / "Matt"
    matt_dir.mkdir(parents=True)
    (matt_dir / "clip.wav").write_bytes(b"audio")

    will_dir = tmp_path / "reference" / "Will"
    will_dir.mkdir(parents=True)
    # No audio files in Will's directory

    output_dir = tmp_path / "embeddings"

    enrolled = enroll_all_speakers(
        audio_dir=str(tmp_path / "reference"),
        output_dir=str(output_dir),
        hf_token="test-token",
    )

    assert enrolled == ["Matt"]
