-- ADR-073: Channel Access Controls
-- Persistent channel settings for enable/disable state and locked channel handling

CREATE TABLE IF NOT EXISTS channel_settings (
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'discord',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_locked BOOLEAN DEFAULT FALSE,
    locked_override BOOLEAN DEFAULT FALSE,
    locked_override_by TEXT,
    locked_override_at TEXT,
    wiki_visible BOOLEAN DEFAULT TRUE,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, channel_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_channel_settings_guild ON channel_settings(guild_id, platform);
CREATE INDEX IF NOT EXISTS idx_channel_settings_locked ON channel_settings(guild_id, is_locked);
CREATE INDEX IF NOT EXISTS idx_channel_settings_enabled ON channel_settings(guild_id, enabled);
