-- ADR-090: Inline KU Extraction Support
-- Track whether KUs came from inline extraction or backfill

-- Add extraction_source column to wiki_knowledge_units
-- Values: 'inline' (during summarization), 'backfill' (from stored_summaries), 'manual' (360° generate)
ALTER TABLE wiki_knowledge_units ADD COLUMN extraction_source TEXT DEFAULT 'manual';

-- Index for finding units by extraction source
CREATE INDEX IF NOT EXISTS idx_ku_extraction_source ON wiki_knowledge_units(guild_id, extraction_source);

-- Add summary_id to link KUs directly to their source summary
-- This enables dual-write from summarization pipeline
ALTER TABLE wiki_knowledge_units ADD COLUMN summary_id TEXT;

-- Index for finding all KUs from a specific summary
CREATE INDEX IF NOT EXISTS idx_ku_summary_id ON wiki_knowledge_units(summary_id);
