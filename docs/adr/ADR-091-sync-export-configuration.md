# ADR-091: Google Drive Sync Export Configuration

## Status

Implementing (wiki export deferred)

## Context

ADR-007 introduced Google Drive sync for backing up summaries. The initial implementation syncs all database summaries as markdown + JSON files to a flat folder structure. Users need more control over:

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

Add sync configuration panel in Retrospective page:

```
┌─────────────────────────────────────────────────────────────┐
│ Google Drive Sync                                           │
├─────────────────────────────────────────────────────────────┤
│ Connected as: user@example.com                              │
│ Folder: Shared Drives > Team > SummaryBot                   │
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
│ [Sync Now]  Last sync: 2026-05-09 10:30                    │
└─────────────────────────────────────────────────────────────┘
```

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

### 7. Period Folder Logic

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
- [ ] Add export settings panel to Retrospective page
- [ ] Integrate summary filter picker
- [ ] Show new-since-last-sync count

## Consequences

### Positive
- Users control what gets synced (reduce noise)
- Organized folder structure (easier to navigate)
- Smaller sync payloads (only markdown by default)
- Wiki and conversations separated (clearer purpose)
- Incremental sync (faster, less API usage)

### Negative
- More configuration options (complexity)
- Period folders may have gaps (if no summaries in period)
- Breaking change for existing syncs (files move to new structure)

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

## References

- ADR-007: Per-Server Google Drive Sync
- ADR-037: Centralized Filter Criteria
- ADR-087: Wiki Ingestion Granularity
