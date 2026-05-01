-- ADR-079: Subdomain Multi-Tenancy - Phase 1 Schema
-- Creates tables for tenant management, workspace linking, and access control

-- Main tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    subdomain TEXT UNIQUE,
    custom_domain TEXT UNIQUE,
    domain_verified BOOLEAN DEFAULT FALSE,
    domain_verification_token TEXT,
    logo_url TEXT,
    primary_color TEXT,
    favicon_url TEXT,
    app_name_override TEXT,
    show_powered_by BOOLEAN DEFAULT TRUE,
    access_mode TEXT DEFAULT 'authenticated',
    allowed_email_domains TEXT,  -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    created_by TEXT NOT NULL,
    settings TEXT DEFAULT '{}'
);

-- Junction table: tenants <-> workspaces (Discord guilds, Slack workspaces, WhatsApp groups)
CREATE TABLE IF NOT EXISTS tenant_workspaces (
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    workspace_type TEXT NOT NULL,  -- discord, slack, whatsapp
    display_name TEXT,
    display_order INTEGER DEFAULT 0,
    added_at TEXT DEFAULT (datetime('now')),
    added_by TEXT NOT NULL,
    PRIMARY KEY (tenant_id, workspace_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- Tenant administrators (users who can manage tenant settings)
CREATE TABLE IF NOT EXISTS tenant_admins (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT DEFAULT 'admin',  -- owner, admin, editor
    added_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- Tenant members (users with access to tenant's dashboards)
CREATE TABLE IF NOT EXISTS tenant_members (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    email TEXT,
    access_level TEXT DEFAULT 'viewer',  -- viewer, contributor
    invited_at TEXT DEFAULT (datetime('now')),
    accepted_at TEXT,
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_tenants_subdomain ON tenants(subdomain);
CREATE INDEX IF NOT EXISTS idx_tenants_custom_domain ON tenants(custom_domain);
CREATE INDEX IF NOT EXISTS idx_tenant_workspaces_workspace ON tenant_workspaces(workspace_id);
CREATE INDEX IF NOT EXISTS idx_tenant_admins_user ON tenant_admins(user_id);
CREATE INDEX IF NOT EXISTS idx_tenant_members_user ON tenant_members(user_id);
CREATE INDEX IF NOT EXISTS idx_tenant_members_email ON tenant_members(email);
