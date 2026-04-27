# ADR-071: Summary Deduplication Strategy

## Status
Proposed

## Context

SummaryBot generates summaries from two primary paths:

1. **Scheduled summaries** - Proactive, recurring summaries from live channel data
2. **Archive summaries** - Retrospective summaries from imported historical data

When both are used for the same time period, identical work is performed twice:
- Same messages are processed by the LLM
- Duplicate wiki entries may be created
- LLM token costs are doubled
- Storage is wasted on redundant summaries

**Key insight**: A scheduled summary and an archive summary covering the same time range contain the same content. There's no need to regenerate - we can reuse.

## Decision

Implement **automatic, hands-free deduplication** that reuses existing summaries rather than regenerating.

### Core Principle

> If a scheduled summary already exists for a time period, use it. Don't regenerate from archive data.

### Algorithm: Backfill with Reuse

When initiating archive backfill for a time range:

```python
async def backfill_with_reuse(guild_id: str, channel_id: str, start: datetime, end: datetime):
    """Backfill archive summaries, reusing existing scheduled ones."""

    periods = generate_periods(start, end, granularity="daily")

    for period in periods:
        # Step 1: Check for existing scheduled summary
        existing = await find_summary_for_period(
            guild_id=guild_id,
            channel_id=channel_id,
            start=period.start,
            end=period.end,
            sources=["scheduled", "realtime", "manual"]  # Any live summary
        )

        if existing:
            # Step 2a: Reuse it - just update source metadata if needed
            if existing.source != "archive":
                await mark_as_archive_verified(existing.id)
            logger.info(f"Reusing existing {existing.source} summary for {period}")
            continue

        # Step 2b: No existing summary - generate from archive
        logger.info(f"No existing summary for {period}, generating from archive")
        await generate_archive_summary(guild_id, channel_id, period)
```

### Summary Matching Logic

Match existing summaries by coverage overlap:

```python
async def find_summary_for_period(guild_id, channel_id, start, end, sources):
    """Find a summary that covers this time period."""

    return await repo.query("""
        SELECT * FROM stored_summaries
        WHERE guild_id = ?
          AND ? = ANY(source_channel_ids)  -- Channel matches
          AND source IN (?)                 -- Right source type
          AND start_time <= ?               -- Covers period start
          AND end_time >= ?                 -- Covers period end
          AND (
            -- At least 80% time overlap
            JULIANDAY(MIN(end_time, ?)) - JULIANDAY(MAX(start_time, ?))
          ) / (JULIANDAY(?) - JULIANDAY(?)) >= 0.8
        ORDER BY created_at DESC
        LIMIT 1
    """, [guild_id, channel_id, sources, start, end, end, start, end, start])
```

### Wiki Backfill Deduplication

When backfilling wiki from summaries, automatically skip duplicates:

```python
async def wiki_backfill_deduped(guild_id: str, summaries: List[StoredSummary]):
    """Ingest summaries to wiki, skipping duplicates."""

    # Group by coverage period (channel + time range)
    coverage_map = {}

    for summary in summaries:
        key = (
            tuple(sorted(summary.source_channel_ids)),
            summary.start_time.date() if summary.start_time else None,
        )

        if key not in coverage_map:
            coverage_map[key] = summary
        else:
            # Keep the one with better source priority
            existing = coverage_map[key]
            if source_priority(summary.source) > source_priority(existing.source):
                coverage_map[key] = summary
                logger.debug(f"Preferring {summary.source} over {existing.source} for {key}")

    # Ingest only unique summaries
    for summary in coverage_map.values():
        await wiki_agent.ingest_summary(summary)


def source_priority(source: str) -> int:
    """Higher = prefer. Scheduled preferred over archive."""
    return {
        "scheduled": 3,  # Most reliable - from live data on schedule
        "realtime": 2,   # Live data, user-triggered
        "manual": 2,     # Live data, user-triggered
        "archive": 1,    # Imported historical
        "imported": 0,   # External import
    }.get(source, 0)
```

### Database Changes

Add coverage tracking for efficient lookups:

```sql
-- Migration: 059_summary_coverage_index.sql

-- Index for fast coverage lookups
CREATE INDEX IF NOT EXISTS idx_stored_summaries_coverage
ON stored_summaries(guild_id, source_channel_ids, start_time, end_time);

-- Optional: Add archive_verified flag
ALTER TABLE stored_summaries ADD COLUMN archive_verified BOOLEAN DEFAULT FALSE;
```

The `archive_verified` flag indicates a scheduled summary that was confirmed to match archive data - useful for auditing but not required for deduplication.

## Implementation

### Phase 1: Wiki Deduplication (Immediate)

Update `wiki_backfill` to use `wiki_backfill_deduped`:
- No migration needed
- Purely code change
- Prevents duplicate wiki pages from existing duplicate summaries

### Phase 2: Backfill Reuse (Next)

Update archive backfill to check for existing summaries:
- Add index for fast lookups
- Modify backfill logic to reuse
- Zero user interaction required

### Phase 3: Coverage Index (Optional)

Add dedicated coverage tracking if query performance needs improvement.

## Consequences

### Positive
- **Hands-free**: No user decisions required
- **Cost savings**: Avoids regenerating summaries that already exist
- **Cleaner wiki**: Single source of truth per time period
- **Simple logic**: Prefer scheduled > archive, first match wins

### Negative
- Requires index for efficient lookups at scale
- Edge case: If scheduled summary was generated with different options (perspective, length), archive might have been "better" - but scheduled is still valid

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| Scheduled exists, archive import requested | Reuse scheduled, skip generation |
| Scheduled failed/missing, archive import | Generate from archive |
| Both scheduled and archive exist | Wiki uses scheduled (higher priority) |
| Scheduled has different options than archive would | Use scheduled anyway - content is same |
| Partial overlap (scheduled covers 80%+) | Reuse scheduled |
| Partial overlap (< 80%) | Generate archive for gap |

## References

- ADR-008: Summary Source Tracking
- ADR-056: Wiki Knowledge Base
- Current backfill: `src/dashboard/routes/wiki.py`
