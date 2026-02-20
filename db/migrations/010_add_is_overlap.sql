-- Add is_overlap column to transcript_segments
-- Flags words where a second speaker has significant crosstalk overlap
ALTER TABLE transcript_segments ADD COLUMN IF NOT EXISTS is_overlap BOOLEAN DEFAULT FALSE;
