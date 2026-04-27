-- ADR-070: Public Issue Tracker
-- Local issue collection for users without GitHub accounts

CREATE TABLE IF NOT EXISTS local_issues (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    guild_id TEXT,  -- NULL for global issues

    -- Issue content
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    issue_type TEXT NOT NULL CHECK (issue_type IN ('bug', 'feature', 'question')),

    -- Reporter info (optional)
    reporter_email TEXT,
    reporter_discord_id TEXT,

    -- Context (auto-captured)
    page_url TEXT,
    browser_info TEXT,
    app_version TEXT,

    -- Lifecycle
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'triaged', 'replicated', 'closed')),
    github_issue_url TEXT,  -- Set when replicated to GitHub
    admin_notes TEXT,       -- Internal notes for triage
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_local_issues_guild ON local_issues(guild_id);
CREATE INDEX IF NOT EXISTS idx_local_issues_status ON local_issues(status);
CREATE INDEX IF NOT EXISTS idx_local_issues_type ON local_issues(issue_type);
CREATE INDEX IF NOT EXISTS idx_local_issues_created ON local_issues(created_at DESC);
