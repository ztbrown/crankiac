"""Speaker identification via voice embeddings.

Maps diarization labels (SPEAKER_00, SPEAKER_01, ...) to real speaker names
by comparing cluster embeddings against enrolled reference embeddings.
"""
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MATCH_THRESHOLD = 0.70
DEFAULT_NOISE_FLOOR = 0.30
DEFAULT_EMBEDDINGS_DIR = "data/speaker_embeddings"


class SpeakerIdentifier:
    """Identifies speakers by matching voice embeddings against references."""

    def __init__(
        self,
        embeddings_dir: str = DEFAULT_EMBEDDINGS_DIR,
        match_threshold: float = DEFAULT_MATCH_THRESHOLD,
        hf_token: Optional[str] = None,
    ):
        self.embeddings_dir = Path(embeddings_dir)
        self.match_threshold = match_threshold
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        self._model = None
        self._references: Optional[Dict[str, np.ndarray]] = None

    @property
    def model(self):
        """Lazy load the pyannote embedding model."""
        if self._model is None:
            # PyTorch 2.6+ changed weights_only default to True, which breaks
            # pyannote model loading. Patch to use weights_only=False.
            import torch
            import lightning_fabric.utilities.cloud_io as cloud_io
            original_load = cloud_io._load
            def patched_load(path_or_url, map_location=None, **kwargs):
                return torch.load(path_or_url, map_location=map_location, weights_only=False)
            cloud_io._load = patched_load

            from pyannote.audio import Model, Inference

            if not self.hf_token:
                raise ValueError(
                    "HuggingFace token required for pyannote embedding model. "
                    "Set HF_TOKEN environment variable."
                )

            try:
                model = Model.from_pretrained(
                    "pyannote/embedding",
                    token=self.hf_token,
                )
            except TypeError:
                model = Model.from_pretrained(
                    "pyannote/embedding",
                    use_auth_token=self.hf_token,
                )
            self._model = Inference(model, window="whole")
            logger.info("Loaded pyannote embedding model")
        return self._model

    def load_reference_embeddings(self) -> Dict[str, np.ndarray]:
        """Load pre-computed reference embeddings from disk.

        Returns:
            Dict mapping speaker name to embedding numpy array.
        """
        if self._references is not None:
            return self._references

        self._references = {}

        if not self.embeddings_dir.exists():
            logger.warning(f"Embeddings directory not found: {self.embeddings_dir}")
            return self._references

        for npy_file in self.embeddings_dir.glob("*.npy"):
            speaker_name = npy_file.stem
            embedding = np.load(npy_file)
            self._references[speaker_name] = embedding
            logger.debug(f"Loaded reference embedding for {speaker_name}")

        logger.info(f"Loaded {len(self._references)} reference embeddings")
        return self._references

    def _load_audio(self, audio_path: str) -> dict:
        """Load audio as waveform dict to avoid torchcodec issues on Windows."""
        try:
            import torchaudio
            waveform, sample_rate = torchaudio.load(audio_path)
            return {"waveform": waveform, "sample_rate": sample_rate}
        except Exception:
            return {"audio": audio_path}

    def extract_cluster_embedding(
        self,
        audio_input,
        segments: list,
        speaker_label: str,
    ) -> np.ndarray:
        """Extract mean embedding for a speaker cluster.

        Collects all segments belonging to a speaker label, extracts embeddings
        for each segment, and returns the mean embedding.

        Args:
            audio_input: Pre-loaded audio dict or path to audio file.
            segments: List of SpeakerSegment objects from diarization.
            speaker_label: The diarization label (e.g., "SPEAKER_00").

        Returns:
            Mean embedding vector for the speaker cluster.
        """
        from pyannote.core import Segment

        # Filter segments for this speaker
        speaker_segs = [s for s in segments if s.speaker == speaker_label]
        if not speaker_segs:
            raise ValueError(f"No segments found for speaker {speaker_label}")

        embeddings = []
        for seg in speaker_segs:
            start = float(seg.start_time)
            end = float(seg.end_time)
            duration = end - start

            # Skip very short segments (< 0.5s) — not enough audio for embedding
            if duration < 0.5:
                continue

            # Cap at 30s to avoid memory issues
            if duration > 30.0:
                end = start + 30.0

            try:
                segment = Segment(start, end)
                embedding = self.model.crop(audio_input, segment)
                embeddings.append(embedding)
            except Exception as e:
                logger.debug(f"Failed to extract embedding for segment {start}-{end}: {e}")
                continue

        if not embeddings:
            raise ValueError(
                f"Could not extract any embeddings for speaker {speaker_label}"
            )

        # Return mean embedding across all segments
        return np.mean(embeddings, axis=0)

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def match_speaker(
        self,
        cluster_embedding: np.ndarray,
        references: Dict[str, np.ndarray],
    ) -> Tuple[Optional[str], float]:
        """Find the best matching reference speaker for a cluster embedding.

        Args:
            cluster_embedding: Embedding vector for the unknown speaker cluster.
            references: Dict mapping speaker names to reference embeddings.

        Returns:
            Tuple of (best_match_name, similarity_score).
            best_match_name is None if no match exceeds the threshold.
        """
        if not references:
            return None, 0.0

        best_name = None
        best_score = -1.0

        for name, ref_embedding in references.items():
            score = self.cosine_similarity(cluster_embedding, ref_embedding)
            if score > best_score:
                best_score = score
                best_name = name

        if best_score >= self.match_threshold:
            return best_name, best_score
        return None, best_score

    def identify(
        self,
        audio_path: str,
        speaker_segments: list,
        expected_speakers: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, str], Dict[str, float]]:
        """Identify speakers by matching diarization clusters to references.

        Uses greedy assignment: best match first, remove from pool, repeat.
        Unmatched clusters get "Unknown_1", "Unknown_2", etc.

        When expected_speakers is provided, matching is constrained to only
        those names and all clusters are assigned to the closest match.

        Args:
            audio_path: Path to the audio file.
            speaker_segments: List of SpeakerSegment objects from diarization.
            expected_speakers: Optional list of expected speaker names to
                constrain matching (e.g., ["Will Menaker", "Felix Biederman"]).

        Returns:
            Tuple of (label_to_name, label_to_score):
                label_to_name: Dict mapping original labels to identified names.
                label_to_score: Dict mapping original labels to confidence scores.
        """
        references = self.load_reference_embeddings()

        if not references:
            logger.warning("No reference embeddings found, skipping identification")
            return {}, {}

        # Filter references to expected speakers if provided
        if expected_speakers:
            filtered = {name: emb for name, emb in references.items() if name in expected_speakers}
            missing = [name for name in expected_speakers if name not in references]
            if missing:
                logger.warning(f"No reference embeddings for expected speakers: {missing}")
            if not filtered:
                logger.warning("None of the expected speakers have reference embeddings")
                return {}, {}
            references = filtered
            logger.info(f"Constrained to {len(references)} expected speakers: {list(references.keys())}")

        # Get unique speaker labels
        unique_labels = sorted(set(s.speaker for s in speaker_segments if s.speaker))
        if not unique_labels:
            return {}, {}

        logger.info(f"Identifying {len(unique_labels)} speakers against {len(references)} references")

        # Pre-load audio to avoid torchcodec issues on Windows
        audio_input = self._load_audio(audio_path)

        # Extract embeddings for each cluster
        cluster_embeddings = {}
        for label in unique_labels:
            try:
                embedding = self.extract_cluster_embedding(
                    audio_input, speaker_segments, label
                )
                cluster_embeddings[label] = embedding
            except ValueError as e:
                logger.warning(f"Could not extract embedding for {label}: {e}")

        if not cluster_embeddings:
            logger.warning("Could not extract any cluster embeddings")
            return {}, {}

        # Hungarian algorithm: optimal 1:1 assignment via cost matrix
        from scipy.optimize import linear_sum_assignment

        # Build cost matrix (negate similarity for minimization)
        labels = list(cluster_embeddings.keys())
        names = list(references.keys())
        cost_matrix = np.zeros((len(labels), len(names)))
        for i, label in enumerate(labels):
            for j, name in enumerate(names):
                cost_matrix[i, j] = -self.cosine_similarity(cluster_embeddings[label], references[name])

        # Find optimal assignment (handles rectangular matrices)
        row_idx, col_idx = linear_sum_assignment(cost_matrix)

        label_to_name = {}
        label_to_score = {}

        for i, j in zip(row_idx, col_idx):
            score = -cost_matrix[i, j]
            if score >= self.match_threshold:
                label_to_name[labels[i]] = names[j]
                label_to_score[labels[i]] = score
                logger.info(f"  {labels[i]} -> {names[j]} (score={score:.3f})")

        # When expected_speakers is set, assign unmatched clusters to their
        # closest expected speaker regardless of score.
        if expected_speakers:
            for label in unique_labels:
                if label in label_to_name:
                    continue
                if label not in cluster_embeddings:
                    # No embedding extracted — assign to first expected speaker as fallback
                    for name in expected_speakers:
                        if name in references:
                            label_to_name[label] = name
                            label_to_score[label] = 0.0
                            logger.info(f"  {label} -> {name} (no embedding, fallback)")
                            break
                    continue
                # Find best matching expected speaker
                best_name = None
                best_score = -1.0
                cluster_emb = cluster_embeddings[label]
                for name, ref_emb in references.items():
                    score = self.cosine_similarity(cluster_emb, ref_emb)
                    if score > best_score:
                        best_score = score
                        best_name = name
                label_to_name[label] = best_name
                label_to_score[label] = best_score
                logger.info(f"  {label} -> {best_name} (score={best_score:.3f}, forced)")
        else:
            # No expected speakers — label unmatched clusters as Unknown
            unknown_counter = 1
            for label in unique_labels:
                if label not in label_to_name:
                    label_to_name[label] = f"Unknown_{unknown_counter}"
                    label_to_score[label] = label_to_score.get(label, 0.0)
                    logger.info(f"  {label} -> Unknown_{unknown_counter}")
                    unknown_counter += 1

        return label_to_name, label_to_score

    def relabel_segments(
        self,
        speaker_segments: list,
        label_map: Dict[str, str],
        score_map: Optional[Dict[str, float]] = None,
    ) -> list:
        """Apply speaker name mapping and confidence scores to diarization segments.

        Args:
            speaker_segments: List of SpeakerSegment objects.
            label_map: Dict mapping original labels to identified names.
            score_map: Optional dict mapping original labels to confidence scores.

        Returns:
            Segments with speaker labels and confidence scores applied.
        """
        for seg in speaker_segments:
            if seg.speaker in label_map:
                original_label = seg.speaker
                seg.speaker = label_map[original_label]
                if score_map and original_label in score_map:
                    seg.speaker_confidence = score_map[original_label]
        return speaker_segments
