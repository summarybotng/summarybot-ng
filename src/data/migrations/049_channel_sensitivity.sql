-- ADR-046: Channel sensitivity configuration (Phase 2)
-- Migration: Add channel sensitivity config to guild_configs and tracking to stored_summaries

-- Add sensitive channels config to guild_configs
-- Using JSON columns for flexible array storage
ALTER TABLE guild_configs ADD COLUMN sensitive_channels TEXT DEFAULT '[]';
ALTER TABLE guild_configs ADD COLUMN sensitive_categories TEXT DEFAULT '[]';
ALTER TABLE guild_configs ADD COLUMN auto_mark_private_sensitive BOOLEAN DEFAULT TRUE;

-- Add index for lookups
CREATE INDEX IF NOT EXISTS idx_guild_configs_auto_sensitive ON guild_configs(auto_mark_private_sensitive);

-- Add contains_sensitive flag to stored_summaries for filtering
ALTER TABLE stored_summaries ADD COLUMN contains_sensitive_channels BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_stored_summaries_sensitive ON stored_summaries(contains_sensitive_channels);
