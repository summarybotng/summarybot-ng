# ADR-019: Database-Primary Archive Storage

## Status
Accepted (Implemented 2026-02-24)

## Context

Archive summaries are currently stored in **two locations**:

1. **Disk files** (`archive/discord/{server_id}/{date}.json`) - Used by the archive generator and Google Drive sync
2. **Database** (`stored_summaries` table) - Used by the dashboard for listing, filtering, and management

This dual-storage architecture has created problems:

### The Bug

When attempting to regenerate summaries for Feb 1-2, 2026:

1. User deleted summaries from dashboard (removed DB entries)
2. Triggered regeneration via archive API
3. Generator checked `summary_exists()` which looks at **disk files**
4. Disk files still existed → summaries skipped
5. Result: "skipped: 2, completed: 0" - no regeneration occurred

### Root Cause

```
Dashboard                    Archive Generator
    │                              │
    ▼                              ▼
 Database  ◄──── NO SYNC ────►  Disk Files
(authoritative                 (authoritative
 for dashboard)                 for generator)
```

Two sources of truth that can diverge, with no synchronization mechanism.

### Current Data Flow

```
Generate Archive Summary
         │
         ├──► Write to disk file (for sync)
         │
         └──► Save to stored_summaries DB (for dashboard)

Skip Check: summary_exists() checks DISK
Delete: Dashboard deletes from DB only
Result: Disk file remains → regeneration blocked
```

## Decision

Make the **database** (`stored_summaries`) the single authoritative source. Disk files become **exports** generated from the database for Google Drive sync.

### New Data Flow

```
Generate Archive Summary
         │
         ▼
    Save to Database (authoritative)
         │
         ▼
    Export to Disk (for Google Drive sync)

Skip Check: Check DATABASE for existing entry
Delete: Remove from DB AND delete disk file
Regenerate: DB entry missing → generates → saves to both
```

### Key Changes

#### 1. `summary_exists()` Checks Database

**Before:**
```python
def summary_exists(archive_root: Path, source: ArchiveSource, target_date: date) -> bool:
    """Check if summary file exists on disk."""
    summary_path = source.get_archive_path(archive_root) / f"{target_date}.json"
    return summary_path.exists()
```

**After:**
```python
async def summary_exists(source: ArchiveSource, target_date: date) -> bool:
    """Check if summary exists in database."""
    repo = await get_stored_summary_repository()
    source_key = f"{source.source_type.value}:{source.server_id}"
    existing = await repo.find_by_archive_period(
        guild_id=source.server_id,
        archive_period=target_date.isoformat(),
    )
    return len(existing) > 0
```

#### 2. Delete Removes Both DB and Disk

**Before:**
```python
async def delete_stored_summary(summary_id: str):
    await stored_repo.delete(summary_id)
```

**After:**
```python
async def delete_stored_summary(summary_id: str):
    stored = await stored_repo.get(summary_id)

    # Delete from database (authoritative)
    await stored_repo.delete(summary_id)

    # Also delete disk file if it exists (for sync cleanup)
    if stored and stored.archive_source_key:
        disk_path = get_archive_path_for_summary(stored)
        if disk_path.exists():
            disk_path.unlink()
```

#### 3. Export to Disk After DB Save

The archive generator already writes to disk. This continues to work but disk files are now considered exports, not the source of truth.

```python
async def _save_summary(self, job: GenerationJob, result: SummaryResult, period_date: date):
    # 1. Save to database FIRST (authoritative)
    stored_summary = StoredSummary(
        id=result.id,
        guild_id=job.source.server_id,
        summary_result=result,
        source=SummarySource.ARCHIVE,
        archive_period=period_date.isoformat(),
        ...
    )
    await stored_repo.save(stored_summary)

    # 2. Export to disk for Google Drive sync
    self._write_to_disk(job, result, period_date)
```

#### 4. Force Regenerate Option

Add explicit force flag that bypasses all skip checks:

```python
class GenerateRequest(BaseModel):
    # ... existing fields ...
    force_regenerate: bool = False  # Delete existing and regenerate
```

```python
async def _generate_period(self, job: GenerationJob, period_start: date):
    if job.force_regenerate:
        # Delete existing from DB and disk
        await self._delete_existing(job.source, period_start)
    elif job.skip_existing and await summary_exists_in_db(job.source, period_start):
        return "skipped"

    # Continue with generation...
```

## Implementation Plan

### Phase 1: Core Changes
1. Create `summary_exists_in_db()` function
2. Update generator to use DB check instead of disk check
3. Update delete endpoint to also remove disk files
4. Add `force_regenerate` option to generate request

### Phase 2: Sync Integrity
1. Add startup check: warn if disk files exist without DB entries
2. Add repair command: sync disk → DB for orphaned files
3. Add cleanup command: remove disk files without DB entries

### Phase 3: Google Drive Sync
1. Verify sync still works with new flow
2. Ensure disk exports happen after successful DB save
3. Add sync status to generation job response

## Database Changes

No schema changes required. The `stored_summaries` table already has:
- `archive_period` - Date of the archive summary
- `archive_source_key` - Source identifier for matching

Add index for efficient lookups:
```sql
CREATE INDEX IF NOT EXISTS idx_stored_summaries_archive_lookup
ON stored_summaries(guild_id, archive_period)
WHERE source = 'archive';
```

## Consequences

### Positive
- **Single source of truth** - Database is authoritative
- **Delete works correctly** - Removes from both locations
- **Regeneration works** - DB check respects deletions
- **Simpler mental model** - One place to look for data
- **Google Drive sync preserved** - Files still exported

### Negative
- **Async operation** - DB check is async (minor performance impact)
- **Migration needed** - Existing deployments need sync verification
- **Disk cleanup** - Orphaned files may need manual cleanup

### Mitigations
- Add caching for `summary_exists_in_db()` during batch operations
- Provide migration script for existing deployments
- Add admin endpoint for disk file cleanup

## Alternatives Considered

### A: Disk-Only Storage
- Remove database storage entirely
- Dashboard reads from disk files
- **Rejected:** Too slow for queries, no indexing, poor dashboard UX

### B: Database-Only Storage
- Remove disk files entirely
- **Rejected:** Breaks Google Drive sync requirement

### C: Bidirectional Sync
- Keep both, sync changes between them
- **Rejected:** Complex, error-prone, unnecessary

## Related ADRs

- ADR-006: Retrospective Summary Archive (original archive design)
- ADR-007: Per-Server Google Drive Sync
- ADR-008: Unified Summary Experience
- ADR-016: Summary Regeneration Data Integrity

## Appendix: Affected Code Paths

| Component | File | Change Required |
|-----------|------|-----------------|
| Existence check | `src/archive/writer.py` | New `summary_exists_in_db()` |
| Generator | `src/archive/generator.py` | Use DB check, add force flag |
| Delete endpoint | `src/dashboard/routes/summaries.py` | Delete disk file too |
| Generate request | `src/dashboard/routes/archive.py` | Add `force_regenerate` param |
| Backfill report | `src/dashboard/routes/archive.py` | Use DB for completeness check |
