-- Migration: WhatsApp Import Management (ADR-081)
-- Date: 2026-05-02
-- Provides comprehensive import tracking, identity resolution, and participant management

-- WhatsApp imports (replaces file-based import-manifest.json)
CREATE TABLE IF NOT EXISTS whatsapp_imports (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    chat_name TEXT NOT NULL,

    -- Attribution
    imported_by TEXT NOT NULL,  -- User ID who uploaded
    imported_at TEXT NOT NULL,

    -- File metadata
    original_filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,  -- SHA-256 for duplicate detection
    file_size_bytes INTEGER NOT NULL,
    format TEXT NOT NULL,  -- 'whatsapp_txt', 'whatsapp_txt_android', 'reader_bot_json'

    -- Content summary
    date_range_start TEXT NOT NULL,
    date_range_end TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    participant_count INTEGER NOT NULL,

    -- Processing status
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    error_message TEXT,
    processed_at TEXT,

    -- Anonymization
    anonymization_version INTEGER DEFAULT 1,
    participants_json TEXT,  -- JSON array of participant summaries

    -- Soft delete
    deleted_at TEXT,
    deleted_by TEXT,

    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wa_imports_guild_chat ON whatsapp_imports(guild_id, chat_id);
CREATE INDEX IF NOT EXISTS idx_wa_imports_guild ON whatsapp_imports(guild_id);
CREATE INDEX IF NOT EXISTS idx_wa_imports_hash ON whatsapp_imports(file_hash);
CREATE INDEX IF NOT EXISTS idx_wa_imports_date ON whatsapp_imports(imported_at);
CREATE INDEX IF NOT EXISTS idx_wa_imports_status ON whatsapp_imports(status);
CREATE INDEX IF NOT EXISTS idx_wa_imports_deleted ON whatsapp_imports(deleted_at) WHERE deleted_at IS NULL;

-- WhatsApp participant identities (canonical identities with alias tracking)
CREATE TABLE IF NOT EXISTS whatsapp_participants (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,

    -- Identity
    phone_hash TEXT,  -- HMAC hash of normalized phone (nullable if only contact names)
    pseudonym TEXT NOT NULL,  -- "Swift Penguin 4827"

    -- Aliases (JSON array of known display names)
    aliases_json TEXT DEFAULT '[]',
    preferred_name TEXT,  -- User-set preferred display name

    -- Statistics
    first_seen_import_id TEXT REFERENCES whatsapp_imports(id),
    message_count INTEGER DEFAULT 0,

    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wa_participants_guild_chat ON whatsapp_participants(guild_id, chat_id);
CREATE INDEX IF NOT EXISTS idx_wa_participants_guild ON whatsapp_participants(guild_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_participants_phone ON whatsapp_participants(guild_id, chat_id, phone_hash)
    WHERE phone_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wa_participants_pseudonym ON whatsapp_participants(pseudonym);

-- Identity merge history (audit trail for manual merges)
CREATE TABLE IF NOT EXISTS whatsapp_identity_merges (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,

    -- The merge operation
    source_participant_id TEXT NOT NULL,
    target_participant_id TEXT NOT NULL,

    -- Attribution
    merged_by TEXT NOT NULL,  -- User ID
    merged_at TEXT NOT NULL,
    reason TEXT,  -- 'manual', 'phone_match', 'fuzzy_alias'

    -- Reversibility
    reversed_at TEXT,
    reversed_by TEXT,

    -- Preserved data for undo
    source_data_json TEXT  -- Original source participant data
);

CREATE INDEX IF NOT EXISTS idx_wa_merges_guild ON whatsapp_identity_merges(guild_id);
CREATE INDEX IF NOT EXISTS idx_wa_merges_target ON whatsapp_identity_merges(target_participant_id);

-- Message fingerprints for deduplication across imports
CREATE TABLE IF NOT EXISTS whatsapp_message_fingerprints (
    fingerprint TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES whatsapp_imports(id) ON DELETE CASCADE,
    participant_id TEXT NOT NULL REFERENCES whatsapp_participants(id),
    message_timestamp TEXT NOT NULL,

    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wa_fingerprints_import ON whatsapp_message_fingerprints(import_id);
CREATE INDEX IF NOT EXISTS idx_wa_fingerprints_time ON whatsapp_message_fingerprints(message_timestamp);
CREATE INDEX IF NOT EXISTS idx_wa_fingerprints_participant ON whatsapp_message_fingerprints(participant_id);
