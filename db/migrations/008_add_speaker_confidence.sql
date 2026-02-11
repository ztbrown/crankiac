-- Add speaker_confidence column to transcript_segments
-- Stores the cosine similarity score from speaker identification (0.0-1.0)
ALTER TABLE transcript_segments ADD COLUMN IF NOT EXISTS speaker_confidence NUMERIC(4, 3);
