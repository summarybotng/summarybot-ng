# ADR-102: Schedule-Summary-Job Traceability

## Status
PROPOSED

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

## Identified Bugs

### Bug 1: task_repository may be None
**Location**: `scheduler.py:650`
**Issue**: `save_task_result` only runs if `self.task_repository` is truthy
**Impact**: Run history is empty if repository not initialized
**Fix**: Ensure `task_repository` is always initialized; log error if None

### Bug 2: Rolling summaries skip normal delivery
**Location**: `executor.py:585-601`
**Issue**: Rolling period summaries return early, bypassing `_deliver_summary`
**Impact**: Confluence delivery skipped for rolling summaries
**Fix**: Execute delivery strategies even for rolling summaries

### Bug 3: Confluence delivery fails silently
**Location**: `delivery/confluence.py`
**Issue**: Errors may be caught but not properly surfaced to TaskResult
**Impact**: User sees "success" but Confluence page not created
**Fix**: Ensure all delivery errors are captured in delivery_results

### Bug 4: schedule_id not set on some summary paths
**Location**: Various
**Issue**: Some code paths may create summaries without setting schedule_id
**Impact**: Summary doesn't link back to schedule
**Fix**: Audit all summary creation paths

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
