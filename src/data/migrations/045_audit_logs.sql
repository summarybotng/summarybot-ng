-- ADR-045: Audit Logging System
-- Migration to create audit_logs table

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',

    -- Actor
    user_id TEXT,
    user_name TEXT,
    session_id TEXT,

    -- Context
    guild_id TEXT,
    guild_name TEXT,
    ip_address TEXT,
    user_agent TEXT,

    -- Target
    resource_type TEXT,
    resource_id TEXT,
    resource_name TEXT,

    -- Details
    action TEXT,
    details TEXT,  -- JSON
    changes TEXT,  -- JSON

    -- Result
    success INTEGER DEFAULT 1,
    error_message TEXT,

    -- Metadata
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    request_id TEXT,
    duration_ms INTEGER,

    -- Constraints
    CONSTRAINT audit_logs_category_check CHECK (
        category IN ('auth', 'access', 'action', 'source', 'admin', 'system')
    ),
    CONSTRAINT audit_logs_severity_check CHECK (
        severity IN ('debug', 'info', 'notice', 'warning', 'alert')
    )
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_guild ON audit_logs(guild_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_logs(event_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_logs(category, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_logs(session_id);

-- Partial index for security monitoring (failed actions and alerts)
CREATE INDEX IF NOT EXISTS idx_audit_failures ON audit_logs(timestamp DESC)
    WHERE success = 0;
CREATE INDEX IF NOT EXISTS idx_audit_alerts ON audit_logs(timestamp DESC)
    WHERE severity IN ('warning', 'alert');
