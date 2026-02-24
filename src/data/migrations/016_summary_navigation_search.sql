-- ADR-020: Summary Navigation and Search
-- Migration: Add navigation index and FTS5 full-text search

-- Phase 1: Navigation index for efficient prev/next queries
-- (guild_id, source, created_at) allows filtering by source type
CREATE INDEX IF NOT EXISTS idx_stored_summaries_nav
ON stored_summaries(guild_id, source, created_at);

-- Phase 2: Full-text search using SQLite FTS5
-- Virtual table for searching summary content
CREATE VIRTUAL TABLE IF NOT EXISTS summary_fts USING fts5(
    summary_id UNINDEXED,  -- Not searchable, just for joining
    guild_id UNINDEXED,    -- Not searchable, just for filtering
    summary_text,          -- Main summary content
    key_points,            -- Bullet points from summary
    action_items,          -- Action items text
    participants,          -- Participant names/IDs
    technical_terms,       -- Technical terms mentioned
    tokenize='porter unicode61'  -- Porter stemming + unicode support
);

-- Populate FTS from existing summaries
INSERT INTO summary_fts (summary_id, guild_id, summary_text, key_points, action_items, participants, technical_terms)
SELECT
    id,
    guild_id,
    COALESCE(json_extract(summary_json, '$.summary_text'), ''),
    COALESCE(
        (SELECT GROUP_CONCAT(value, ' ') FROM json_each(json_extract(summary_json, '$.key_points'))),
        ''
    ),
    COALESCE(
        (SELECT GROUP_CONCAT(json_extract(value, '$.text'), ' ') FROM json_each(json_extract(summary_json, '$.action_items'))),
        ''
    ),
    COALESCE(
        (SELECT GROUP_CONCAT(
            COALESCE(json_extract(value, '$.display_name'), '') || ' ' ||
            COALESCE(json_extract(value, '$.user_id'), ''),
            ' '
        ) FROM json_each(json_extract(summary_json, '$.participants'))),
        ''
    ),
    COALESCE(
        (SELECT GROUP_CONCAT(value, ' ') FROM json_each(json_extract(summary_json, '$.technical_terms'))),
        ''
    )
FROM stored_summaries;

-- Triggers to keep FTS in sync with main table

-- Insert trigger
CREATE TRIGGER IF NOT EXISTS summary_fts_insert AFTER INSERT ON stored_summaries
BEGIN
    INSERT INTO summary_fts (summary_id, guild_id, summary_text, key_points, action_items, participants, technical_terms)
    VALUES (
        NEW.id,
        NEW.guild_id,
        COALESCE(json_extract(NEW.summary_json, '$.summary_text'), ''),
        COALESCE(
            (SELECT GROUP_CONCAT(value, ' ') FROM json_each(json_extract(NEW.summary_json, '$.key_points'))),
            ''
        ),
        COALESCE(
            (SELECT GROUP_CONCAT(json_extract(value, '$.text'), ' ') FROM json_each(json_extract(NEW.summary_json, '$.action_items'))),
            ''
        ),
        COALESCE(
            (SELECT GROUP_CONCAT(
                COALESCE(json_extract(value, '$.display_name'), '') || ' ' ||
                COALESCE(json_extract(value, '$.user_id'), ''),
                ' '
            ) FROM json_each(json_extract(NEW.summary_json, '$.participants'))),
            ''
        ),
        COALESCE(
            (SELECT GROUP_CONCAT(value, ' ') FROM json_each(json_extract(NEW.summary_json, '$.technical_terms'))),
            ''
        )
    );
END;

-- Delete trigger
CREATE TRIGGER IF NOT EXISTS summary_fts_delete AFTER DELETE ON stored_summaries
BEGIN
    DELETE FROM summary_fts WHERE summary_id = OLD.id;
END;

-- Update trigger (delete + insert approach for FTS)
CREATE TRIGGER IF NOT EXISTS summary_fts_update AFTER UPDATE ON stored_summaries
BEGIN
    DELETE FROM summary_fts WHERE summary_id = OLD.id;
    INSERT INTO summary_fts (summary_id, guild_id, summary_text, key_points, action_items, participants, technical_terms)
    VALUES (
        NEW.id,
        NEW.guild_id,
        COALESCE(json_extract(NEW.summary_json, '$.summary_text'), ''),
        COALESCE(
            (SELECT GROUP_CONCAT(value, ' ') FROM json_each(json_extract(NEW.summary_json, '$.key_points'))),
            ''
        ),
        COALESCE(
            (SELECT GROUP_CONCAT(json_extract(value, '$.text'), ' ') FROM json_each(json_extract(NEW.summary_json, '$.action_items'))),
            ''
        ),
        COALESCE(
            (SELECT GROUP_CONCAT(
                COALESCE(json_extract(value, '$.display_name'), '') || ' ' ||
                COALESCE(json_extract(value, '$.user_id'), ''),
                ' '
            ) FROM json_each(json_extract(NEW.summary_json, '$.participants'))),
            ''
        ),
        COALESCE(
            (SELECT GROUP_CONCAT(value, ' ') FROM json_each(json_extract(NEW.summary_json, '$.technical_terms'))),
            ''
        )
    );
END;
