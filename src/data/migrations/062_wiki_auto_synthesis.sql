-- ADR-076: Continuous Wiki Synthesis

-- Guild setting for auto-synthesis toggle (defaults to TRUE)
-- When enabled, wiki pages are automatically re-synthesized after new content is ingested
ALTER TABLE guild_configs ADD COLUMN wiki_auto_synthesis BOOLEAN DEFAULT TRUE;
