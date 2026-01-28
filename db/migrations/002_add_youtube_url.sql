-- Add youtube_url column to episodes for free Monday episodes available on YouTube
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS youtube_url TEXT;
