-- Migration 019: Guild Prompt Templates (ADR-034)
-- Adds support for guild-level reusable prompt templates

-- Create the guild_prompt_templates table
CREATE TABLE IF NOT EXISTS guild_prompt_templates (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    content TEXT NOT NULL,
    based_on_default TEXT,  -- e.g., "developer/detailed" if seeded from default
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(guild_id, name)
);

-- Index for efficient guild lookups
CREATE INDEX IF NOT EXISTS idx_prompt_templates_guild ON guild_prompt_templates(guild_id);

-- Add prompt_template_id to scheduled_tasks
-- References a template from guild_prompt_templates, SET NULL on delete
ALTER TABLE scheduled_tasks ADD COLUMN prompt_template_id TEXT REFERENCES guild_prompt_templates(id) ON DELETE SET NULL;
