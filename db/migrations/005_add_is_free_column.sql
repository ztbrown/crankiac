-- Add is_free column to episodes to indicate publicly available episodes
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS is_free BOOLEAN DEFAULT FALSE;

-- Index for querying free episodes efficiently
CREATE INDEX IF NOT EXISTS idx_episodes_is_free ON episodes(is_free) WHERE is_free = TRUE;
