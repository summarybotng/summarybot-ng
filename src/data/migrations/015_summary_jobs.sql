-- Migration 015: Unified Job Tracking (ADR-013)
-- Persistent tracking for all summary generation jobs

CREATE TABLE IF NOT EXISTS summary_jobs (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    job_type TEXT NOT NULL,  -- 'manual', 'scheduled', 'retrospective'
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed', 'cancelled', 'paused'

    -- Job configuration
    scope TEXT,  -- 'channel', 'category', 'guild'
    channel_ids TEXT,  -- JSON array
    category_id TEXT,
    schedule_id TEXT,  -- For scheduled jobs

    -- Time range for summary
    period_start TIMESTAMP,
    period_end TIMESTAMP,

    -- Retrospective-specific
    date_range_start DATE,
    date_range_end DATE,
    granularity TEXT,  -- 'daily', 'weekly', 'monthly'
    summary_type TEXT,  -- 'brief', 'detailed', 'comprehensive'
    perspective TEXT,  -- 'general', 'developer', etc.
    force_regenerate INTEGER DEFAULT 0,

    -- Progress tracking
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 1,
    progress_message TEXT,
    current_period TEXT,  -- For retrospective: current date being processed

    -- Cost tracking
    cost_usd REAL DEFAULT 0,
    tokens_input INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,

    -- Results
    summary_id TEXT,  -- Link to generated summary (for single-summary jobs)
    summary_ids TEXT,  -- JSON array of summary IDs (for multi-day jobs)
    error TEXT,
    pause_reason TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Metadata
    created_by TEXT,  -- User ID who initiated
    source_key TEXT,  -- For retrospective: 'discord:guild_id'
    server_name TEXT,
    metadata TEXT  -- JSON for additional data
);

CREATE INDEX IF NOT EXISTS idx_summary_jobs_guild ON summary_jobs(guild_id);
CREATE INDEX IF NOT EXISTS idx_summary_jobs_status ON summary_jobs(status);
CREATE INDEX IF NOT EXISTS idx_summary_jobs_type ON summary_jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_summary_jobs_created ON summary_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_summary_jobs_guild_status ON summary_jobs(guild_id, status);
