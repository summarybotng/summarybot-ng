-- ADR-067: Automatic Wiki Ingestion

-- Track wiki ingestion status on stored summaries
ALTER TABLE stored_summaries ADD COLUMN wiki_ingested BOOLEAN DEFAULT FALSE;
ALTER TABLE stored_summaries ADD COLUMN wiki_ingested_at TEXT;

-- Guild setting for auto-ingest toggle (using guild_configs, not guilds)
-- Note: guilds table doesn't exist per ADR-012/migration 013
ALTER TABLE guild_configs ADD COLUMN wiki_auto_ingest BOOLEAN DEFAULT TRUE;

-- Index for finding non-ingested summaries
CREATE INDEX IF NOT EXISTS idx_stored_summaries_wiki_ingested
ON stored_summaries(guild_id, wiki_ingested)
WHERE wiki_ingested = FALSE;
