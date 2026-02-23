-- ADR-014: Discord Push Templates with Thread Support
-- Migration: Add guild_push_templates table for customizable push formatting

-- ============================================================================
-- STEP 1: Create guild_push_templates table
-- ============================================================================

CREATE TABLE IF NOT EXISTS guild_push_templates (
    guild_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL DEFAULT 1,
    template_json TEXT NOT NULL,  -- JSON serialized PushTemplate
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT  -- User ID who configured
);

-- Index for finding recently updated templates
CREATE INDEX IF NOT EXISTS idx_guild_push_templates_updated
    ON guild_push_templates(updated_at DESC);

-- ============================================================================
-- STEP 2: Update schema version
-- ============================================================================

INSERT OR REPLACE INTO schema_version (version, applied_at, description)
VALUES (14, datetime('now'), 'ADR-014: Guild push templates for Discord summary delivery');
