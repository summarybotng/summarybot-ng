# ADR-018: Bulk Summary Operations

## Status
Accepted (Implemented)

## Context

Users managing many summaries need efficient ways to:
1. Delete multiple summaries at once (e.g., all failed regenerations, old archives)
2. Regenerate multiple summaries to add grounding references
3. Filter summaries by content attributes (has key points, has action items)

Currently, operations are single-summary only, requiring tedious manual work for cleanup or batch improvements.

## Decision

### 1. Bulk Selection & Actions

Add multi-select capability to the summary list view:

```
┌─────────────────────────────────────────────────────────┐
│ ☑ Select All (filtered)  │ 23 selected │ Actions ▼    │
├─────────────────────────────────────────────────────────┤
│ ☑ Summary 1...                                          │
│ ☑ Summary 2...                                          │
│ ☐ Summary 3...                                          │
└─────────────────────────────────────────────────────────┘
```

**Bulk Actions:**
- **Bulk Delete**: Delete all selected summaries with confirmation
- **Bulk Regenerate**: Queue regeneration for summaries without grounding
- **Bulk Archive/Unarchive**: Move to/from archived state
- **Bulk Tag**: Add/remove tags from selected summaries

### 2. Content-Based Filters

Extend ADR-017 filters with content attribute filters:

| Filter | Type | Description |
|--------|------|-------------|
| `has_key_points` | boolean | Summaries with ≥1 key point |
| `has_action_items` | boolean | Summaries with ≥1 action item |
| `has_participants` | boolean | Summaries with participant data |
| `min_message_count` | number | Minimum messages summarized |
| `max_message_count` | number | Maximum messages summarized |

### 3. Backend API

#### Bulk Delete
```
POST /api/v1/guilds/{guild_id}/stored-summaries/bulk-delete
{
  "summary_ids": ["sum_1", "sum_2", ...],
  "filters": { ... }  // Alternative: delete all matching filters
}

Response:
{
  "deleted_count": 23,
  "failed_ids": [],
  "errors": []
}
```

#### Bulk Regenerate
```
POST /api/v1/guilds/{guild_id}/stored-summaries/bulk-regenerate
{
  "summary_ids": ["sum_1", "sum_2", ...],
  "filters": { ... }  // Alternative: regenerate all matching filters
}

Response:
{
  "queued_count": 15,
  "skipped_count": 3,  // Already have grounding or can't regenerate
  "skipped_ids": ["sum_5", ...],
  "task_id": "bulk_regen_abc123"
}
```

#### Enhanced List Filters
```
GET /api/v1/guilds/{guild_id}/stored-summaries
  ?has_key_points=true
  &has_action_items=false
  &min_message_count=10
  &has_participants=true
```

### 4. Safety Measures

1. **Confirmation Dialog**: Require explicit confirmation for destructive bulk actions
2. **Preview Count**: Show count of affected items before action
3. **Rate Limiting**: Limit bulk operations to prevent abuse
4. **Audit Log**: Record bulk operations for accountability
5. **Undo Window**: 30-second undo for bulk delete (soft delete first)

### 5. UI Components

#### BulkActionBar
```typescript
interface BulkActionBarProps {
  selectedIds: string[];
  onSelectAll: () => void;
  onClearSelection: () => void;
  onBulkDelete: () => void;
  onBulkRegenerate: () => void;
  onBulkArchive: () => void;
  totalFilteredCount: number;
}
```

#### Enhanced Filter State
```typescript
interface FilterState {
  // Existing from ADR-017
  source: SummarySourceType;
  archived: boolean;
  createdAfter?: string;
  createdBefore?: string;
  // ...

  // New content filters
  hasKeyPoints?: boolean;
  hasActionItems?: boolean;
  hasParticipants?: boolean;
  minMessageCount?: number;
  maxMessageCount?: number;
}
```

## Implementation Plan

### Phase 1: Content Filters
1. Add filter fields to backend repository queries
2. Add filter UI components to SummaryFilters
3. Update API query parameters

### Phase 2: Selection & Bulk Actions
1. Add selection state to StoredSummariesTab
2. Create BulkActionBar component
3. Add bulk delete endpoint and handler
4. Add confirmation dialogs

### Phase 3: Bulk Regenerate
1. Create bulk regeneration queue
2. Add progress tracking
3. Handle partial failures gracefully

## Consequences

### Positive
- Efficient management of large summary collections
- Quick cleanup of failed or incomplete summaries
- Batch improvement of summary quality (grounding)
- Better filtering for specific summary types

### Negative
- More complex state management for selection
- Risk of accidental bulk deletion
- Regeneration queue management overhead

### Mitigations
- Clear selection count display
- Explicit confirmation with count
- Soft delete with undo window
- Background queue with progress tracking

## Related ADRs
- ADR-004: Grounded Summaries (regeneration adds references)
- ADR-017: Summary Overview and Navigation (filter foundation)
- ADR-016: Repair During Regenerate (integrity tracking)
