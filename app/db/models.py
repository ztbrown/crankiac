from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

@dataclass
class Episode:
    id: Optional[int]
    patreon_id: str
    title: str
    audio_url: Optional[str] = None
    published_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    youtube_url: Optional[str] = None
    youtube_id: Optional[str] = None
    is_free: bool = False
    processed: bool = False
    manually_reviewed: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class TranscriptSegment:
    id: Optional[int]
    episode_id: int
    word: str
    start_time: Decimal
    end_time: Decimal
    segment_index: int
    speaker: Optional[str] = None
    speaker_confidence: Optional[Decimal] = None
    is_overlap: bool = False
    created_at: Optional[datetime] = None
