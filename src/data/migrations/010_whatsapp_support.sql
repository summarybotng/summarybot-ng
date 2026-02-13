-- Migration: Add WhatsApp and multi-source ingest support (ADR-002)
-- Date: 2026-02-13

-- Add source tracking to existing summaries table
ALTER TABLE summaries ADD COLUMN source_type TEXT NOT NULL DEFAULT 'discord';
ALTER TABLE summaries ADD COLUMN source_channel_id TEXT;

-- WhatsApp/multi-source ingested message batches
CREATE TABLE IF NOT EXISTS ingest_batches (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    channel_type TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    time_range_start TEXT NOT NULL,
    time_range_end TEXT NOT NULL,
    raw_payload TEXT NOT NULL,       -- JSON of IngestDocument
    processed INTEGER DEFAULT 0,
    document_id TEXT,                -- Link to generated document/summary
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ingest_batch_source_channel ON ingest_batches(source_type, channel_id);
CREATE INDEX IF NOT EXISTS idx_ingest_batch_time ON ingest_batches(time_range_start, time_range_end);
CREATE INDEX IF NOT EXISTS idx_ingest_batch_created ON ingest_batches(created_at);

-- Ingested messages (denormalized for fast query)
CREATE TABLE IF NOT EXISTS ingest_messages (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES ingest_batches(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    content TEXT,
    has_attachments INTEGER DEFAULT 0,
    attachments_json TEXT,           -- JSON array of attachment info
    reply_to_id TEXT,
    is_forwarded INTEGER DEFAULT 0,
    is_edited INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',      -- JSON for source-specific data
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ingest_msg_source_channel_time ON ingest_messages(source_type, channel_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ingest_msg_sender ON ingest_messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_ingest_msg_batch ON ingest_messages(batch_id);

-- Track which chats are configured for auto-summarization
CREATE TABLE IF NOT EXISTS tracked_chats (
    chat_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    chat_name TEXT,
    chat_type TEXT NOT NULL,         -- 'individual', 'group', 'channel'
    auto_summarize INTEGER DEFAULT 0,
    summary_schedule TEXT,           -- cron expression, e.g. '0 9 * * 1' (Monday 9am)
    summary_type TEXT DEFAULT 'comprehensive',
    webhook_url TEXT,                -- Deliver summaries here
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tracked_chats_source ON tracked_chats(source_type);
CREATE INDEX IF NOT EXISTS idx_tracked_chats_auto ON tracked_chats(auto_summarize) WHERE auto_summarize = 1;

-- Channel statistics cache (aggregated from ingest_messages)
CREATE TABLE IF NOT EXISTS channel_stats (
    source_type TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    channel_type TEXT,
    message_count INTEGER DEFAULT 0,
    participant_count INTEGER DEFAULT 0,
    first_message_at TEXT,
    last_message_at TEXT,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (source_type, channel_id)
);

-- Note: schema version is automatically tracked by the migration runner
