-- ADR-049: Google Workspace SSO
-- Migration to support Google authenticated users

-- Google user records for domain-to-guild mapping
CREATE TABLE IF NOT EXISTS google_users (
    id TEXT PRIMARY KEY,                    -- google_{google_user_id}
    email TEXT NOT NULL,
    email_domain TEXT NOT NULL,             -- Extracted from hd claim
    name TEXT,
    picture TEXT,

    -- Access control
    status TEXT NOT NULL DEFAULT 'active',  -- active, suspended, pending

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP,

    -- Constraints
    CONSTRAINT google_users_status_check CHECK (
        status IN ('active', 'suspended', 'pending')
    )
);

-- Google user guild access (explicit mapping)
CREATE TABLE IF NOT EXISTS google_user_guilds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',    -- member, admin (never auto-admin)
    granted_by TEXT,                        -- Who granted access
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT google_user_guilds_unique UNIQUE (google_user_id, guild_id),
    CONSTRAINT google_user_guilds_role_check CHECK (
        role IN ('member', 'admin')
    ),
    FOREIGN KEY (google_user_id) REFERENCES google_users(id) ON DELETE CASCADE
);

-- Domain-to-guild mapping (configured by admins)
CREATE TABLE IF NOT EXISTS google_domain_guilds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    auto_approve BOOLEAN NOT NULL DEFAULT 0,  -- Auto-approve users from this domain
    default_role TEXT NOT NULL DEFAULT 'member',
    created_by TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT google_domain_guilds_unique UNIQUE (domain, guild_id),
    CONSTRAINT google_domain_guilds_role_check CHECK (
        default_role IN ('member', 'admin')
    )
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_google_users_email ON google_users(email);
CREATE INDEX IF NOT EXISTS idx_google_users_domain ON google_users(email_domain);
CREATE INDEX IF NOT EXISTS idx_google_users_status ON google_users(status);
CREATE INDEX IF NOT EXISTS idx_google_user_guilds_user ON google_user_guilds(google_user_id);
CREATE INDEX IF NOT EXISTS idx_google_user_guilds_guild ON google_user_guilds(guild_id);
CREATE INDEX IF NOT EXISTS idx_google_domain_guilds_domain ON google_domain_guilds(domain);
