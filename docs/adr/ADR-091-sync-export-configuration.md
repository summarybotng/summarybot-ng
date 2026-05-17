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
    scope?: "server" | "channel";   // Server-wide vs single-channel
    channels?: string[];            // Specific channel IDs
    createdAfter?: string;          // ISO date
    createdBefore?: string;         // ISO date
    hasKeyPoints?: boolean;
    hasActionItems?: boolean;
    minMessageCount?: number;
    tags?: string[];
    syncEligible?: boolean;         // Only summaries marked for sync
  };

  // Format options
  includeMarkdown: boolean;        // Default: true
  includeJson: boolean;            // Default: false

  // Folder structure
  folderStructure: "flat" | "by-period" | "by-channel";
  periodGrouping: "week" | "month";  // When folderStructure = "by-period"
}
```

### Common Filter Presets

| Preset | Filters | Use Case |
|--------|---------|----------|
| Weekly Channel Summaries | `granularity: "weekly", scope: "channel"` | Individual channel reports |
| Server-wide Weeklies | `granularity: "weekly", scope: "server"` | Cross-channel rollups |
| Scheduled Only | `source: "scheduled"` | Automated summaries only |
| Manual Exports | `source: "manual"` | User-triggered summaries |
| With Action Items | `hasActionItems: true` | Actionable summaries |
| Sync-Eligible Only | `syncEligible: true` | Per-summary opt-in |

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
| JSON only | `.json` | Machine-readable, restoration capability |
| Markdown + JSON | `.md` + `.json` | Full backup with both formats |

**Default settings**:
- `includeMarkdown: true` - Human-readable format
- `includeJson: false` - Machine-readable backup (opt-in)

**Rationale for defaults**:
- Most users want human-readable files in Drive
- JSON doubles storage and sync time
- Users who need full backup can enable JSON
- Sample sync respects both toggles for accurate preview

**Sample sync behavior**:
- Sample sync includes both MD and JSON if configured
- Allows admin to verify both file types before full sync

### 4. Sync Eligibility at Creation

Summaries can be marked as "sync eligible" at the point of creation, providing per-summary control over what gets synced.

#### Discord Push Options

When pushing a summary to Discord, add sync eligibility toggle:

```
┌─────────────────────────────────────────────────────────────┐
│ Push Summary to Discord                                     │
├─────────────────────────────────────────────────────────────┤
│ Channel: #dev-updates                                       │
│ Format:  [Detailed ▼]                                       │
│                                                             │
│ [x] Available for Google Drive sync                         │
│     └─ This summary will be included in the next sync       │
│                                                             │
│ [Cancel]  [Push to Discord]                                 │
└─────────────────────────────────────────────────────────────┘
```

#### Scheduler Configuration

Scheduled summaries can have a default sync eligibility:

```yaml
# Schedule configuration
schedule:
  name: "Weekly Dev Summary"
  cron: "0 9 * * 1"  # Monday 9am
  channels: ["#dev-general"]
  granularity: "weekly"
  sync_eligible: true  # Default: respect server settings
```

#### Resolution Hierarchy

Sync eligibility is determined by:

```
┌─────────────────────────────────────────────────────────────┐
│             Sync Eligibility Resolution                      │
├─────────────────────────────────────────────────────────────┤
│  1. Server sync settings (always takes precedence)          │
│     └─► If server filters exclude the summary, skip         │
│     └─► Server-level filters are the final authority        │
│                                                             │
│  2. Per-summary sync_eligible flag                          │
│     └─► Set at creation (push/scheduler)                    │
│     └─► Can be toggled later in summary details             │
│     └─► Default: true (opt-out model)                       │
│                                                             │
│  3. Implicit eligibility                                    │
│     └─► All summaries eligible unless explicitly excluded   │
│     └─► Older summaries without flag treated as eligible    │
└─────────────────────────────────────────────────────────────┘
```

**Opt-out model rationale**:
- Most summaries should be synced by default
- Users explicitly exclude sensitive content
- Server settings provide additional layer of control
- Prevents accidentally missing important summaries

#### Database Extension

```sql
-- Add sync eligibility to stored summaries
ALTER TABLE stored_summaries ADD COLUMN sync_eligible INTEGER DEFAULT 1;
```

### 5. UI Configuration

Add sync configuration panel in **Settings page** (not Retrospective - sync configuration is a settings concern):

```
┌─────────────────────────────────────────────────────────────┐
│ Google Drive Sync                                           │
├─────────────────────────────────────────────────────────────┤
│ Connected as: admin@example.com                             │
│ Folder: Shared Drives > Engineering > SummaryBot            │
│                                                             │
│ Filter Settings                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Preset:   [Weekly Channel Summaries ▼] [Custom...]      │ │
│ │ Scope:    [x] Channel  [ ] Server-wide                  │ │
│ │ Period:   [Weekly ▼]                                    │ │
│ │ Source:   [x] Scheduled  [x] Manual  [ ] Archive        │ │
│ │ Eligible: [x] Only sync-eligible summaries              │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Export Format                                               │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [x] Markdown (.md)    Human-readable format             │ │
│ │ [ ] JSON (.json)      Machine-readable backup           │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Folder Organization                                         │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Structure: [By Period ▼]  Period: [Weekly ▼]            │ │
│ │ Include:   [x] Conversations  [ ] Wiki Pages            │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Stats: 247 summaries matching filters (12 new)              │
│                                                             │
│ [Sync Sample (3)]  [Sync All (247)]  Last: 2026-05-09      │
│                                                             │
│ ℹ️  "Sync Sample" uploads 3 files (MD + JSON if enabled)   │
│     so you can verify format before syncing everything.     │
└─────────────────────────────────────────────────────────────┘
```

**Note**: For tenanted servers, only Shared Drives are available as destinations. My Drive is disabled to ensure organizational data ownership and continuity.

**Location rationale**: Sync configuration belongs in Settings because:
- It's a per-server configuration, not a retrospective action
- Users configure it once and forget about it
- Consistent with other integration settings (prompt repos, channel sensitivity)

### 6. Database Schema

Extend `sync_server_configs` table:

```sql
ALTER TABLE sync_server_configs ADD COLUMN export_filters TEXT;  -- JSON
ALTER TABLE sync_server_configs ADD COLUMN include_markdown INTEGER DEFAULT 1;
ALTER TABLE sync_server_configs ADD COLUMN include_json INTEGER DEFAULT 0;
ALTER TABLE sync_server_configs ADD COLUMN folder_structure TEXT DEFAULT 'by-period';
ALTER TABLE sync_server_configs ADD COLUMN period_grouping TEXT DEFAULT 'week';
ALTER TABLE sync_server_configs ADD COLUMN include_wiki INTEGER DEFAULT 0;
ALTER TABLE sync_server_configs ADD COLUMN include_conversations INTEGER DEFAULT 1;
```

Add sync eligibility to stored summaries:

```sql
ALTER TABLE stored_summaries ADD COLUMN sync_eligible INTEGER DEFAULT 1;
```

### 7. Incremental Sync

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

### 8. Sync Sample Preview

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

### 9. Period Folder Logic

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
- [ ] Add `SyncExportConfig` model with filters
- [ ] Extend `ServerSyncConfig` with export settings
- [ ] Create migration for new columns (include_markdown, include_json, filters)
- [ ] Update sync trigger to use filters
- [ ] Add filter presets (Weekly Channel, Server-wide, etc.)

### Phase 2: Format Options
- [x] Implement markdown export
- [ ] Add `include_markdown` toggle (default: true)
- [ ] Add `include_json` toggle (default: false)
- [ ] Sample sync respects both format toggles
- [ ] Upload both file types when both enabled

### Phase 3: Folder Structure
- [x] Implement period folder creation in Drive
- [x] Add `conversations/` top-level folder
- [ ] Add `wiki/` top-level folder
- [x] Place files in correct period folders

### Phase 4: Incremental Sync
- [ ] Create `sync_history` table
- [ ] Track synced files by Drive file ID
- [ ] Only sync new/updated summaries

### Phase 5: UI Filters
- [x] Add export settings panel to Settings page
- [ ] Add filter preset dropdown
- [ ] Add scope filter (channel vs server-wide)
- [ ] Add source filter (scheduled, manual, archive)
- [ ] Add sync-eligible filter checkbox
- [ ] Show new-since-last-sync count
- [x] Add "Sync Sample" button with preview
- [x] Disable My Drive selection for tenanted servers
- [x] Show warning when Shared Drive required

### Phase 6: Sync Eligibility at Creation
- [ ] Add `sync_eligible` column to stored_summaries
- [ ] Add sync eligibility toggle to Discord push dialog
- [ ] Add sync_eligible option to scheduler configuration
- [ ] Default to true (opt-out model)
- [ ] Server settings take precedence over per-summary flag

### Phase 7: Domain Validation (Future)
- [ ] Add Google Admin SDK scope for domain lookup
- [ ] Validate Shared Drive ownership matches user domain
- [ ] Block sync to external organization drives
- [ ] Add admin override for cross-domain (if needed)

## Consequences

### Positive
- Users control what gets synced (reduce noise)
- Filter presets simplify common use cases (weekly channel summaries)
- Per-summary sync eligibility for fine-grained control
- Both MD and JSON formats available (toggle independently)
- Organized folder structure (easier to navigate)
- Smaller sync payloads (only markdown by default)
- Wiki and conversations separated (clearer purpose)
- Incremental sync (faster, less API usage)
- Shared Drive requirement ensures data ownership continuity
- Sample sync with format preview reduces configuration errors
- Scheduler/push integration for sync-at-creation decisions
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
