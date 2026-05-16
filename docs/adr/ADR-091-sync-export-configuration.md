# ADR-091: Google Drive Sync Export Configuration

## Status

Implementing (wiki export deferred)

## Context

ADR-007 introduced **per-server Google Drive sync** for backing up summaries. Each Discord server (tenant) can configure their own Google Drive destination, with a fallback to the bot operator's global Drive.

### Per-Tenant Model

| Level | Authentication | Use Case |
|-------|---------------|----------|
| Server-specific | OAuth (server admin's account) | Organizations owning their data |
| Global fallback | Service account (bot operator) | Servers without custom config |

The initial implementation syncs all database summaries as markdown + JSON files to a flat folder structure. Users need more control over:

1. **What to sync** - Filter by source, date range, channels, or any summary attribute
2. **Export format** - JSON is verbose; many users only want human-readable markdown
3. **Folder organization** - Flat structure becomes unwieldy with hundreds of files
4. **Content types** - Wiki pages should sync separately from chat summaries

## Decision

### 1. Export Filtering

Allow users to configure sync filters using the same criteria as the Summaries page (ADR-037: Centralized Filter Criteria):

```typescript
interface SyncExportConfig {
  // What to export
  filters: {
    source?: "realtime" | "scheduled" | "archive" | "manual" | "imported";
    platform?: "discord" | "slack" | "whatsapp";
    granularity?: "daily" | "weekly" | "monthly";
    channels?: string[];           // Specific channel IDs
    createdAfter?: string;         // ISO date
    createdBefore?: string;        // ISO date
    hasKeyPoints?: boolean;
    hasActionItems?: boolean;
    minMessageCount?: number;
    tags?: string[];
  };

  // Format options
  includeJson: boolean;            // Default: false (markdown only)

  // Folder structure
  folderStructure: "flat" | "by-period" | "by-channel";
  periodGrouping: "week" | "month";  // When folderStructure = "by-period"
}
```

### 2. Folder Structure

Top-level separation by content type:

```
SummaryBot Sync/
├── conversations/               # Chat summaries
│   ├── 2026-05-05--2026-05-11/  # Period folders (date range)
│   │   ├── weekly-dev-sync_12ab.md
│   │   └── weekly-dev-sync_12ab.json  # If includeJson = true
│   └── 2026-05-12--2026-05-18/
│       └── ...
└── wiki/                        # Wiki page exports
    ├── 2026-05-05--2026-05-11/
    │   ├── authentication.md
    │   └── api-reference.md
    └── 2026-05-12--2026-05-18/
        └── ...
```

**Period folder naming**: Use date ranges (`YYYY-MM-DD--YYYY-MM-DD`) rather than "week" terminology to:
- Avoid confusion with wiki weekly summaries
- Be self-documenting (no need to decode week numbers)
- Work naturally for both weekly and monthly groupings

### 3. Export Format Options

| Option | Files Created | Use Case |
|--------|--------------|----------|
| Markdown only (default) | `.md` | Human-readable backup, Drive preview |
| Markdown + JSON | `.md` + `.json` | Full backup with restoration capability |

JSON excluded by default because:
- Most users want human-readable files in Drive
- JSON doubles storage and sync time
- Users who need full backup can enable it

### 4. UI Configuration

Add sync configuration panel in **Settings page** (not Retrospective - sync configuration is a settings concern):

```
┌─────────────────────────────────────────────────────────────┐
│ Google Drive Sync                                           │
├─────────────────────────────────────────────────────────────┤
│ Connected as: admin@example.com                             │
│ Folder: Shared Drives > Engineering > SummaryBot            │
│                                                             │
│ Export Settings                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Content: [All Summaries ▼] [Edit Filters]               │ │
│ │ Format:  [x] Markdown  [ ] Include JSON backup          │ │
│ │ Organize: [By Period ▼] → [Weekly ▼]                    │ │
│ │ Include:  [x] Conversations  [ ] Wiki Pages             │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Stats: 247 summaries available (12 new since last sync)    │
│                                                             │
│ [Sync Sample (3)]  [Sync All (247)]  Last: 2026-05-09      │
│                                                             │
│ ℹ️  "Sync Sample" uploads 3 recent files so you can verify │
│     folder structure and format before syncing everything.  │
└─────────────────────────────────────────────────────────────┘
```

**Note**: For tenanted servers, only Shared Drives are available as destinations. My Drive is disabled to ensure organizational data ownership and continuity.

**Location rationale**: Sync configuration belongs in Settings because:
- It's a per-server configuration, not a retrospective action
- Users configure it once and forget about it
- Consistent with other integration settings (prompt repos, channel sensitivity)

### 5. Database Schema

Extend `sync_server_configs` table:

```sql
ALTER TABLE sync_server_configs ADD COLUMN export_filters TEXT;  -- JSON
ALTER TABLE sync_server_configs ADD COLUMN include_json INTEGER DEFAULT 0;
ALTER TABLE sync_server_configs ADD COLUMN folder_structure TEXT DEFAULT 'by-period';
ALTER TABLE sync_server_configs ADD COLUMN period_grouping TEXT DEFAULT 'week';
ALTER TABLE sync_server_configs ADD COLUMN include_wiki INTEGER DEFAULT 0;
ALTER TABLE sync_server_configs ADD COLUMN include_conversations INTEGER DEFAULT 1;
```

### 6. Incremental Sync

Track what's been synced to avoid re-uploading:

```sql
CREATE TABLE sync_history (
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    summary_id TEXT NOT NULL,
    drive_file_id TEXT,          -- Google Drive file ID
    synced_at TEXT NOT NULL,
    file_type TEXT NOT NULL,     -- 'md' or 'json'
    UNIQUE(server_id, summary_id, file_type)
);
```

On sync:
1. Query summaries matching filters
2. Exclude those already in `sync_history`
3. Upload only new/updated summaries
4. Record in `sync_history`

### 7. Sync Sample Preview

Allow admins to preview what will be synced before committing to a full sync:

```
┌─────────────────────────────────────────────────────────────┐
│ Google Drive Sync                                           │
├─────────────────────────────────────────────────────────────┤
│ Connected as: admin@example.com                             │
│ Folder: Shared Drives > Engineering > SummaryBot            │
│                                                             │
│ Export Settings                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Content: Weekly summaries only                          │ │
│ │ Format:  [x] Markdown  [ ] Include JSON backup          │ │
│ │ Organize: By Period → Weekly                            │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ [Sync Sample (3 files)]  [Sync All (247 files)]            │
│                                                             │
│ Preview: What "Sync Sample" will create                     │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ conversations/                                          │ │
│ │   └─ 2026-05-12--2026-05-18/                            │ │
│ │       ├─ weekly-dev-sync_a1b2.md (2.1 KB)               │ │
│ │       ├─ weekly-product-standup_c3d4.md (1.8 KB)        │ │
│ │       └─ weekly-design-review_e5f6.md (3.2 KB)          │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Sample Sync Behavior**:
- Syncs only the **3 most recent** summaries matching current filters
- Creates actual files in Google Drive (not a dry run)
- Admin can verify folder structure, file format, and content
- Files are marked in `sync_history` so they won't be re-synced

**API Endpoint**:
```python
@router.post("/sync/sample")
async def sync_sample(
    server_id: str,
    config: SyncExportConfig,
    sample_size: int = 3,
) -> SyncResult:
    """
    Sync a small sample of summaries for admin preview.

    Args:
        server_id: Discord server ID
        config: Current export configuration
        sample_size: Number of summaries to sync (default: 3)

    Returns:
        SyncResult with files synced and their Drive URLs
    """
    summaries = await get_summaries_matching_filters(
        server_id=server_id,
        filters=config.filters,
        limit=sample_size,
        order_by="created_at DESC",  # Most recent first
    )
    return await sync_summaries_to_drive(server_id, summaries, config)
```

**Benefits**:
- Admins see exactly what will happen before full sync
- Catches configuration errors early (wrong folder, format issues)
- Builds confidence in sync configuration
- Low-risk way to test new filter settings

### 8. Period Folder Logic

```python
def get_period_folder_name(date: datetime, grouping: str) -> str:
    """Generate period folder name from a date."""
    if grouping == "week":
        # ISO week: Monday to Sunday
        week_start = date - timedelta(days=date.weekday())
        week_end = week_start + timedelta(days=6)
        return f"{week_start.strftime('%Y-%m-%d')}--{week_end.strftime('%Y-%m-%d')}"
    elif grouping == "month":
        month_start = date.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        return f"{month_start.strftime('%Y-%m-%d')}--{month_end.strftime('%Y-%m-%d')}"
```

## Implementation

### Phase 1: Core Export Configuration
- [ ] Add `SyncExportConfig` model
- [ ] Extend `ServerSyncConfig` with export settings
- [ ] Create migration for new columns
- [ ] Update sync trigger to use filters

### Phase 2: Folder Structure
- [ ] Implement period folder creation in Drive
- [ ] Add `conversations/` and `wiki/` top-level folders
- [ ] Place files in correct period folders

### Phase 3: Incremental Sync
- [ ] Create `sync_history` table
- [ ] Track synced files by Drive file ID
- [ ] Only sync new/updated summaries

### Phase 4: UI
- [x] Add export settings panel to Settings page (moved from Retrospective)
- [ ] Integrate summary filter picker
- [ ] Show new-since-last-sync count
- [ ] Add "Sync Sample" button with preview
- [ ] Disable My Drive selection for tenanted servers
- [ ] Show warning when Shared Drive required

### Phase 5: Domain Validation (Future)
- [ ] Add Google Admin SDK scope for domain lookup
- [ ] Validate Shared Drive ownership matches user domain
- [ ] Block sync to external organization drives
- [ ] Add admin override for cross-domain (if needed)

## Consequences

### Positive
- Users control what gets synced (reduce noise)
- Organized folder structure (easier to navigate)
- Smaller sync payloads (only markdown by default)
- Wiki and conversations separated (clearer purpose)
- Incremental sync (faster, less API usage)
- Shared Drive requirement ensures data ownership continuity
- Sample sync reduces configuration errors
- Domain validation (future) prevents data leakage

### Negative
- More configuration options (complexity)
- Period folders may have gaps (if no summaries in period)
- Breaking change for existing syncs (files move to new structure)
- Shared Drive requirement may block personal use cases
- Users without Shared Drive access cannot use per-server sync

### Migration
- Existing synced files remain in place (don't move)
- New syncs use new folder structure
- Optional: "Reorganize existing files" button

## Alternatives Considered

### Folder naming alternatives

| Option | Example | Pros | Cons |
|--------|---------|------|------|
| ISO week | `2026-W19` | Compact | Requires lookup to know dates |
| Date range | `2026-05-05--2026-05-11` | Self-documenting | Longer |
| Month + week | `2026-05-W2` | Compact, contextual | Still needs interpretation |
| Named periods | `period-19-2026` | Neutral | Less intuitive |

**Chosen**: Date range - most user-friendly, no mental math required.

### Top-level naming alternatives

| Option | Chosen |
|--------|--------|
| `chat/` vs `wiki/` | ❌ "chat" too informal |
| `conversations/` vs `wiki/` | ✅ Clear, professional |
| `summaries/` vs `wiki/` | ❌ "summaries" ambiguous |
| `messages/` vs `wiki/` | ❌ Messages aren't synced |

## Per-Tenant Architecture

Google Drive sync uses a **per-server (per-tenant) model** as defined in ADR-007:

### Configuration Isolation

Each Discord server has its own:
- Google Drive connection (via OAuth)
- Target folder (Shared Drive only for tenanted servers)
- Export settings (folder structure, JSON toggle, period grouping)
- Sync statistics (files synced, last sync time)

### Shared Drive Requirement for Tenanted Servers

**Policy**: Tenanted servers (those with per-server OAuth) MUST use a Shared Drive, not My Drive.

| Server Type | My Drive | Shared Drive |
|-------------|----------|--------------|
| Tenanted (per-server OAuth) | ❌ Disabled | ✅ Required |
| Global fallback (service account) | ✅ Allowed | ✅ Allowed |

**Rationale**:
- **Data ownership**: My Drive is personal; if the admin leaves the org, data is lost
- **Team access**: Shared Drives provide org-wide access control
- **Compliance**: Data stays in org-controlled storage
- **Continuity**: Admin changes don't disrupt sync

**UI Enforcement**:
```
┌─────────────────────────────────────────────────────────────┐
│ Select Destination Folder                                   │
├─────────────────────────────────────────────────────────────┤
│ ⚠️  My Drive is not available for server sync.              │
│     Please select a Shared Drive folder.                    │
│                                                             │
│ Shared Drives                                               │
│   ├─ Engineering Team                                       │
│   │   └─ SummaryBot Sync                                    │
│   └─ Product                                                │
│       └─ Archives                                           │
└─────────────────────────────────────────────────────────────┘
```

### Future: Domain-Owned Shared Drive Validation

**Status**: Planned (Phase 5)

For enhanced security, validate that the selected Shared Drive belongs to the same Google Workspace domain as the authenticating user:

```python
async def validate_shared_drive_domain(
    drive_id: str,
    user_email: str,
    credentials: Credentials,
) -> bool:
    """
    Validate Shared Drive is owned by the user's domain.

    Args:
        drive_id: Google Drive ID of the Shared Drive
        user_email: Authenticated user's email (e.g., admin@example.com)
        credentials: OAuth credentials

    Returns:
        True if Shared Drive domain matches user's email domain
    """
    user_domain = user_email.split("@")[1]

    # Get Shared Drive metadata
    drive_service = build("drive", "v3", credentials=credentials)
    drive_info = drive_service.drives().get(driveId=drive_id).execute()

    # Check org unit or domain ownership
    # Note: Requires additional Google Admin SDK access
    return drive_info.get("orgUnitId") == get_org_unit_for_domain(user_domain)
```

**Benefits**:
- Prevents sync to external organizations
- Ensures data stays within tenant's Google Workspace
- Supports compliance requirements (data residency)

**Implementation Notes**:
- Requires Google Admin SDK access (additional scope)
- May need org-level consent for domain validation
- Fallback: Trust user selection if domain validation unavailable

### Resolution Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                  Sync Destination Resolution                │
├─────────────────────────────────────────────────────────────┤
│  1. Server-specific Shared Drive (OAuth, configured admin)  │
│     └─► Admin connects their Google Workspace account       │
│     └─► MUST select a Shared Drive (My Drive disabled)      │
│     └─► Files sync to chosen Shared Drive folder            │
│                                                             │
│  2. Global fallback Drive (Service Account, by bot op)      │
│     └─► Used when server has no custom config               │
│     └─► Creates subfolder: {server_name}_{server_id}        │
│     └─► My Drive or Shared Drive allowed (operator choice)  │
│                                                             │
│  3. Local storage only (no cloud sync)                      │
│     └─► When no Drive is configured at any level            │
└─────────────────────────────────────────────────────────────┘
```

### Data Ownership Benefits

- **Compliance**: Each org controls their data storage location
- **Cost isolation**: Storage costs attributed to respective orgs
- **Access control**: Only that org's members access their Drive
- **Independence**: One org disconnecting doesn't affect others

## References

- ADR-007: Per-Server Google Drive Sync
- ADR-037: Centralized Filter Criteria
- ADR-087: Wiki Ingestion Granularity
