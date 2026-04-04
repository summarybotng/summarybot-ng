# ADR-037: Centralized Filter Criteria for Lists and Feeds

## Status

Accepted (Phase 1 & 2 Implemented)

## Context

Multiple features need to filter summaries, but each implements filtering differently:

1. **Summary List** (`SummaryFilters.tsx`) - Full filtering UI
2. **Bulk Operations** (`BulkActionBar.tsx`) - Uses `BulkFilters` type
3. **Feeds** - Only channel filtering
4. **Webhooks** - No filtering (fires for all summaries)

Currently, the summary list view (`SummaryFilters.tsx`) has extensive filtering capabilities:
- Source type (manual, scheduled, archive, etc.)
- Archived status
- Date range (created after/before)
- Archive period
- Channel mode (single/multi)
- Content flags (has grounding, key points, action items, participants)
- Content counts (min/max messages, key points, action items, participants)
- Platform filter
- Sort options

However, RSS/Atom feeds (`FeedCard.tsx`) can only filter by:
- Channel (single or all)
- Public/private access

Users should be able to create feeds with the same powerful filtering as the list view. For example:
- "Feed of all scheduled summaries from #engineering"
- "Feed of summaries with action items from the last 7 days"
- "Feed of archive summaries only"

## Decision

### 1. Create Centralized Filter Criteria Definition

Define all filter criteria in a single location that can be used by:
- Summary list UI (`SummaryFilters.tsx`)
- Bulk operations (`BulkActionBar.tsx`) - replaces current `BulkFilters`
- Feed creation/editing
- Webhook filtering ("only notify when criteria match")
- API endpoints
- Future: Email digests, scheduled reports

```typescript
// src/frontend/src/types/filters.ts
export interface SummaryFilterCriteria {
  // Source filtering
  source?: SummarySourceType | "all";
  archived?: boolean;

  // Time filtering
  createdAfter?: string;  // ISO date
  createdBefore?: string; // ISO date
  archivePeriod?: string; // e.g., "2024-01"

  // Channel filtering
  channelMode?: "all" | "single" | "multi";
  channelIds?: string[];

  // Content flags
  hasGrounding?: boolean;
  hasKeyPoints?: boolean;
  hasActionItems?: boolean;
  hasParticipants?: boolean;

  // Content counts
  minMessageCount?: number;
  maxMessageCount?: number;
  minKeyPoints?: number;
  maxKeyPoints?: number;
  minActionItems?: number;
  maxActionItems?: number;
  minParticipants?: number;
  maxParticipants?: number;

  // Other
  platform?: string;
  tags?: string[];

  // Sort (for lists, not feeds)
  sortBy?: "created_at" | "message_count" | "key_points_count";
  sortOrder?: "asc" | "desc";
}
```

### 2. Update Feed Model

Extend the Feed model to store filter criteria:

```python
# Backend model
class Feed(BaseModel):
    id: str
    guild_id: str
    title: str
    feed_type: Literal["rss", "atom", "json"]
    is_public: bool
    token: Optional[str]

    # Existing simple filter
    channel_id: Optional[str]  # Deprecated, use criteria.channelIds

    # New: Full filter criteria
    criteria: Optional[SummaryFilterCriteria]

    # Limits
    max_items: int = 50
```

### 3. Shared Filter Components

Create reusable filter components:

```
src/frontend/src/components/filters/
├── FilterCriteriaForm.tsx    # Full form for all criteria
├── FilterCriteriaSummary.tsx # Compact display of active filters
├── useFilterCriteria.ts      # Hook for managing filter state
└── index.ts
```

These components are used by:
- `SummaryFilters.tsx` - Refactored to use shared components
- `FeedForm.tsx` - New/Edit feed dialog with filter criteria
- Future: Schedule filters, webhook filters

### 4. API Changes

Update feed endpoints to accept and return criteria:

```
POST /guilds/{guild_id}/feeds
{
  "title": "Engineering Updates",
  "feed_type": "rss",
  "is_public": false,
  "criteria": {
    "source": "scheduled",
    "channelIds": ["123456789"],
    "hasActionItems": true
  },
  "max_items": 25
}

GET /guilds/{guild_id}/feeds/{feed_id}/content
# Returns summaries matching criteria, formatted as RSS/Atom/JSON
```

### 5. Update Webhook Model

Webhooks currently fire for all summaries. Add criteria to filter:

```python
class Webhook(BaseModel):
    id: str
    guild_id: str
    name: str
    url: str
    type: Literal["generic", "slack", "discord"]
    enabled: bool

    # New: Only fire when criteria match
    criteria: Optional[SummaryFilterCriteria]
```

Use cases:
- "Notify Slack only for summaries with action items"
- "Webhook fires only for scheduled summaries from #engineering"
- "Alert on archive summaries only"

### 6. Unify BulkFilters

Replace the existing `BulkFilters` type with `SummaryFilterCriteria`:

```typescript
// Before (hooks/useStoredSummaries.ts)
export interface BulkFilters {
  source?: string;
  archived?: boolean;
  created_after?: string;
  // ... duplicated definition
}

// After - just use SummaryFilterCriteria
import { SummaryFilterCriteria } from "@/types/filters";
```

### 7. Migration Path

1. Existing feeds with `channel_id` continue to work
2. New feeds use `criteria.channelIds`
3. Existing webhooks with no criteria fire for all (backward compatible)
4. UI shows migration prompt for old feeds
5. Eventually deprecate `channel_id` field

## Implementation Plan

### Phase 1: Foundation (Completed)
- [x] Create `SummaryFilterCriteria` type definition in `types/filters.ts`
- [x] Create shared filter components in `components/filters/`
- [x] Refactor `SummaryFilters.tsx` to use shared components (uses shared types)
- [x] Replace `BulkFilters` with `SummaryFilterCriteria` (now alias)

### Phase 2: Feed Integration (Completed)
- [x] Update Feed model with criteria field
- [x] Update feed creation/edit UI with filter form
- [ ] Update feed content endpoint to apply criteria (backend pending)

### Phase 3: Webhook Integration
- [ ] Update Webhook model with criteria field
- [ ] Update webhook creation/edit UI with filter form
- [ ] Update webhook trigger logic to check criteria

### Phase 4: Polish
- [ ] Add filter presets (common combinations)
- [ ] Add "Copy filters from list" feature
- [ ] Add filter validation and helpful error messages
- [ ] Add "Test filter" preview showing matching summary count

## Consequences

### Positive

- Single source of truth for filter criteria
- All features get same powerful filtering as list view
- Easy to add new filter criteria in one place
- Consistent behavior across all features
- Eliminates code duplication (`BulkFilters` vs `SummaryFilters` state)
- Webhook notifications become much more useful

### Negative

- More complex feed and webhook models
- Migration needed for existing feeds
- Larger API payloads
- UI complexity for webhook/feed creation

## Consumers Summary

| Feature | Status | Notes |
|---------|--------|-------|
| Summary List | Existing | Refactor to shared components |
| Bulk Operations | Existing | Replace `BulkFilters` type |
| Feeds | New | Full criteria support |
| Webhooks | New | "Only notify when..." |
| Email Digests | Future | Scheduled filtered digests |
| Reports | Future | Periodic filtered reports |

## UI Mockup

### Feed Creation Dialog (Updated)

```
┌─────────────────────────────────────────────────┐
│ Create Feed                                      │
├─────────────────────────────────────────────────┤
│ Title: [Engineering Updates____________]        │
│ Format: [RSS ▼]  Access: [Private ▼]           │
│                                                 │
│ ─── Filter Criteria ───────────────────────    │
│                                                 │
│ Source: [Scheduled ▼]                          │
│ Channels: [#engineering, #dev ▼]               │
│ Time: [Last 7 days ▼]                          │
│                                                 │
│ Content:                                        │
│ ☑ Has action items                             │
│ ☐ Has grounding                                │
│                                                 │
│ [Advanced filters...]                           │
│                                                 │
│ Max items: [50]                                 │
├─────────────────────────────────────────────────┤
│                    [Cancel] [Create Feed]       │
└─────────────────────────────────────────────────┘
```

## References

- ADR-017: Summary Filtering and Calendar View
- ADR-021: Content Count Filters
- Current `SummaryFilters.tsx` implementation
