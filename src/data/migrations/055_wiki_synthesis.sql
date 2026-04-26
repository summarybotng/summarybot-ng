-- ADR-063: Wiki Page Tabs (Updates + Synthesis)
-- Add synthesis columns to wiki_pages for LLM-generated summaries

ALTER TABLE wiki_pages ADD COLUMN synthesis TEXT;
ALTER TABLE wiki_pages ADD COLUMN synthesis_updated_at TEXT;
ALTER TABLE wiki_pages ADD COLUMN synthesis_source_count INTEGER DEFAULT 0;
