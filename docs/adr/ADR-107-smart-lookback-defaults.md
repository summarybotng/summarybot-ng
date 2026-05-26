# ADR-107: Smart Lookback Period Defaults

## Status
Accepted

## Context

When creating scheduled summaries, users select two related parameters:
1. **Frequency**: How often the schedule runs (daily, weekly, etc.)
2. **Lookback Period**: How far back to look for messages on each run

These parameters interact in ways that can be confusing:

| Frequency | Lookback | Behavior |
|-----------|----------|----------|
| Weekly (Friday) | 7 days | Captures all week's messages |
| Weekly (Friday) | 24 hours | Captures only Friday's messages |
| Daily | 24 hours | Captures each day fully |
| Daily | 4 hours | Captures only recent hours, may miss content |

Without guidance, users might accidentally create schedules that miss content (e.g., weekly schedule with 24h lookback only captures 1/7 of the week).

However, intentional "sampling" schedules are also valid use cases:
- "Friday 24h" captures only Friday activity as a weekly snapshot
- "Daily 4h" captures morning activity only
- Rolling period summaries that accumulate specific time slices

## Decision

### Smart Defaults (Auto-Update)

When the user changes the frequency, automatically update the lookback period to a sensible default that covers the interval:

| Frequency | Default Lookback |
|-----------|-----------------|
| Every 15 minutes | 4 hours |
| Hourly | 4 hours |
| Every 4 hours | 24 hours |
| Daily | 24 hours |
| Weekly | 7 days (168 hours) |
| Monthly | 7 days (168 hours)* |
| Once | 24 hours |

*Monthly defaults to 7 days (our max option) even though a full month is longer.

### No Restrictions

Users can still select any lookback period after the default is applied. We do **not**:
- Disable shorter lookback options
- Show warning messages
- Prevent form submission

This allows intentional use cases like "Friday 24h weekly summaries" that capture only Friday's activity.

## Implementation

In `WhenStep.tsx`:

```typescript
const getRecommendedLookback = (freq: ScheduleFrequency): number => {
  switch (freq) {
    case "weekly": return 168;  // 7 days
    case "daily": return 24;
    case "every-4-hours": return 24;
    case "hourly": return 4;
    case "fifteen-minutes": return 4;
    default: return 24;
  }
};

const handleFrequencyChange = (newFreq: ScheduleFrequency) => {
  const updates: Partial<typeof state> = { frequency: newFreq };

  // Auto-update lookback to cover the frequency interval
  const recommendedLookback = getRecommendedLookback(newFreq);
  if (state.lookbackHours < recommendedLookback) {
    updates.lookbackHours = recommendedLookback;
  }

  onChange(updates);
};
```

### Key Behavior

- Only increases lookback, never decreases it
- Applies when frequency changes, not on initial load
- User can manually override afterward

## Consequences

### Positive
- Prevents accidental "gap" schedules where content is missed
- Sensible defaults reduce cognitive load
- Still allows power-user configurations

### Negative
- Users must manually reduce lookback if they want a sampling schedule
- "Increase but never decrease" logic may be non-obvious

### Neutral
- Existing schedules are not affected (this is UI-only)
- No backend validation (API accepts any combination)

## Examples

### Intended Behavior

1. User selects "Weekly" → lookback auto-updates to "7 days"
2. User then manually selects "24 hours" → allowed (Friday-only schedule)

### Accidental Prevention

1. User has "Daily" selected with "24 hours" lookback
2. User changes to "Weekly" → lookback auto-updates to "7 days"
3. Without this, they'd have a weekly schedule capturing only 1 day

## Alternatives Considered

### 1. Warning Messages
Show a warning when lookback < frequency interval.
**Rejected**: Too noisy, and sampling schedules are valid.

### 2. Disable Short Options
Gray out lookback options that are too short.
**Rejected**: Prevents valid use cases.

### 3. Validation on Submit
Block form submission if lookback seems wrong.
**Rejected**: Too restrictive, power users need flexibility.

### 4. No Auto-Update (Documentation Only)
Just document the relationship in help text.
**Rejected**: Users don't read help text; defaults prevent mistakes.

## References

- ADR-089: Unified Summary Wizard
- ADR-101: Rolling Period Summaries
- ADR-105: Frequency/Rolling Period Constraints
