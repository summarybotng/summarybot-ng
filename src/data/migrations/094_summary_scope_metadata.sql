-- ADR-098: Summary Scope Metadata
-- Add scope tracking to stored_summaries for filtering and display

-- Add scope type column (guild, category, channel)
ALTER TABLE stored_summaries ADD COLUMN scope_type TEXT;

-- Add category info for category-scoped summaries
ALTER TABLE stored_summaries ADD COLUMN category_id TEXT;
ALTER TABLE stored_summaries ADD COLUMN category_name TEXT;

-- Index for scope filtering
CREATE INDEX IF NOT EXISTS idx_stored_summaries_scope ON stored_summaries(scope_type);
CREATE INDEX IF NOT EXISTS idx_stored_summaries_category ON stored_summaries(category_id);

-- Backfill scope_type from archive_source_key
-- Pattern: discord:123 = guild, discord:123:category:456 = category, discord:123:channel:789 = channel
UPDATE stored_summaries
SET scope_type = CASE
    WHEN archive_source_key LIKE '%:category:%' THEN 'category'
    WHEN archive_source_key LIKE '%:channel:%' THEN 'channel'
    WHEN archive_source_key IS NOT NULL THEN 'guild'
    WHEN json_array_length(source_channel_ids) = 1 THEN 'channel'
    WHEN json_array_length(source_channel_ids) > 1 THEN 'guild'
    ELSE 'channel'
END
WHERE scope_type IS NULL;

-- Extract category_id from archive_source_key for category summaries
-- Pattern: discord:123:category:456 -> 456
UPDATE stored_summaries
SET category_id = SUBSTR(
    archive_source_key,
    INSTR(archive_source_key, ':category:') + 10
)
WHERE scope_type = 'category' AND category_id IS NULL AND archive_source_key LIKE '%:category:%';
