# ADR-013: Unified Job Tracking

**Status:** Implemented
**Date:** 2026-02-22
**Updated:** 2026-03-03
**Depends on:** ADR-012 (Summaries UI Consolidation)

## 1. Context

Currently, summary generation jobs have inconsistent visibility:

| Job Type | Where Visible | Status Tracking |
|----------|---------------|-----------------|
| Manual (Generate button) | Spinner only, no history | In-memory `_generation_tasks` dict |
| Scheduled | Nowhere visible in UI | Task scheduler internal state |
| Retrospective | Retrospective Jobs tab | Full job tracking with progress |

**Problems:**
1. Manual generation shows a spinner but if it fails, no persistent record exists
2. Scheduled jobs run silently - users can't see if they succeeded/failed
3. Retrospective has full job tracking but it's buried in a separate tab
4. No way to "rescue" a stuck job or see what went wrong
5. Database locked errors or other failures are invisible to users

## 2. Decision

### Create a unified Job Tracking system visible from the main Summaries page.

**Key Changes:**

1. **Jobs Tab in Summaries Page**
   - Move from Retrospective-only to main Summaries page
   - Show ALL job types: Manual, Scheduled, Retrospective
   - Persistent job history (not just in-memory)

2. **Persistent Job Storage**
   - New `summary_jobs` table to track all generation jobs
   - Store: job_id, type, status, progress, error, created_at, completed_at
   - Replace in-memory `_generation_tasks` dict

3. **Job Types (Enum)**
   ```python
   class JobType(Enum):
       MANUAL = "manual"       # Generate button
       SCHEDULED = "scheduled" # Scheduled task
       RETROSPECTIVE = "retrospective"  # Archive backfill
   ```

4. **Job Statuses**
   ```python
   class JobStatus(Enum):
       PENDING = "pending"
       RUNNING = "running"
       COMPLETED = "completed"
       FAILED = "failed"
       CANCELLED = "cancelled"
   ```

## 3. UI Changes

### Navigation Placement
> **Note:** See ADR-040 for planned UI rethink moving Jobs to left nav bar.

Current placement (Summaries Page Tabs):
```
[ All Summaries ] [ Jobs ] [ Retrospective Setup ]
```

- **All Summaries**: Unified view of all summaries (ADR-012)
- **Jobs**: All running/recent jobs with status, progress, errors
- **Retrospective Setup**: Configure date ranges for archive generation (moved from current Retrospective Jobs tab)

### Jobs Tab Features:
- Real-time status updates (polling or SSE)
- Filter by: type (manual/scheduled/retrospective), status
- Show errors clearly with "Retry" action
- Cancel running jobs
- Job history (last 50 jobs)

### Job Card Display:
```
┌─────────────────────────────────────────────────────┐
│ [Manual] #general Summary                           │
│ Started: 2 minutes ago                              │
│ Status: ████████░░ 80% - Generating summary...      │
│                                          [Cancel]   │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ [Scheduled] Daily Digest                            │
│ Completed: 5 minutes ago                            │
│ Status: ✓ Completed - 1 summary generated           │
│                                   [View Summary]    │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ [Manual] Server-wide Summary                        │
│ Failed: 10 minutes ago                              │
│ Status: ✗ Failed - Database locked                  │
│                                          [Retry]    │
└─────────────────────────────────────────────────────┘
```

### Regeneration Jobs - Parameter Change Tracking

When a summary is regenerated (via Retry or manual re-run), jobs should track which parameters changed:

```
┌─────────────────────────────────────────────────────┐
│ [Regeneration] #general Summary                     │
│ Regenerating from: summary-abc123                   │
│ Started: 1 minute ago                               │
│ Status: ████░░░░░░ 40% - Fetching messages...       │
│                                                     │
│ Parameter Changes:                                  │
│   perspective: general → security                   │
│   summary_length: brief → detailed                  │
│   prompt_template: (none) → "Security Review v2"    │
│                                          [Cancel]   │
└─────────────────────────────────────────────────────┘
```

#### Regeneration Metadata

Jobs for regeneration should include:

```python
class RegenerationMetadata(TypedDict):
    original_summary_id: str
    parameter_changes: list[ParameterChange]
    reason: str  # "retry_failed", "parameter_update", "manual_regen"

class ParameterChange(TypedDict):
    field: str       # "perspective", "summary_length", "prompt_template_id"
    old_value: Any
    new_value: Any
```

#### API Extension

```python
@router.post("/guilds/{guild_id}/summaries/{summary_id}/regenerate")
async def regenerate_summary(
    guild_id: str,
    summary_id: str,
    body: RegenerationRequest,
    user: dict = Depends(get_current_user)
) -> JobResponse:
    """
    Regenerate a summary with optionally modified parameters.
    Tracks old vs new parameter values in the job record.
    """
    pass

class RegenerationRequest(BaseModel):
    # Optional overrides - if not provided, uses original values
    perspective: Optional[str] = None
    summary_length: Optional[str] = None
    prompt_template_id: Optional[str] = None
    reason: str = "manual_regen"
```

## 4. Database Schema

```sql
CREATE TABLE summary_jobs (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    job_type TEXT NOT NULL,  -- 'manual', 'scheduled', 'retrospective'
    status TEXT NOT NULL DEFAULT 'pending',

    -- Job configuration
    scope TEXT,  -- 'channel', 'category', 'guild'
    channel_ids TEXT,  -- JSON array
    category_id TEXT,
    schedule_id TEXT,  -- For scheduled jobs

    -- Time range
    start_time TIMESTAMP,
    end_time TIMESTAMP,

    -- Progress tracking
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0,
    progress_message TEXT,

    -- Results
    summary_id TEXT,  -- Link to generated summary
    error TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Metadata
    created_by TEXT,  -- User ID who initiated
    metadata TEXT,  -- JSON for additional data

    FOREIGN KEY (guild_id) REFERENCES guilds(id),
    FOREIGN KEY (schedule_id) REFERENCES schedules(id)
);

CREATE INDEX idx_summary_jobs_guild ON summary_jobs(guild_id);
CREATE INDEX idx_summary_jobs_status ON summary_jobs(status);
CREATE INDEX idx_summary_jobs_created ON summary_jobs(created_at DESC);
```

## 5. API Endpoints

```
GET  /guilds/{guild_id}/jobs                    # List jobs (paginated, filterable)
GET  /guilds/{guild_id}/jobs/{job_id}           # Get job details
POST /guilds/{guild_id}/jobs/{job_id}/cancel    # Cancel running job
POST /guilds/{guild_id}/jobs/{job_id}/retry     # Retry failed job
```

## 6. Implementation Plan

### Phase 1: Database & Models
- [ ] Create `summary_jobs` table migration
- [ ] Create `SummaryJob` model
- [ ] Create `SummaryJobRepository`

### Phase 2: Backend Integration
- [ ] Update Generate endpoint to create job record
- [ ] Update scheduled task runner to create job records
- [ ] Update retrospective generator to use same job tracking
- [ ] Add job list/detail/cancel/retry endpoints

### Phase 3: Frontend
- [ ] Add Jobs tab to Summaries page
- [ ] Create JobCard component
- [ ] Add real-time status updates
- [ ] Add retry/cancel actions
- [ ] Update Retrospective page to link to Jobs tab

### Phase 4: Error Visibility
- [ ] Ensure all errors are captured in job record
- [ ] Add clear error messages for common issues (DB locked, rate limits, etc.)
- [ ] Add toast notifications for job completion/failure

## 7. Benefits

1. **Visibility**: Users can see all running and recent jobs in one place
2. **Debugging**: Failed jobs show clear error messages
3. **Recovery**: Retry button for failed jobs
4. **Consistency**: Same job tracking for all generation types
5. **History**: Persistent record of what ran and when

## 8. Migration Path

1. Keep existing in-memory tracking as fallback during transition
2. Gradually migrate all job types to new system
3. Remove legacy tracking once stable

## 9. Implementation Status

### Completed
- [x] Database schema (`015_summary_jobs.sql`)
- [x] `SummaryJob` model with all fields
- [x] `SummaryJobRepository` abstract interface
- [x] `SQLiteSummaryJobRepository` implementation
- [x] Retrospective jobs persist to database via `_persist_job()`
- [x] **Startup recovery**: Jobs with status RUNNING are marked PAUSED with reason "server_restart" on startup
- [x] **Manual generation creates job records** (`src/dashboard/routes/summaries.py`)
- [x] **Scheduled jobs create job records** (`src/scheduling/scheduler.py`)
- [x] **Jobs API endpoints** - list, get, cancel, retry (`/guilds/{guild_id}/jobs/*`)
- [x] **Jobs tab in frontend Summaries page** (`src/frontend/src/components/summaries/JobsTab.tsx`)
- [x] **Real-time status updates** (polling every 3s for active jobs)
- [x] **Cancel/retry actions in UI**

### Pending
- [ ] Job history cleanup cron (low priority)

### Key Files
- `src/models/summary_job.py` - Job model
- `src/data/base.py` - `SummaryJobRepository` interface
- `src/data/sqlite.py` - SQLite implementation
- `src/data/migrations/015_summary_jobs.sql` - Database schema
- `src/archive/generator.py` - Retrospective job persistence
- `src/main.py` - Startup recovery via `_recover_interrupted_jobs()`
- `src/dashboard/routes/summaries.py` - Manual job tracking + Jobs API endpoints
- `src/scheduling/scheduler.py` - Scheduled job tracking
- `src/frontend/src/components/summaries/JobsTab.tsx` - Jobs tab UI component
- `src/frontend/src/pages/Summaries.tsx` - Integrated Jobs tab
