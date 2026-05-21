-- Migration 097: Add title_template to scheduled_tasks
-- Allows users to customize summary titles with template variables
-- Variables: {date}, {time}, {datetime}, {channels}, {channel_count}, {platform}, {schedule}, {period}

ALTER TABLE scheduled_tasks ADD COLUMN title_template TEXT DEFAULT NULL;

-- Add index for querying schedules with custom titles
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_title_template ON scheduled_tasks(title_template) WHERE title_template IS NOT NULL;
