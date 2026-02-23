# ADR-017: Summary Overview and Navigation

## Status
Proposed

## Context

Users generate many summaries across multiple channels and time periods. Currently, finding specific summaries is difficult:

### Current Limitations

1. **Linear List View Only** - Summaries displayed in a simple paginated list, grouped by recency
2. **Limited Filtering** - Only filter by source type (archive/scheduled/manual) and archived status
3. **No Date Navigation** - Cannot browse by calendar or filter by date range
4. **No Period Awareness** - Archive summaries have `archive_period` but it's not used for navigation
5. **Missing Data Display** - Some summaries lack source channels, participants, or grounding

### Specific Issues (sum_8d35d83ed123)

Investigation of retrospective summary `sum_8d35d83ed123` revealed:
- No grounding (reference_index not populated)
- No source channels (source_channel_ids empty)
- Participant count = 0

This indicates data integrity issues where the archive generator doesn't preserve all required fields through the pipeline.

### User Requirements

Users need to:
1. View summaries by **generated date** (when created) via calendar
2. View summaries by **covered period** (what time range they summarize)
3. Filter by **single vs multiple channels**
4. Filter by **single vs multiple days**
5. Sort by various date fields
6. Navigate directly to a summary by ID or URL (ADR-015)

## SPARC Analysis

### Specification

#### Calendar Views Required

| View | Primary Date | Secondary Info | Use Case |
|------|--------------|----------------|----------|
| Generation Calendar | `created_at` | Summary count per day | "What did I generate?" |
| Coverage Calendar | `start_time`/`end_time` | Channels covered | "What periods are summarized?" |
| Archive Period View | `archive_period` | Granularity (daily/weekly) | "What historical data is covered?" |

#### Filtering Dimensions

| Filter | Field | Options |
|--------|-------|---------|
| Date Range | `created_at` | Quick: Today, 7d, 30d, Custom |
| Covered Period | `start_time`/`end_time` | Custom range picker |
| Channel Count | `source_channel_ids.length` | Single, Multi-channel |
| Source Type | `source` | Archive, Scheduled, Manual, All |
| Data Completeness | derived | Has grounding, Has participants |

#### Sorting Options

| Sort | Fields | Direction |
|------|--------|-----------|
| Newest Generated | `created_at` | DESC (default) |
| Oldest Generated | `created_at` | ASC |
| Most Recent Period | `end_time` | DESC |
| Oldest Period | `start_time` | ASC |
| Most Messages | `message_count` | DESC |
| Most Participants | `participants.length` | DESC |

### Pseudocode

#### Calendar Data Query

```python
async def get_calendar_data(
    guild_id: str,
    year: int,
    month: int,
    calendar_type: str = "generated"  # or "coverage"
) -> Dict[str, CalendarDay]:
    """
    Return summary counts and metadata grouped by day.

    Returns:
        {
            "2026-02-15": {
                "count": 5,
                "sources": ["archive", "scheduled"],
                "channels": ["general", "dev"],
                "has_incomplete": True  # Any missing data
            },
            ...
        }
    """
    if calendar_type == "generated":
        date_field = "created_at"
    else:
        date_field = "start_time"

    query = """
        SELECT
            DATE({date_field}) as day,
            COUNT(*) as count,
            GROUP_CONCAT(DISTINCT source) as sources,
            GROUP_CONCAT(DISTINCT source_channel_ids) as channels,
            SUM(CASE WHEN source_channel_ids = '[]' THEN 1 ELSE 0 END) as incomplete
        FROM stored_summaries
        WHERE guild_id = ?
          AND strftime('%Y', {date_field}) = ?
          AND strftime('%m', {date_field}) = ?
        GROUP BY DATE({date_field})
    """
    return execute_and_map(query, [guild_id, str(year), f"{month:02d}"])
```

#### Enhanced Find Query

```python
async def find_summaries_advanced(
    guild_id: str,
    # Date filters
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    period_after: Optional[datetime] = None,
    period_before: Optional[datetime] = None,
    archive_period: Optional[str] = None,
    # Content filters
    channel_mode: Optional[str] = None,  # "single" or "multi"
    min_participants: Optional[int] = None,
    has_grounding: Optional[bool] = None,
    # Sorting
    sort_by: str = "created_at",
    sort_order: str = "desc",
    # Pagination
    limit: int = 20,
    offset: int = 0,
) -> Tuple[List[StoredSummary], int]:
    """
    Advanced query with multiple filter dimensions.
    """
    conditions = ["guild_id = ?"]
    params = [guild_id]

    if created_after:
        conditions.append("created_at >= ?")
        params.append(created_after.isoformat())

    if created_before:
        conditions.append("created_at <= ?")
        params.append(created_before.isoformat())

    # Period filters use summary_json extraction
    if period_after:
        conditions.append("json_extract(summary_json, '$.start_time') >= ?")
        params.append(period_after.isoformat())

    if period_before:
        conditions.append("json_extract(summary_json, '$.end_time') <= ?")
        params.append(period_before.isoformat())

    if archive_period:
        conditions.append("archive_period = ?")
        params.append(archive_period)

    if channel_mode == "single":
        conditions.append("json_array_length(source_channel_ids) = 1")
    elif channel_mode == "multi":
        conditions.append("json_array_length(source_channel_ids) > 1")

    if has_grounding is True:
        conditions.append("json_array_length(json_extract(summary_json, '$.reference_index')) > 0")
    elif has_grounding is False:
        conditions.append("(json_extract(summary_json, '$.reference_index') IS NULL OR json_array_length(json_extract(summary_json, '$.reference_index')) = 0)")

    # Build and execute query
    ...
```

### Architecture

#### Component Hierarchy

```
SummariesPage
├── SummaryViewSelector (list | calendar | timeline)
├── SummaryFilters
│   ├── DateRangeFilter (quick picks + custom)
│   ├── SourceFilter (existing)
│   ├── ChannelModeFilter (single/multi)
│   ├── DataCompletenessFilter
│   └── SortSelector
├── CalendarView (new)
│   ├── MonthNavigation
│   ├── CalendarGrid
│   │   └── CalendarDay (count badge, click to filter)
│   └── CalendarTypeSwitcher (generated/coverage)
├── StoredSummariesTab (enhanced)
│   └── StoredSummaryCard (existing)
└── SummaryDetailSheet (existing, enhanced)
```

#### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /guilds/{id}/stored-summaries` | Enhanced | Add filter params |
| `GET /guilds/{id}/stored-summaries/calendar/{year}/{month}` | New | Calendar data |
| `GET /guilds/{id}/stored-summaries/stats` | New | Overview stats |

#### Database Indexes (Performance)

```sql
-- Calendar queries by creation date
CREATE INDEX idx_stored_summaries_created_date
ON stored_summaries(guild_id, DATE(created_at));

-- Period-based queries (requires JSON extraction)
CREATE INDEX idx_stored_summaries_archive_period
ON stored_summaries(guild_id, archive_period)
WHERE archive_period IS NOT NULL;

-- Partial index for incomplete summaries
CREATE INDEX idx_stored_summaries_incomplete
ON stored_summaries(guild_id, created_at)
WHERE source_channel_ids = '[]' OR source_channel_ids IS NULL;
```

### Refinement: Data Integrity Layer

Since sum_8d35d83ed123 and other summaries have missing data, we need:

#### 1. Integrity Status in List View

```typescript
interface SummaryIntegrityStatus {
  hasSourceChannels: boolean;
  hasParticipants: boolean;
  hasGrounding: boolean;
  hasTimeRange: boolean;
  isComplete: boolean;  // All fields present
  canRegenerate: boolean;  // Has enough for regeneration
}
```

#### 2. Visual Indicators

- Badge showing data completeness
- Warning icon for summaries missing critical fields
- "Repair" action for incomplete summaries (links to regenerate)

#### 3. Root Cause Fixes

The data gaps in sum_8d35d83ed123 indicate the archive pipeline isn't copying all fields:

```python
# In src/archive/generator.py - ensure all fields copied
result = SummaryResult(
    ...
    participants=summary_result.participants or [],  # Never None
    reference_index=getattr(summary_result, 'reference_index', []),
    source_channel_ids=channel_ids,  # Always set from source
)
```

## Implementation Plan

### Phase 1: Data Integrity ✅ Partial (ADR-016)
- [ ] Fix archive generator to always populate source_channel_ids
- [ ] Fix archive generator to always populate participants
- [ ] Add validation warnings on save
- [ ] Add `validate_regeneration()` method

### Phase 2: Enhanced Query API
- [ ] Add date range parameters to `find_by_guild()`
- [ ] Add sorting options
- [ ] Add channel mode filter
- [ ] Add grounding filter
- [ ] Create calendar endpoint

### Phase 3: Frontend Filters
- [ ] Add DateRangeFilter component
- [ ] Add SortSelector component
- [ ] Add ChannelModeFilter component
- [ ] Add DataCompletenessFilter component
- [ ] Enhance query hooks with new parameters

### Phase 4: Calendar View
- [ ] Create CalendarView component
- [ ] Create MonthNavigation component
- [ ] Create CalendarGrid with day cells
- [ ] Add calendar type switcher (generated/coverage)
- [ ] Click-to-filter interaction

### Phase 5: Integrity UI
- [ ] Add integrity status to list items
- [ ] Add warning badges for incomplete summaries
- [ ] Add bulk repair action
- [ ] Add statistics showing data quality

## File Changes

### Backend

| File | Action | Changes |
|------|--------|---------|
| `src/data/sqlite.py` | Modify | Add advanced query methods, calendar query |
| `src/data/base.py` | Modify | Add abstract methods for new queries |
| `src/dashboard/routes/summaries.py` | Modify | Add filter params, new endpoints |
| `src/dashboard/models.py` | Modify | Add filter models, calendar response |
| `src/archive/generator.py` | Modify | Fix field population (source_channel_ids, participants) |
| `src/data/migrations/` | Add | New indexes for performance |

### Frontend

| File | Action | Changes |
|------|--------|---------|
| `src/components/summaries/SummaryFilters.tsx` | Add | New filter panel component |
| `src/components/summaries/CalendarView.tsx` | Add | Calendar navigation component |
| `src/components/summaries/StoredSummariesTab.tsx` | Modify | Integrate filters and view switcher |
| `src/hooks/useStoredSummaries.ts` | Modify | Add filter parameters to queries |
| `src/api/types.ts` | Modify | Add filter and calendar types |

## Consequences

### Positive
- Users can find summaries by multiple dimensions
- Calendar view provides visual overview of activity
- Data completeness is visible and actionable
- Future summaries will have complete data

### Negative
- Additional database queries for calendar data
- JSON extraction in queries may be slower than indexed columns
- Migration needed to fix existing incomplete summaries
- UI complexity increases

### Mitigations
- Add database indexes for common queries
- Cache calendar data (invalidate on new summaries)
- Background job to repair existing summaries
- Progressive disclosure of advanced filters

## Related ADRs

- **ADR-004**: Grounded Citations - Reference index that may be missing
- **ADR-008**: Unified Summary Experience - Source tracking fields
- **ADR-015**: Deep Linking - Navigation to specific summaries
- **ADR-016**: Regeneration Data Integrity - Root causes for missing data

## Appendix: Data Quality Assessment

### Fields to Track for Completeness

```python
REQUIRED_FIELDS = {
    "source_channel_ids": "List of channels summarized",
    "start_time": "Period start (from summary_result)",
    "end_time": "Period end (from summary_result)",
    "participants": "Who participated (list)",
    "message_count": "Messages processed",
}

OPTIONAL_BUT_VALUABLE = {
    "reference_index": "Grounded citations",
    "source_content": "Original messages (for offline regen)",
    "key_points": "Extracted key points",
    "action_items": "Extracted action items",
}
```

### Assessment Query

```sql
SELECT
    source,
    COUNT(*) as total,
    SUM(CASE WHEN source_channel_ids = '[]' THEN 1 ELSE 0 END) as missing_channels,
    SUM(CASE WHEN json_extract(summary_json, '$.participants') = '[]' THEN 1 ELSE 0 END) as missing_participants,
    SUM(CASE WHEN json_extract(summary_json, '$.reference_index') IS NULL
             OR json_extract(summary_json, '$.reference_index') = '[]' THEN 1 ELSE 0 END) as missing_grounding
FROM stored_summaries
WHERE guild_id = ?
GROUP BY source;
```

This will show data quality breakdown by source type, helping prioritize fixes.
