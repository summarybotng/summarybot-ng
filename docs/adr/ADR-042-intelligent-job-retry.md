# ADR-042: Intelligent Job Retry Strategy

**Status:** Proposed
**Date:** 2026-04-05
**Depends on:** ADR-013 (Unified Job Tracking), ADR-024 (Resilient Summary Generation)

---

## 1. Context

The current job retry mechanism (ADR-013) is overly simplistic:

### Current Problems

1. **Retry doesn't execute**: The `retry_job` endpoint creates a new job record but doesn't trigger execution (see TODO at line 2847 in `summaries.py`)

2. **No failure classification**: All failures are treated identically regardless of cause:
   - Transient errors (rate limits, network issues) → should auto-retry with backoff
   - Persistent errors (invalid config, missing permissions) → should NOT auto-retry
   - Resource errors (DB locked) → should retry after delay

3. **No retry limits**: Jobs can be manually retried infinitely, wasting resources on permanently broken configs

4. **No auto-retry**: Users must manually click "Retry" for every failure, even transient ones

5. **No backoff strategy**: Immediate retries can amplify rate limits and resource contention

6. **No context preservation**: Retries don't consider:
   - Why the original failed
   - What's different this time
   - Whether retry is likely to succeed

### Real-World Failure Example

Job `job_DkYcy2jA` failed with "cannot unpack non-iterable NoneType object" - a code bug. Retrying with identical parameters would fail identically. The system should:
1. Classify this as a persistent/code error
2. NOT auto-retry
3. Show clear guidance that this requires a code fix

---

## 2. Decision

### 2.1 Failure Classification System

Categorize failures to determine retry strategy:

```python
class FailureCategory(Enum):
    # Auto-retry with exponential backoff
    TRANSIENT = "transient"       # Rate limits, network timeouts, 5xx errors
    RESOURCE = "resource"          # DB locked, file busy, memory pressure

    # Manual retry only (may succeed with different conditions)
    RECOVERABLE = "recoverable"    # Insufficient messages, channel empty

    # No retry (requires config/code fix)
    PERSISTENT = "persistent"      # Permission denied, invalid config
    CODE_ERROR = "code_error"      # Unhandled exceptions, type errors

    # Unknown - allow manual retry but don't auto-retry
    UNKNOWN = "unknown"
```

### 2.2 Failure Detection Rules

```python
FAILURE_PATTERNS = {
    # TRANSIENT - Auto-retry
    r"rate.?limit": FailureCategory.TRANSIENT,
    r"429": FailureCategory.TRANSIENT,
    r"timeout": FailureCategory.TRANSIENT,
    r"connection.*refused": FailureCategory.TRANSIENT,
    r"502|503|504": FailureCategory.TRANSIENT,

    # RESOURCE - Auto-retry with longer delay
    r"database.*locked": FailureCategory.RESOURCE,
    r"SQLITE_BUSY": FailureCategory.RESOURCE,
    r"too many connections": FailureCategory.RESOURCE,

    # RECOVERABLE - Manual retry
    r"insufficient.*messages?": FailureCategory.RECOVERABLE,
    r"no messages.*found": FailureCategory.RECOVERABLE,
    r"channel.*empty": FailureCategory.RECOVERABLE,

    # PERSISTENT - No retry
    r"permission.*denied": FailureCategory.PERSISTENT,
    r"403": FailureCategory.PERSISTENT,
    r"channel.*not.*found": FailureCategory.PERSISTENT,
    r"invalid.*config": FailureCategory.PERSISTENT,

    # CODE_ERROR - No auto-retry
    r"TypeError": FailureCategory.CODE_ERROR,
    r"AttributeError": FailureCategory.CODE_ERROR,
    r"cannot unpack": FailureCategory.CODE_ERROR,
    r"NoneType": FailureCategory.CODE_ERROR,
    r"KeyError": FailureCategory.CODE_ERROR,
}
```

### 2.3 Retry Policy Per Category

| Category | Auto-Retry | Max Attempts | Backoff | Manual Retry |
|----------|------------|--------------|---------|--------------|
| TRANSIENT | Yes | 3 | Exponential (1s, 2s, 4s) | Yes |
| RESOURCE | Yes | 3 | Fixed delay (30s, 60s, 120s) | Yes |
| RECOVERABLE | No | - | - | Yes (with guidance) |
| PERSISTENT | No | - | - | No (shows fix guidance) |
| CODE_ERROR | No | - | - | No (shows bug report) |
| UNKNOWN | No | - | - | Yes (once) |

### 2.4 Enhanced Job Model

```python
@dataclass
class SummaryJob:
    # Existing fields...

    # NEW: Retry tracking
    failure_category: Optional[FailureCategory] = None
    retry_count: int = 0
    max_retries: int = 3
    retry_of: Optional[str] = None  # Parent job ID
    retry_chain: List[str] = field(default_factory=list)  # All job IDs in chain
    next_retry_at: Optional[datetime] = None
    retry_strategy: Optional[str] = None  # "exponential", "fixed", "manual"

    # NEW: Guidance for users
    failure_guidance: Optional[str] = None  # Human-readable next steps

    @property
    def can_auto_retry(self) -> bool:
        """Check if job can be automatically retried."""
        if self.status != JobStatus.FAILED:
            return False
        if self.failure_category not in (FailureCategory.TRANSIENT, FailureCategory.RESOURCE):
            return False
        if self.retry_count >= self.max_retries:
            return False
        return True

    @property
    def can_manual_retry(self) -> bool:
        """Check if user can manually retry."""
        if self.status != JobStatus.FAILED:
            return False
        if self.failure_category in (FailureCategory.PERSISTENT, FailureCategory.CODE_ERROR):
            return False
        if self.failure_category == FailureCategory.UNKNOWN and self.retry_count > 0:
            return False  # Only allow one manual retry for unknown
        return True
```

### 2.5 Retry Execution Flow

```
                     ┌─────────────┐
                     │  Job Fails  │
                     └──────┬──────┘
                            │
                   ┌────────▼────────┐
                   │ Classify Failure │
                   └────────┬────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐        ┌─────▼─────┐       ┌─────▼─────┐
   │TRANSIENT│        │RECOVERABLE│       │PERSISTENT │
   │RESOURCE │        │  UNKNOWN  │       │CODE_ERROR │
   └────┬────┘        └─────┬─────┘       └─────┬─────┘
        │                   │                   │
   ┌────▼────┐        ┌─────▼─────┐       ┌─────▼─────┐
   │Schedule │        │  Wait for │       │   Show    │
   │Auto-Retry│       │Manual Retry│      │ Guidance  │
   └────┬────┘        └─────┬─────┘       └───────────┘
        │                   │
   ┌────▼────┐        ┌─────▼─────┐
   │ Execute │        │   User    │
   │After Delay│      │Clicks Retry│
   └────┬────┘        └─────┬─────┘
        │                   │
        └───────────────────┘
                   │
           ┌───────▼───────┐
           │Execute New Job │
           │(with tracking) │
           └───────────────┘
```

### 2.6 Auto-Retry Worker

New background worker to process scheduled retries:

```python
class RetryWorker:
    """Processes scheduled job retries with backoff."""

    async def process_pending_retries(self):
        """Check for jobs due for retry and execute them."""
        jobs = await job_repo.get_jobs_pending_retry(
            before=utc_now_naive()
        )

        for job in jobs:
            if job.retry_count >= job.max_retries:
                # Mark as permanently failed
                job.fail(f"Max retries ({job.max_retries}) exceeded")
                job.failure_guidance = "This job failed after multiple retry attempts. Check error details for root cause."
                await job_repo.update(job)
                continue

            # Create retry job
            new_job = await self._create_retry_job(job)

            # Actually execute it
            await self._execute_job(new_job)

    def calculate_next_retry(self, job: SummaryJob) -> datetime:
        """Calculate when to retry based on strategy."""
        if job.failure_category == FailureCategory.TRANSIENT:
            # Exponential backoff: 1s, 2s, 4s, 8s...
            delay_seconds = 2 ** job.retry_count
            return utc_now_naive() + timedelta(seconds=delay_seconds)

        elif job.failure_category == FailureCategory.RESOURCE:
            # Fixed delays: 30s, 60s, 120s
            delays = [30, 60, 120]
            delay = delays[min(job.retry_count, len(delays) - 1)]
            return utc_now_naive() + timedelta(seconds=delay)

        return None  # No auto-retry
```

### 2.7 User Guidance Messages

```python
FAILURE_GUIDANCE = {
    FailureCategory.TRANSIENT:
        "Temporary issue (rate limit/network). Auto-retrying...",

    FailureCategory.RESOURCE:
        "System resource busy. Will retry automatically in {delay}s.",

    FailureCategory.RECOVERABLE:
        "No messages found in time range. Try a different time period or check channel activity.",

    FailureCategory.PERSISTENT:
        "Permission issue. Grant bot 'Read Message History' permission to the channels, "
        "or remove inaccessible channels from the schedule.",

    FailureCategory.CODE_ERROR:
        "Internal error detected. This has been logged for investigation. "
        "Please report at: https://github.com/summarybotng/summarybot-ng/issues",

    FailureCategory.UNKNOWN:
        "Unexpected error. You can retry once. If it fails again, please report the issue.",
}
```

---

## 3. API Changes

### 3.1 Enhanced Job Response

```python
class JobResponse(BaseModel):
    # Existing fields...

    # NEW: Retry info
    failure_category: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    can_auto_retry: bool = False
    can_manual_retry: bool = True
    next_retry_at: Optional[datetime] = None
    failure_guidance: Optional[str] = None
    retry_chain: List[str] = []
```

### 3.2 Retry Endpoint Enhancement

```python
@router.post("/guilds/{guild_id}/jobs/{job_id}/retry")
async def retry_job(
    guild_id: str,
    job_id: str,
    force: bool = Query(False, description="Force retry even if not recommended"),
    user: dict = Depends(get_current_user),
) -> JobRetryResponse:
    """
    Retry a failed job.

    - For TRANSIENT/RESOURCE failures: executes immediately
    - For RECOVERABLE failures: creates new job with execution
    - For PERSISTENT/CODE_ERROR: returns 400 unless force=true
    """
    job = await job_repo.get(job_id)

    if not job.can_manual_retry and not force:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "RETRY_NOT_RECOMMENDED",
                "message": job.failure_guidance,
                "category": job.failure_category.value,
            }
        )

    # Create new job linked to original
    new_job = create_retry_job(job, user)
    await job_repo.save(new_job)

    # ACTUALLY EXECUTE IT (the missing piece!)
    asyncio.create_task(execute_job(new_job))

    return JobRetryResponse(
        success=True,
        job_id=job_id,
        new_job_id=new_job.id,
        message="Retry started.",
    )
```

---

## 4. UI Changes

### 4.1 Job Card Enhancements

```
┌─────────────────────────────────────────────────────────────────┐
│ [Manual] Server Summary                              3m ago     │
│ Status: ✗ Failed - Rate limit exceeded                         │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐│
│ │ 🔄 Auto-retrying in 4s... (attempt 2/3)                     ││
│ └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ [Scheduled] Daily Digest                            10m ago     │
│ Status: ✗ Failed - TypeError: cannot unpack non-iterable...    │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐│
│ │ ⚠️ Internal error detected. This has been logged.           ││
│ │ Please report: [Open Issue]                                 ││
│ └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│ Retry disabled - requires code fix                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ [Manual] #general Summary                           5m ago      │
│ Status: ✗ Failed - Insufficient messages (3 < 10 required)     │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐│
│ │ 💡 Try a longer time range or check channel activity.       ││
│ └─────────────────────────────────────────────────────────────┘│
│                                                 [Retry Anyway]  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Retry Chain Visibility

Show the history of retry attempts:

```
┌─────────────────────────────────────────────────────────────────┐
│ [Manual] Server Summary                                         │
│ Status: ✓ Completed (after 2 retries)                          │
│                                                                 │
│ Retry history:                                                  │
│   job_abc123 → ✗ Rate limit (1s) → job_def456 → ✗ Timeout (2s) │
│   → job_ghi789 → ✓ Completed                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Database Changes

```sql
-- Migration 042: Enhanced retry tracking
ALTER TABLE summary_jobs ADD COLUMN failure_category TEXT;
ALTER TABLE summary_jobs ADD COLUMN retry_count INTEGER DEFAULT 0;
ALTER TABLE summary_jobs ADD COLUMN max_retries INTEGER DEFAULT 3;
ALTER TABLE summary_jobs ADD COLUMN next_retry_at TIMESTAMP;
ALTER TABLE summary_jobs ADD COLUMN retry_strategy TEXT;
ALTER TABLE summary_jobs ADD COLUMN failure_guidance TEXT;

-- Index for retry worker
CREATE INDEX idx_jobs_pending_retry
ON summary_jobs(next_retry_at)
WHERE status = 'failed' AND next_retry_at IS NOT NULL;
```

---

## 6. Implementation Plan

### Phase 1: Failure Classification
1. Add `FailureCategory` enum to models
2. Implement `classify_failure()` with pattern matching
3. Update `job.fail()` to classify and set guidance
4. Add new fields to job schema

### Phase 2: Fix Manual Retry ✓ COMPLETED (2026-04-12)
1. ~~Update `retry_job` endpoint to actually execute the job~~ **DONE** - Created `job_executor.py` service
2. Track retry chain (parent → child relationships) - Basic tracking via `metadata.retry_of`
3. Prevent retry of PERSISTENT/CODE_ERROR without force flag - Pending failure classification

See **ADR-044: Deferred Technical Debt Tracker** for implementation details.

### Phase 3: Auto-Retry Worker
1. Create `RetryWorker` class
2. Add to scheduler startup
3. Process pending retries every 5 seconds
4. Implement backoff strategies

### Phase 4: UI Enhancements
1. Show failure category badge
2. Display guidance message
3. Show auto-retry countdown
4. Disable retry button for non-retriable failures
5. Show retry chain history

---

## 7. Consequences

### Positive
- Failed jobs auto-recover when possible (rate limits, DB locks)
- Users get clear guidance on what to do
- Reduced manual intervention needed
- Code bugs are clearly identified for developers
- Retry attempts are bounded (no infinite loops)

### Negative
- More complex failure handling code
- Auto-retries consume resources (mitigated by limits)
- Requires migration for existing jobs

### Neutral
- Existing retry behavior preserved for manual clicks
- Backward compatible API response structure

---

## 8. Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `src/models/failure_category.py` | Failure classification enum and patterns |
| `src/scheduling/retry_worker.py` | Background auto-retry processor |
| `src/data/migrations/042_retry_tracking.sql` | Database schema changes |

### Modified Files
| File | Changes |
|------|---------|
| `src/models/summary_job.py` | Add retry tracking fields |
| `src/dashboard/routes/summaries.py` | Fix retry endpoint to execute, classify failures |
| `src/dashboard/models.py` | Enhanced job response models |
| `src/scheduling/scheduler.py` | Call failure classification on job.fail() |
| `src/frontend/src/components/summaries/JobsTab.tsx` | Show guidance, disable buttons |

---

## 9. Verification

### Unit Tests
- Failure pattern matching accuracy
- Backoff calculation correctness
- can_auto_retry / can_manual_retry logic

### Integration Tests
- End-to-end retry flow for each category
- Auto-retry worker processes pending jobs
- Manual retry actually executes

### Manual Testing
1. Trigger rate limit error → verify auto-retry
2. Trigger DB locked error → verify delayed retry
3. Trigger permission error → verify no retry, guidance shown
4. Trigger code error → verify bug report link
5. Click manual retry → verify job executes
