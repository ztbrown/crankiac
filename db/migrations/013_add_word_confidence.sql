-- Add word_confidence column to transcript_segments
-- Stores Whisper's per-word transcription probability (0.0-1.0)
ALTER TABLE transcript_segments ADD COLUMN IF NOT EXISTS word_confidence NUMERIC(4, 3);
