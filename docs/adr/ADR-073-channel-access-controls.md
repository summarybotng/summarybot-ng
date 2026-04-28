# ADR-073: Channel Access Controls and Summary Governance

## Status
Accepted

## Context
Server administrators need control over which channels are summarized and visibility into when summaries exist for channels they've since disabled. Additionally, channels with restricted Discord permissions ("locked down" channels) require special handling to prevent accidental exposure of sensitive content.

Current issues:
1. Channel disable states don't persist across refresh operations
2. No visibility into summaries existing for now-disabled channels
3. Locked/private channels are enabled by default, risking sensitive content exposure
4. No audit trail when admins override restrictions on locked channels
5. Private channel summaries can inadvertently appear in public wiki

## Decision

### 1. Persistent Channel Enable/Disable State
- Channel enable/disable state stored in `channel_settings` table (new)
- State persists across coverage refreshes and bot restarts
- UI shows clear indication when a channel is manually disabled

### 2. Disabled Channel Summary Detection
- Summaries list includes filter: "Show summaries for disabled channels"
- Visual indicator on summaries from disabled channels
- Helps admins identify channels where summarization was stopped after content was already summarized

### 3. Locked Channel Defaults
Channels are considered "locked down" if:
- `@everyone` role lacks `VIEW_CHANNEL` permission
- `@everyone` role lacks `READ_MESSAGE_HISTORY` permission
- Channel is in a category with restricted access

For locked channels:
- **Default state: DISABLED** for summarization
- Warning banner shown when viewing channel in settings
- Explicit admin action required to enable summarization

### 4. Audit Trail for Locked Channel Overrides
When an admin enables summarization on a locked channel:
- Audit event recorded: `LOCKED_CHANNEL_ENABLED`
- Event includes: channel_id, channel_name, admin_user_id, timestamp, permissions snapshot
- Warning confirmation dialog required before enabling

### 5. Wiki Privacy Boundary (Future - ADR-074)
- Summaries from locked/private channels excluded from wiki assimilation by default
- Separate "private summaries" collection that doesn't sync to wiki
- Configurable per-channel wiki visibility independent of summary generation

## Database Schema

```sql
-- New table for persistent channel settings
CREATE TABLE IF NOT EXISTS channel_settings (
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'discord',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_locked BOOLEAN DEFAULT FALSE,
    locked_override BOOLEAN DEFAULT FALSE,  -- Admin explicitly enabled despite locked
    locked_override_by TEXT,                 -- User ID who overrode
    locked_override_at TEXT,                 -- When override happened
    wiki_visible BOOLEAN DEFAULT TRUE,       -- Can summaries appear in wiki
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, channel_id, platform)
);

CREATE INDEX idx_channel_settings_guild ON channel_settings(guild_id, platform);
CREATE INDEX idx_channel_settings_locked ON channel_settings(guild_id, is_locked);
```

## API Changes

### GET /guilds/{guild_id}/channels
Returns `is_locked` and `locked_override` fields for each channel.

### PATCH /guilds/{guild_id}/channels/{channel_id}
- If enabling a locked channel, requires `confirm_locked_override: true`
- Creates audit event on locked channel override

### GET /guilds/{guild_id}/summaries
- New query param: `disabled_channels_only=true`
- Returns summaries where source channel is now disabled

## UI Changes

1. **Channels Page**
   - Locked channels shown with 🔒 icon
   - Locked channels disabled by default
   - Warning dialog when enabling locked channel
   - "Disabled" state persists across refresh

2. **Summaries Page**
   - Filter dropdown: "Disabled channel summaries"
   - Badge on summaries from disabled channels

3. **Audit Log**
   - New event type for locked channel overrides

## Consequences

### Positive
- Admins have full control over which channels are summarized
- Clear audit trail for security-sensitive decisions
- Reduced risk of accidental sensitive content exposure
- Better visibility into historical summarization decisions

### Negative
- Additional database table and queries
- More complex channel state management
- UI complexity for locked channel warnings

## Implementation Order
1. Database migration for `channel_settings`
2. Persist enable/disable state in channel settings
3. Detect locked channels from Discord permissions
4. Default locked channels to disabled
5. Add audit events for locked channel override
6. UI: locked channel warnings and confirmation
7. Summaries filter for disabled channels
8. (Future ADR-074) Wiki privacy boundary
