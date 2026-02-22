-- ADR-012: Summaries UI Consolidation
-- Migration: Consolidate summaries and stored_summaries tables
--
-- This migration:
-- 1. Adds missing columns to stored_summaries for full compatibility
-- 2. Migrates existing data from summaries to stored_summaries
-- 3. Marks summaries table as deprecated (kept for rollback safety)

-- ============================================================================
-- STEP 1: Add missing columns to stored_summaries for unified access
-- ============================================================================

-- Add channel_id column (stored_summaries uses source_channel_ids as JSON array)
-- We'll use the first channel as primary for backwards compatibility
ALTER TABLE stored_summaries ADD COLUMN channel_id TEXT;

-- Add channel_name for display (extracted from summary_json or set explicitly)
ALTER TABLE stored_summaries ADD COLUMN channel_name TEXT;

-- Add explicit time range columns (also in summary_json but useful for queries)
ALTER TABLE stored_summaries ADD COLUMN start_time TEXT;
ALTER TABLE stored_summaries ADD COLUMN end_time TEXT;
ALTER TABLE stored_summaries ADD COLUMN timezone TEXT DEFAULT 'UTC';

-- Add explicit stats columns for efficient queries
ALTER TABLE stored_summaries ADD COLUMN message_count INTEGER DEFAULT 0;
ALTER TABLE stored_summaries ADD COLUMN participant_count INTEGER DEFAULT 0;

-- Add scope column for ADR-011 unified scope selection
ALTER TABLE stored_summaries ADD COLUMN scope TEXT DEFAULT 'channel';
ALTER TABLE stored_summaries ADD COLUMN category_id TEXT;
ALTER TABLE stored_summaries ADD COLUMN category_name TEXT;

-- ============================================================================
-- STEP 2: Create indexes for efficient unified queries
-- ============================================================================

-- Index for time-range queries
CREATE INDEX IF NOT EXISTS idx_stored_summaries_time_range
    ON stored_summaries(guild_id, start_time, end_time);

-- Index for channel queries
CREATE INDEX IF NOT EXISTS idx_stored_summaries_channel
    ON stored_summaries(guild_id, channel_id);

-- Index for scope queries
CREATE INDEX IF NOT EXISTS idx_stored_summaries_scope
    ON stored_summaries(guild_id, scope);

-- ============================================================================
-- STEP 3: Migrate data from summaries to stored_summaries
-- ============================================================================

-- Insert summaries that don't already exist in stored_summaries
-- Mark them as source='manual' since they came from the Generate button
INSERT OR IGNORE INTO stored_summaries (
    id,
    guild_id,
    source_channel_ids,
    channel_id,
    channel_name,
    summary_json,
    title,
    source,
    start_time,
    end_time,
    message_count,
    scope,
    created_at,
    is_pinned,
    is_archived
)
SELECT
    s.id,
    s.guild_id,
    json_array(s.channel_id),  -- Convert single channel to JSON array
    s.channel_id,
    COALESCE(
        json_extract(s.metadata, '$.channel_name'),
        json_extract(s.context, '$.channel_name'),
        'Unknown Channel'
    ),
    -- Construct summary_json from individual columns
    json_object(
        'id', s.id,
        'channel_id', s.channel_id,
        'guild_id', s.guild_id,
        'summary_text', s.summary_text,
        'key_points', json(s.key_points),
        'action_items', json(s.action_items),
        'technical_terms', json(s.technical_terms),
        'participants', json(s.participants),
        'message_count', s.message_count,
        'start_time', s.start_time,
        'end_time', s.end_time,
        'metadata', json(s.metadata),
        'context', json(s.context)
    ),
    'Summary ' || date(s.created_at),  -- Generate title
    'manual',  -- Source type for Generate button summaries
    s.start_time,
    s.end_time,
    s.message_count,
    'channel',  -- Default scope
    s.created_at,
    0,  -- Not pinned
    0   -- Not archived
FROM summaries s
WHERE NOT EXISTS (
    SELECT 1 FROM stored_summaries ss WHERE ss.id = s.id
);

-- ============================================================================
-- STEP 4: Update schema version
-- ============================================================================

INSERT OR REPLACE INTO schema_version (version, applied_at, description)
VALUES (12, datetime('now'), 'ADR-012: Consolidate summaries into stored_summaries table');
