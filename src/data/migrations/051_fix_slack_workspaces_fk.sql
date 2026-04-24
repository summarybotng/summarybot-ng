-- Fix slack_workspaces foreign key to non-existent guilds table
-- The guilds table doesn't exist - guild_id is just a reference string

-- SQLite doesn't support ALTER TABLE DROP CONSTRAINT, so we need to recreate

-- Step 1: Disable foreign keys temporarily
PRAGMA foreign_keys=OFF;

-- Step 2: Create new table without invalid foreign key
CREATE TABLE IF NOT EXISTS slack_workspaces_new (
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
    CONSTRAINT slack_workspaces_scope_tier_check CHECK (
        scope_tier IN ('public', 'full')
    )
);

-- Step 3: Copy existing data (if any)
INSERT OR IGNORE INTO slack_workspaces_new
SELECT * FROM slack_workspaces;

-- Step 4: Drop old table
DROP TABLE IF EXISTS slack_workspaces;

-- Step 5: Rename new table
ALTER TABLE slack_workspaces_new RENAME TO slack_workspaces;

-- Step 6: Recreate indexes
CREATE INDEX IF NOT EXISTS idx_slack_workspaces_guild ON slack_workspaces(linked_guild_id);
CREATE INDEX IF NOT EXISTS idx_slack_workspaces_enabled ON slack_workspaces(enabled);
CREATE INDEX IF NOT EXISTS idx_slack_workspaces_enterprise ON slack_workspaces(enterprise_id);

-- Step 7: Re-enable foreign keys
PRAGMA foreign_keys=ON;
