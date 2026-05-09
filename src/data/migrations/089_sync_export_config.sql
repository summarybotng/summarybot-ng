-- ADR-091: Sync Export Configuration
-- Adds incremental sync tracking for Google Drive exports
--
-- Note: ServerSyncConfig (export_filters, include_json, folder_structure, period_grouping)
-- is stored in server-manifest.json files, not in the database.
-- See src/archive/sync/service.py ServerSyncConfig dataclass.

-- Track synced files for incremental sync
CREATE TABLE IF NOT EXISTS sync_history (
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    summary_id TEXT NOT NULL,
    drive_file_id TEXT,
    drive_folder_id TEXT,
    synced_at TEXT NOT NULL,
    file_type TEXT NOT NULL,  -- 'md' or 'json'
    period_folder TEXT,       -- e.g., '2026-05-05--2026-05-11'
    UNIQUE(server_id, summary_id, file_type)
);

CREATE INDEX IF NOT EXISTS idx_sync_history_server ON sync_history(server_id);
CREATE INDEX IF NOT EXISTS idx_sync_history_summary ON sync_history(summary_id);
