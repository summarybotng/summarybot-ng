-- ADR-012 Hotfix: Remove invalid foreign key reference to non-existent guilds table
--
-- Migration 009 defined: FOREIGN KEY (guild_id) REFERENCES guilds(id)
-- But no guilds table exists in any migration, causing:
-- "no such table - main.guilds" when PRAGMA foreign_keys=ON
--
-- SQLite doesn't support ALTER TABLE DROP CONSTRAINT, so we must:
-- 1. Create a new table without the invalid FK
-- 2. Copy all data
-- 3. Drop the old table
-- 4. Rename the new table

-- ============================================================================
-- STEP 1: Create new table without invalid foreign key
-- ============================================================================

CREATE TABLE IF NOT EXISTS stored_summaries_new (
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

    -- ADR-008: Source tracking
    source TEXT DEFAULT 'realtime',
    archive_period TEXT,
    archive_granularity TEXT,
    archive_source_key TEXT,

    -- ADR-012: Consolidation columns
    channel_id TEXT,
    channel_name TEXT,
    start_time TEXT,
    end_time TEXT,
    timezone TEXT DEFAULT 'UTC',
    message_count INTEGER DEFAULT 0,
    participant_count INTEGER DEFAULT 0,
    scope TEXT DEFAULT 'channel',
    category_id TEXT,
    category_name TEXT,

    -- Only keep valid foreign key (scheduled_tasks table exists)
    FOREIGN KEY (schedule_id) REFERENCES scheduled_tasks(id) ON DELETE SET NULL
);

-- ============================================================================
-- STEP 2: Copy all data from old table to new table
-- ============================================================================

INSERT INTO stored_summaries_new (
    id, guild_id, source_channel_ids, schedule_id,
    summary_json, created_at, viewed_at, pushed_at,
    push_deliveries, title, is_pinned, is_archived, tags,
    source, archive_period, archive_granularity, archive_source_key,
    channel_id, channel_name, start_time, end_time, timezone,
    message_count, participant_count, scope, category_id, category_name
)
SELECT
    id, guild_id, source_channel_ids, schedule_id,
    summary_json, created_at, viewed_at, pushed_at,
    push_deliveries, title, is_pinned, is_archived, tags,
    COALESCE(source, 'realtime'), archive_period, archive_granularity, archive_source_key,
    channel_id, channel_name, start_time, end_time, COALESCE(timezone, 'UTC'),
    COALESCE(message_count, 0), COALESCE(participant_count, 0), COALESCE(scope, 'channel'), category_id, category_name
FROM stored_summaries;

-- ============================================================================
-- STEP 3: Drop old table and rename new table
-- ============================================================================

DROP TABLE stored_summaries;

ALTER TABLE stored_summaries_new RENAME TO stored_summaries;

-- ============================================================================
-- STEP 4: Recreate indexes (they don't survive the rename)
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_stored_summaries_guild ON stored_summaries(guild_id);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_created ON stored_summaries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_schedule ON stored_summaries(schedule_id);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_pinned ON stored_summaries(guild_id, is_pinned) WHERE is_pinned = TRUE;
CREATE INDEX IF NOT EXISTS idx_stored_summaries_archived ON stored_summaries(guild_id, is_archived);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_time_range ON stored_summaries(guild_id, start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_channel ON stored_summaries(guild_id, channel_id);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_scope ON stored_summaries(guild_id, scope);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_source ON stored_summaries(guild_id, source);

-- ============================================================================
-- STEP 5: Update schema version
-- ============================================================================

INSERT OR REPLACE INTO schema_version (version, applied_at, description)
VALUES (13, datetime('now'), 'Fix invalid foreign key reference to non-existent guilds table');
