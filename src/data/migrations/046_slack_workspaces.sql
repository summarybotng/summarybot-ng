-- ADR-043: Slack Workspace Integration (Phase 1)
-- Migration to create Slack workspace, channel, and user tables

CREATE TABLE IF NOT EXISTS slack_workspaces (
    workspace_id TEXT PRIMARY KEY,
    workspace_name TEXT NOT NULL,
    workspace_domain TEXT,
    encrypted_bot_token TEXT NOT NULL,
    bot_user_id TEXT NOT NULL,
    installed_by_discord_user TEXT NOT NULL,
    installed_at TEXT NOT NULL DEFAULT (datetime('now')),
    scopes TEXT NOT NULL,
    scope_tier TEXT NOT NULL DEFAULT 'public',
    is_enterprise BOOLEAN DEFAULT FALSE,
    enterprise_id TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    last_sync_at TEXT,
    metadata TEXT DEFAULT '{}',
    linked_guild_id TEXT,
    linked_at TEXT,
    -- Note: No FK to guilds table as it doesn't exist; guild_id is just a reference string
    CONSTRAINT slack_workspaces_scope_tier_check CHECK (
        scope_tier IN ('public', 'full')
    )
);

CREATE TABLE IF NOT EXISTS slack_channels (
    channel_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    channel_type TEXT NOT NULL DEFAULT 'public_channel',
    is_shared BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    is_sensitive BOOLEAN DEFAULT FALSE,
    auto_summarize BOOLEAN DEFAULT FALSE,
    summary_schedule TEXT,
    last_message_ts TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    topic TEXT,
    purpose TEXT,
    member_count INTEGER DEFAULT 0,
    FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE,
    CONSTRAINT slack_channels_type_check CHECK (
        channel_type IN ('public_channel', 'private_channel', 'im', 'mpim')
    )
);

CREATE TABLE IF NOT EXISTS slack_users (
    user_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    real_name TEXT,
    email TEXT,
    is_bot BOOLEAN DEFAULT FALSE,
    is_admin BOOLEAN DEFAULT FALSE,
    is_owner BOOLEAN DEFAULT FALSE,
    avatar_url TEXT,
    updated_at TEXT DEFAULT (datetime('now')),
    timezone TEXT,
    status_text TEXT,
    status_emoji TEXT,
    PRIMARY KEY (workspace_id, user_id),
    FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_slack_workspaces_guild ON slack_workspaces(linked_guild_id);
CREATE INDEX IF NOT EXISTS idx_slack_workspaces_enabled ON slack_workspaces(enabled);
CREATE INDEX IF NOT EXISTS idx_slack_workspaces_enterprise ON slack_workspaces(enterprise_id);

CREATE INDEX IF NOT EXISTS idx_slack_channels_workspace ON slack_channels(workspace_id);
CREATE INDEX IF NOT EXISTS idx_slack_channels_type ON slack_channels(channel_type);
CREATE INDEX IF NOT EXISTS idx_slack_channels_auto_summarize ON slack_channels(auto_summarize);
CREATE INDEX IF NOT EXISTS idx_slack_channels_last_message ON slack_channels(workspace_id, last_message_ts DESC);

CREATE INDEX IF NOT EXISTS idx_slack_users_workspace ON slack_users(workspace_id);
CREATE INDEX IF NOT EXISTS idx_slack_users_bot ON slack_users(workspace_id, is_bot);
