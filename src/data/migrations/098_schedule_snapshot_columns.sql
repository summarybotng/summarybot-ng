-- ADR-109: Bi-Directional Schedule-Summary Linking
-- Add snapshot columns to preserve schedule information after deletion

-- Schedule name at time of summary creation
-- Preserved even if schedule is later deleted (ON DELETE SET NULL on FK)
ALTER TABLE stored_summaries ADD COLUMN schedule_name_snapshot TEXT;

-- Index for finding summaries by deleted schedules (where schedule_id is null but snapshot exists)
CREATE INDEX IF NOT EXISTS idx_stored_summaries_schedule_snapshot
ON stored_summaries(guild_id, schedule_name_snapshot)
WHERE schedule_name_snapshot IS NOT NULL AND schedule_id IS NULL;
