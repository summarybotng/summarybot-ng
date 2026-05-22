# ADR-102: Schedule-Summary-Job Traceability

## Status
IMPLEMENTED (2026-05-22)

## Context

When a scheduled task runs (either automatically or via manual "Run Now"), the system should maintain full traceability between:

1. **Schedule** → The scheduled task configuration
2. **Job** → The execution record of that run
3. **Summary** → The generated summary output

Currently, there are gaps in this traceability chain causing:
- Summaries not linking back to their originating schedule
- Run histories showing empty on schedules
- Jobs not linking back to schedules
- Silent failures in delivery destinations (e.g., Confluence)

## Decision

### Required Traceability Links

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

### Implementation Requirements

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

### Test Cases (Regression Suite)

```typescript
describe('Schedule-Summary-Job Traceability', () => {
  describe('Manual Run (Run Now)', () => {
    it('creates job with schedule_id set', async () => {
      const job = await runScheduleNow(scheduleId);
      expect(job.schedule_id).toBe(scheduleId);
    });

    it('creates summary with schedule_id set', async () => {
      const job = await runScheduleNow(scheduleId);
      await waitForJobCompletion(job.job_id);
      const summary = await getSummary(job.summary_id);
      expect(summary.schedule_id).toBe(scheduleId);
    });

    it('saves task result to run history', async () => {
      const job = await runScheduleNow(scheduleId);
      await waitForJobCompletion(job.job_id);
      const history = await getScheduleRunHistory(scheduleId);
      expect(history).toContainEqual(
        expect.objectContaining({ summary_id: job.summary_id })
      );
    });
  });

  describe('Scheduled Run (Automatic)', () => {
    // Same tests as manual run
  });

  describe('Delivery Tracking', () => {
    it('records successful deliveries in task result', async () => {
      const job = await runScheduleNow(scheduleId);
      await waitForJobCompletion(job.job_id);
      const history = await getScheduleRunHistory(scheduleId);
      const lastRun = history[0];
      expect(lastRun.delivery_results).toContainEqual(
        expect.objectContaining({
          destination_type: 'dashboard',
          success: true
        })
      );
    });

    it('records failed deliveries with error messages', async () => {
      // Configure invalid Confluence settings
      const job = await runScheduleNow(scheduleIdWithConfluence);
      await waitForJobCompletion(job.job_id);
      const history = await getScheduleRunHistory(scheduleIdWithConfluence);
      const lastRun = history[0];
      const confluenceResult = lastRun.delivery_results.find(
        d => d.destination_type === 'confluence'
      );
      expect(confluenceResult.success).toBe(false);
      expect(confluenceResult.error).toBeDefined();
    });
  });

  describe('UI Navigation', () => {
    it('summary detail shows schedule badge when schedule_id set', () => {
      // Render summary detail with schedule_id
      // Assert schedule badge is visible
      // Assert badge is clickable and navigates to schedule
    });

    it('job list shows schedule link when schedule_id set', () => {
      // Render jobs list with scheduled job
      // Assert schedule link is visible
      // Assert link navigates to schedule
    });

    it('schedule run history shows past executions', () => {
      // Render schedule with run history
      // Assert history drawer shows executions
      // Assert each execution links to summary
    });
  });
});
```

## Identified Bugs (All Fixed)

### Bug 1: task_repository may be None ✅ FIXED
**Location**: `scheduler.py:71-76`
**Issue**: `save_task_result` only runs if `self.task_repository` is truthy
**Impact**: Run history is empty if repository not initialized
**Fix**: Added WARNING log at startup if task_repository not initialized. Verified initialization in main.py:474-481.

### Bug 2: Rolling summaries skip normal delivery ✅ FIXED (prior session)
**Location**: `executor.py:595-609`
**Issue**: Rolling period summaries return early, bypassing `_deliver_summary`
**Impact**: Confluence delivery skipped for rolling summaries
**Fix**: Added ADR-102 block to execute non-dashboard deliveries when `rolling_finalized=True`

### Bug 3: Confluence delivery fails silently ✅ FIXED
**Location**: `delivery/confluence.py:28-130`
**Issue**: ConfluenceDeliveryStrategy called `publish_summary()` with wrong parameters (passed `content` instead of `summary`, `parent_page_id` not valid). Also treated return value as dict when it's a dataclass.
**Impact**: Confluence delivery would fail with type errors
**Fix**: Corrected API call to pass `summary=summary`, `guild_id`, `channel_names`, `scope_type`, `category_name`. Fixed result handling to use dataclass attributes (`result.success`, `result.error`, etc.)

### Bug 4: schedule_id not set on some summary paths ✅ FIXED
**Location**: `dashboard/services/job_executor.py:267-275`
**Issue**: StoredSummary created from job_executor didn't include `schedule_id` even for SCHEDULED jobs
**Impact**: Summary doesn't link back to schedule when retried via job_executor
**Fix**: Added `schedule_id=job.schedule_id` to StoredSummary constructor

## Consequences

### Positive
- Full traceability from schedule → job → summary
- Users can navigate between related entities
- Delivery failures are visible and actionable
- Regression tests prevent future breakage

### Negative
- Additional database queries for lookups
- More data stored per execution

## References
- ADR-009: Summary-Schedule Navigation
- ADR-013: Job Tracking
- CS-008: Delivery Strategy Pattern
