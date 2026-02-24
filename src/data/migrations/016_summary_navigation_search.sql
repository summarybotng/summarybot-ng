-- ADR-020: Summary Navigation and Search
-- Migration: Add navigation index and FTS5 full-text search

-- Phase 1: Navigation index for efficient prev/next queries
-- (guild_id, source, created_at) allows filtering by source type
CREATE INDEX IF NOT EXISTS idx_stored_summaries_nav
ON stored_summaries(guild_id, source, created_at);

-- Phase 2: Full-text search using SQLite FTS5
-- Virtual table for searching summary content
CREATE VIRTUAL TABLE IF NOT EXISTS summary_fts USING fts5(
    summary_id UNINDEXED,
    guild_id UNINDEXED,
    summary_text,
    key_points,
    action_items,
    participants,
    technical_terms,
    tokenize='porter unicode61'
);

-- Note: FTS population and triggers are handled at the application level
-- to avoid complex SQL parsing issues with the migration runner.
-- The SQLiteStoredSummaryRepository.save() method will populate the FTS table.
