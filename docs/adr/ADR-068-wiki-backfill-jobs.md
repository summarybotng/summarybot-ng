# ADR-068: Wiki Backfill Jobs

## Status
Implemented (2026-04-26)

## Context

ADR-067 implemented automatic wiki ingestion for **new** summaries. However, existing summaries created before the feature was enabled remain un-ingested. Users need a way to:

1. Backfill existing summaries into the wiki
2. See progress of the backfill operation
3. Cancel or pause long-running backfills
4. Distinguish wiki jobs from chat summarization jobs

### Current State

| Scenario | Wiki Ingestion |
|----------|----------------|
| New summary (post-ADR-067) | Automatic |
| Existing summary (pre-ADR-067) | Manual only via "Populate Wiki" |
| Failed auto-ingestion | No retry mechanism |

The "Populate Wiki" button in the wiki page triggers a one-shot operation that:
- Fetches last N days of summaries
- Processes them synchronously
- Has no progress visibility
- Cannot be cancelled
- Blocks the UI

---

## Decision

Integrate wiki backfill into the **existing job system** (ADR-013) with a new job type, enabling:
- Progress tracking in Jobs page
- Cancel/pause support
- Clear separation from chat summarization jobs
- Retry on failure

---

## Implementation

### New Job Type

```python
class JobType(Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    RETROSPECTIVE = "retrospective"
    REGENERATE = "regenerate"
    WIKI_BACKFILL = "wiki_backfill"  # NEW
```

### Job Category for UI Filtering

Add job category to separate concerns:

```python
class JobCategory(Enum):
    CHAT_SUMMARY = "chat_summary"    # Manual, Scheduled, Retrospective, Regenerate
    WIKI_MANAGEMENT = "wiki_management"  # Wiki Backfill, future wiki jobs

JOB_TYPE_CATEGORY = {
    JobType.MANUAL: JobCategory.CHAT_SUMMARY,
    JobType.SCHEDULED: JobCategory.CHAT_SUMMARY,
    JobType.RETROSPECTIVE: JobCategory.CHAT_SUMMARY,
    JobType.REGENERATE: JobCategory.CHAT_SUMMARY,
    JobType.WIKI_BACKFILL: JobCategory.WIKI_MANAGEMENT,
}
```

### Jobs Page Filter Tabs

```
[ All Jobs ] [ Chat Summaries ] [ Wiki Management ]
```

Or as a dropdown filter:
```
Category: [All ▼] [Chat Summaries] [Wiki Management]
```

---

## API Endpoints

### Start Wiki Backfill

```
POST /guilds/{guild_id}/wiki/backfill
```

**Request:**
```json
{
  "mode": "unprocessed",      // "unprocessed" | "all" | "date_range"
  "date_from": "2026-01-01",  // Optional: only for date_range mode
  "date_to": "2026-04-01",    // Optional: only for date_range mode
  "batch_size": 10,           // Summaries per batch (default: 10)
  "delay_between_batches": 1.0  // Seconds between batches (default: 1.0)
}
```

**Response:**
```json
{
  "job_id": "wiki-backfill-abc123",
  "status": "pending",
  "total_summaries": 150,
  "message": "Wiki backfill job created"
}
```

### Backfill Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `unprocessed` | Only summaries where `wiki_ingested = FALSE` | Normal backfill |
| `all` | Re-ingest all summaries (overwrites existing) | Full rebuild |
| `date_range` | Summaries within date range | Targeted backfill |

### Resume Paused Job

```
POST /guilds/{guild_id}/jobs/{job_id}/resume
```

**Response:**
```json
{
  "job_id": "wiki-backfill-abc123",
  "status": "running",
  "message": "Job resumed from summary 47/150"
}
```

Resumes a paused job from where it left off. The job continues processing from `progress_current` position.

**Error Cases:**
- `404` - Job not found
- `409` - Job is not paused (must be in PAUSED status)
- `409` - Another backfill is already running

### Pause Running Job

```
POST /guilds/{guild_id}/jobs/{job_id}/pause
```

**Response:**
```json
{
  "job_id": "wiki-backfill-abc123",
  "status": "paused",
  "message": "Job paused at summary 47/150"
}
```

Pauses a running job. The job can be resumed later with `/resume`.

---

## Job Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Wiki Backfill Job                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. PENDING: Job created, queued for execution               │
│       ↓                                                      │
│  2. RUNNING: Processing summaries in batches                 │
│       │                                                      │
│       ├─→ Batch 1: summaries 1-10                           │
│       │     └─→ Ingest each → mark wiki_ingested=TRUE        │
│       │     └─→ Update progress: 10/150                      │
│       │     └─→ Sleep 1s                                     │
│       │                                                      │
│       ├─→ Batch 2: summaries 11-20                          │
│       │     └─→ ...                                          │
│       │                                                      │
│       ├─→ [User clicks Cancel] → CANCELLED                   │
│       ├─→ [User clicks Pause] → PAUSED                       │
│       │     └─→ [User clicks Resume] → RUNNING (continues)   │
│       ├─→ [Error occurs] → Continue or FAILED                │
│       │                                                      │
│  3. COMPLETED: All summaries processed                       │
│       └─→ Show: "150 summaries ingested, 3 failed"          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Job Progress Tracking

### Progress Fields

```python
@dataclass
class WikiBackfillProgress:
    total_summaries: int
    processed: int
    ingested: int      # Successfully ingested
    skipped: int       # Already ingested (mode=all skip check)
    failed: int        # Failed to ingest
    current_summary_id: Optional[str]
    current_summary_title: Optional[str]
    estimated_remaining_seconds: Optional[float]
```

### Progress Message Examples

```
"Processing batch 3/15: 'Discord: #general — Apr 03, 05:11'"
"Ingested 47/150 summaries (3 failed, 2 skipped)"
"Completed: 145 ingested, 3 failed, 2 already processed"
```

---

## Job Card Display

```
┌─────────────────────────────────────────────────────────────┐
│ [Wiki Backfill] Knowledge Base Update                 📚    │
│ Started: 5 minutes ago                                      │
│ Status: ████████░░░░ 67% (100/150 summaries)               │
│ Current: "Discord: Server Summary (6 channels) — Apr 03"   │
│                                                             │
│ Stats: 98 ingested · 2 skipped · 0 failed                  │
│ Est. remaining: ~2 minutes                                  │
│                                          [Pause] [Cancel]   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ [Wiki Backfill] Knowledge Base Update                 📚    │
│ Paused: 2 minutes ago                                       │
│ Status: ⏸ Paused at 67% (100/150 summaries)                │
│                                                             │
│ Stats: 98 ingested · 2 skipped · 0 failed                  │
│ Paused by: User request                                     │
│                                         [Resume] [Cancel]   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ [Wiki Backfill] Knowledge Base Update                 📚    │
│ Completed: 10 minutes ago                                   │
│ Status: ✓ Completed                                        │
│                                                             │
│ Results: 145 ingested · 3 failed · 2 already processed     │
│ Duration: 8 minutes 32 seconds                              │
│                                              [View Errors]   │
└─────────────────────────────────────────────────────────────┘
```

---

## Error Handling

### Per-Summary Errors

Errors on individual summaries don't fail the job:

```python
for summary in batch:
    try:
        await wiki_agent.ingest_summary(...)
        await mark_wiki_ingested(summary.id)
        progress.ingested += 1
    except Exception as e:
        progress.failed += 1
        job.metadata["errors"].append({
            "summary_id": summary.id,
            "summary_title": summary.title,
            "error": str(e),
            "timestamp": utc_now_naive().isoformat()
        })
        # Continue to next summary
```

### Job-Level Errors

Job fails only on critical errors:
- Database connection lost
- Wiki repository unavailable
- Out of memory

### View Errors Action

Shows failed summaries with option to retry just those:

```
┌─────────────────────────────────────────────────────────────┐
│ Failed Summaries (3)                                        │
├─────────────────────────────────────────────────────────────┤
│ • Discord: #dev — Mar 15, 10:30                            │
│   Error: "Topic extraction failed: empty key_points"        │
│                                                             │
│ • WhatsApp: Team Chat — Mar 20, 14:22                       │
│   Error: "Database locked (retried 3 times)"                │
│                                                             │
│ • Discord: Server Summary — Mar 25, 09:00                   │
│   Error: "Unicode decode error in participant name"         │
│                                                             │
│                              [Retry Failed] [Dismiss]       │
└─────────────────────────────────────────────────────────────┘
```

---

## Wiki Page Integration

### Backfill Button

Add to Wiki page header:

```tsx
<WikiPageHeader>
  <h1>Knowledge Base</h1>
  <div className="actions">
    <Button onClick={handlePopulate}>
      <RefreshCw /> Backfill Summaries
    </Button>
    {activeBackfillJob && (
      <Badge variant="outline">
        Backfill in progress: {activeBackfillJob.progress.percent}%
      </Badge>
    )}
  </div>
</WikiPageHeader>
```

### Backfill Dialog

```tsx
<Dialog>
  <DialogHeader>
    <DialogTitle>Backfill Wiki from Summaries</DialogTitle>
  </DialogHeader>
  <DialogContent>
    <RadioGroup value={mode}>
      <RadioItem value="unprocessed">
        Only un-processed summaries (recommended)
        <span className="text-muted">~{unprocessedCount} summaries</span>
      </RadioItem>
      <RadioItem value="date_range">
        Date range
      </RadioItem>
      <RadioItem value="all">
        All summaries (full rebuild)
        <span className="text-warning">This may take a while</span>
      </RadioItem>
    </RadioGroup>

    {mode === "date_range" && (
      <DateRangePicker value={dateRange} onChange={setDateRange} />
    )}

    <Collapsible title="Advanced Options">
      <Label>Batch Size</Label>
      <Input type="number" value={batchSize} min={1} max={50} />
      <Label>Delay Between Batches (seconds)</Label>
      <Input type="number" value={delay} step={0.5} min={0.5} max={10} />
    </Collapsible>
  </DialogContent>
  <DialogFooter>
    <Button variant="ghost">Cancel</Button>
    <Button onClick={startBackfill}>Start Backfill</Button>
  </DialogFooter>
</Dialog>
```

---

## Database Changes

### Migration 058_wiki_backfill.sql

```sql
-- No schema changes needed - uses existing summary_jobs table
-- Job type 'wiki_backfill' stored in job_type column
-- Progress stored in existing progress_* columns
-- Errors stored in metadata JSON column

-- Add index for finding active wiki jobs
CREATE INDEX IF NOT EXISTS idx_summary_jobs_wiki_backfill
ON summary_jobs(guild_id, job_type, status)
WHERE job_type = 'wiki_backfill';
```

---

## Rate Limiting

### Default Limits

| Setting | Default | Configurable |
|---------|---------|--------------|
| Batch size | 10 | Yes (1-50) |
| Delay between batches | 1.0s | Yes (0.5-10s) |
| Max concurrent backfills per guild | 1 | No |
| Max total concurrent backfills | 5 | Environment var |

### Concurrency Control

```python
async def start_wiki_backfill(guild_id: str, request: BackfillRequest) -> SummaryJob:
    # Check for existing active backfill
    existing = await job_repo.find_active_by_type(guild_id, JobType.WIKI_BACKFILL)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Wiki backfill already in progress: {existing.id}"
        )

    # Create and start job
    job = SummaryJob(
        id=generate_id("wiki-backfill-"),
        guild_id=guild_id,
        job_type=JobType.WIKI_BACKFILL,
        metadata={
            "mode": request.mode,
            "batch_size": request.batch_size,
            "delay": request.delay_between_batches,
            "errors": [],
        }
    )
    await job_repo.save(job)

    # Start in background
    asyncio.create_task(execute_wiki_backfill(job))

    return job
```

### Adaptive Rate Control

To prevent backfill from impacting real-time operations:

#### 1. Priority Yielding

Backfill yields to higher-priority work:

```python
class BackfillPriority:
    """Backfill pauses when higher-priority work is pending."""

    async def should_yield(self) -> bool:
        # Yield if real-time summary jobs are queued
        active_summary_jobs = await job_repo.count_active_by_types(
            [JobType.MANUAL, JobType.SCHEDULED]
        )
        return active_summary_jobs > 0

    async def wait_for_capacity(self, job: SummaryJob) -> None:
        while await self.should_yield():
            job.update_progress(
                job.progress_current,
                message="Paused: waiting for real-time jobs to complete"
            )
            await asyncio.sleep(5)  # Check every 5s
```

#### 2. Resource Monitoring

Auto-pause when system is under load:

```python
import psutil

class ResourceMonitor:
    CPU_THRESHOLD = 80.0      # Pause if CPU > 80%
    MEMORY_THRESHOLD = 85.0   # Pause if memory > 85%
    CHECK_INTERVAL = 10       # Check every 10 seconds

    async def check_resources(self) -> Tuple[bool, str]:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent

        if cpu > self.CPU_THRESHOLD:
            return False, f"CPU at {cpu:.0f}% (threshold: {self.CPU_THRESHOLD}%)"
        if memory > self.MEMORY_THRESHOLD:
            return False, f"Memory at {memory:.0f}% (threshold: {self.MEMORY_THRESHOLD}%)"

        return True, "OK"

    async def wait_for_resources(self, job: SummaryJob) -> None:
        while True:
            ok, reason = await self.check_resources()
            if ok:
                return

            job.update_progress(
                job.progress_current,
                message=f"Paused: {reason}"
            )
            await asyncio.sleep(self.CHECK_INTERVAL)
```

#### 3. Time-of-Day Restrictions (Optional)

Configurable quiet hours:

```python
@dataclass
class BackfillSchedule:
    """Optional time restrictions for backfill."""
    enabled: bool = False
    allowed_hours_start: int = 2   # 2 AM
    allowed_hours_end: int = 6     # 6 AM
    timezone: str = "UTC"

    def is_allowed_now(self) -> bool:
        if not self.enabled:
            return True

        now = datetime.now(ZoneInfo(self.timezone))
        return self.allowed_hours_start <= now.hour < self.allowed_hours_end
```

#### 4. Adaptive Delay

Increase delay when system is busy:

```python
class AdaptiveDelay:
    """Dynamically adjust delay based on system load."""

    def __init__(self, base_delay: float = 1.0):
        self.base_delay = base_delay
        self.min_delay = 0.5
        self.max_delay = 10.0

    async def get_delay(self) -> float:
        cpu = psutil.cpu_percent()

        if cpu < 30:
            return self.min_delay
        elif cpu < 50:
            return self.base_delay
        elif cpu < 70:
            return self.base_delay * 2
        else:
            return self.max_delay
```

### Batch Execution with Rate Control

```python
async def execute_wiki_backfill(job: SummaryJob) -> None:
    priority = BackfillPriority()
    resources = ResourceMonitor()
    delay = AdaptiveDelay(job.metadata.get("delay", 1.0))

    summaries = await get_summaries_to_process(job)
    job.update_progress(0, total=len(summaries))

    for i, batch in enumerate(batched(summaries, job.metadata["batch_size"])):
        # Check if cancelled
        if job.status == JobStatus.CANCELLED:
            return

        # Yield to higher priority work
        await priority.wait_for_capacity(job)

        # Wait for system resources
        await resources.wait_for_resources(job)

        # Process batch
        for summary in batch:
            await process_summary(summary, job)

        job.update_progress(min((i + 1) * len(batch), len(summaries)))

        # Adaptive delay between batches
        wait_time = await delay.get_delay()
        await asyncio.sleep(wait_time)

    job.complete()
```

---

## Implementation Order

1. Add `WIKI_BACKFILL` to `JobType` enum
2. Add `JobCategory` enum and mapping
3. Add category filter to Jobs API and UI
4. Create `WikiBackfillExecutor` class
5. Add `/wiki/backfill` endpoint
6. Add backfill dialog to Wiki page
7. Update Jobs page to show wiki-specific progress
8. Add "View Errors" action for failed summaries

---

## Consequences

### Positive
- Full visibility into backfill progress
- Can cancel/pause long-running backfills
- Errors tracked and retryable
- Consistent with existing job system
- Clear separation from chat summarization

### Negative
- Adds complexity to job system
- UI needs category filtering
- Need to handle "only one backfill at a time" constraint

### Mitigations
- Category filtering is optional (All Jobs still works)
- Single-backfill constraint prevents resource exhaustion
- Batch processing with delays prevents overwhelming wiki

---

## Future Enhancements

1. **Auto-backfill on first wiki visit**: If wiki is empty and summaries exist, prompt to backfill
2. **Scheduled backfill**: Run backfill weekly for any missed summaries
3. **Selective re-ingestion**: Re-ingest specific topics only
4. **Backfill from specific sources**: Only Discord, only WhatsApp, etc.

---

## References

- [ADR-013: Unified Job Tracking](./013-unified-job-tracking.md)
- [ADR-067: Automatic Wiki Ingestion](./ADR-067-automatic-wiki-ingestion.md)
- [ADR-056: Compounding Wiki Standard](./ADR-056-compounding-wiki-standard.md)
