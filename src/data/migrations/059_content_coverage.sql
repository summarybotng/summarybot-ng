-- ADR-072: Content Coverage Tracking
-- Tracks what percentage of server content has been summarized

-- Coverage summary per channel
CREATE TABLE IF NOT EXISTS content_coverage (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    platform TEXT NOT NULL DEFAULT 'discord',

    -- Content boundaries (from platform inventory)
    content_start TEXT,          -- Earliest message timestamp
    content_end TEXT,            -- Latest message timestamp
    estimated_messages INTEGER,  -- Estimated message count

    -- Coverage boundaries (from summaries)
    covered_start TEXT,          -- Earliest summarized timestamp
    covered_end TEXT,            -- Latest summarized timestamp
    summary_count INTEGER DEFAULT 0,

    -- Computed metrics
    coverage_percent REAL DEFAULT 0,  -- 0-100
    gap_count INTEGER DEFAULT 0,
    covered_days INTEGER DEFAULT 0,
    total_days INTEGER DEFAULT 0,

    -- Timestamps
    last_summary_at TEXT,
    last_computed_at TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now')),

    UNIQUE(guild_id, channel_id, platform)
);

-- Individual coverage gaps
CREATE TABLE IF NOT EXISTS coverage_gaps (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    platform TEXT NOT NULL DEFAULT 'discord',

    -- Gap boundaries
    gap_start TEXT NOT NULL,
    gap_end TEXT NOT NULL,
    gap_days INTEGER,

    -- Backfill status
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, scheduled, running, complete, failed, skipped
    priority INTEGER DEFAULT 0,              -- Higher = process first

    -- Backfill tracking
    job_id TEXT,
    summary_id TEXT,                         -- If complete, the summary that filled this gap
    error_message TEXT,

    -- Timestamps
    scheduled_for TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (summary_id) REFERENCES stored_summaries(id)
);

-- Backfill schedules per guild
CREATE TABLE IF NOT EXISTS backfill_schedules (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    guild_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'discord',

    -- Configuration
    channels TEXT,              -- JSON array of channel IDs, null = all
    priority_mode TEXT DEFAULT 'oldest_first',  -- oldest_first, newest_first, largest_gaps
    rate_limit INTEGER DEFAULT 10,              -- Summaries per hour

    -- Status
    enabled BOOLEAN DEFAULT TRUE,
    paused BOOLEAN DEFAULT FALSE,

    -- Progress
    total_gaps INTEGER DEFAULT 0,
    completed_gaps INTEGER DEFAULT 0,
    failed_gaps INTEGER DEFAULT 0,

    -- Timestamps
    last_run_at TEXT,
    next_run_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),

    UNIQUE(guild_id, platform)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_content_coverage_guild ON content_coverage(guild_id);
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_guild_status ON coverage_gaps(guild_id, status);
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_pending ON coverage_gaps(guild_id, status, priority DESC) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_backfill_schedules_next ON backfill_schedules(next_run_at) WHERE enabled = TRUE AND paused = FALSE;
