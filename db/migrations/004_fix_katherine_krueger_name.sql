-- Fix misspellings of Katherine Krueger's name in transcript segments
-- Katherine variations -> Katherine
UPDATE transcript_segments SET word = 'Katherine' WHERE lower(word) IN ('kathryn', 'kathrine', 'catheryn', 'catherine', 'katherin', 'katharine');

-- Krueger variations -> Krueger
UPDATE transcript_segments SET word = 'Krueger' WHERE lower(word) IN ('kruger', 'kreuger', 'kruegar', 'krugar', 'kreugar', 'kroeger', 'kruger', 'krugger');

-- Fix possessive forms as well
UPDATE transcript_segments SET word = 'Katherine''s' WHERE lower(word) IN ('kathryn''s', 'kathrine''s', 'catheryn''s', 'catherine''s', 'katherin''s', 'katharine''s');

UPDATE transcript_segments SET word = 'Krueger''s' WHERE lower(word) IN ('kruger''s', 'kreuger''s', 'kruegar''s', 'krugar''s', 'kreugar''s', 'kroeger''s', 'kruger''s', 'krugger''s');
