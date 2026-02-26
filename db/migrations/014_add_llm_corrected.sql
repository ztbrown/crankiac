-- Add llm_corrected flag to episodes
-- Tracks whether LLM post-processing correction has been applied
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS llm_corrected BOOLEAN DEFAULT FALSE;
