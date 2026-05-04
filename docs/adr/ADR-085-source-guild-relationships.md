# ADR-085: Source-Guild Relationship Model

## Status
Accepted

## Context

SummaryBot supports multiple source types (Discord, WhatsApp, Slack) that need to be associated with Discord guilds for access control and organization. The current model has inconsistencies:

1. **Discord channels**: Native 1:1 - channels belong to exactly one guild
2. **WhatsApp imports**: 1:1 - each import is owned by the guild that imported it (stored in `whatsapp_imports.guild_id`)
3. **Slack workspaces**: Currently 1:1 via `slack_workspaces.linked_guild_id`, but organizations need the same Slack workspace visible from multiple Discord guilds

### Current Problems

- Slack workspaces can only link to one Discord guild, but teams often have multiple Discord servers (e.g., public community + private team)
- Sources page doesn't show Slack channel breakdown, only workspace level
- No unified model for source-to-guild relationships

## Decision

### 1. Source Ownership Model

| Source Type | Ownership Model | Storage |
|-------------|-----------------|---------|
| Discord | Native (channels belong to guild) | Guild's channel list |
| WhatsApp | Single owner (importing guild) | `whatsapp_imports.guild_id` |
| Slack | Many-to-many (workspace visible to multiple guilds) | New `slack_guild_links` table |

### 2. New Junction Table: `slack_guild_links`

```sql
CREATE TABLE slack_guild_links (
    workspace_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    linked_at TEXT DEFAULT (datetime('now')),
    can_view BOOLEAN DEFAULT TRUE,
    can_summarize BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (workspace_id, guild_id),
    FOREIGN KEY (workspace_id) REFERENCES slack_workspaces(workspace_id) ON DELETE CASCADE
);
```

**Fields:**
- `workspace_id`: Slack workspace ID
- `guild_id`: Discord guild ID that can view this workspace
- `linked_by`: Discord user ID who created the link
- `can_view`: Whether guild members can view Slack content
- `can_summarize`: Whether guild can generate summaries from Slack

### 3. Source Visibility Rules

**WhatsApp:**
- Only visible to the guild that owns the import
- Ownership cannot be transferred or shared
- Filter: `whatsapp_imports.guild_id = current_guild_id`

**Slack:**
- Visible to all guilds with an entry in `slack_guild_links`
- Primary guild (original `linked_guild_id`) always has full access
- Additional guilds added via UI
- Filter: `slack_guild_links.guild_id = current_guild_id`

**Discord:**
- Channels only visible within their native guild
- No cross-guild visibility

### 4. API Changes

**GET /archive/sources**

Now accepts optional `guild_id` parameter and returns:
- `guild_id`: For WhatsApp, the owning guild; for Slack, null (check `linked_guilds`)
- `linked_guilds`: For Slack, list of guild IDs with access

```json
{
  "source_key": "slack:T12345678",
  "source_type": "slack",
  "server_id": "T12345678",
  "server_name": "Engineering",
  "guild_id": null,
  "linked_guilds": ["932336455026638848", "1420188750394167447"],
  "channels": [
    {"channel_id": "C123", "channel_name": "general", "summary_count": 45},
    {"channel_id": "C456", "channel_name": "engineering", "summary_count": 23}
  ]
}
```

**POST /guilds/{guild_id}/slack/link**

Link a Slack workspace to a guild:
```json
{
  "workspace_id": "T12345678",
  "can_view": true,
  "can_summarize": false
}
```

**DELETE /guilds/{guild_id}/slack/{workspace_id}/unlink**

Remove Slack workspace access from a guild.

### 5. Sources Page Display

For each platform on the Sources page:

| Platform | Display Level | Shown |
|----------|---------------|-------|
| Discord | Channel | All channels in guild |
| WhatsApp | Import | Imports owned by this guild |
| Slack | Channel | Channels from linked workspaces |

### 6. Migration Path

1. Existing `slack_workspaces.linked_guild_id` entries are migrated to `slack_guild_links`
2. Keep `linked_guild_id` for backward compatibility (primary/original link)
3. Additional guilds use `slack_guild_links` only

## Consequences

### Positive
- Organizations can share Slack content across multiple Discord communities
- Unified source visibility model
- Better channel-level granularity for Slack
- Consistent filtering on Sources page

### Negative
- Additional complexity for Slack access control
- Migration required for existing Slack links
- Need to handle permission checks for multi-guild Slack

### Neutral
- WhatsApp remains single-owner (appropriate for private imports)
- Discord unchanged (native model is correct)

## Related ADRs

- ADR-043: Slack Workspace Integration
- ADR-079: Subdomain Multi-Tenancy
- ADR-081: WhatsApp Import Management
