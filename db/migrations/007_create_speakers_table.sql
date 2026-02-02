-- Migration 007: Create speakers table and normalize speaker data
-- This migration creates a dedicated speakers table and migrates existing speaker
-- names from the varchar field in transcript_segments to the new normalized structure.

-- Create speakers table
CREATE TABLE IF NOT EXISTS speakers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on speaker name for fast lookups
CREATE INDEX IF NOT EXISTS idx_speakers_name ON speakers(name);

-- Insert existing unique speakers from transcript_segments
INSERT INTO speakers (name)
SELECT DISTINCT speaker
FROM transcript_segments
WHERE speaker IS NOT NULL
ON CONFLICT (name) DO NOTHING;

-- Add speaker_id column to transcript_segments (nullable initially for migration)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'transcript_segments' AND column_name = 'speaker_id'
    ) THEN
        ALTER TABLE transcript_segments
        ADD COLUMN speaker_id INTEGER REFERENCES speakers(id);
    END IF;
END $$;

-- Populate speaker_id based on existing speaker names (only for rows that don't have it set)
UPDATE transcript_segments ts
SET speaker_id = s.id
FROM speakers s
WHERE ts.speaker = s.name
AND ts.speaker_id IS NULL;

-- Create index on speaker_id for fast joins
CREATE INDEX IF NOT EXISTS idx_transcript_segments_speaker_id ON transcript_segments(speaker_id);

-- Note: We're keeping the old 'speaker' varchar column for backward compatibility
-- during the transition. It can be dropped in a future migration once all code
-- is updated to use speaker_id.

-- Add comment to document the change
COMMENT ON COLUMN transcript_segments.speaker_id IS 'Foreign key to speakers table. Replaces the speaker varchar column.';
COMMENT ON TABLE speakers IS 'Normalized speaker names. Each speaker has a unique ID.';
