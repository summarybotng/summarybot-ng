-- ADR-005: Summary Delivery Destinations
-- Migration: Add stored_summaries table for dashboard delivery

-- Table for storing summaries delivered to the DASHBOARD destination
CREATE TABLE IF NOT EXISTS stored_summaries (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    source_channel_ids TEXT NOT NULL,  -- JSON array of channel IDs
    schedule_id TEXT,                   -- FK to scheduled_tasks if from a schedule

    -- Summary content (full SummaryResult as JSON)
    summary_json TEXT NOT NULL,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    viewed_at TIMESTAMP,
    pushed_at TIMESTAMP,

    -- Delivery tracking (JSON array of push delivery records)
    push_deliveries TEXT,

    -- Metadata
    title TEXT NOT NULL,
    is_pinned BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    tags TEXT,  -- JSON array of tag strings

    -- Foreign keys
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON DELETE CASCADE,
    FOREIGN KEY (schedule_id) REFERENCES scheduled_tasks(id) ON DELETE SET NULL
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_stored_summaries_guild ON stored_summaries(guild_id);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_created ON stored_summaries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_schedule ON stored_summaries(schedule_id);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_pinned ON stored_summaries(guild_id, is_pinned) WHERE is_pinned = TRUE;
CREATE INDEX IF NOT EXISTS idx_stored_summaries_archived ON stored_summaries(guild_id, is_archived);
