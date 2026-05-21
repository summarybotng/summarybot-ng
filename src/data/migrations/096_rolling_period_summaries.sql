-- ADR-101: Rolling Period Summaries
-- Migration: Add rolling period tracking for accumulating summaries

-- Add rolling period columns to stored_summaries
-- rolling_period_type: 'weekly', 'biweekly', 'monthly' (null for non-rolling)
ALTER TABLE stored_summaries ADD COLUMN rolling_period_type TEXT;

-- rolling_period_start: First day of the period (e.g., 2026-01-05 for week starting Sunday)
ALTER TABLE stored_summaries ADD COLUMN rolling_period_start DATE;

-- rolling_accumulated_through: Timestamp of last message included in accumulation
ALTER TABLE stored_summaries ADD COLUMN rolling_accumulated_through TIMESTAMP;

-- rolling_finalized: True when period is complete (no more accumulations)
ALTER TABLE stored_summaries ADD COLUMN rolling_finalized INTEGER DEFAULT 0;

-- rolling_accumulation_count: Number of accumulation passes (1 = initial, 2+ = updates)
ALTER TABLE stored_summaries ADD COLUMN rolling_accumulation_count INTEGER DEFAULT 0;

-- rolling_raw_content: JSON array of daily content segments for re-summarization
-- Used by hybrid and resummarize strategies
ALTER TABLE stored_summaries ADD COLUMN rolling_raw_content TEXT;

-- Index for finding active (non-finalized) rolling summaries by guild/channel/schedule
CREATE INDEX IF NOT EXISTS idx_rolling_active
ON stored_summaries(guild_id, schedule_id, rolling_period_type, rolling_finalized)
WHERE rolling_period_type IS NOT NULL AND rolling_finalized = 0;

-- Add rolling period settings to scheduled_tasks
-- rolling_period: 'weekly', 'biweekly', 'monthly' (null for standard schedules)
ALTER TABLE scheduled_tasks ADD COLUMN rolling_period TEXT;

-- rolling_end_day: Day of week to finalize (0=Sun, 6=Sat) for weekly
ALTER TABLE scheduled_tasks ADD COLUMN rolling_end_day INTEGER;

-- accumulation_strategy: 'append', 'resummarize', 'hybrid'
ALTER TABLE scheduled_tasks ADD COLUMN accumulation_strategy TEXT DEFAULT 'hybrid';
