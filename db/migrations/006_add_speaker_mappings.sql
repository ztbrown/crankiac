-- Speaker mappings table for mapping speaker labels (SPEAKER_00) to actual names (Matt)
CREATE TABLE IF NOT EXISTS speaker_mappings (
    id SERIAL PRIMARY KEY,
    episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    speaker_label VARCHAR(100) NOT NULL,  -- e.g., SPEAKER_00, SPEAKER_01
    speaker_name VARCHAR(100) NOT NULL,   -- e.g., Matt, Will, Felix
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_episode_speaker_label UNIQUE (episode_id, speaker_label)
);

-- Index for episode lookups
CREATE INDEX IF NOT EXISTS idx_speaker_mappings_episode_id ON speaker_mappings(episode_id);

-- Trigger for updated_at
DROP TRIGGER IF EXISTS update_speaker_mappings_updated_at ON speaker_mappings;
CREATE TRIGGER update_speaker_mappings_updated_at
    BEFORE UPDATE ON speaker_mappings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
