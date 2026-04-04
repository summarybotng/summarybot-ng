# ADR-037: Centralized Filter Criteria for Lists and Feeds

## Status

Proposed

## Context

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
- Feed creation/editing
- API endpoints for both lists and feeds
- Future: Scheduled report filters, webhook filters, etc.

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

### 5. Migration Path

1. Existing feeds with `channel_id` continue to work
2. New feeds use `criteria.channelIds`
3. UI shows migration prompt for old feeds
4. Eventually deprecate `channel_id` field

## Implementation Plan

### Phase 1: Foundation
- [ ] Create `SummaryFilterCriteria` type definition
- [ ] Create shared filter components
- [ ] Refactor `SummaryFilters.tsx` to use shared components

### Phase 2: Feed Integration
- [ ] Update Feed model with criteria field
- [ ] Update feed creation/edit UI with filter form
- [ ] Update feed content endpoint to apply criteria

### Phase 3: Polish
- [ ] Add filter presets (common combinations)
- [ ] Add "Copy filters from list" feature
- [ ] Add filter validation and helpful error messages

## Consequences

### Positive

- Single source of truth for filter criteria
- Feeds get same powerful filtering as list view
- Easy to add new filter criteria in one place
- Consistent behavior across lists and feeds
- Foundation for future filtering (schedules, webhooks, reports)

### Negative

- More complex feed model
- Migration needed for existing feeds
- Larger API payloads

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
