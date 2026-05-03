-- ADR-082: Google Drive Import for WhatsApp Exports (Shared Folder Approach)
-- Migration: Guild upload folders and import logging

-- Track guild upload folders (one folder per guild)
CREATE TABLE IF NOT EXISTS guild_drive_folders (
    guild_id TEXT PRIMARY KEY,
    folder_id TEXT NOT NULL,
    folder_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Track Drive imports for audit/debugging
CREATE TABLE IF NOT EXISTS drive_import_log (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    drive_file_id TEXT NOT NULL,
    drive_file_name TEXT NOT NULL,
    file_size_bytes INTEGER,
    import_id TEXT,  -- References whatsapp_imports.id
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, downloading, processing, completed, failed
    error_message TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    FOREIGN KEY (import_id) REFERENCES whatsapp_imports(id)
);

CREATE INDEX IF NOT EXISTS idx_drive_import_log_guild ON drive_import_log(guild_id);
CREATE INDEX IF NOT EXISTS idx_drive_import_log_status ON drive_import_log(status);
