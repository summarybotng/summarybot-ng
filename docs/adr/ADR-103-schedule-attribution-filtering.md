# ADR-103: Schedule Attribution and Filtering for Summaries

## Status
IMPLEMENTED (2026-05-22)

## Context

When viewing the summaries list, users need to quickly identify which summaries came from scheduled tasks and filter to see summaries from specific schedules. Currently:

- Summaries have `schedule_id` and `schedule_name` fields (added in ADR-102)
- The schedule badge exists but may not be prominently visible
- No ability to filter summaries by originating schedule

## Decision

### 1. Prominent Schedule Badge on Summary Cards

Display schedule attribution on all scheduled summary cards:

```
┌─────────────────────────────────────────────────────┐
│ #general Summary - May 22, 2026                     │
│                                                     │
│ [Scheduled] [📅 Daily Standup Summary →]           │
│                                                     │
│ Key points: 5  •  Action items: 3  •  45 messages  │
└─────────────────────────────────────────────────────┘
```

- Badge shows schedule name with clock icon
- Clicking badge navigates to `/guilds/{id}/schedules?highlight={schedule_id}`
- Only displayed when `source === 'scheduled'` and `schedule_id` exists

### 2. Schedule Filter in Summary Filters

Add schedule filter dropdown to SummaryFilters:

```
Source: [All Sources ▼]  Schedule: [All Schedules ▼]  ...
                                   ├─ All Schedules
                                   ├─ Daily Standup Summary
                                   ├─ Weekly Team Digest
                                   └─ Monthly Report
```

- Populated from guild's schedules (active + inactive with summaries)
- Multi-select support for filtering multiple schedules
- Filter persists in URL query params

### 3. API Enhancements

#### Filter Parameter
```
GET /guilds/{guild_id}/stored-summaries?schedule_ids=abc123,def456
```

#### Schedule List Endpoint
```
GET /guilds/{guild_id}/schedules/for-filter
Response: [{ id, name, is_active, summary_count }]
```

## Implementation

### Files to Modify

| File | Changes |
|------|---------|
| `src/dashboard/routes/summaries.py` | Add `schedule_ids` filter parameter |
| `src/dashboard/routes/schedules.py` | Add `/for-filter` endpoint |
| `src/frontend/src/types/filters.ts` | Add `scheduleIds` to criteria |
| `src/frontend/src/components/summaries/SummaryFilters.tsx` | Add schedule dropdown |
| `src/frontend/src/components/summaries/StoredSummaryCard.tsx` | Ensure schedule badge visible |

### Data Flow

```
User selects schedule in filter
         ↓
SummaryFilters updates criteria.scheduleIds
         ↓
useStoredSummaries sends ?schedule_ids=... to API
         ↓
summaries.py filters by schedule_id IN (...)
         ↓
Filtered summaries returned and displayed
```

## Consequences

### Positive
- Users can quickly find summaries from specific schedules
- Clear attribution helps understand summary origin
- Supports schedule-centric workflows

### Negative
- Additional API call needed for schedule list in filter
- More filter options may increase UI complexity

## References
- [ADR-102](./ADR-102-schedule-summary-job-traceability.md): Schedule-Summary-Job Traceability
- [ADR-009](./009-schedule-run-summary-navigation.md): Schedule → Run → Summary Navigation
- [GitHub Issue #20](https://github.com/summarybotng/summarybot-ng/issues/20): Implementation tracking
