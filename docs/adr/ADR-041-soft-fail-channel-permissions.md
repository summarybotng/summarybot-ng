# ADR-041: Soft-Fail Channel Permission Handling

## Status
Partially Implemented

## Context

When scheduled summaries run with `scope: guild` or `scope: category`, the bot attempts to fetch messages from all channels in scope. However, the bot may lack "Read Message History" permission in some channels (e.g., admin-only, private staff channels).

**Current behavior:**
- Bot gets 403 "Missing Access" error for each restricted channel
- Error is logged to `error_logs` table
- Summary generation continues with accessible channels
- No indication in the summary itself that channels were skipped
- Admins see errors in the Errors page but can't easily correlate them to summaries

**Problems:**
1. Admins don't know which summaries are incomplete due to permission issues
2. No way to filter for "summaries with access issues" in the UI
3. Error logs pile up with repetitive permission errors
4. Schedules may get disabled due to failure count even though partial success occurred

## Decision

Implement a **soft-fail** approach for channel permission errors:

### 1. Continue on Permission Errors

When a 403 error occurs for a channel:
- Log a warning (not error)
- Skip the channel and continue with remaining channels
- Do NOT increment schedule failure count for permission errors
- Mark the summary as having partial access

### 2. Track Skipped Channels in Summary Metadata

```python
# In summary metadata
{
    "channels_requested": 55,
    "channels_accessible": 43,
    "channels_skipped": 12,
    "skipped_channels": [
        {
            "channel_id": "123456789",
            "channel_name": "🛠️admins",
            "reason": "missing_access",
            "error_code": 50001
        },
        # ...
    ],
    "has_access_issues": True,  # Filterable flag
    "access_coverage_percent": 78.2  # 43/55 * 100
}
```

### 3. Add Filterable Attribute

```python
# New filter for stored summaries
class AccessFilter(BaseModel):
    has_access_issues: Optional[bool] = None  # True = only partial access
    min_coverage_percent: Optional[float] = None  # e.g., 80.0

# API endpoint extension
@router.get("/guilds/{guild_id}/stored-summaries")
async def list_summaries(
    # ... existing params ...
    has_access_issues: Optional[bool] = Query(None),
    min_coverage_percent: Optional[float] = Query(None),
):
    pass
```

### 4. UI Indicators

#### Summary Card Badge
```tsx
{summary.metadata.has_access_issues && (
  <Badge variant="outline" className="bg-amber-500/10 text-amber-600">
    <AlertTriangle className="mr-1 h-3 w-3" />
    Partial Access ({summary.metadata.access_coverage_percent}%)
  </Badge>
)}
```

#### Summary Detail Panel
```tsx
<Collapsible>
  <CollapsibleTrigger>
    <AlertTriangle className="h-4 w-4 text-amber-500" />
    {skippedChannels.length} channels skipped due to missing permissions
  </CollapsibleTrigger>
  <CollapsibleContent>
    <ul>
      {skippedChannels.map(ch => (
        <li key={ch.channel_id}>
          #{ch.channel_name} - {ch.reason}
        </li>
      ))}
    </ul>
    <p className="text-sm text-muted-foreground mt-2">
      Grant the bot "Read Message History" permission in these channels,
      or exclude them from the schedule.
    </p>
  </CollapsibleContent>
</Collapsible>
```

#### Filter Option
```tsx
<FilterGroup label="Access Status">
  <FilterOption value="full">Full access</FilterOption>
  <FilterOption value="partial">Partial access (has skipped channels)</FilterOption>
</FilterGroup>
```

### 5. Schedule Behavior Changes

```python
class ScheduleExecutor:
    async def run_scheduled_summary(self, task: ScheduledTask):
        result = await self._generate_summary(task)

        # Don't count permission errors as failures
        if result.has_access_issues and result.accessible_channels > 0:
            # Partial success - don't increment failure count
            task.last_run = utc_now()
            # Log warning instead of error
            logger.warning(
                f"Schedule {task.id} completed with partial access: "
                f"{result.accessible_channels}/{result.total_channels} channels"
            )
        elif result.accessible_channels == 0:
            # Complete failure - no channels accessible
            task.failure_count += 1
            logger.error(f"Schedule {task.id} failed: no accessible channels")
```

### 6. Error Log Deduplication

For repetitive permission errors, consolidate into a single error per job:

```python
# Instead of 12 separate error logs for 12 inaccessible channels:
{
    "error_type": "channel_permissions_summary",
    "message": "12 channels skipped due to missing permissions",
    "details": {
        "job_id": "job_xyz",
        "schedule_id": "schedule_abc",
        "skipped_channels": [...],
        "recommendation": "Grant bot 'Read Message History' permission or exclude channels"
    }
}
```

### 7. Admin Notification

When a schedule first encounters permission issues (not on every run):

```python
async def notify_permission_issues(schedule: ScheduledTask, skipped: list):
    # Only notify once per unique set of skipped channels
    cache_key = f"perm_notify:{schedule.id}:{hash(tuple(sorted(c['id'] for c in skipped)))}"
    if await cache.exists(cache_key):
        return

    await cache.set(cache_key, "1", ttl=86400 * 7)  # 7 days

    # Create a single consolidated error for the admin
    await error_repo.create(ErrorLog(
        error_type="schedule_permission_warning",
        severity="warning",
        message=f"Schedule '{schedule.name}' cannot access {len(skipped)} channels",
        details={
            "schedule_id": schedule.id,
            "skipped_channels": skipped,
            "action_required": "Grant permissions or update schedule exclusions"
        }
    ))
```

## Implementation Phases

### Phase 1: Backend - Soft Fail Logic
- [x] Catch 403 errors in message fetching
- [x] Continue with accessible channels instead of failing
- [x] Track skipped channels in generation context
- [x] Don't increment failure count for permission-only issues

### Phase 2: Metadata Enhancement
- [x] Add `has_access_issues`, `channels_skipped`, `skipped_channels` to summary metadata
- [x] Add `access_coverage_percent` calculation
- [x] Store skipped channel details (id, name, reason)

### Phase 3: API & Filtering
- [x] Add `has_access_issues` filter to stored summaries endpoint
- [ ] Add `min_coverage_percent` filter (deferred - low priority)
- [x] Update search/filter models

### Phase 4: UI Indicators
- [x] Add "Partial Access" badge to summary cards
- [ ] Add skipped channels section to summary detail (future enhancement)
- [x] Add access status filter to summary list

### Phase 5: Error Consolidation
- [ ] Consolidate multiple permission errors into single log entry
- [ ] Add `schedule_permission_warning` error type
- [ ] Implement notification deduplication

## Consequences

### Positive
- Schedules don't fail due to partial permission issues
- Admins can easily find summaries with access problems
- Clear visibility into which channels need permission fixes
- Reduced error log noise
- Better user experience for partial-success scenarios

### Negative
- Summaries may be incomplete without obvious indication (mitigated by badges)
- Additional metadata storage per summary
- Need to handle edge case of 0% accessible channels

### Neutral
- Existing summaries won't have the new metadata (only affects new summaries)
- Admins need to learn about the new filter option

## Database Changes

```sql
-- No schema changes required - metadata is stored as JSON
-- But add index for filtering if performance becomes an issue:
CREATE INDEX idx_stored_summaries_access_issues
ON stored_summaries(
    json_extract(summary_json, '$.metadata.has_access_issues')
);
```

## Related ADRs
- ADR-013: Unified Job Tracking
- ADR-038: Self-Healing Parameter Validation
- ADR-039: User Problem Reporting

## Notes

Current error pattern observed in production:
```
Type: discord_permission
Message: 403 Forbidden (error code: 50001): Missing Access
Details: {"job_id": "job_xxx", "channel_name": "🛠️admins"}
```

This occurs for 12+ channels per scheduled run, creating repetitive errors that obscure real issues.
