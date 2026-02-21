-- ADR-008: Unified Summary Experience
-- Migration: Add source tracking and archive metadata to stored_summaries
--
-- This migration adds support for storing archive summaries alongside
-- real-time summaries in the same table, enabling unified access and
-- consistent features (push to channel, view details).

-- Add source column to track where the summary came from
-- Values: realtime, scheduled, manual, archive, imported
ALTER TABLE stored_summaries ADD COLUMN source TEXT NOT NULL DEFAULT 'realtime';

-- Add archive-specific metadata columns (null for non-archive summaries)
ALTER TABLE stored_summaries ADD COLUMN archive_period TEXT;       -- e.g., "2026-01-15" for daily
ALTER TABLE stored_summaries ADD COLUMN archive_granularity TEXT;  -- "daily", "weekly", "monthly"
ALTER TABLE stored_summaries ADD COLUMN archive_source_key TEXT;   -- Archive source registry key

-- Index for efficient filtering by source
CREATE INDEX IF NOT EXISTS idx_stored_summaries_source ON stored_summaries(source);

-- Index for archive-specific queries
CREATE INDEX IF NOT EXISTS idx_stored_summaries_archive ON stored_summaries(guild_id, source, archive_period)
    WHERE source = 'archive';

-- Composite index for unified listing (all sources, ordered by date)
CREATE INDEX IF NOT EXISTS idx_stored_summaries_unified ON stored_summaries(guild_id, created_at DESC, source);
