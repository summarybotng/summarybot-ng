-- ADR-056: Fix Wiki Schema - Remove foreign key constraints
-- The guilds table doesn't exist in our schema, so remove FK references

-- Drop existing tables (in reverse dependency order)
DROP TABLE IF EXISTS wiki_fts;
DROP INDEX IF EXISTS idx_wiki_pages_guild;
DROP INDEX IF EXISTS idx_wiki_pages_updated;
DROP INDEX IF EXISTS idx_wiki_pages_path;
DROP INDEX IF EXISTS idx_wiki_links_guild;
DROP INDEX IF EXISTS idx_wiki_log_operation;
DROP INDEX IF EXISTS idx_wiki_log_guild;
DROP INDEX IF EXISTS idx_wiki_sources_guild;
DROP INDEX IF EXISTS idx_wiki_contradictions_guild;
DROP INDEX IF EXISTS idx_wiki_contradictions_unresolved;
DROP TABLE IF EXISTS wiki_contradictions;
DROP TABLE IF EXISTS wiki_log;
DROP TABLE IF EXISTS wiki_links;
DROP TABLE IF EXISTS wiki_sources;
DROP TABLE IF EXISTS wiki_pages;

-- Recreate wiki_pages without FK constraint
CREATE TABLE IF NOT EXISTS wiki_pages (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    topics TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    source_refs TEXT DEFAULT '[]',
    inbound_links INTEGER DEFAULT 0,
    outbound_links INTEGER DEFAULT 0,
    confidence INTEGER DEFAULT 100,
    UNIQUE(guild_id, path)
);

-- Recreate wiki_links without FK constraint
CREATE TABLE IF NOT EXISTS wiki_links (
    from_page TEXT NOT NULL,
    to_page TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    link_text TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, from_page, to_page)
);

-- Recreate wiki_log without FK constraint
CREATE TABLE IF NOT EXISTS wiki_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    timestamp TEXT DEFAULT (datetime('now')),
    operation TEXT NOT NULL,
    details TEXT NOT NULL,
    agent_id TEXT
);

-- Recreate wiki_contradictions without FK constraint
CREATE TABLE IF NOT EXISTS wiki_contradictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    page_a TEXT NOT NULL,
    page_b TEXT NOT NULL,
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    detected_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    resolution TEXT
);

-- Recreate wiki_sources without FK constraint
CREATE TABLE IF NOT EXISTS wiki_sources (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    ingested_at TEXT DEFAULT (datetime('now'))
);

-- Recreate FTS virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
    path,
    title,
    content,
    topics,
    guild_id UNINDEXED,
    tokenize='porter unicode61'
);

-- Recreate indexes
CREATE INDEX IF NOT EXISTS idx_wiki_pages_guild ON wiki_pages(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_updated ON wiki_pages(updated_at);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_path ON wiki_pages(guild_id, path);
CREATE INDEX IF NOT EXISTS idx_wiki_links_guild ON wiki_links(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_log_operation ON wiki_log(operation);
CREATE INDEX IF NOT EXISTS idx_wiki_log_guild ON wiki_log(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_sources_guild ON wiki_sources(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_contradictions_guild ON wiki_contradictions(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_contradictions_unresolved ON wiki_contradictions(guild_id, resolved_at) WHERE resolved_at IS NULL;
