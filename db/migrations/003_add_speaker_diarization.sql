-- Add speaker column for diarization support
ALTER TABLE transcript_segments ADD COLUMN IF NOT EXISTS speaker VARCHAR(100);

-- Index for filtering by speaker
CREATE INDEX IF NOT EXISTS idx_transcript_segments_speaker ON transcript_segments(speaker);

-- Index for speaker + episode combined queries
CREATE INDEX IF NOT EXISTS idx_transcript_segments_episode_speaker ON transcript_segments(episode_id, speaker);
