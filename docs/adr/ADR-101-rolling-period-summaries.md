# ADR-101: Rolling Period Summaries

## Status
Accepted

## Context

Currently, our summarization system offers two primary patterns:
1. **Point-in-time summaries** - Generate a summary for a specific time range (e.g., last 24h, last 7 days)
2. **Recurring schedules** - Generate summaries on a fixed schedule (daily at 9am, weekly on Saturdays)

A gap exists for teams who want **accumulating weekly summaries** that build throughout the week rather than being generated all at once at week's end. The current approach requires either:
- Daily summaries that users must mentally aggregate
- Weekly summaries that process 7 days of messages in one batch (potentially missing nuance)

## Decision

Implement **Rolling Period Summaries** that aggregate content daily toward a single period summary until the period ends.

### Behavior

1. **Period Start**: First day of period (e.g., Sunday) creates a new `rolling_summary` record
2. **Daily Accumulation**: Each day's scheduled run:
   - Fetches messages since last accumulation
   - Appends/merges into the existing period summary
   - Updates `accumulated_through` timestamp
3. **Period End**: Final day (e.g., Saturday) marks summary as `finalized`
4. **New Period**: Next day starts fresh rolling summary

### Data Model

```sql
-- Extend stored_summaries or new table
ALTER TABLE stored_summaries ADD COLUMN rolling_period_type TEXT;  -- 'weekly', 'biweekly', 'monthly'
ALTER TABLE stored_summaries ADD COLUMN rolling_period_start DATE;
ALTER TABLE stored_summaries ADD COLUMN rolling_accumulated_through TIMESTAMP;
ALTER TABLE stored_summaries ADD COLUMN rolling_finalized BOOLEAN DEFAULT FALSE;
ALTER TABLE stored_summaries ADD COLUMN rolling_accumulation_count INTEGER DEFAULT 0;

-- Index for finding active rolling summaries
CREATE INDEX idx_rolling_active ON stored_summaries(guild_id, channel_id, rolling_period_type, rolling_finalized);
```

### Accumulation Strategies

Three strategies for merging daily content into the rolling summary:

#### Strategy A: Append Sections
- Each day's summary becomes a dated section in the rolling summary
- Preserves chronological narrative
- Result: "Monday: ..., Tuesday: ..., Wednesday: ..."

#### Strategy B: Re-summarize All
- Keep raw accumulated content in a separate field
- Re-generate the summary each day from all accumulated content
- Better coherence but higher token cost

#### Strategy C: Hybrid Merge (Recommended)
- Maintain structured data (action items, participants, key points) separately
- Use LLM to merge new day's highlights with existing summary narrative
- Deduplicate action items and participants
- Lower cost than full re-summarization, better coherence than append

### API Changes

```python
class CreateScheduleRequest(BaseModel):
    # ... existing fields
    rolling_period: Optional[str] = None  # 'weekly', 'biweekly', 'monthly'
    rolling_end_day: Optional[int] = None  # 0-6 (Sun-Sat) for weekly
    accumulation_strategy: str = "hybrid"  # 'append', 'resummarize', 'hybrid'
```

### Wizard UX

In the "When" step for recurring schedules:
- New option: "Rolling period summary"
- Period selector: Weekly / Biweekly / Monthly
- End day selector (for weekly): Which day finalizes the period
- Strategy selector (advanced): How to merge daily content

### Confluence Integration (ADR-099)

Rolling summaries integrate with Confluence publishing:
- Page is created on first accumulation
- Page is updated (not replaced) on each subsequent accumulation
- Clear indication of "Week in Progress" vs "Week Complete"
- Version history shows each day's additions

## Consequences

### Positive
- Teams get continuously updated weekly context
- Reduces cognitive load vs. reading multiple daily summaries
- More nuanced weekly summaries (LLM sees context build over time)
- Better for async teams across time zones

### Negative
- More complex state management
- Potential for confusion if summary changes unexpectedly
- Storage cost for accumulation data (Strategy B/C)
- Need to handle edge cases (missed days, schedule changes mid-period)

### Neutral
- Existing daily/weekly schedules continue to work unchanged
- Rolling periods are opt-in via wizard or API

## Implementation Order

1. Database schema changes
2. Rolling summary detection/creation logic in scheduler
3. Accumulation strategies (start with Append, add Hybrid later)
4. Wizard UX for rolling period selection
5. Confluence integration for rolling updates
6. Backfill support (generate rolling summary for past period)

## Invariants

### One Active Rolling Summary Per Schedule

**Critical**: At any given time, there must be at most **one active (non-finalized) rolling summary** per schedule. This is enforced by the `find_active_rolling_summary()` query which matches on `(guild_id, schedule_id, rolling_period_type, rolling_finalized=0)`.

If multiple active rolling summaries exist for the same schedule, subsequent runs will only accumulate into the most recent one (by `rolling_period_start`), leaving others orphaned.

**Causes of duplicate active summaries:**
- Missing `schedule_id` on stored summaries (now fixed via ADR-102/103 which ensures schedule attribution)
- Manual summary creation without proper schedule linking
- Bug in finalization logic

**Resolution**: If duplicates are found, either:
1. Finalize the older ones (`rolling_finalized = 1`)
2. Delete the duplicates
3. Merge content into the canonical summary

## Decisions

1. **Missed days**: Yes, catch up all missed content on next run
2. **Manual regeneration**: Restart the rolling period (clear and begin fresh)
3. **Channel changes**: Regenerate from scratch with new channel scope
4. **Visibility**: Yes, show in-progress rolling summaries with "In Progress" badge

## References

- ADR-089: Unified Summary Wizard
- ADR-099: Confluence Publishing
- ADR-096: Per-Channel Summary Generation
- Continuity chains (existing feature for linking related summaries)
