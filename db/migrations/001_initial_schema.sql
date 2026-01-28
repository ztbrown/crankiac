-- Enable trigram extension for fast prefix/substring search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Episodes table
CREATE TABLE IF NOT EXISTS episodes (
    id SERIAL PRIMARY KEY,
    patreon_id VARCHAR(255) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    audio_url TEXT,
    published_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index on patreon_id for lookups
CREATE INDEX IF NOT EXISTS idx_episodes_patreon_id ON episodes(patreon_id);

-- Index on processed status for finding unprocessed episodes
CREATE INDEX IF NOT EXISTS idx_episodes_processed ON episodes(processed) WHERE NOT processed;

-- Transcript segments table (stores word-level data with timestamps)
CREATE TABLE IF NOT EXISTS transcript_segments (
    id SERIAL PRIMARY KEY,
    episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    word TEXT NOT NULL,
    start_time NUMERIC(10, 3) NOT NULL,  -- seconds with millisecond precision
    end_time NUMERIC(10, 3) NOT NULL,
    segment_index INTEGER NOT NULL,  -- order within episode
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for episode lookups
CREATE INDEX IF NOT EXISTS idx_transcript_segments_episode_id ON transcript_segments(episode_id);

-- Trigram index on word for fast prefix/substring search
CREATE INDEX IF NOT EXISTS idx_transcript_segments_word_trgm ON transcript_segments USING gin(word gin_trgm_ops);

-- Index for ordering by time within an episode
CREATE INDEX IF NOT EXISTS idx_transcript_segments_episode_time ON transcript_segments(episode_id, start_time);

-- Full text search on words (alternative to trigram for exact word matching)
CREATE INDEX IF NOT EXISTS idx_transcript_segments_word_btree ON transcript_segments(lower(word));

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for episodes updated_at
DROP TRIGGER IF EXISTS update_episodes_updated_at ON episodes;
CREATE TRIGGER update_episodes_updated_at
    BEFORE UPDATE ON episodes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
