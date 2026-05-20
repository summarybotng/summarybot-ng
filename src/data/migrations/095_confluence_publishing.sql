-- ADR-099: Confluence Publishing MVP
-- Enables publishing summaries to Confluence pages with per-tenant settings

-- Per-guild Confluence settings (admin-only configuration)
CREATE TABLE IF NOT EXISTS confluence_settings (
    guild_id TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    base_url TEXT,                -- e.g., https://company.atlassian.net
    space_key TEXT,               -- e.g., TEAM
    parent_page_id TEXT,          -- Optional parent page for hierarchy
    email TEXT,                   -- Service account email
    api_token_encrypted TEXT,     -- API token (encrypted)
    page_title_template TEXT DEFAULT '{title}',  -- Template for page titles
    configured_by TEXT,
    configured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Publication tracking for idempotent updates
CREATE TABLE IF NOT EXISTS confluence_publications (
    id TEXT PRIMARY KEY,
    summary_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    page_url TEXT NOT NULL,
    page_version INTEGER DEFAULT 1,
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_by TEXT NOT NULL,
    last_updated_at TIMESTAMP,
    status TEXT DEFAULT 'published',
    FOREIGN KEY (summary_id) REFERENCES stored_summaries(id) ON DELETE CASCADE
);

-- Index for quick lookup by summary
CREATE INDEX IF NOT EXISTS idx_confluence_publications_summary ON confluence_publications(summary_id);

-- Unique index on page_id to prevent duplicate page tracking
CREATE UNIQUE INDEX IF NOT EXISTS idx_confluence_publications_page ON confluence_publications(page_id);

-- Index for guild-based queries
CREATE INDEX IF NOT EXISTS idx_confluence_publications_guild ON confluence_publications(guild_id);
