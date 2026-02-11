"""Speaker enrollment utilities.

Compute and store reference embeddings from audio clips for speaker identification.
"""
import os
import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_REFERENCE_AUDIO_DIR = "data/reference_audio"
DEFAULT_EMBEDDINGS_DIR = "data/speaker_embeddings"


def compute_speaker_embedding(
    audio_paths: List[str],
    hf_token: Optional[str] = None,
) -> np.ndarray:
    """Compute mean embedding from reference audio clips.

    Args:
        audio_paths: List of paths to reference audio files.
        hf_token: HuggingFace token for pyannote model access.

    Returns:
        Mean embedding vector across all clips.
    """
    from pyannote.audio import Model, Inference

    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError(
            "HuggingFace token required. Set HF_TOKEN environment variable."
        )

    model = Model.from_pretrained("pyannote/embedding", use_auth_token=token)
    inference = Inference(model, window="whole")

    embeddings = []
    for path in audio_paths:
        if not os.path.exists(path):
            logger.warning(f"Audio file not found, skipping: {path}")
            continue
        try:
            embedding = inference(path)
            embeddings.append(embedding)
            logger.info(f"  Extracted embedding from {Path(path).name}")
        except Exception as e:
            logger.warning(f"  Failed to extract embedding from {path}: {e}")

    if not embeddings:
        raise ValueError("Could not extract any embeddings from reference audio")

    return np.mean(embeddings, axis=0)


def enroll_speaker(
    name: str,
    audio_dir: str = DEFAULT_REFERENCE_AUDIO_DIR,
    output_dir: str = DEFAULT_EMBEDDINGS_DIR,
    hf_token: Optional[str] = None,
) -> Path:
    """Enroll a single speaker from reference audio clips.

    Reads all audio files from audio_dir/name/ and saves a mean embedding
    to output_dir/name.npy.

    Args:
        name: Speaker name (must match a subdirectory in audio_dir).
        audio_dir: Root directory containing speaker subdirectories.
        output_dir: Directory to save the embedding .npy file.
        hf_token: HuggingFace token for pyannote model access.

    Returns:
        Path to the saved .npy file.
    """
    speaker_dir = Path(audio_dir) / name
    if not speaker_dir.exists():
        raise FileNotFoundError(f"Speaker directory not found: {speaker_dir}")

    # Collect audio files
    audio_extensions = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
    audio_files = sorted(
        str(f) for f in speaker_dir.iterdir()
        if f.suffix.lower() in audio_extensions
    )

    if not audio_files:
        raise FileNotFoundError(f"No audio files found in {speaker_dir}")

    logger.info(f"Enrolling speaker '{name}' from {len(audio_files)} clips...")

    embedding = compute_speaker_embedding(audio_files, hf_token=hf_token)

    # Save embedding
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    npy_path = out_path / f"{name}.npy"
    np.save(npy_path, embedding)

    logger.info(f"Saved embedding to {npy_path}")
    return npy_path


def enroll_all_speakers(
    audio_dir: str = DEFAULT_REFERENCE_AUDIO_DIR,
    output_dir: str = DEFAULT_EMBEDDINGS_DIR,
    hf_token: Optional[str] = None,
) -> List[str]:
    """Enroll all speakers with reference audio directories.

    Processes each subdirectory of audio_dir as a separate speaker.

    Args:
        audio_dir: Root directory containing speaker subdirectories.
        output_dir: Directory to save the embedding .npy files.
        hf_token: HuggingFace token for pyannote model access.

    Returns:
        List of successfully enrolled speaker names.
    """
    root = Path(audio_dir)
    if not root.exists():
        raise FileNotFoundError(f"Reference audio directory not found: {root}")

    speaker_dirs = sorted(d for d in root.iterdir() if d.is_dir())
    if not speaker_dirs:
        raise FileNotFoundError(f"No speaker directories found in {root}")

    enrolled = []
    for speaker_dir in speaker_dirs:
        name = speaker_dir.name
        try:
            enroll_speaker(name, audio_dir=audio_dir, output_dir=output_dir, hf_token=hf_token)
            enrolled.append(name)
        except Exception as e:
            logger.error(f"Failed to enroll '{name}': {e}")

    logger.info(f"Enrolled {len(enrolled)}/{len(speaker_dirs)} speakers")
    return enrolled
