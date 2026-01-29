-- Add table for storing timestamp alignment anchors between Patreon and YouTube transcripts

CREATE TABLE IF NOT EXISTS timestamp_anchors (
    id SERIAL PRIMARY KEY,
    episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    patreon_time NUMERIC(10, 3) NOT NULL,
    youtube_time NUMERIC(10, 3) NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    matched_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for looking up anchors by episode
CREATE INDEX IF NOT EXISTS idx_timestamp_anchors_episode_id ON timestamp_anchors(episode_id);

-- Index for time-based lookups
CREATE INDEX IF NOT EXISTS idx_timestamp_anchors_patreon_time ON timestamp_anchors(episode_id, patreon_time);

-- Unique constraint to prevent duplicate anchors at same timestamp
CREATE UNIQUE INDEX IF NOT EXISTS idx_timestamp_anchors_unique ON timestamp_anchors(episode_id, patreon_time);
