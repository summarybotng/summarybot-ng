-- ADR-064: Wiki Navigation Filters
-- ADR-065: Wiki Synthesis Rating & Regeneration Controls

-- Add rating and model tracking to wiki_pages
ALTER TABLE wiki_pages ADD COLUMN rating_sum INTEGER DEFAULT 0;
ALTER TABLE wiki_pages ADD COLUMN rating_count INTEGER DEFAULT 0;
ALTER TABLE wiki_pages ADD COLUMN synthesis_model TEXT;

-- Create indexes for filtering
CREATE INDEX IF NOT EXISTS idx_wiki_pages_updated_at ON wiki_pages(guild_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_created_at ON wiki_pages(guild_id, created_at);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_rating ON wiki_pages(guild_id, rating_count);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_synthesis_model ON wiki_pages(guild_id, synthesis_model);

-- Synthesis ratings table
CREATE TABLE IF NOT EXISTS wiki_synthesis_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    page_path TEXT NOT NULL,
    user_id TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    feedback TEXT,
    synthesis_model TEXT,
    synthesis_version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (guild_id, page_path, user_id)
);

CREATE INDEX IF NOT EXISTS idx_wiki_ratings_page ON wiki_synthesis_ratings(guild_id, page_path);
