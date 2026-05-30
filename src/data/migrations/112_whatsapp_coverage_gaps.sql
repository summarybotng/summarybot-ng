-- Migration: WhatsApp Coverage Gap Awareness (ADR-112)
-- Date: 2026-05-30
-- Adds join date detection and coverage gap tracking

-- Add columns for detected events from system messages
ALTER TABLE whatsapp_imports ADD COLUMN detected_join_date TEXT;
ALTER TABLE whatsapp_imports ADD COLUMN detected_events_json TEXT;

-- Index for fast join date lookups
CREATE INDEX IF NOT EXISTS idx_wa_imports_join_date ON whatsapp_imports(detected_join_date) WHERE detected_join_date IS NOT NULL;

-- Coverage gap tracking (aggregated per chat)
CREATE TABLE IF NOT EXISTS whatsapp_coverage_gaps (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,

    -- Gap boundaries
    gap_start TEXT NOT NULL,  -- ISO date
    gap_end TEXT NOT NULL,    -- ISO date
    gap_days INTEGER NOT NULL,

    -- Gap classification
    gap_type TEXT NOT NULL,  -- 'before_join', 'between_imports', 'after_last'
    can_fill INTEGER DEFAULT 1,  -- Boolean: can another user fill this?

    -- Resolution tracking
    resolved_at TEXT,  -- When gap was filled by another import
    resolved_by_import_id TEXT REFERENCES whatsapp_imports(id),

    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wa_gaps_chat ON whatsapp_coverage_gaps(guild_id, chat_id);
CREATE INDEX IF NOT EXISTS idx_wa_gaps_unresolved ON whatsapp_coverage_gaps(guild_id, chat_id) WHERE resolved_at IS NULL;
