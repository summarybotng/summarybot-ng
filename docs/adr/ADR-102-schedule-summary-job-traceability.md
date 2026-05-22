# ADR-102: Schedule-Summary-Job Traceability

## Status
IMPLEMENTED (2026-05-22)

## Context

When a scheduled task runs (either automatically or via manual "Run Now"), the system must maintain full traceability between:

1. **Schedule** → The scheduled task configuration
2. **Job** → The execution record of that run
3. **Summary** → The generated summary output

Prior to this ADR, gaps in the traceability chain caused:
- Summaries not linking back to their originating schedule
- Run histories showing empty on schedules
- Jobs not linking back to schedules
- Silent failures in delivery destinations (e.g., Confluence)

## Decision

### Traceability Model

```
┌──────────────┐     creates      ┌──────────────┐     produces     ┌──────────────┐
│   Schedule   │ ───────────────► │     Job      │ ───────────────► │   Summary    │
│              │                  │              │                  │              │
│  id: abc123  │                  │ schedule_id  │                  │ schedule_id  │
│              │ ◄─────────────── │   = abc123   │ ◄─────────────── │   = abc123   │
│ run_history: │    references    │ summary_id   │    references    │              │
│  [job_xyz]   │                  │   = sum456   │                  │              │
└──────────────┘                  └──────────────┘                  └──────────────┘
```

### Requirements

#### 1. Schedule → Job Link (Run History)
- When a schedule executes, save `TaskResult` to `task_results` table
- `TaskResult.task_id` = schedule ID
- `TaskResult.summary_id` = generated summary ID
- Run History UI fetches from `task_results` table

#### 2. Job → Schedule Link
- `SummaryJob.schedule_id` must be set when created
- Jobs API must return `schedule_name` via lookup
- Jobs UI must show clickable schedule link

#### 3. Summary → Schedule Link
- `StoredSummary.schedule_id` must be set during dashboard delivery
- Summaries API must return `schedule_name` via lookup
- Summary detail UI must show clickable schedule badge

#### 4. Delivery Error Reporting
- All delivery failures must be logged at WARNING or ERROR level
- Failures must be stored in `TaskResult.delivery_results`
- UI must surface delivery failures to users

## Implementation

### Files Changed

| File | Change |
|------|--------|
| `src/scheduling/scheduler.py` | Added startup warning if task_repository not initialized |
| `src/scheduling/executor.py` | Execute deliveries for finalized rolling summaries |
| `src/scheduling/delivery/confluence.py` | Fixed API call parameters and result handling |
| `src/dashboard/services/job_executor.py` | Added schedule_id to StoredSummary |
| `src/dashboard/routes/summaries.py` | Added schedule_name lookup with database fallback |
| `src/frontend/.../StoredSummariesTab.tsx` | Added ScheduleBadge component |
| `src/frontend/.../JobsTab.tsx` | Added clickable schedule link |

### Bugs Fixed

#### Bug 1: task_repository may be None
- **Location**: `scheduler.py` startup
- **Issue**: `save_task_result` only runs if `self.task_repository` is truthy
- **Impact**: Run history empty if repository not initialized
- **Fix**: Added WARNING log at startup; verified initialization in `main.py`

#### Bug 2: Rolling summaries skip delivery
- **Location**: `executor.py` `_execute_combined_mode`
- **Issue**: Rolling period summaries returned early, bypassing `_deliver_summary`
- **Impact**: Confluence delivery skipped for rolling summaries
- **Fix**: Execute non-dashboard deliveries when `rolling_finalized=True`

#### Bug 3: Confluence delivery parameter mismatch
- **Location**: `delivery/confluence.py`
- **Issue**: `ConfluenceDeliveryStrategy.deliver()` passed wrong parameters to `publish_summary()` and treated dataclass result as dict
- **Impact**: Confluence delivery failed with type errors
- **Fix**: Pass `summary` object with required metadata; use dataclass attributes for result

#### Bug 4: schedule_id missing in job_executor
- **Location**: `dashboard/services/job_executor.py`
- **Issue**: `StoredSummary` created without `schedule_id` even for SCHEDULED jobs
- **Impact**: Retried jobs didn't link back to schedule
- **Fix**: Added `schedule_id=job.schedule_id` to constructor

## Test Cases

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestScheduleSummaryJobTraceability:
    """ADR-102: Regression tests for traceability chain."""

    @pytest.mark.asyncio
    async def test_manual_run_creates_job_with_schedule_id(self, scheduler, sample_schedule):
        """Run Now creates job linked to schedule."""
        job = await scheduler.run_now(sample_schedule.id)
        assert job.schedule_id == sample_schedule.id

    @pytest.mark.asyncio
    async def test_manual_run_creates_summary_with_schedule_id(self, scheduler, sample_schedule):
        """Summary produced by Run Now links to schedule."""
        job = await scheduler.run_now(sample_schedule.id)
        await wait_for_job_completion(job.id)
        summary = await get_summary(job.summary_id)
        assert summary.schedule_id == sample_schedule.id

    @pytest.mark.asyncio
    async def test_run_history_contains_task_result(self, scheduler, sample_schedule):
        """Task result saved to run history."""
        job = await scheduler.run_now(sample_schedule.id)
        await wait_for_job_completion(job.id)
        history = await scheduler.get_run_history(sample_schedule.id)
        assert any(r.summary_id == job.summary_id for r in history)

    @pytest.mark.asyncio
    async def test_delivery_success_recorded(self, scheduler, sample_schedule):
        """Successful deliveries recorded in task result."""
        job = await scheduler.run_now(sample_schedule.id)
        await wait_for_job_completion(job.id)
        history = await scheduler.get_run_history(sample_schedule.id)
        last_run = history[0]
        dashboard_result = next(
            (d for d in last_run.delivery_results if d["destination_type"] == "dashboard"),
            None
        )
        assert dashboard_result is not None
        assert dashboard_result["success"] is True

    @pytest.mark.asyncio
    async def test_delivery_failure_recorded_with_error(self, scheduler, schedule_with_bad_confluence):
        """Failed deliveries recorded with error message."""
        job = await scheduler.run_now(schedule_with_bad_confluence.id)
        await wait_for_job_completion(job.id)
        history = await scheduler.get_run_history(schedule_with_bad_confluence.id)
        last_run = history[0]
        confluence_result = next(
            (d for d in last_run.delivery_results if d["destination_type"] == "confluence"),
            None
        )
        assert confluence_result is not None
        assert confluence_result["success"] is False
        assert "error" in confluence_result
```

## Consequences

### Positive
- Full traceability from schedule → job → summary
- Users can navigate between related entities in UI
- Delivery failures visible and actionable
- Regression tests prevent future breakage

### Negative
- Additional database queries for schedule name lookups
- More data stored per execution (delivery_results)

## References
- [ADR-009](./ADR-009-summary-schedule-navigation.md): Summary-Schedule Navigation
- [ADR-013](./ADR-013-job-tracking.md): Job Tracking
- [CS-008](../specs/CS-008-delivery-strategy-pattern.md): Delivery Strategy Pattern
- [GitHub Issue #18](https://github.com/summarybotng/summarybot-ng/issues/18): Implementation tracking
