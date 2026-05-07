-- ADR-090: Wiki ingestion path switches
-- Enable separate control over page-based and vector-based wiki ingestion

-- Add vector ingestion toggle (off by default for existing guilds)
ALTER TABLE guild_configs ADD COLUMN wiki_ingest_to_vectors INTEGER DEFAULT 0;

-- Note: wiki_auto_ingest (existing) controls page-based ingestion
-- wiki_ingest_to_vectors (new) controls RuVector knowledge unit extraction
--
-- Both can be enabled simultaneously for comparison:
--   wiki_auto_ingest = 1, wiki_ingest_to_vectors = 1  -> dual-write mode
--   wiki_auto_ingest = 1, wiki_ingest_to_vectors = 0  -> pages only (current default)
--   wiki_auto_ingest = 0, wiki_ingest_to_vectors = 1  -> vectors only (future)
--   wiki_auto_ingest = 0, wiki_ingest_to_vectors = 0  -> wiki disabled
