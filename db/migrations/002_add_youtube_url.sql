-- Add youtube_url and is_free columns to episodes for free Monday episodes available on YouTube
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS youtube_url TEXT;
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS is_free BOOLEAN DEFAULT false;

-- Index for querying free episodes efficiently
CREATE INDEX IF NOT EXISTS idx_episodes_is_free ON episodes(is_free) WHERE is_free = true;
