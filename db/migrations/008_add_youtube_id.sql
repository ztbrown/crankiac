-- Add youtube_id column to episodes table for normalized YouTube video IDs
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS youtube_id VARCHAR(20);

-- Partial index on non-null values for efficient lookups
CREATE INDEX IF NOT EXISTS idx_episodes_youtube_id ON episodes(youtube_id) WHERE youtube_id IS NOT NULL;
