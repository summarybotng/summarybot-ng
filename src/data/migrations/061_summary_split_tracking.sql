-- ADR-075: Private Content Regeneration Split
-- Add columns to track split relationships between summaries

-- split_from: The original summary ID this was split from
-- split_private_id: Reference to the private portion (set on public summary)
-- split_public_id: Reference to the public portion (set on private summary)

ALTER TABLE stored_summaries ADD COLUMN split_from TEXT;
ALTER TABLE stored_summaries ADD COLUMN split_private_id TEXT;
ALTER TABLE stored_summaries ADD COLUMN split_public_id TEXT;

-- Index for finding related summaries efficiently
CREATE INDEX IF NOT EXISTS idx_stored_summaries_split_from ON stored_summaries(split_from);
