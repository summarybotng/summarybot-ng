-- ADR-056: Compounding Wiki Schema
-- Wiki pages, links, logs, contradictions, and sources

-- Wiki pages metadata
CREATE TABLE IF NOT EXISTS wiki_pages (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    topics TEXT DEFAULT '[]',  -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    source_refs TEXT DEFAULT '[]',  -- JSON array of source IDs
    inbound_links INTEGER DEFAULT 0,
    outbound_links INTEGER DEFAULT 0,
    confidence INTEGER DEFAULT 100,  -- 0-100
    UNIQUE(guild_id, path),
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON DELETE CASCADE
);

-- Page links (for orphan detection, link graph)
CREATE TABLE IF NOT EXISTS wiki_links (
    from_page TEXT NOT NULL,
    to_page TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    link_text TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, from_page, to_page),
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON DELETE CASCADE
);

-- Operation log (append-only)
CREATE TABLE IF NOT EXISTS wiki_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    timestamp TEXT DEFAULT (datetime('now')),
    operation TEXT NOT NULL,  -- ingest, query, query_persist, lint
    details TEXT NOT NULL,  -- JSON
    agent_id TEXT,
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON DELETE CASCADE
);

-- Contradictions (for human review)
CREATE TABLE IF NOT EXISTS wiki_contradictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    page_a TEXT NOT NULL,
    page_b TEXT NOT NULL,
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    detected_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    resolution TEXT,
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON DELETE CASCADE
);

-- Source documents (immutable)
CREATE TABLE IF NOT EXISTS wiki_sources (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- summary, archive, document
    title TEXT,
    content TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',  -- JSON
    ingested_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON DELETE CASCADE
);

-- Full-text search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
    path,
    title,
    content,
    topics,
    guild_id UNINDEXED,
    tokenize='porter unicode61'
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_wiki_pages_guild ON wiki_pages(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_updated ON wiki_pages(updated_at);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_path ON wiki_pages(guild_id, path);
CREATE INDEX IF NOT EXISTS idx_wiki_links_guild ON wiki_links(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_log_operation ON wiki_log(operation);
CREATE INDEX IF NOT EXISTS idx_wiki_log_guild ON wiki_log(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_sources_guild ON wiki_sources(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_contradictions_guild ON wiki_contradictions(guild_id);
CREATE INDEX IF NOT EXISTS idx_wiki_contradictions_unresolved ON wiki_contradictions(guild_id, resolved_at) WHERE resolved_at IS NULL;

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS wiki_fts_insert AFTER INSERT ON wiki_pages BEGIN
    INSERT INTO wiki_fts(path, title, content, topics, guild_id)
    VALUES (NEW.path, NEW.title, NEW.content, NEW.topics, NEW.guild_id);
END;

CREATE TRIGGER IF NOT EXISTS wiki_fts_update AFTER UPDATE ON wiki_pages BEGIN
    DELETE FROM wiki_fts WHERE path = OLD.path AND guild_id = OLD.guild_id;
    INSERT INTO wiki_fts(path, title, content, topics, guild_id)
    VALUES (NEW.path, NEW.title, NEW.content, NEW.topics, NEW.guild_id);
END;

CREATE TRIGGER IF NOT EXISTS wiki_fts_delete AFTER DELETE ON wiki_pages BEGIN
    DELETE FROM wiki_fts WHERE path = OLD.path AND guild_id = OLD.guild_id;
END;
