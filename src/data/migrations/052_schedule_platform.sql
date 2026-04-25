-- ADR-051: Add platform column to scheduled_tasks for multi-platform support
-- Migration: 052_schedule_platform.sql

-- Add platform column to scheduled_tasks
ALTER TABLE scheduled_tasks ADD COLUMN platform TEXT DEFAULT 'discord';

-- Add index for platform-based queries
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_platform ON scheduled_tasks(platform);

-- Update existing tasks to have explicit discord platform
UPDATE scheduled_tasks SET platform = 'discord' WHERE platform IS NULL;
