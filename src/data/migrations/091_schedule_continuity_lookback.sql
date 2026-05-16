-- ADR-087/ADR-089: Weekly Continuity and Lookback Period
-- Migration: Add continuity and time_range_hours columns to scheduled_tasks
-- Note: Migration 065 was skipped due to version numbering gap, so we add those columns here

-- Enable continuity for weekly summaries (originally in 065)
-- If column already exists, this will fail gracefully
ALTER TABLE scheduled_tasks ADD COLUMN enable_continuity INTEGER DEFAULT 0;

-- Lookback period: how far back to fetch messages (ADR-089)
ALTER TABLE scheduled_tasks ADD COLUMN time_range_hours INTEGER DEFAULT 24;

-- Add continuity tracking to stored_summaries (originally in 065)
-- These may already exist, handled gracefully
ALTER TABLE stored_summaries ADD COLUMN previous_summary_id TEXT;
ALTER TABLE stored_summaries ADD COLUMN continuity_week_number INTEGER;

-- Index for efficient lookup of previous weekly summaries (if not exists)
CREATE INDEX IF NOT EXISTS idx_stored_summaries_continuity
ON stored_summaries(guild_id, source_channel_ids, archive_granularity, created_at DESC);
