-- ADR-087: Weekly Continuity Summaries
-- Migration: Add continuity tracking for weekly scheduled summaries

-- Add enable_continuity to scheduled_tasks
-- When true, weekly summaries carry context from previous week
ALTER TABLE scheduled_tasks ADD COLUMN enable_continuity INTEGER DEFAULT 0;

-- Add continuity tracking to stored_summaries
-- previous_summary_id: links to the prior week's summary for continuity chain
-- continuity_week_number: position in the continuity chain (1, 2, 3, ...)
ALTER TABLE stored_summaries ADD COLUMN previous_summary_id TEXT;
ALTER TABLE stored_summaries ADD COLUMN continuity_week_number INTEGER;

-- Index for efficient lookup of previous weekly summaries
-- Used by get_previous_weekly_summary() to find the most recent weekly summary
-- for a given channel before a specific date
CREATE INDEX IF NOT EXISTS idx_stored_summaries_continuity
ON stored_summaries(guild_id, channel_id, archive_granularity, created_at DESC)
WHERE archive_granularity = 'weekly';

-- Note: channel_id column may not exist in older schemas, so we use a partial index
-- that filters on archive_granularity='weekly' which is the primary use case.
-- For multi-channel summaries, source_channel_ids JSON is used for lookup.
