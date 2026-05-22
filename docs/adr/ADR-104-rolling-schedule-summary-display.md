# ADR-104: Rolling Schedule Summary Display

## Status
Accepted

## Context

Rolling period summaries (ADR-101) accumulate content daily until the period ends. Currently, when viewing a schedule's associated summaries, users see all summaries in reverse chronological order without distinction between:

1. The **current active** rolling summary (still accumulating)
2. **Finalized** rolling summaries from previous periods
3. The **rollover date** when the current period ends

This makes it difficult for users to understand the rolling schedule's state at a glance.

## Decision

When displaying summaries for a rolling schedule, the UI should present:

### 1. Current Active Summary (Prominent)
- Display the single active rolling summary prominently at the top
- Show the **rollover date** (when the period finalizes)
- Include an "In Progress" or "Rolling" badge
- Show accumulation count (e.g., "Day 4 of 7")

### 2. Previous Finalized Summaries (Limited)
- Show the **3 most recent** finalized rolling summaries below
- These represent completed weekly/biweekly/monthly periods
- Include period date ranges (e.g., "May 11-17, 2026")

### 3. "View All" Link
- If more than 3 finalized summaries exist, show a link to view full history

### Visual Hierarchy

```
┌─────────────────────────────────────────────────────────┐
│ CURRENT PERIOD                              [Rolling]   │
│ Weekly Summary - May 18-24, 2026                        │
│ Rollover: Saturday, May 24 at 09:00 UTC                 │
│ Progress: Day 5 of 7 (3 accumulations)                  │
│ Last updated: May 22 at 09:00                           │
└─────────────────────────────────────────────────────────┘

Previous Periods
┌─────────────────────────────────────────────────────────┐
│ May 11-17, 2026                            [Finalized]  │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│ May 4-10, 2026                             [Finalized]  │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│ Apr 27 - May 3, 2026                       [Finalized]  │
└─────────────────────────────────────────────────────────┘

[View all 12 summaries →]
```

### API Changes

The schedule detail endpoint should return structured summary data:

```typescript
interface RollingScheduleSummaries {
  current: {
    summary: StoredSummary | null;
    rolloverDate: string;        // ISO timestamp
    periodStart: string;         // ISO timestamp
    accumulationCount: number;
    totalDaysInPeriod: number;
  } | null;
  previous: StoredSummary[];     // Max 3, ordered by period_start DESC
  totalCount: number;            // Total finalized summaries
}
```

### Query Logic

```sql
-- Current active summary
SELECT * FROM stored_summaries
WHERE schedule_id = ?
  AND rolling_period_type IS NOT NULL
  AND rolling_finalized = 0
LIMIT 1;

-- Previous 3 finalized summaries
SELECT * FROM stored_summaries
WHERE schedule_id = ?
  AND rolling_period_type IS NOT NULL
  AND rolling_finalized = 1
ORDER BY rolling_period_start DESC
LIMIT 3;
```

### Rollover Date Calculation

The rollover date is calculated from:
- `rolling_end_day` (0-6, Sunday-Saturday for weekly)
- `schedule_time` (e.g., "09:00")
- `timezone` (e.g., "America/New_York")

For the current period, find the next occurrence of `rolling_end_day` at `schedule_time`.

## Consequences

### Positive
- Users immediately understand the rolling schedule's current state
- Clear distinction between in-progress and completed periods
- Rollover date sets expectations for when summary finalizes
- Limited display (1 + 3) keeps UI clean

### Negative
- Additional API complexity for structured response
- Rollover date calculation must account for timezone edge cases
- UI must handle missing current summary (e.g., new schedule with no runs yet)

### Neutral
- Non-rolling schedules continue showing summaries in simple list format
- Schedule detail view requires minor redesign

## Implementation Order

1. Add rollover date calculation to `ScheduledTask` model
2. Create `get_rolling_schedule_summaries()` repository method
3. Add endpoint or extend existing schedule detail endpoint
4. Update frontend schedule detail component
5. Add "In Progress" badge and rollover date display

## References

- ADR-101: Rolling Period Summaries
- ADR-102: Schedule-Summary-Job Traceability
- ADR-103: Schedule Attribution Filtering
