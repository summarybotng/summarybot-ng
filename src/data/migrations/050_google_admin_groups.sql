-- ADR-050: Google Workspace Group-Based Admin Access
-- Maps Discord guilds to Google Workspace groups that grant admin permissions

CREATE TABLE IF NOT EXISTS guild_google_admin_groups (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    google_group_email TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    UNIQUE(guild_id, google_group_email)
);

CREATE INDEX IF NOT EXISTS idx_guild_google_admin_groups_guild
ON guild_google_admin_groups(guild_id);
