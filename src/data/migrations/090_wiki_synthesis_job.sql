-- ADR-076 Amendment: Periodic Wiki Synthesis Job
-- Adds settings for background job that regenerates dirty wiki pages

-- Guild settings for periodic synthesis job
ALTER TABLE guild_configs ADD COLUMN wiki_synthesis_job_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE guild_configs ADD COLUMN wiki_synthesis_job_last_run TEXT;
ALTER TABLE guild_configs ADD COLUMN wiki_synthesis_job_interval_hours INTEGER DEFAULT 24;

-- Index for finding dirty pages efficiently
CREATE INDEX IF NOT EXISTS idx_wiki_pages_dirty ON wiki_pages(guild_id, updated_at, synthesis_updated_at);
