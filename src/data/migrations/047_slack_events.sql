-- ADR-043: Slack Events API (Phase 2)
-- Migration for event tracking and deduplication

CREATE TABLE IF NOT EXISTS slack_event_log (
    event_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_subtype TEXT,
    channel_id TEXT,
    user_id TEXT,
    message_ts TEXT,
    thread_ts TEXT,
    received_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed BOOLEAN DEFAULT FALSE,
    processed_at TEXT,
    error_message TEXT,
    raw_event TEXT,  -- JSON payload for debugging
    FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
);

-- Indexes for event deduplication and lookup
CREATE INDEX IF NOT EXISTS idx_slack_events_workspace ON slack_event_log(workspace_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_slack_events_type ON slack_event_log(event_type, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_slack_events_channel ON slack_event_log(workspace_id, channel_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_slack_events_processed ON slack_event_log(processed, received_at DESC);

-- Cleanup trigger: Remove events older than 7 days
-- SQLite doesn't support scheduled jobs, so cleanup happens on insert
CREATE TRIGGER IF NOT EXISTS cleanup_old_slack_events
AFTER INSERT ON slack_event_log
BEGIN
    DELETE FROM slack_event_log
    WHERE received_at < datetime('now', '-7 days');
END;

-- App installation/uninstallation tracking for security (ADR-043 Section 8.3)
CREATE TABLE IF NOT EXISTS slack_app_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- 'app_installed', 'app_uninstalled', 'tokens_revoked'
    triggered_by_user TEXT,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata TEXT DEFAULT '{}',  -- JSON for additional context
    FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE,
    CONSTRAINT slack_app_events_type_check CHECK (
        event_type IN ('app_installed', 'app_uninstalled', 'tokens_revoked', 'scope_changed')
    )
);

CREATE INDEX IF NOT EXISTS idx_slack_app_events_workspace ON slack_app_events(workspace_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_slack_app_events_type ON slack_app_events(event_type, occurred_at DESC);
