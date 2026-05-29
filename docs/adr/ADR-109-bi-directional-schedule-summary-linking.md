# ADR-109: Bi-Directional Schedule-Summary Linking

## Status
PROPOSED (2026-05-28)

## Context

ADR-102 established the traceability model for Schedule → Job → Summary relationships. However, investigation revealed gaps in the bi-directional linking:

### Current State Analysis

**Database Query Results:**
```
source=scheduled: NO schedule_id: 313 summaries
source=scheduled: HAS schedule_id: 2 summaries (both rolling)
```

Only 2 out of 315 scheduled summaries have their `schedule_id` properly set - both are rolling summaries.

### Root Causes Identified

#### 1. ON DELETE SET NULL FK Constraint
The `stored_summaries.schedule_id` foreign key uses `ON DELETE SET NULL`:
```sql
FOREIGN KEY (schedule_id) REFERENCES scheduled_tasks(id) ON DELETE SET NULL
```

When a schedule is deleted, all associated summaries lose their `schedule_id`, breaking traceability.

#### 2. DashboardDeliveryStrategy Source Hardcoding
In `src/scheduling/delivery/dashboard.py:96`:
```python
source=SummarySource.SCHEDULED,  # Always set, even when schedule_id is None
```

The source is hardcoded to SCHEDULED regardless of whether `schedule_id_value` is actually available.

#### 3. Historical Data Gap
Summaries created before proper schedule_id tracking may have NULL values even though the schedule still exists.

## Decision

### 1. Preserve Schedule Metadata on Deletion

Add `schedule_name_snapshot` and `schedule_config_snapshot` columns to preserve schedule information even after deletion:

```sql
-- Migration: 097_schedule_snapshot_columns.sql
ALTER TABLE stored_summaries ADD COLUMN schedule_name_snapshot TEXT;
ALTER TABLE stored_summaries ADD COLUMN schedule_config_snapshot TEXT;
```

Update `DashboardDeliveryStrategy.deliver()` to capture schedule metadata:
```python
# Capture schedule snapshot for historical reference
schedule_name_snapshot = None
schedule_config_snapshot = None
if context.scheduled_task:
    schedule_name_snapshot = context.scheduled_task.name
    schedule_config_snapshot = json.dumps({
        "schedule_type": context.scheduled_task.schedule_type,
        "scope": context.scheduled_task.scope.value if context.scheduled_task.scope else None,
        "time_range_hours": context.scheduled_task.time_range_hours,
    })
```

### 2. Fix Source Assignment Logic

Update `DashboardDeliveryStrategy` to set source based on actual context:
```python
# Determine source based on actual schedule context
if schedule_id_value:
    source = SummarySource.SCHEDULED
else:
    source = SummarySource.MANUAL  # Fallback if no schedule link
```

### 3. Data Repair Migration

Create a repair migration to fix historical summaries where schedule_id can be inferred:

```sql
-- Migration: 098_repair_schedule_links.sql

-- Step 1: Update schedule_id for summaries where we can infer from job records
UPDATE stored_summaries
SET schedule_id = (
    SELECT sj.schedule_id
    FROM summary_jobs sj
    WHERE sj.summary_id = stored_summaries.id
    AND sj.schedule_id IS NOT NULL
    LIMIT 1
)
WHERE schedule_id IS NULL
AND source = 'scheduled';

-- Step 2: Capture schedule name snapshot for remaining valid links
UPDATE stored_summaries
SET schedule_name_snapshot = (
    SELECT st.name
    FROM scheduled_tasks st
    WHERE st.id = stored_summaries.schedule_id
)
WHERE schedule_id IS NOT NULL
AND schedule_name_snapshot IS NULL;
```

### 4. Schedule Deletion Handling

When a schedule is deleted:
1. Keep `ON DELETE SET NULL` to prevent cascade deletion of summaries
2. Before deletion, populate snapshot columns for all linked summaries:

```python
async def delete_schedule(self, schedule_id: str) -> None:
    # Snapshot schedule info to linked summaries before deletion
    schedule = await self.get(schedule_id)
    if schedule:
        await self._snapshot_schedule_to_summaries(schedule)

    # Now delete (ON DELETE SET NULL will clear schedule_id)
    await self._delete(schedule_id)
```

## Implementation

### Files to Create

| File | Purpose |
|------|---------|
| `src/data/migrations/097_schedule_snapshot_columns.sql` | Add snapshot columns |
| `src/data/migrations/098_repair_schedule_links.sql` | Repair historical data |

### Files to Modify

| File | Change |
|------|--------|
| `src/scheduling/delivery/dashboard.py` | Capture schedule snapshot, fix source logic |
| `src/models/stored_summary.py` | Add `schedule_name_snapshot`, `schedule_config_snapshot` |
| `src/data/sqlite/stored_summary_repository.py` | Handle new columns |
| `src/data/sqlite/schedule_repository.py` | Add pre-deletion snapshot method |
| `src/dashboard/routes/summaries.py` | Use snapshot for display when schedule deleted |

### API Changes

StoredSummaryDetail response adds:
```json
{
  "schedule_id": "abc123",
  "schedule_name": "Daily General",
  "schedule_name_snapshot": "Daily General",
  "schedule_deleted": false
}
```

When `schedule_id` is NULL but `schedule_name_snapshot` exists:
```json
{
  "schedule_id": null,
  "schedule_name": null,
  "schedule_name_snapshot": "Daily General (deleted)",
  "schedule_deleted": true
}
```

## Consequences

### Positive
- Full bi-directional traceability between schedules and summaries
- Historical reference preserved even after schedule deletion
- Data integrity maintained for audit purposes
- Existing data repaired where possible

### Negative
- Additional storage for snapshot columns
- Migration may take time on large databases
- Slight complexity increase in deletion workflow

## Test Cases

```python
class TestBidirectionalScheduleSummaryLinking:
    """ADR-109: Bi-directional linking tests."""

    @pytest.mark.asyncio
    async def test_scheduled_summary_has_schedule_id(self, schedule, executor):
        """Non-rolling scheduled summary must have schedule_id."""
        result = await executor.execute_summary_task(schedule.create_task())
        summary = await get_summary(result.summary_id)
        assert summary.schedule_id == schedule.id
        assert summary.source == SummarySource.SCHEDULED

    @pytest.mark.asyncio
    async def test_schedule_deletion_preserves_snapshot(self, schedule, summary_repo, schedule_repo):
        """Schedule deletion preserves name snapshot on linked summaries."""
        # Create summary linked to schedule
        summary = await create_scheduled_summary(schedule)
        assert summary.schedule_id == schedule.id

        # Delete schedule
        await schedule_repo.delete(schedule.id)

        # Verify summary updated
        updated = await summary_repo.get(summary.id)
        assert updated.schedule_id is None  # FK SET NULL
        assert updated.schedule_name_snapshot == schedule.name

    @pytest.mark.asyncio
    async def test_data_repair_links_via_job_records(self, orphan_summary, job_with_schedule):
        """Repair migration links summaries via job records."""
        # Run repair migration
        await run_migration("098_repair_schedule_links.sql")

        # Verify link restored
        summary = await summary_repo.get(orphan_summary.id)
        assert summary.schedule_id == job_with_schedule.schedule_id
```

## References
- [ADR-102](./ADR-102-schedule-summary-job-traceability.md): Schedule-Summary-Job Traceability
- [ADR-013](./ADR-013-job-tracking.md): Job Tracking
- [Migration 009](../src/data/migrations/009_stored_summaries.sql): Original stored_summaries schema
