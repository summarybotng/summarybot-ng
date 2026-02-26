# ADR-021: Content Count Filters

## Status
Implemented (2026-02-26)

## Date
2026-02-26

## Context

The current summary filtering system (ADR-018) provides boolean filters for content presence (`hasKeyPoints`, `hasActionItems`, `hasParticipants`) but lacks the ability to filter by content quantity. Users want to:

1. Find summaries with substantial key points (e.g., "show summaries with at least 5 key points")
2. Identify summaries with few action items that might need review
3. Filter by participant engagement level (summaries involving many vs few participants)

This enhancement builds on ADR-018's content filters by adding numeric range filtering.

## Decision

Extend the content filtering system with min/max count filters for:
- Key Points count
- Action Items count
- Participants count

### API Changes

Extend the stored summaries endpoint query parameters:

```
GET /guilds/{guild_id}/stored-summaries
Query params (new):
  - min_key_points: Minimum number of key points
  - max_key_points: Maximum number of key points
  - min_action_items: Minimum number of action items
  - max_action_items: Maximum number of action items
  - min_participants: Minimum number of participants
  - max_participants: Maximum number of participants
```

### Frontend Changes

Update `SummaryFilters.tsx` to add range inputs under the "Content" filter section:

```typescript
interface ContentCountFilters {
  minKeyPoints?: number;
  maxKeyPoints?: number;
  minActionItems?: number;
  maxActionItems?: number;
  minParticipants?: number;
  maxParticipants?: number;
}
```

UI Components:
- Use dual number inputs (min/max) for each content type
- Show filter badges for active count filters
- Include quick presets: "Substantial (5+)", "Light (1-3)", "None (0)"

### Backend Implementation

In `SQLiteStoredSummaryRepository.find_by_guild()`:

```python
# Key points count filtering
if min_key_points is not None:
    conditions.append(
        "json_array_length(json_extract(summary_json, '$.key_points')) >= ?"
    )
    params.append(min_key_points)

if max_key_points is not None:
    conditions.append(
        "json_array_length(json_extract(summary_json, '$.key_points')) <= ?"
    )
    params.append(max_key_points)

# Similar for action_items and participants
```

### Database Considerations

For performance with large datasets, consider adding generated columns:

```sql
-- Optional: Add computed columns for frequently filtered counts
ALTER TABLE stored_summaries
ADD COLUMN key_points_count INTEGER
GENERATED ALWAYS AS (json_array_length(json_extract(summary_json, '$.key_points')));

CREATE INDEX idx_stored_summaries_key_points_count
ON stored_summaries(guild_id, key_points_count);
```

## UI Design

In the "Content" section of SummaryFilters:

```
Content
├── [x] Has Key Points      Min: [___] Max: [___]
├── [x] Has Action Items    Min: [___] Max: [___]
└── [x] Has Participants    Min: [___] Max: [___]

Quick filters:
[Substantial Content (5+ key points)]
[Many Participants (10+)]
[Has Action Items]
```

Active filters display as badges:
- "Key Points: 5-10"
- "Participants: 10+"
- "Action Items: 0" (for finding summaries without action items)

## Implementation Phases

### Phase 1: Backend Support
- Add min/max parameters to `find_by_guild()`
- Implement JSON array length filtering
- Add to API endpoint

### Phase 2: Frontend Integration
- Add range inputs to SummaryFilters
- Update hook parameters
- Add filter badges

### Phase 3: Performance Optimization (if needed)
- Add generated columns
- Create indexes on count columns

## Consequences

### Positive
- Fine-grained content filtering
- Better summary discovery
- Identifies summaries needing review (few key points)
- Enables quality metrics dashboards

### Negative
- More complex filter UI
- JSON function overhead on queries
- May need optimization for large datasets

### Risks
- SQLite JSON functions vary by version (requires SQLite 3.38+)
- Performance impact on large datasets without indexes

## References

- ADR-018: Bulk Summary Operations (content filters)
- ADR-017: Summary Overview and Navigation
- [SQLite JSON Functions](https://www.sqlite.org/json1.html)
