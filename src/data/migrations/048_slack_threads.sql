-- ADR-043: Slack Threads and Files (Phase 3)
-- Migration for thread tracking and file management

CREATE TABLE IF NOT EXISTS slack_threads (
    thread_ts TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    reply_count INTEGER DEFAULT 0,
    reply_users_count INTEGER DEFAULT 0,
    latest_reply_ts TEXT,
    last_fetched_at TEXT,
    parent_user_id TEXT,
    parent_text TEXT,  -- First 500 chars of parent message
    is_active BOOLEAN DEFAULT TRUE,  -- Has recent activity
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (workspace_id, channel_id, thread_ts),
    FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS slack_files (
    file_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    channel_id TEXT,
    user_id TEXT,
    filename TEXT NOT NULL,
    title TEXT,
    mimetype TEXT,
    filetype TEXT,  -- Slack's file type classification
    size_bytes INTEGER,
    permalink TEXT,
    permalink_public TEXT,
    url_private TEXT,
    url_private_download TEXT,
    local_path TEXT,  -- Path if downloaded locally
    downloaded_at TEXT,
    expires_at TEXT,  -- Slack URLs have expiration
    is_external BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT FALSE,
    shares TEXT,  -- JSON: channels/groups this file is shared to
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
);

-- Thread tracking indexes
CREATE INDEX IF NOT EXISTS idx_slack_threads_workspace ON slack_threads(workspace_id, last_fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_slack_threads_channel ON slack_threads(workspace_id, channel_id, latest_reply_ts DESC);
CREATE INDEX IF NOT EXISTS idx_slack_threads_active ON slack_threads(workspace_id, is_active, reply_count DESC);

-- File tracking indexes
CREATE INDEX IF NOT EXISTS idx_slack_files_workspace ON slack_files(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_slack_files_channel ON slack_files(workspace_id, channel_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_slack_files_type ON slack_files(workspace_id, mimetype);
CREATE INDEX IF NOT EXISTS idx_slack_files_local ON slack_files(local_path) WHERE local_path IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_slack_files_expires ON slack_files(expires_at) WHERE expires_at IS NOT NULL;

-- Track which thread replies have been fetched
CREATE TABLE IF NOT EXISTS slack_thread_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    thread_ts TEXT NOT NULL,
    message_ts TEXT NOT NULL,
    user_id TEXT,
    text TEXT,
    has_files BOOLEAN DEFAULT FALSE,
    fetched_at TEXT DEFAULT (datetime('now')),
    UNIQUE(workspace_id, channel_id, thread_ts, message_ts),
    FOREIGN KEY (workspace_id, channel_id, thread_ts)
        REFERENCES slack_threads(workspace_id, channel_id, thread_ts) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_slack_thread_messages_thread
    ON slack_thread_messages(workspace_id, channel_id, thread_ts, message_ts);
