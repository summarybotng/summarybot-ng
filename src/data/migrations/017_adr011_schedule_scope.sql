-- Migration 017: Add ADR-011 scope fields to scheduled_tasks
-- Adds support for channel/category/guild scope with runtime resolution

-- Add scope column (channel, category, guild)
ALTER TABLE scheduled_tasks ADD COLUMN scope TEXT DEFAULT 'channel';

-- Add channel_ids for multi-channel support (JSON array)
ALTER TABLE scheduled_tasks ADD COLUMN channel_ids TEXT DEFAULT '[]';

-- Add category_id for category scope
ALTER TABLE scheduled_tasks ADD COLUMN category_id TEXT;

-- Add excluded_channel_ids for category/guild scope (JSON array)
ALTER TABLE scheduled_tasks ADD COLUMN excluded_channel_ids TEXT DEFAULT '[]';

-- Add resolve_category_at_runtime flag
ALTER TABLE scheduled_tasks ADD COLUMN resolve_category_at_runtime INTEGER DEFAULT 0;

-- Add timezone column (was missing)
ALTER TABLE scheduled_tasks ADD COLUMN timezone TEXT DEFAULT 'UTC';

-- Create index for scope queries
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_scope ON scheduled_tasks(scope);

-- Migrate existing tasks: set scope based on existing data
-- Tasks with multiple channels (in JSON destinations or cross-channel pattern)
-- will need manual review, default to 'channel' scope
UPDATE scheduled_tasks SET scope = 'channel' WHERE scope IS NULL;
