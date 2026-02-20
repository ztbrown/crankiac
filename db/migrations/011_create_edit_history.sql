-- Migration 011: Create edit_history table
-- Tracks before/after values for every manual edit to transcript segments.
-- This provides a foundation for mining corrections and building a feedback loop.

CREATE TABLE IF NOT EXISTS edit_history (
    id SERIAL PRIMARY KEY,
    episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    segment_id INTEGER,
    field VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_edit_history_episode_id ON edit_history(episode_id);
CREATE INDEX IF NOT EXISTS idx_edit_history_segment_id ON edit_history(segment_id);
CREATE INDEX IF NOT EXISTS idx_edit_history_field ON edit_history(field);

COMMENT ON TABLE edit_history IS 'Audit log of manual edits to transcript segments.';
COMMENT ON COLUMN edit_history.field IS 'Type of edit: word, delete, insert, speaker.';
COMMENT ON COLUMN edit_history.old_value IS 'Value before edit (NULL for inserts).';
COMMENT ON COLUMN edit_history.new_value IS 'Value after edit (NULL for deletes).';
