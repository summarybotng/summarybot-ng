-- ADR-084: Bulk Wiki Regeneration
-- Track wiki regeneration jobs for async processing

CREATE TABLE IF NOT EXISTS wiki_regeneration_jobs (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    scope TEXT NOT NULL,  -- 'selected', 'date_range', 'full'
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
    summary_ids TEXT,  -- JSON array of summary IDs for scope='selected'
    start_date TEXT,  -- For scope='date_range'
    end_date TEXT,  -- For scope='date_range'
    page_count INTEGER NOT NULL DEFAULT 0,
    processed_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_wiki_regen_guild ON wiki_regeneration_jobs(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_regen_status ON wiki_regeneration_jobs(status);
CREATE INDEX IF NOT EXISTS idx_wiki_regen_created ON wiki_regeneration_jobs(created_at);
