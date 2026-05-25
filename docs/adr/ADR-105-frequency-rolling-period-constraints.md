Sched# ADR-105: Frequency and Rolling Period Constraints

## Status
Accepted

## Context

ADR-101 introduced rolling period summaries that accumulate content over time (weekly, biweekly, monthly). However, rolling periods only make sense when the schedule runs **more frequently** than the accumulation period.

For example:
- A **weekly rolling period** with **daily frequency** = 7 runs accumulate into 1 weekly summary ✓
- A **weekly rolling period** with **weekly frequency** = 1 run per period, nothing to accumulate ✗
- A **monthly rolling period** with **monthly frequency** = 1 run per period, nothing to accumulate ✗

Without constraints, users could configure nonsensical combinations that would produce unexpected behavior or errors.

## Decision

Implement **frequency-based constraints** on rolling period options in the wizard UI:

### Constraint Matrix

| Schedule Frequency | Valid Rolling Periods | Rationale |
|-------------------|----------------------|-----------|
| Every 15 minutes | weekly, biweekly, monthly | High frequency = many runs per period |
| Hourly | weekly, biweekly, monthly | High frequency = many runs per period |
| Every 4 hours | weekly, biweekly, monthly | 6 runs/day = many runs per period |
| Daily | weekly, biweekly, monthly | 7 runs/week = good accumulation |
| Weekly | biweekly, monthly | 1 run/week = can only accumulate across multiple weeks |
| Monthly | none | 1 run/month = cannot accumulate |
| Once | none | Single run = cannot accumulate |

### Key Insight

Rolling periods require **at least 2 runs within the period** to have any meaningful accumulation. Therefore:
- Weekly rolling requires at least **twice-weekly frequency** (daily or more frequent)
- Biweekly rolling requires at least **biweekly frequency** (weekly or more frequent)
- Monthly rolling requires at least **monthly frequency** (weekly or more frequent)

We chose to be more conservative: **weekly rolling disabled for weekly frequency** because having exactly 1 run per period produces a rolling summary identical to a non-rolling summary, which could confuse users.

## Implementation

### UI Behavior

1. **Disable incompatible options**: Rolling period dropdown disables options that don't work with the current frequency

2. **Auto-reset on frequency change**: If a user selects a frequency that invalidates their current rolling period, automatically reset to "none"

3. **Explanatory message**: When options are disabled, show a message explaining why:
   - "Rolling periods require a more frequent schedule to accumulate multiple runs"
   - "Weekly rolling requires daily or more frequent schedules"

### Code Location

`src/frontend/src/components/summary-wizard/steps/WhenStep.tsx`:
- `getValidRollingPeriods(frequency)` - Returns array of valid periods for given frequency
- `handleFrequencyChange()` - Auto-resets rolling period if needed
- Rolling period `<Select>` - Disables invalid options

## Consequences

### Positive
- Prevents configuration of nonsensical schedules
- Clearer user experience with disabled options + explanations
- Reduces support burden from confused users
- No invalid states can be saved

### Negative
- Slightly more complex wizard logic
- Users who don't understand the constraints may be initially confused by disabled options

### Neutral
- Backend still accepts any combination (for API flexibility / edge cases)
- Constraints are UI-only; validation could be added to backend if needed

## References

- ADR-101: Rolling Period Summaries
- ADR-089: Unified Summary Wizard
