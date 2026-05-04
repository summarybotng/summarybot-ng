-- ADR-085: Source-Guild Relationship Model
-- Enables many-to-many relationship between Slack workspaces and Discord guilds

-- Junction table for Slack workspace to Discord guild links
CREATE TABLE IF NOT EXISTS slack_guild_links (
    workspace_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    linked_at TEXT DEFAULT (datetime('now')),
    can_view BOOLEAN DEFAULT TRUE,
    can_summarize BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (workspace_id, guild_id),
    FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
);

-- Index for efficient guild-based lookups
CREATE INDEX IF NOT EXISTS idx_slack_guild_links_guild ON slack_guild_links(guild_id);
CREATE INDEX IF NOT EXISTS idx_slack_guild_links_workspace ON slack_guild_links(workspace_id);

-- Migrate existing linked_guild_id entries to the new table
-- This preserves existing Slack-Discord links
INSERT OR IGNORE INTO slack_guild_links (workspace_id, guild_id, linked_by, linked_at, can_view, can_summarize)
SELECT
    workspace_id,
    linked_guild_id,
    installed_by_discord_user,
    COALESCE(linked_at, datetime('now')),
    TRUE,
    TRUE  -- Original links have full access
FROM slack_workspaces
WHERE linked_guild_id IS NOT NULL;
