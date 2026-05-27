# ADR-108: Per-Destination Rolling Period Delivery Control

## Status
Accepted

## Context

Rolling period summaries (ADR-101) accumulate content across multiple runs before finalizing at the end of the period (weekly, biweekly, monthly). The original implementation (ADR-102) only delivered to external destinations (Discord, Confluence, email, etc.) when the rolling summary was finalized.

Users requested the ability to receive intermediate updates during the rolling period. For example:
- A biweekly Confluence page that updates every Friday showing progress
- Email notifications after each run to keep stakeholders informed
- Discord channel posts showing the accumulating summary

Different destinations may have different requirements - some should wait for finalization, others should deliver on every run.

## Decision

Add a per-destination `rolling_deliver_intermediate` flag that controls when each destination receives deliveries for rolling summaries:

| Flag Value | Behavior |
|------------|----------|
| `false` (default) | Deliver only when rolling period is finalized |
| `true` | Deliver on every run during the rolling period |

### Data Model

```python
# src/models/task.py
@dataclass
class Destination(BaseModel):
    type: DestinationType
    target: str
    format: str = "embed"
    enabled: bool = True
    rolling_deliver_intermediate: bool = False  # ADR-108
```

### Executor Logic

```python
# src/scheduling/executor.py
if rolling_summary.rolling_finalized:
    # Finalized: deliver to all destinations
    destinations_to_deliver = other_destinations
else:
    # Intermediate: only deliver to destinations with flag=True
    destinations_to_deliver = [
        d for d in other_destinations
        if getattr(d, 'rolling_deliver_intermediate', False)
    ]
```

### Frontend UI

When a rolling period is selected in the wizard, each destination shows an additional checkbox:
- "Deliver on each run (not just when finalized)"

This checkbox only appears when:
1. A rolling period is selected (not "none")
2. The destination is enabled

## Examples

### Scenario 1: Biweekly Summary with Progress Updates

A team wants:
- Confluence: Update on each Friday to show progress
- Email: Only send when finalized (avoid noise)

Configuration:
```json
{
  "rolling_period": "biweekly",
  "destinations": [
    { "type": "confluence", "rolling_deliver_intermediate": true },
    { "type": "email", "rolling_deliver_intermediate": false }
  ]
}
```

Behavior:
| Run | Confluence | Email |
|-----|------------|-------|
| Friday 1 | ✅ Published | ❌ Not sent |
| Friday 2 (finalized) | ✅ Published | ✅ Sent |

### Scenario 2: Weekly Discord Updates

A team wants Discord channel posts on every run to show the week's progress:

Configuration:
```json
{
  "rolling_period": "weekly",
  "frequency": "daily",
  "destinations": [
    { "type": "discord_channel", "rolling_deliver_intermediate": true }
  ]
}
```

Behavior:
- Monday through Saturday: Posts to Discord showing accumulated content
- Sunday (finalized): Final post with complete weekly summary

## Consequences

### Positive
- Granular control over delivery timing per destination
- Teams can get progress updates without waiting for finalization
- Default behavior (false) maintains backward compatibility

### Negative
- More complex UI with conditional checkboxes
- Intermediate deliveries may contain incomplete/changing content
- Users must understand the rolling period lifecycle

### Neutral
- Dashboard always shows the latest version (unaffected by this flag)
- Existing schedules default to `false` (no behavior change)

## Implementation Files

- `src/models/task.py` - Added field to Destination
- `src/scheduling/executor.py` - Updated delivery logic
- `src/scheduling/persistence.py` - Serialize/deserialize field
- `src/dashboard/models.py` - API response model
- `src/dashboard/routes/schedules.py` - API endpoints
- `src/frontend/src/types/index.ts` - TypeScript type
- `src/frontend/src/components/summary-wizard/types.ts` - Wizard state
- `src/frontend/src/components/summary-wizard/steps/WhereStep.tsx` - UI checkboxes
- `src/frontend/src/pages/Summaries.tsx` - API calls

## References

- ADR-101: Rolling Period Summaries
- ADR-102: Rolling Summary Delivery Strategy
- ADR-099: Confluence Publishing
