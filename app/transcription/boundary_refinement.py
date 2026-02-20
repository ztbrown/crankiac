"""Word-level speaker boundary refinement using voice embeddings.

Words at speaker transitions get assigned by maximum time overlap — essentially
a coin flip.  Comparing voice embeddings for the actual audio at each word's
timestamp is more accurate.
"""
import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# Window around each transition (seconds) within which words are considered
# boundary candidates.
BOUNDARY_WINDOW_SECONDS = 2.0

# Minimum word duration (seconds) — shorter words don't have enough audio.
MIN_WORD_DURATION = 0.1

# Minimum cosine-similarity improvement required to trigger a reassignment.
REASSIGNMENT_MARGIN = 0.05


def find_boundary_words(segments: list) -> list[int]:
    """Find word indices within BOUNDARY_WINDOW_SECONDS of any speaker transition.

    A speaker transition is any point where consecutive words are assigned to
    different speakers.  Words whose midpoint falls within
    BOUNDARY_WINDOW_SECONDS of a transition are returned as candidates for
    embedding-based refinement.

    Args:
        segments: List of word segments.  Each must have ``start_time``,
            ``end_time``, and ``speaker`` attributes.

    Returns:
        Sorted list of unique word indices that are boundary candidates.
    """
    if not segments:
        return []

    # Find all transition times: midpoint between consecutive words that differ.
    transition_times: list[float] = []
    for i in range(len(segments) - 1):
        if segments[i].speaker != segments[i + 1].speaker:
            t = (float(segments[i].end_time) + float(segments[i + 1].start_time)) / 2.0
            transition_times.append(t)

    if not transition_times:
        return []

    boundary_indices: set[int] = set()
    for idx, word in enumerate(segments):
        midpoint = (float(word.start_time) + float(word.end_time)) / 2.0
        for t in transition_times:
            if abs(midpoint - t) <= BOUNDARY_WINDOW_SECONDS:
                boundary_indices.add(idx)
                break  # already counted for this word

    return sorted(boundary_indices)


def refine_speaker_boundaries(
    words: list,
    speaker_segs: list,
    audio,
    identifier,
    label_map: dict,
    score_map: dict,
) -> list:
    """Refine speaker assignments for boundary words using voice embeddings.

    For each boundary word (as determined by :func:`find_boundary_words`),
    this function:

    1. Extracts a voice embedding for the word's audio segment.
    2. Compares it against the reference embeddings of the word's current
       speaker *and* its adjacent speakers (speakers that appear immediately
       before/after the word in the transcript).
    3. Reassigns the word to the best-matching speaker if that speaker's
       similarity exceeds the current speaker's similarity by at least
       ``REASSIGNMENT_MARGIN``.

    Args:
        words: List of word segments (mutated in place).
        speaker_segs: List of :class:`~app.transcription.diarization.SpeakerSegment`
            objects from diarization (currently unused — retained for API
            compatibility with future use of speaker-level embeddings).
        audio: Audio input accepted by ``identifier.model.crop()`` — either a
            ``{"waveform": ..., "sample_rate": ...}`` dict or a file path.
        identifier: A :class:`~app.transcription.speaker_identification.SpeakerIdentifier`
            instance with a loaded embedding model and ``load_reference_embeddings()``.
        label_map: Dict mapping diarization labels to speaker names (e.g.
            ``{"SPEAKER_00": "Alice"}``).  Pass an identity map when labels
            already contain names.
        score_map: Dict mapping diarization labels to confidence scores
            (currently informational, not used in reassignment logic).

    Returns:
        The same ``words`` list with speaker assignments potentially updated.
    """
    if not words:
        return words

    # Identify which words are boundary candidates.
    boundary_indices = find_boundary_words(words)
    if not boundary_indices:
        return words

    # Load reference embeddings once.
    references = identifier.load_reference_embeddings()
    if not references:
        logger.debug("No reference embeddings available — skipping boundary refinement")
        return words

    from pyannote.core import Segment

    n = len(words)

    for idx in boundary_indices:
        word = words[idx]
        start = float(word.start_time)
        end = float(word.end_time)
        duration = end - start

        # Skip words too short to embed reliably.
        if duration < MIN_WORD_DURATION:
            logger.debug(f"Skipping short word at {start:.3f}-{end:.3f} ({duration:.3f}s)")
            continue

        # Determine current and adjacent speaker names.
        current_speaker = word.speaker
        adjacent_speakers: set[Optional[str]] = set()
        if idx > 0:
            adjacent_speakers.add(words[idx - 1].speaker)
        if idx < n - 1:
            adjacent_speakers.add(words[idx + 1].speaker)

        # Build the set of candidate speakers to compare (current + adjacent).
        candidate_speakers = {current_speaker} | adjacent_speakers
        candidate_speakers.discard(None)

        # Filter to speakers that have reference embeddings.
        candidate_refs = {
            spk: references[spk]
            for spk in candidate_speakers
            if spk in references
        }
        if not candidate_refs:
            logger.debug(
                f"No reference embeddings for candidates {candidate_speakers} "
                f"at word {idx}"
            )
            continue

        # Extract embedding for this word.
        try:
            segment = Segment(start, end)
            word_emb = identifier.model.crop(audio, segment)
        except Exception as e:
            logger.debug(f"Failed to extract embedding for word {idx} ({start:.3f}-{end:.3f}): {e}")
            continue

        # Score each candidate.
        scores = {
            spk: identifier.cosine_similarity(word_emb, ref_emb)
            for spk, ref_emb in candidate_refs.items()
        }

        current_score = scores.get(current_speaker, -1.0)
        best_speaker = max(scores, key=lambda s: scores[s])
        best_score = scores[best_speaker]

        # Only reassign if improvement meets the required margin.
        if best_speaker != current_speaker and best_score >= current_score + REASSIGNMENT_MARGIN:
            logger.info(
                f"Reassigning word {idx} ({start:.3f}-{end:.3f}) "
                f"from {current_speaker!r} to {best_speaker!r} "
                f"(score {current_score:.3f} → {best_score:.3f})"
            )
            word.speaker = best_speaker

    return words
