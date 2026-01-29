-- Add timestamp_anchors table for storing alignment results between Patreon and YouTube timestamps
CREATE TABLE IF NOT EXISTS timestamp_anchors (
    id SERIAL PRIMARY KEY,
    episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    patreon_time NUMERIC(10, 3) NOT NULL,  -- seconds with millisecond precision
    youtube_time NUMERIC(10, 3) NOT NULL,  -- seconds with millisecond precision
    confidence NUMERIC(5, 4),              -- confidence score 0.0000 to 1.0000
    matched_text TEXT,                     -- text that was matched for alignment
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(episode_id, patreon_time)       -- one anchor per patreon timestamp per episode
);

-- Index for episode lookups
CREATE INDEX IF NOT EXISTS idx_timestamp_anchors_episode_id ON timestamp_anchors(episode_id);

-- Index for querying anchors by time within an episode
CREATE INDEX IF NOT EXISTS idx_timestamp_anchors_episode_time ON timestamp_anchors(episode_id, patreon_time);
