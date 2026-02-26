"""LLM-based transcript corrector for low-confidence words."""
import copy
import json
import logging
from typing import Optional, TYPE_CHECKING

import anthropic

from app.db.connection import get_cursor
from app.transcription.llm_prompts import SYSTEM_PROMPT, make_user_prompt

if TYPE_CHECKING:
    from app.transcription.whisper_transcriber import WordSegment

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7
CONTEXT_WINDOW = 50       # words of context around each flagged region
MAX_CHUNK_WORDS = 2000    # max words per LLM call
GROUP_DISTANCE = 15       # max index gap to group low-conf words together


class LLMCorrector:
    """Corrects low-confidence transcript words using an LLM."""

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        threshold: float = CONFIDENCE_THRESHOLD,
        context_window: int = CONTEXT_WINDOW,
        max_chunk_words: int = MAX_CHUNK_WORDS,
        group_distance: int = GROUP_DISTANCE,
    ):
        self.model = model
        self.threshold = threshold
        self.context_window = context_window
        self.max_chunk_words = max_chunk_words
        self.group_distance = group_distance
        self._client: Optional[anthropic.Anthropic] = None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    # ------------------------------------------------------------------
    # Core pipeline steps
    # ------------------------------------------------------------------

    def identify_low_confidence_regions(self, segments: list[dict]) -> list[dict]:
        """Find contiguous regions of low-confidence words with context.

        Args:
            segments: List of segment dicts with 'word_confidence', 'speaker', etc.

        Returns:
            List of region dicts: {'start': int, 'end': int, 'flagged': set[int]}
            where start/end are absolute positional indices into *segments*.
        """
        low_conf = [
            i for i, seg in enumerate(segments)
            if seg.get("word_confidence") is not None
            and float(seg["word_confidence"]) < self.threshold
        ]

        if not low_conf:
            return []

        # Group positions within group_distance of each other
        groups: list[list[int]] = [[low_conf[0]]]
        for pos in low_conf[1:]:
            if pos - groups[-1][-1] <= self.group_distance:
                groups[-1].append(pos)
            else:
                groups.append([pos])

        # Expand each group with context and build regions
        regions: list[dict] = []
        for group in groups:
            start = max(0, min(group) - self.context_window)
            end = min(len(segments) - 1, max(group) + self.context_window)
            regions.append({"start": start, "end": end, "flagged": set(group)})

        # Merge overlapping regions
        merged: list[dict] = []
        for region in regions:
            if merged and region["start"] <= merged[-1]["end"]:
                merged[-1]["end"] = max(merged[-1]["end"], region["end"])
                merged[-1]["flagged"] |= region["flagged"]
            else:
                merged.append(region)

        return merged

    def build_chunks(self, segments: list[dict], regions: list[dict]) -> list[dict]:
        """Build LLM-ready chunks from regions, splitting large ones at speaker turns.

        Args:
            segments: Full flat list of segment dicts.
            regions: Output of identify_low_confidence_regions().

        Returns:
            List of chunk dicts: {'segments': list[dict], 'flagged': set[int]}
            where 'flagged' contains positional indices *within* the chunk sublist.
        """
        chunks: list[dict] = []
        for region in regions:
            start, end = region["start"], region["end"]
            flagged_abs = region["flagged"]
            region_segs = segments[start : end + 1]

            if len(region_segs) <= self.max_chunk_words:
                local_flagged = {pos - start for pos in flagged_abs}
                chunks.append({
                    "segments": region_segs,
                    "flagged": local_flagged,
                })
            else:
                chunks.extend(
                    self._split_at_speaker_boundaries(region_segs, flagged_abs, start)
                )
        return chunks

    def _split_at_speaker_boundaries(
        self,
        region_segs: list[dict],
        flagged_abs: set[int],
        global_start: int,
    ) -> list[dict]:
        """Split an oversized region at speaker change points.

        Only returns sub-chunks that contain at least one flagged word.
        """
        # Collect speaker-change indices (relative to region_segs)
        split_points = [0]
        for i in range(1, len(region_segs)):
            if region_segs[i].get("speaker") != region_segs[i - 1].get("speaker"):
                split_points.append(i)
        split_points.append(len(region_segs))

        chunks: list[dict] = []
        for k in range(len(split_points) - 1):
            sub_start = split_points[k]
            sub_end = split_points[k + 1]
            sub_segs = region_segs[sub_start:sub_end]

            local_flagged = set()
            for abs_pos in flagged_abs:
                local_pos = abs_pos - global_start - sub_start
                if 0 <= local_pos < len(sub_segs):
                    local_flagged.add(local_pos)

            if local_flagged:
                chunks.append({"segments": sub_segs, "flagged": local_flagged})

        return chunks

    def format_chunk(self, chunk: dict) -> str:
        """Render a chunk as text with flagged words annotated.

        Flagged words appear as: [?word?](confidence)[id]
        where *id* is the segment's 'id' field (DB id or list index).
        """
        parts: list[str] = []
        flagged = chunk["flagged"]
        for i, seg in enumerate(chunk["segments"]):
            if i in flagged:
                conf = seg.get("word_confidence")
                conf_str = f"{float(conf):.2f}" if conf is not None else "?"
                parts.append(f"[?{seg['word']}?]({conf_str})[{seg['id']}]")
            else:
                parts.append(seg["word"])
        return " ".join(parts)

    def call_llm(self, formatted_text: str) -> dict:
        """Send a formatted chunk to the LLM and return corrections.

        Retries once on invalid JSON. Returns {} on persistent failure.

        Returns:
            Dict mapping str(id) -> corrected_word.
        """
        user_prompt = make_user_prompt(formatted_text)

        for attempt in range(2):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw = response.content[0].text.strip()

                # Strip markdown code fences if present
                if "```" in raw:
                    start = raw.find("```") + 3
                    if raw[start:].startswith("json"):
                        start += 4
                    end = raw.rfind("```")
                    raw = raw[start:end].strip()

                corrections = json.loads(raw)
                if not isinstance(corrections, dict):
                    raise ValueError(f"Expected dict, got {type(corrections).__name__}")
                return corrections

            except (json.JSONDecodeError, ValueError) as exc:
                if attempt == 0:
                    logger.warning("LLM returned invalid JSON (attempt 1): %s — retrying", exc)
                else:
                    logger.error("LLM returned invalid JSON after retry: %s — skipping chunk", exc)
                    return {}
            except Exception as exc:
                logger.error("LLM API call failed: %s", exc)
                return {}

        return {}

    def apply_corrections(
        self,
        episode_id: int,
        segments: list[dict],
        chunks: list[dict],
        corrections_by_chunk: list[dict],
    ) -> int:
        """Write corrections to the DB within a single transaction.

        Validates:
        - Key resolves to a flagged segment (rejects corrections to unmarked words).
        - Corrected value is a single word (rejects non-1:1 replacements).

        Logs each correction with field='llm_word' and clears word_confidence.

        Returns:
            Number of corrections applied.
        """
        id_to_seg = {seg["id"]: seg for seg in segments}
        total = 0

        with get_cursor() as cursor:
            for chunk, corrections in zip(chunks, corrections_by_chunk):
                flagged_ids = {chunk["segments"][i]["id"] for i in chunk["flagged"]}

                for key, new_word in corrections.items():
                    try:
                        seg_id = int(key)
                    except (ValueError, TypeError):
                        logger.warning("LLM returned non-integer key %r, skipping", key)
                        continue

                    if seg_id not in flagged_ids:
                        logger.warning(
                            "LLM tried to correct unmarked segment id=%s, skipping", seg_id
                        )
                        continue

                    new_word = str(new_word)
                    if " " in new_word:
                        logger.warning(
                            "LLM returned multi-word correction for id=%s: %r, skipping",
                            seg_id,
                            new_word,
                        )
                        continue

                    seg = id_to_seg.get(seg_id)
                    if not seg:
                        logger.warning("Segment id=%s not in segments list, skipping", seg_id)
                        continue

                    old_word = seg["word"]
                    if old_word == new_word:
                        continue

                    cursor.execute(
                        "UPDATE transcript_segments SET word = %s, word_confidence = NULL WHERE id = %s",
                        (new_word, seg_id),
                    )
                    cursor.execute(
                        """INSERT INTO edit_history (episode_id, segment_id, field, old_value, new_value)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (episode_id, seg_id, "llm_word", old_word, new_word),
                    )
                    total += 1

        return total

    # ------------------------------------------------------------------
    # High-level entry points
    # ------------------------------------------------------------------

    def correct_episode(self, episode_id: int) -> int:
        """Correct low-confidence words for a DB-persisted episode.

        Uses an advisory lock (UPDATE ... RETURNING) to prevent double-processing.

        Returns:
            Number of corrections applied, or -1 if already processed / not found.
        """
        # Advisory lock: atomically claim this episode
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE episodes SET llm_corrected = TRUE
                   WHERE id = %s AND llm_corrected = FALSE
                   RETURNING id""",
                (episode_id,),
            )
            row = cursor.fetchone()

        if not row:
            logger.info("Episode %s already llm_corrected or not found", episode_id)
            return -1

        # Fetch segments ordered by index
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                """SELECT id, word, segment_index, word_confidence, speaker
                   FROM transcript_segments
                   WHERE episode_id = %s
                   ORDER BY segment_index""",
                (episode_id,),
            )
            rows = cursor.fetchall()

        if not rows:
            return 0

        segments = [dict(row) for row in rows]
        regions = self.identify_low_confidence_regions(segments)
        if not regions:
            logger.info("Episode %s: no low-confidence regions found", episode_id)
            return 0

        chunks = self.build_chunks(segments, regions)
        corrections_by_chunk = [self.call_llm(self.format_chunk(chunk)) for chunk in chunks]
        total = self.apply_corrections(episode_id, segments, chunks, corrections_by_chunk)
        logger.info("Episode %s: applied %d LLM corrections", episode_id, total)
        return total

    def correct_segments(
        self,
        segments: list["WordSegment"],
        episode_id: Optional[int] = None,
    ) -> list["WordSegment"]:
        """Correct low-confidence words in an in-memory WordSegment list.

        Intended for pipeline use: no DB reads or writes. Uses list indices as
        segment keys so the LLM can reference them.

        Args:
            segments: WordSegment objects from the transcription pipeline.
            episode_id: Unused; present for API symmetry.

        Returns:
            New list of WordSegments with corrections applied and word_confidence
            set to None for corrected words.
        """
        seg_dicts = [
            {
                "id": i,
                "word": seg.word,
                "word_confidence": (
                    float(seg.word_confidence)
                    if seg.word_confidence is not None
                    else None
                ),
                "speaker": getattr(seg, "speaker", None),
            }
            for i, seg in enumerate(segments)
        ]

        regions = self.identify_low_confidence_regions(seg_dicts)
        if not regions:
            return list(segments)

        chunks = self.build_chunks(seg_dicts, regions)

        all_corrections: dict[int, str] = {}
        for chunk in chunks:
            formatted = self.format_chunk(chunk)
            raw_corrections = self.call_llm(formatted)
            flagged_ids = {chunk["segments"][i]["id"] for i in chunk["flagged"]}

            for key, new_word in raw_corrections.items():
                try:
                    idx = int(key)
                except (ValueError, TypeError):
                    logger.warning("LLM returned non-integer key %r, skipping", key)
                    continue

                if idx not in flagged_ids:
                    logger.warning(
                        "LLM tried to correct unmarked segment idx=%s, skipping", idx
                    )
                    continue

                new_word = str(new_word)
                if " " in new_word:
                    logger.warning(
                        "LLM returned multi-word correction for idx=%s: %r, skipping",
                        idx,
                        new_word,
                    )
                    continue

                all_corrections[idx] = new_word

        result: list["WordSegment"] = []
        for i, seg in enumerate(segments):
            if i in all_corrections:
                new_seg = copy.copy(seg)
                new_seg.word = all_corrections[i]
                new_seg.word_confidence = None
                result.append(new_seg)
            else:
                result.append(seg)

        return result
