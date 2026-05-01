-- ADR-080: Wiki Perspective Filtering
-- Add wiki_allowed_perspectives setting to guild_configs
-- Default to ["general"] - only general perspective summaries are auto-ingested

ALTER TABLE guild_configs
ADD COLUMN wiki_allowed_perspectives TEXT DEFAULT '["general"]';
