# ADR-099: Remote Platform Publishing

## Status
Proposed

## Context

Summaries can currently be delivered via:
- Discord channel push
- Direct Message (ADR-047)
- Email (ADR-030)
- Google Drive sync (ADR-091)

Users want to publish summaries to external knowledge management platforms like Atlassian Confluence, Notion, and others. This enables teams to build a searchable knowledge base from their Discord conversations.

### Requirements
1. **Extensible Platform Support**: Start with Confluence, design for others (Notion, SharePoint, etc.)
2. **Service Account Authentication**: Shared connections via service account, not per-user OAuth
3. **Role-Based Access Control**: Only certain Discord roles can publish
4. **Guild-Level Configuration**: Target space/database configurable per guild
5. **Idempotent Operations**: Re-publishing updates existing page, doesn't create duplicates
6. **Publication Tracking**: Remember what's been published, when, and where
7. **Bidirectional References**: Published page links back to SummaryBot (hidden metadata)
8. **Labels/Tags System**: Categorize summaries for filtering and workflow status

## Decision

### 1. Platform Connection Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Remote Platform Connections            │
├─────────────────────────────────────────────────────────┤
│  Guild Config                                           │
│  ├── confluence_connection_id: "conn_abc123"            │
│  ├── confluence_space_key: "TEAM"                       │
│  ├── confluence_parent_page_id: "12345" (optional)      │
│  ├── publish_roles: ["Admin", "Moderator"]              │
│  └── auto_publish_labels: ["approved"]                  │
├─────────────────────────────────────────────────────────┤
│  Platform Connections (tenant-level)                    │
│  ├── id: "conn_abc123"                                  │
│  ├── platform: "confluence"                             │
│  ├── base_url: "https://company.atlassian.net"          │
│  ├── credentials: (encrypted service account)          │
│  ├── guild_ids: ["123", "456"] (guilds with access)     │
│  └── created_by: "user_id"                              │
└─────────────────────────────────────────────────────────┘
```

### 2. Database Schema

```sql
-- Remote platform connections (service accounts)
CREATE TABLE remote_platform_connections (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,  -- 'confluence', 'notion', 'sharepoint'
    name TEXT NOT NULL,      -- Display name
    base_url TEXT NOT NULL,
    credentials_encrypted TEXT NOT NULL,  -- Encrypted JSON
    created_by TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Guild access to connections
CREATE TABLE remote_platform_guild_access (
    connection_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    space_key TEXT,          -- Confluence space key
    parent_page_id TEXT,     -- Optional parent page
    publish_roles TEXT,      -- JSON array of role names
    auto_publish_labels TEXT, -- JSON array of labels that trigger auto-publish
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (connection_id, guild_id),
    FOREIGN KEY (connection_id) REFERENCES remote_platform_connections(id)
);

-- Publication tracking
CREATE TABLE remote_publications (
    id TEXT PRIMARY KEY,
    summary_id TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,    -- Confluence page ID, Notion page ID, etc.
    external_url TEXT,            -- Direct link to published page
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_by TEXT NOT NULL,   -- User who triggered publish
    version INTEGER DEFAULT 1,    -- Incremented on re-publish
    last_updated_at TIMESTAMP,
    status TEXT DEFAULT 'published',  -- 'published', 'deleted', 'failed'
    FOREIGN KEY (summary_id) REFERENCES stored_summaries(id),
    FOREIGN KEY (connection_id) REFERENCES remote_platform_connections(id)
);

CREATE INDEX idx_remote_publications_summary ON remote_publications(summary_id);
CREATE INDEX idx_remote_publications_external ON remote_publications(platform, external_id);

-- Summary labels (extends existing tags)
CREATE TABLE summary_labels (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    name TEXT NOT NULL,
    color TEXT,              -- Hex color code
    description TEXT,
    category TEXT,           -- 'status', 'topic', 'priority', 'custom'
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, name)
);

CREATE TABLE summary_label_assignments (
    summary_id TEXT NOT NULL,
    label_id TEXT NOT NULL,
    assigned_by TEXT,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (summary_id, label_id),
    FOREIGN KEY (summary_id) REFERENCES stored_summaries(id),
    FOREIGN KEY (label_id) REFERENCES summary_labels(id)
);

-- Guild publishers (users who can publish to remote platforms)
CREATE TABLE guild_publishers (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    granted_by TEXT NOT NULL,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    can_force_update BOOLEAN DEFAULT FALSE,  -- Override external modifications
    UNIQUE(guild_id, user_id)
);

CREATE INDEX idx_guild_publishers_guild ON guild_publishers(guild_id);
```

### 3. Label System Design

Labels are **local only** - they control SummaryBot workflow and filtering but are not
synced to Confluence. Confluence labels are managed directly in Confluence by users.

#### Default Labels (Created Per Guild)

| Category | Label | Color | Description |
|----------|-------|-------|-------------|
| **Status** | `draft` | Gray | Not ready for publishing |
| **Status** | `review` | Yellow | Awaiting review |
| **Status** | `approved` | Green | Ready to publish |
| **Status** | `published` | Blue | Published to external platform |
| **Status** | `archived` | Purple | Historical, no longer active |
| **Priority** | `important` | Red | High-priority summary |
| **Priority** | `routine` | Gray | Regular summary |
| **Topic** | `decision` | Orange | Contains decisions |
| **Topic** | `action-items` | Teal | Contains action items |

#### Label UX Locations

1. **Summary List View**: Small colored chips next to title
2. **Summary Detail View**: Label bar below title with add/remove
3. **Filter Panel**: Filter by label in summary list
4. **Bulk Operations**: Apply/remove labels to multiple summaries
5. **Publish Dialog**: Show current labels, require "approved" for publish
6. **Auto-Publish Rules**: Configure which labels trigger auto-publish

### 4. Confluence Integration

#### 4.1 Idempotency & Conflict Handling

```
On Publish:
1. Check if summary has stored remote_page_id
   ├── NO: Create new page, store page_id
   └── YES:
       a. Check if page exists on Confluence
          └── If DELETED: Create new page, update stored page_id
       b. Check if page modified externally (compare version numbers)
          └── If MODIFIED: REFUSE with error "Page was modified on Confluence.
              Delete it there to re-publish, or use 'Force Update' (admin only)"
       c. Update page content, increment version
2. Store/update publication record
```

#### 4.2 API Operations

```python
class ConfluencePublisher:
    """Confluence publishing via REST API v2."""

    async def publish_summary(
        self,
        summary: StoredSummary,
        connection: RemotePlatformConnection,
        config: GuildPlatformConfig,
        force: bool = False,  # Admin-only override for conflicts
    ) -> RemotePublication:
        """
        Publish or update summary to Confluence.

        Raises:
            PageModifiedExternallyError: If page was edited on Confluence
            PageDeletedError: (handled internally - recreates page)
        """

        existing = await self.get_existing_publication(summary.id, connection.id)

        if existing:
            # Check if page still exists
            page_exists = await self.page_exists(existing.external_id)

            if not page_exists:
                # Page was deleted on Confluence - recreate
                return await self._create_new_page(summary, connection, config)

            # Check for external modifications
            current_version = await self.get_page_version(existing.external_id)
            if current_version != existing.version and not force:
                raise PageModifiedExternallyError(
                    f"Page was modified on Confluence (version {current_version} vs "
                    f"expected {existing.version}). Delete it on Confluence to re-publish."
                )

            # Update existing page
            page = await self.update_page(
                page_id=existing.external_id,
                title=summary.title,
                content=self._format_adf_content(summary),
                version=current_version + 1,
            )
            existing.version = current_version + 1
            existing.last_updated_at = utc_now()
            return existing
        else:
            return await self._create_new_page(summary, connection, config)

    async def _create_new_page(
        self,
        summary: StoredSummary,
        connection: RemotePlatformConnection,
        config: GuildPlatformConfig,
    ) -> RemotePublication:
        """Create new Confluence page."""
        page = await self.create_page(
            space_key=config.space_key,
            parent_id=config.parent_page_id,
            title=summary.title,
            content=self._format_adf_content(summary),
            labels=["summarybot"],  # Minimal identifier; users manage labels in Confluence
            metadata={
                "summarybot_summary_id": summary.id,
                "summarybot_guild_id": summary.guild_id,
                "summarybot_url": f"https://summarybot.app/guilds/{summary.guild_id}/summaries?view={summary.id}",
            },
        )
        return RemotePublication(
            id=generate_id("pub"),
            summary_id=summary.id,
            connection_id=connection.id,
            platform="confluence",
            external_id=page.id,
            external_url=page.url,
            version=1,
        )

    def _format_adf_content(self, summary: StoredSummary) -> dict:
        """
        Format summary as Atlassian Document Format (ADF).

        ADF is JSON-based and supports rich macros for enhanced display.
        See: https://developer.atlassian.com/cloud/confluence/adf-json-specification/
        """
        return {
            "type": "doc",
            "version": 1,
            "content": [
                # Info panel with source link
                {
                    "type": "panel",
                    "attrs": {"panelType": "info"},
                    "content": [{
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Generated by "},
                            {
                                "type": "text",
                                "text": "SummaryBot",
                                "marks": [{"type": "link", "attrs": {
                                    "href": f"https://summarybot.app/guilds/{summary.guild_id}/summaries?view={summary.id}"
                                }}]
                            },
                            {"type": "text", "text": " on "},
                            # Date macro - renders as localized date
                            {
                                "type": "date",
                                "attrs": {"timestamp": str(int(summary.created_at.timestamp() * 1000))}
                            }
                        ]
                    }]
                },
                # Summary section
                {"type": "heading", "attrs": {"level": 2}, "content": [
                    {"type": "text", "text": "Summary"}
                ]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": summary.summary_result.summary_text}
                ]},
                # Key Points section
                {"type": "heading", "attrs": {"level": 2}, "content": [
                    {"type": "text", "text": "Key Points"}
                ]},
                {
                    "type": "bulletList",
                    "content": [
                        {"type": "listItem", "content": [
                            {"type": "paragraph", "content": [
                                {"type": "text", "text": point}
                            ]}
                        ]} for point in summary.summary_result.key_points
                    ]
                },
                # Action items with task list and status lozenges
                *self._format_action_items_adf(summary),
                # Decisions section (if any)
                *self._format_decisions_adf(summary),
                # Expandable metadata
                {
                    "type": "expand",
                    "attrs": {"title": "SummaryBot Metadata"},
                    "content": [{
                        "type": "table",
                        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
                        "content": [
                            self._table_row("Summary ID", summary.id),
                            self._table_row("Guild", summary.guild_id),
                            self._table_row("Channels", ", ".join(summary.channel_names or [])),
                            self._table_row("Messages", str(summary.message_count)),
                        ]
                    }]
                }
            ]
        }

    def _format_action_items_adf(self, summary: StoredSummary) -> list:
        """Format action items with task list and status lozenges."""
        if not summary.summary_result.action_items:
            return []

        return [
            {"type": "heading", "attrs": {"level": 2}, "content": [
                {"type": "text", "text": "Action Items"}
            ]},
            {
                "type": "taskList",
                "attrs": {"localId": f"tasks-{summary.id}"},
                "content": [
                    {
                        "type": "taskItem",
                        "attrs": {"localId": f"task-{i}", "state": "TODO"},
                        "content": [{
                            "type": "paragraph",
                            "content": [
                                # Status lozenge for priority
                                {
                                    "type": "status",
                                    "attrs": {
                                        "text": "TODO",
                                        "color": "neutral",
                                        "localId": f"status-{i}"
                                    }
                                },
                                {"type": "text", "text": f" {item.description}"},
                                # Mention placeholder (deferred - requires user mapping)
                                # {"type": "mention", "attrs": {"id": "user_id", "text": "@assignee"}}
                            ]
                        }]
                    } for i, item in enumerate(summary.summary_result.action_items)
                ]
            }
        ]

    def _format_decisions_adf(self, summary: StoredSummary) -> list:
        """Format decisions with decision macro styling."""
        if not summary.summary_result.decisions:
            return []

        return [
            {"type": "heading", "attrs": {"level": 2}, "content": [
                {"type": "text", "text": "Decisions"}
            ]},
            # Decision panel for each decision
            *[{
                "type": "panel",
                "attrs": {"panelType": "success"},  # Green panel for decisions
                "content": [{
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "status",
                            "attrs": {"text": "DECIDED", "color": "green", "localId": f"dec-{i}"}
                        },
                        {"type": "text", "text": f" {decision}"}
                    ]
                }]
            } for i, decision in enumerate(summary.summary_result.decisions)]
        ]

    def _table_row(self, label: str, value: str) -> dict:
        """Create a table row for metadata display."""
        return {
            "type": "tableRow",
            "content": [
                {"type": "tableCell", "content": [
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": label, "marks": [{"type": "strong"}]}
                    ]}
                ]},
                {"type": "tableCell", "content": [
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": value}
                    ]}
                ]}
            ]
        }
```

#### 4.3 ADF Macros Used

| Macro | Purpose | Example |
|-------|---------|---------|
| **panel** | Info/success/warning boxes | Source attribution, decisions |
| **date** | Localized date display | Generated timestamp |
| **status** | Colored status lozenges | TODO, DECIDED, IN PROGRESS |
| **taskList** | Interactive task items | Action items with checkboxes |
| **expand** | Collapsible sections | Hidden metadata |
| **table** | Structured data display | Summary metadata |
| **mention** | User references | Assignees (deferred - requires user mapping) |

Future: When user mapping is implemented, `@username` references in action items
can be converted to Confluence mentions via `{"type": "mention", "attrs": {"id": "atlassian_user_id"}}`.

### 5. API Endpoints

```
# Platform Connections (Admin only)
POST   /api/v1/platforms/connections           # Create connection
GET    /api/v1/platforms/connections           # List connections
GET    /api/v1/platforms/connections/{id}      # Get connection
PUT    /api/v1/platforms/connections/{id}      # Update connection
DELETE /api/v1/platforms/connections/{id}      # Delete connection
POST   /api/v1/platforms/connections/{id}/test # Test connection

# Guild Platform Config
GET    /api/v1/guilds/{guild_id}/platforms                    # List configured platforms
POST   /api/v1/guilds/{guild_id}/platforms/{connection_id}    # Configure for guild
PUT    /api/v1/guilds/{guild_id}/platforms/{connection_id}    # Update config
DELETE /api/v1/guilds/{guild_id}/platforms/{connection_id}    # Remove access

# Publishing
POST   /api/v1/guilds/{guild_id}/summaries/{id}/publish       # Publish to platform
GET    /api/v1/guilds/{guild_id}/summaries/{id}/publications  # List publications
DELETE /api/v1/guilds/{guild_id}/summaries/{id}/publications/{pub_id}  # Unpublish

# Labels
GET    /api/v1/guilds/{guild_id}/labels                       # List labels
POST   /api/v1/guilds/{guild_id}/labels                       # Create label
PUT    /api/v1/guilds/{guild_id}/labels/{id}                  # Update label
DELETE /api/v1/guilds/{guild_id}/labels/{id}                  # Delete label
POST   /api/v1/guilds/{guild_id}/summaries/{id}/labels        # Assign labels
DELETE /api/v1/guilds/{guild_id}/summaries/{id}/labels/{label_id}  # Remove label
```

### 6. Frontend Components

#### Summary Detail - Publish Menu
```
┌─────────────────────────────────────────┐
│  📤 Publish to...                       │
├─────────────────────────────────────────┤
│  ☁️ Confluence (TEAM space)     [Publish]│
│     └─ Last published: Never            │
│                                         │
│  📝 Notion (coming soon)        [Setup] │
│                                         │
│  ─────────────────────────────────────  │
│  Labels: [draft ×] [+ Add label]        │
│                                         │
│  ⚠️ Add "approved" label to publish     │
└─────────────────────────────────────────┘
```

#### Label Management
```
┌─────────────────────────────────────────┐
│  Summary Labels                         │
├─────────────────────────────────────────┤
│  Status                                 │
│  ○ draft  ○ review  ● approved          │
│                                         │
│  Topics                                 │
│  ☑ decision  ☐ action-items             │
│                                         │
│  Custom                                 │
│  [+ Create label]                       │
└─────────────────────────────────────────┘
```

### 7. Publisher Role System

Publishing requires a dedicated **Publisher** role, separate from Discord server roles.
This allows fine-grained control over who can publish to external platforms.

#### 7.1 Database Schema

```sql
-- Guild publishers (users who can publish)
CREATE TABLE guild_publishers (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    granted_by TEXT NOT NULL,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    can_force_update BOOLEAN DEFAULT FALSE,  -- Admin override for conflicts
    UNIQUE(guild_id, user_id)
);

CREATE INDEX idx_guild_publishers_guild ON guild_publishers(guild_id);
```

#### 7.2 Access Control Logic

```python
@dataclass
class PublisherRole:
    """Publisher permissions for a guild."""
    user_id: str
    guild_id: str
    can_force_update: bool = False  # Override external modifications

async def can_publish(user: User, guild_id: str) -> bool:
    """Check if user has Publisher role for this guild."""
    # Guild admins can always publish
    if await is_guild_admin(user, guild_id):
        return True

    # Check explicit Publisher role
    publisher = await get_publisher_role(user.id, guild_id)
    return publisher is not None

async def can_force_update(user: User, guild_id: str) -> bool:
    """Check if user can force-update externally modified pages."""
    # Only guild admins or publishers with explicit permission
    if await is_guild_admin(user, guild_id):
        return True

    publisher = await get_publisher_role(user.id, guild_id)
    return publisher is not None and publisher.can_force_update
```

#### 7.3 Publisher Management API

```
# Publisher management (Admin only)
GET    /api/v1/guilds/{guild_id}/publishers           # List publishers
POST   /api/v1/guilds/{guild_id}/publishers           # Grant publisher role
DELETE /api/v1/guilds/{guild_id}/publishers/{user_id} # Revoke publisher role
PUT    /api/v1/guilds/{guild_id}/publishers/{user_id} # Update permissions
```

#### 7.4 Frontend - Publisher Management

```
┌─────────────────────────────────────────────────────┐
│  Publishers                                    [+Add]│
├─────────────────────────────────────────────────────┤
│  👤 Alice                                           │
│     └─ Can force update: ✓                    [Remove]│
│                                                     │
│  👤 Bob                                             │
│     └─ Can force update: ✗                    [Remove]│
│                                                     │
│  ─────────────────────────────────────────────────  │
│  ℹ️ Admins can always publish. Publishers can       │
│     publish summaries to configured platforms.      │
└─────────────────────────────────────────────────────┘
```

### 8. Publication Workflow

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌───────────┐
│  Draft   │───▶│  Review  │───▶│ Approved │───▶│ Published │
└──────────┘    └──────────┘    └──────────┘    └───────────┘
     │                                               │
     │              Manual publish                   │
     └───────────────────────────────────────────────┘

Auto-publish (if configured):
- Summary gets "approved" label → auto-publish to Confluence
```

## Implementation Plan

### Phase 1: Foundation
1. Database migrations for connections, publications, labels, publishers
2. Label CRUD API and UI
3. Label assignment to summaries
4. Publisher role management API and UI

### Phase 2: Confluence Integration
1. Confluence API client with long-lived API token auth
2. ADF content formatting with macros (panel, date, status, taskList, expand, table)
3. Connection management UI (admin)
4. Guild configuration UI
5. Publish action with idempotency and conflict detection

### Phase 3: Publishing UI
1. Publish menu in summary detail (Publishers only)
2. Publication status indicators
3. Re-publish / unpublish actions
4. Force update option (admin/elevated Publishers only)
5. Bulk publish support

### Phase 4: Auto-Publish & Extensions
1. Label-based auto-publish rules (local labels trigger publish)
2. Notion integration
3. SharePoint integration (future)
4. User mapping for @mentions (future)

## Consequences

### Positive
- Summaries become part of team knowledge base
- Searchable in Confluence alongside other docs
- Workflow support via labels
- Service account = no per-user auth needed

### Negative
- Additional external dependency (Confluence API)
- Credential management complexity
- Need to handle API rate limits
- Content formatting differences between platforms

### Risks
- Confluence API changes could break integration
- Large summaries may hit content limits
- Service account permissions need careful scoping

## Security Considerations

1. **Credential Storage**: Encrypt service account credentials at rest using AES-256-GCM
2. **Long-Lived API Tokens**: Use Atlassian API tokens (not OAuth) for service accounts
   - Tokens created at https://id.atlassian.com/manage-profile/security/api-tokens
   - Stored as `email:api_token` base64-encoded in credentials_encrypted
   - No token refresh logic needed - tokens are long-lived until manually revoked
3. **Access Control**: Guild admins configure connections; Publishers can publish
4. **Publisher Role**: Dedicated role separate from Discord roles for publishing permissions
5. **Audit Trail**: Log all publish/unpublish actions with user, timestamp, and target
6. **Scope Limiting**: Request minimal Confluence permissions (read/write pages in configured space)
7. **Data Exposure**: Only publish summaries explicitly requested by Publisher role users

### Credential Format

```python
@dataclass
class ConfluenceCredentials:
    """Confluence API credentials using long-lived API token."""
    email: str           # Atlassian account email (service account)
    api_token: str       # API token from https://id.atlassian.com/manage
    # No refresh_token - API tokens are long-lived

    def to_auth_header(self) -> str:
        """Generate Basic auth header value."""
        import base64
        credentials = f"{self.email}:{self.api_token}"
        return f"Basic {base64.b64encode(credentials.encode()).decode()}"
```

## References

- [Confluence REST API v2](https://developer.atlassian.com/cloud/confluence/rest/v2/)
- [ADR-030: Email Delivery](./ADR-030-email-delivery.md)
- [ADR-047: Discord DM Delivery](./ADR-047-discord-dm-delivery.md)
- [ADR-091: Google Drive Sync](./ADR-091-google-drive-sync.md)
