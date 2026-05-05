-- ADR-057: RuVector Foundation Schema
-- Knowledge units, vector embeddings, GNN edges, and learning signals

-- Knowledge units: Atomic facts extracted from summaries/messages
CREATE TABLE IF NOT EXISTS wiki_knowledge_units (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    content TEXT NOT NULL,
    unit_type TEXT NOT NULL,  -- claim, decision, question, action_item, context
    source_id TEXT NOT NULL,  -- Reference to summary or message
    source_type TEXT NOT NULL,  -- summary, message, archive, human_edit
    source_channel TEXT,
    source_date TEXT,
    embedding BLOB,  -- 1536-dim float32 vector (text-embedding-3-small)
    embedding_model TEXT DEFAULT 'text-embedding-3-small',
    confidence REAL DEFAULT 1.0,  -- 0-1, human edits get 1.0
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- GNN edges: Inferred relationships between knowledge units
CREATE TABLE IF NOT EXISTS wiki_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    from_unit_id TEXT NOT NULL,
    to_unit_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,  -- relates_to, depends_on, contradicts, supersedes, supports
    weight REAL DEFAULT 1.0,  -- Confidence of the edge
    inferred_by TEXT DEFAULT 'gnn',  -- gnn, manual, coherence_gate
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(guild_id, from_unit_id, to_unit_id, edge_type),
    FOREIGN KEY (from_unit_id) REFERENCES wiki_knowledge_units(id),
    FOREIGN KEY (to_unit_id) REFERENCES wiki_knowledge_units(id)
);

-- SONA learning signals: Track user interactions for relevance learning
CREATE TABLE IF NOT EXISTS wiki_learning_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,  -- search_click, dwell, refinement, feedback, page_view
    unit_id TEXT,  -- Optional: specific unit interacted with
    context TEXT NOT NULL,  -- JSON: query, results, position, dwell_time, etc.
    user_id TEXT,  -- Optional: anonymized after 30 days
    created_at TEXT DEFAULT (datetime('now'))
);

-- Coherence validations: Track validation results for audit
CREATE TABLE IF NOT EXISTS wiki_coherence_validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    validation_type TEXT NOT NULL,  -- contradiction, unsupported, drift
    status TEXT NOT NULL,  -- approved, rejected, flagged
    details TEXT,  -- JSON: conflicting units, confidence scores
    reviewed_by TEXT,  -- human reviewer if flagged
    created_at TEXT DEFAULT (datetime('now')),
    reviewed_at TEXT,
    FOREIGN KEY (unit_id) REFERENCES wiki_knowledge_units(id)
);

-- Weekly continuity checkpoints: Carry context forward
CREATE TABLE IF NOT EXISTS wiki_continuity_checkpoints (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    week_start TEXT NOT NULL,  -- ISO date of week start
    week_end TEXT NOT NULL,
    summary TEXT NOT NULL,  -- Context summary for next week
    key_topics TEXT DEFAULT '[]',  -- JSON array of main topics
    open_threads TEXT DEFAULT '[]',  -- JSON array of unresolved discussions
    unit_count INTEGER DEFAULT 0,  -- Number of units in this week
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(guild_id, channel_id, week_start)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_knowledge_units_guild ON wiki_knowledge_units(guild_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_source ON wiki_knowledge_units(source_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_type ON wiki_knowledge_units(guild_id, unit_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_date ON wiki_knowledge_units(guild_id, source_date);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_channel ON wiki_knowledge_units(guild_id, source_channel);

CREATE INDEX IF NOT EXISTS idx_edges_guild ON wiki_edges(guild_id);
CREATE INDEX IF NOT EXISTS idx_edges_from ON wiki_edges(from_unit_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON wiki_edges(to_unit_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON wiki_edges(guild_id, edge_type);

CREATE INDEX IF NOT EXISTS idx_learning_signals_guild ON wiki_learning_signals(guild_id);
CREATE INDEX IF NOT EXISTS idx_learning_signals_unit ON wiki_learning_signals(unit_id);
CREATE INDEX IF NOT EXISTS idx_learning_signals_type ON wiki_learning_signals(signal_type);

CREATE INDEX IF NOT EXISTS idx_coherence_guild ON wiki_coherence_validations(guild_id);
CREATE INDEX IF NOT EXISTS idx_coherence_status ON wiki_coherence_validations(status);

CREATE INDEX IF NOT EXISTS idx_checkpoints_guild ON wiki_continuity_checkpoints(guild_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_channel ON wiki_continuity_checkpoints(guild_id, channel_id);
