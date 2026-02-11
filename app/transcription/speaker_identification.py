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

    def extract_cluster_embedding(
        self,
        audio_path: str,
        segments: list,
        speaker_label: str,
    ) -> np.ndarray:
        """Extract mean embedding for a speaker cluster.

        Collects all segments belonging to a speaker label, extracts embeddings
        for each segment, and returns the mean embedding.

        Args:
            audio_path: Path to the audio file.
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
                embedding = self.model.crop(audio_path, segment)
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
    ) -> Dict[str, str]:
        """Identify speakers by matching diarization clusters to references.

        Uses greedy assignment: best match first, remove from pool, repeat.
        Unmatched clusters get "Unknown_1", "Unknown_2", etc.

        Args:
            audio_path: Path to the audio file.
            speaker_segments: List of SpeakerSegment objects from diarization.

        Returns:
            Dict mapping original labels to identified names.
            e.g., {"SPEAKER_00": "Matt", "SPEAKER_01": "Will", "SPEAKER_02": "Unknown_1"}
        """
        references = self.load_reference_embeddings()

        if not references:
            logger.warning("No reference embeddings found, skipping identification")
            return {}

        # Get unique speaker labels
        unique_labels = sorted(set(s.speaker for s in speaker_segments if s.speaker))
        if not unique_labels:
            return {}

        logger.info(f"Identifying {len(unique_labels)} speakers against {len(references)} references")

        # Extract embeddings for each cluster
        cluster_embeddings = {}
        for label in unique_labels:
            try:
                embedding = self.extract_cluster_embedding(
                    audio_path, speaker_segments, label
                )
                cluster_embeddings[label] = embedding
            except ValueError as e:
                logger.warning(f"Could not extract embedding for {label}: {e}")

        if not cluster_embeddings:
            logger.warning("Could not extract any cluster embeddings")
            return {}

        # Greedy assignment: compute all scores, assign best first
        scores = []
        for label, cluster_emb in cluster_embeddings.items():
            for name, ref_emb in references.items():
                score = self.cosine_similarity(cluster_emb, ref_emb)
                scores.append((score, label, name))

        # Sort by score descending
        scores.sort(key=lambda x: x[0], reverse=True)

        label_to_name = {}
        assigned_labels = set()
        assigned_names = set()

        for score, label, name in scores:
            if label in assigned_labels or name in assigned_names:
                continue
            if score >= self.match_threshold:
                label_to_name[label] = name
                assigned_labels.add(label)
                assigned_names.add(name)
                logger.info(f"  {label} -> {name} (score={score:.3f})")

        # Assign unknown labels to unmatched clusters
        unknown_counter = 1
        for label in unique_labels:
            if label not in label_to_name:
                label_to_name[label] = f"Unknown_{unknown_counter}"
                logger.info(f"  {label} -> Unknown_{unknown_counter}")
                unknown_counter += 1

        return label_to_name

    def relabel_segments(
        self,
        speaker_segments: list,
        label_map: Dict[str, str],
    ) -> list:
        """Apply speaker name mapping to diarization segments.

        Args:
            speaker_segments: List of SpeakerSegment objects.
            label_map: Dict mapping original labels to identified names.

        Returns:
            The same segments with speaker labels replaced.
        """
        for seg in speaker_segments:
            if seg.speaker in label_map:
                seg.speaker = label_map[seg.speaker]
        return speaker_segments
