# Architecture: Database Schema

**SPARC Phase**: Architecture
**Module**: `v3/src/adapters/repositories/`
**Database**: SQLite (with async via aiosqlite)

---

## Schema Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USERS                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ name            │ email           │ avatar_url       │
│ created_at       │ last_login_at   │ preferences     │                  │
└────────┬────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          USER_IDENTITIES                                 │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ user_id (FK)    │ provider        │ provider_id      │
│ provider_username│ metadata        │ linked_at       │                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                            WORKSPACES                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ name            │ owner_id (FK)   │ settings         │
│ created_at       │ updated_at      │                 │                  │
└────────┬────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PLATFORM_CONNECTIONS                                │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ workspace_id(FK)│ platform        │ platform_id      │
│ platform_name    │ access_token    │ refresh_token   │ token_expires_at │
│ connected_at     │ connected_by(FK)│                 │                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                            SUMMARIES                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ workspace_id(FK)│ channel_ids     │ content          │
│ key_points       │ participants    │ message_count   │ start_time       │
│ end_time         │ generation_opts │ input_tokens    │ output_tokens    │
│ cost_usd         │ model_used      │ status          │ created_at       │
│ published_at     │                 │                 │                  │
└────────┬────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          ACTION_ITEMS                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ summary_id (FK) │ content         │ assignee         │
│ deadline         │ priority        │ completed       │ completed_at     │
│ extracted_from   │                 │                 │                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                            SCHEDULES                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ workspace_id(FK)│ name            │ scope            │
│ channel_ids      │ category_id     │ frequency       │ cron_expression  │
│ timezone         │ lookback_hours  │ min_messages    │ summary_options  │
│ enabled          │ last_run_at     │ next_run_at     │ run_count        │
│ failure_count    │ max_failures    │ created_at      │ created_by (FK)  │
└────────┬────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      DELIVERY_DESTINATIONS                               │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ schedule_id(FK) │ type            │ target           │
│ options          │ enabled         │                 │                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                              JOBS                                        │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ workspace_id(FK)│ type            │ status           │
│ request          │ progress        │ result          │ failure_reason   │
│ created_at       │ started_at      │ completed_at    │                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         REFRESH_TOKENS                                   │
├─────────────────────────────────────────────────────────────────────────┤
│ token_hash (PK)  │ user_id (FK)    │ oauth_access    │ oauth_refresh    │
│ oauth_expires_at │ created_at      │ expires_at      │                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         DELIVERY_LOGS                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ id (PK)          │ summary_id (FK) │ destination_type│ target           │
│ success          │ message_id      │ error           │ delivered_at     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## SQL DDL

```sql
-- Users
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    avatar_url TEXT,
    preferences TEXT DEFAULT '{}',  -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT
);

CREATE INDEX idx_users_email ON users(email);

-- User Identities (multi-provider auth)
CREATE TABLE user_identities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,  -- discord, slack, google, email
    provider_id TEXT NOT NULL,
    provider_username TEXT,
    metadata TEXT DEFAULT '{}',  -- JSON
    linked_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(provider, provider_id)
);

CREATE INDEX idx_user_identities_user ON user_identities(user_id);
CREATE INDEX idx_user_identities_provider ON user_identities(provider, provider_id);

-- Workspaces
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL REFERENCES users(id),
    settings TEXT DEFAULT '{}',  -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_workspaces_owner ON workspaces(owner_id);

-- Platform Connections
CREATE TABLE platform_connections (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,  -- discord, slack, whatsapp
    platform_id TEXT NOT NULL,
    platform_name TEXT NOT NULL,
    access_token TEXT NOT NULL,  -- Encrypted
    refresh_token TEXT,  -- Encrypted
    token_expires_at TEXT,
    connected_at TEXT NOT NULL DEFAULT (datetime('now')),
    connected_by TEXT REFERENCES users(id),
    UNIQUE(platform, platform_id)
);

CREATE INDEX idx_platform_connections_workspace ON platform_connections(workspace_id);
CREATE INDEX idx_platform_connections_platform ON platform_connections(platform, platform_id);

-- Summaries
CREATE TABLE summaries (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    channel_ids TEXT NOT NULL,  -- JSON array
    content TEXT NOT NULL,
    key_points TEXT DEFAULT '[]',  -- JSON array
    participants TEXT DEFAULT '[]',  -- JSON array
    message_count INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    generation_options TEXT DEFAULT '{}',  -- JSON
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    model_used TEXT,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, published, archived
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    published_at TEXT
);

CREATE INDEX idx_summaries_workspace ON summaries(workspace_id);
CREATE INDEX idx_summaries_workspace_time ON summaries(workspace_id, start_time, end_time);
CREATE INDEX idx_summaries_status ON summaries(status);

-- Action Items
CREATE TABLE action_items (
    id TEXT PRIMARY KEY,
    summary_id TEXT NOT NULL REFERENCES summaries(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    assignee TEXT,
    deadline TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',  -- low, medium, high, urgent
    completed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    extracted_from TEXT
);

CREATE INDEX idx_action_items_summary ON action_items(summary_id);

-- Schedules
CREATE TABLE schedules (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    scope TEXT NOT NULL,  -- workspace, category, channel
    channel_ids TEXT,  -- JSON array, for scope=channel
    category_id TEXT,  -- for scope=category
    frequency TEXT NOT NULL,  -- daily, weekly, monthly
    cron_expression TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    lookback_hours INTEGER NOT NULL DEFAULT 24,
    min_messages INTEGER NOT NULL DEFAULT 5,
    summary_options TEXT DEFAULT '{}',  -- JSON
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    next_run_at TEXT NOT NULL,
    run_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    max_failures INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT REFERENCES users(id)
);

CREATE INDEX idx_schedules_workspace ON schedules(workspace_id);
CREATE INDEX idx_schedules_next_run ON schedules(enabled, next_run_at);

-- Delivery Destinations
CREATE TABLE delivery_destinations (
    id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    type TEXT NOT NULL,  -- discord_channel, email, webhook, confluence
    target TEXT NOT NULL,
    options TEXT DEFAULT '{}',  -- JSON
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_delivery_destinations_schedule ON delivery_destinations(schedule_id);

-- Jobs
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    type TEXT NOT NULL,  -- summary_generation, schedule_execution
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed, rate_limited
    request TEXT DEFAULT '{}',  -- JSON
    progress TEXT DEFAULT '{}',  -- JSON
    result TEXT,  -- JSON
    failure_reason TEXT,  -- rate_limited, quota_exceeded, invalid_request, service_unavailable
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX idx_jobs_workspace ON jobs(workspace_id);
CREATE INDEX idx_jobs_status ON jobs(status);

-- Refresh Tokens
CREATE TABLE refresh_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    oauth_access_token TEXT,  -- Encrypted
    oauth_refresh_token TEXT,  -- Encrypted
    oauth_expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens(expires_at);

-- Delivery Logs
CREATE TABLE delivery_logs (
    id TEXT PRIMARY KEY,
    summary_id TEXT NOT NULL REFERENCES summaries(id) ON DELETE CASCADE,
    destination_type TEXT NOT NULL,
    target TEXT NOT NULL,
    success INTEGER NOT NULL,
    message_id TEXT,
    error TEXT,
    delivered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_delivery_logs_summary ON delivery_logs(summary_id);
```

---

## Migration Strategy

### From V1 to V3

```python
# Key mappings:
V1_TABLE -> V3_TABLE:
  guilds -> workspaces (guild_id becomes workspace + platform_connection)
  stored_summaries -> summaries
  summary_schedules -> schedules
  confluence_publications -> delivery_logs (type=confluence)
  # Users: new table, created on first login
```

### Migration Script Location

```
v3/scripts/migrate_v1.py
```

---

*Next: `04-infrastructure.md`*
