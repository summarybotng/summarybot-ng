-- Track RuVector ingestion status on stored summaries
-- Mirrors wiki_ingested pattern for consistency

ALTER TABLE stored_summaries ADD COLUMN vector_ingested INTEGER DEFAULT 0;
ALTER TABLE stored_summaries ADD COLUMN vector_ingested_at TEXT;
ALTER TABLE stored_summaries ADD COLUMN vector_unit_count INTEGER DEFAULT 0;

-- Index for finding summaries pending vector ingestion
CREATE INDEX IF NOT EXISTS idx_stored_summaries_vector_ingested
ON stored_summaries(guild_id, vector_ingested)
WHERE vector_ingested = 0;
