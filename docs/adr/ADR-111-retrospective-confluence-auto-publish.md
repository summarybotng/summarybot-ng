# ADR-111: Retrospective Summary Auto-Publish to Confluence

## Status
Proposed

## Date
2026-05-29

## Context

ADR-099 introduced Confluence publishing for individual summaries, and ADR-110 added bulk publish/unpublish capabilities. However, retrospective summary generation (Archive page) currently has no option to automatically publish summaries to Confluence as they are generated.

Users generating historical summaries often want them published to Confluence immediately, creating a knowledge base of past conversations. Currently, this requires:
1. Generate retrospective summaries (potentially 100+ across many dates)
2. Navigate to Summaries page
3. Select all generated summaries
4. Use bulk publish action

This is cumbersome and disconnects the generation workflow from the publishing outcome.

### Requirements

1. **Unified Publishing**: Reuse `ConfluencePublisher.publish_summary()` - same code path as manual and bulk publish
2. **Rate Limiting**: Respect Confluence API limits with throttling (2s between publishes, per ADR-110)
3. **Non-Blocking Failures**: Publishing errors should not fail the generation job - summaries are still saved
4. **Progress Tracking**: Track publish counts and errors in job response
5. **Graceful Degradation**: If Confluence is not configured, skip publishing silently

## Decision

### 1. API Changes

#### GenerateRequest Model Enhancement

Add `auto_publish_confluence` option to `src/dashboard/routes/archive.py:GenerateRequest`:

```python
class GenerateRequest(BaseModel):
    # ... existing fields ...

    # ADR-111: Auto-publish to Confluence
    auto_publish_confluence: bool = False
```

#### Job Response Enhancement

Add tracking fields to job status response:

```python
class JobResponse(BaseModel):
    # ... existing fields ...

    # ADR-111: Confluence auto-publish tracking
    confluence_published: int = 0
    confluence_errors: Dict[str, str] = {}  # summary_id → error message
```

### 2. Backend Implementation

#### GenerationJob Dataclass

Add tracking fields to `src/archive/generator.py:GenerationJob`:

```python
@dataclass
class GenerationJob:
    # ... existing fields ...

    # ADR-111: Auto-publish to Confluence
    auto_publish_confluence: bool = False
    confluence_published: int = 0
    confluence_errors: Dict[str, str] = field(default_factory=dict)
```

#### Auto-Publish Method

New method in `src/archive/generator.py`:

```python
async def _auto_publish_to_confluence(
    self,
    job: GenerationJob,
    stored: StoredSummary,
    summary_id: str,
) -> bool:
    """
    ADR-111: Auto-publish summary to Confluence if enabled and configured.

    Non-blocking: errors are logged and tracked but don't fail the job.
    Uses same publish logic as manual/bulk publish (ADR-099/110).
    """
    from src.services.confluence import get_confluence_service
    from src.data.sqlite.confluence_repository import ConfluencePublication
    from src.data.repositories import get_confluence_repository
    import secrets

    guild_id = stored.guild_id

    # Check if Confluence is configured for this guild
    confluence_service = await get_confluence_service(guild_id)
    if not confluence_service or not confluence_service.is_configured():
        logger.debug(f"Confluence not configured for guild {guild_id}, skipping auto-publish")
        return False

    try:
        # Extract channel names from stored summary for labels
        channel_names = None
        if stored.summary_result and hasattr(stored.summary_result, 'metadata'):
            channel_names = stored.summary_result.metadata.get('channel_names')

        # Publish using same method as manual/bulk publish
        result = await confluence_service.publish_summary(
            summary=stored.summary_result,
            title=stored.title or f"Summary {summary_id[:8]}",
            summary_id=summary_id,
            guild_id=guild_id,
            channel_names=channel_names,
            scope_type=stored.scope_type,
            category_name=stored.category_name,
        )

        if result.success:
            # Save publication record (same as manual publish)
            confluence_repo = await get_confluence_repository()
            if confluence_repo:
                publication = ConfluencePublication(
                    id=f"cfp_{secrets.token_urlsafe(16)}",
                    summary_id=summary_id,
                    guild_id=guild_id,
                    page_id=result.page_id or "",
                    page_url=result.page_url or "",
                    page_version=result.page_version or 1,
                    published_by="auto_retrospective",
                )
                await confluence_repo.save(publication)

            job.confluence_published += 1
            logger.info(f"[{job.job_id}] Auto-published {summary_id} to Confluence: {result.page_url}")
            return True
        else:
            job.confluence_errors[summary_id] = result.error or "Unknown error"
            logger.warning(f"[{job.job_id}] Failed to auto-publish {summary_id}: {result.error}")
            return False

    except Exception as e:
        job.confluence_errors[summary_id] = str(e)
        logger.exception(f"[{job.job_id}] Error auto-publishing {summary_id} to Confluence: {e}")
        return False
```

#### Integration Point

Call auto-publish in `_save_to_database()` after saving `StoredSummary`:

```python
async def _save_to_database(self, job, period, summary_result, ...):
    # ... existing code to create and save StoredSummary ...

    await self.stored_summary_repository.save(stored)
    logger.debug(f"Saved archive summary to database: {summary_id}")

    # ADR-111: Auto-publish to Confluence if enabled
    if job.auto_publish_confluence:
        await self._auto_publish_to_confluence(job, stored, summary_id)
        # Throttle between publishes (ADR-110: 2s default)
        await asyncio.sleep(2.0)
```

### 3. Frontend Changes

#### TypeScript Types

Update `src/frontend/src/hooks/useArchive.ts`:

```typescript
interface GenerateRequest {
  // ... existing fields ...
  auto_publish_confluence?: boolean;
}

interface JobResponse {
  // ... existing fields ...
  confluence_published?: number;
  confluence_errors?: Record<string, string>;
}
```

#### UI Component

Add checkbox to `src/frontend/src/pages/Archive.tsx` generation dialog:

```tsx
{confluenceConfigured && (
  <FormControlLabel
    control={
      <Checkbox
        checked={formData.auto_publish_confluence ?? false}
        onChange={(e) => setFormData({
          ...formData,
          auto_publish_confluence: e.target.checked,
        })}
      />
    }
    label="Auto-publish to Confluence"
  />
)}
```

If Confluence is not configured, either hide the checkbox or show it disabled with a tooltip:
```tsx
{!confluenceConfigured && (
  <Tooltip title="Configure Confluence in Settings to enable auto-publish">
    <FormControlLabel
      disabled
      control={<Checkbox />}
      label="Auto-publish to Confluence"
    />
  </Tooltip>
)}
```

### 4. Job Status Display

Update job progress UI to show Confluence publish stats:

```tsx
{job.confluence_published > 0 && (
  <Typography variant="body2" color="success.main">
    ✓ {job.confluence_published} published to Confluence
  </Typography>
)}
{Object.keys(job.confluence_errors || {}).length > 0 && (
  <Typography variant="body2" color="error">
    ⚠ {Object.keys(job.confluence_errors).length} Confluence publish errors
  </Typography>
)}
```

## Files to Modify

| File | Change |
|------|--------|
| `src/dashboard/routes/archive.py` | Add `auto_publish_confluence` to `GenerateRequest`, update `JobResponse` |
| `src/archive/generator.py` | Add fields to `GenerationJob`, add `_auto_publish_to_confluence()`, call in `_save_to_database()` |
| `src/frontend/src/hooks/useArchive.ts` | Update TypeScript types |
| `src/frontend/src/pages/Archive.tsx` | Add checkbox to generation dialog |

## Key Files Reference

| Purpose | File Path | Line |
|---------|-----------|------|
| Request model | `src/dashboard/routes/archive.py` | :54 (GenerateRequest) |
| Job dataclass | `src/archive/generator.py` | :92 (GenerationJob) |
| Database save | `src/archive/generator.py` | :859 (_save_to_database) |
| Confluence publish | `src/services/confluence.py` | :158 (publish_summary) |
| Publication model | `src/data/sqlite/confluence_repository.py` | :67 (ConfluencePublication) |
| Frontend page | `src/frontend/src/pages/Archive.tsx` | |
| Frontend hooks | `src/frontend/src/hooks/useArchive.ts` | |

## Reused Components

- `ConfluencePublisher.publish_summary()` - Same method as manual/bulk publish (ADR-099)
- `ConfluencePublication` model - Same tracking record format
- `ConfluenceRepository.save()` - Same persistence logic
- 2-second throttle delay - Same pattern as bulk publish (ADR-110)

## Error Handling

| Scenario | Handling |
|----------|----------|
| Confluence not configured | Skip silently, log debug message |
| Publish API error | Log warning, record in `confluence_errors`, continue |
| Network timeout | Log exception, record error, continue |
| Rate limit hit | Natural throttling via 2s delay should prevent this |

**Critical**: Publishing failures **never** fail the job. Summaries are saved to the database regardless of Confluence publish status.

## Rate Limiting

Per ADR-110, Confluence Cloud has rate limits (~30 requests/minute for standard tier).

The 2-second delay between publishes results in:
- ~30 publishes/minute (within limits)
- 100 summaries ≈ 3.5 minutes of publish time (added to generation time)

For large retrospective jobs (e.g., 365 daily summaries for a year), the total time impact is:
- Generation: ~1-2 hours depending on content
- Publishing: ~12 additional minutes

## Verification Steps

1. **Setup**: Configure Confluence for a guild via Settings → Confluence
2. **Generate with auto-publish**:
   - Go to Archive → Generate Retrospective
   - Check "Auto-publish to Confluence" checkbox
   - Select date range (e.g., last 7 days)
   - Start generation
3. **Verify results**:
   - Summaries appear in Summaries list
   - Confluence pages created (check Confluence)
   - Job status shows `confluence_published` count
   - Publication badge shows on summary cards
4. **Test idempotency**:
   - Re-run same date range with `skip_existing=true`
   - Existing summaries should be skipped
   - No duplicate Confluence pages created
5. **Test error handling**:
   - Temporarily break Confluence connection
   - Run generation with auto-publish
   - Verify summaries are still saved
   - Verify errors appear in `confluence_errors`
6. **Test without Confluence**:
   - For guild without Confluence configured
   - Checkbox should be disabled/hidden
   - If enabled via API, should skip gracefully

## Implementation Order

1. Update `GenerateRequest` model in archive.py (add `auto_publish_confluence` field)
2. Update `GenerationJob` dataclass in generator.py (add tracking fields)
3. Update `create_job()` to copy the flag from request to job
4. Add `_auto_publish_to_confluence()` method in generator.py
5. Call new method in `_save_to_database()` after saving StoredSummary
6. Update job `to_dict()` method to include publish stats
7. Update frontend types in useArchive.ts
8. Add checkbox to Archive.tsx generation dialog
9. Test end-to-end

## Consequences

### Positive

- Streamlined workflow: generate-and-publish in one action
- Knowledge base creation: historical conversations immediately available in Confluence
- Consistent experience: uses same publish logic as manual/bulk
- Resilient: publishing failures don't block summary generation

### Negative

- Longer job runtime: 2s per summary for Confluence publish
- Additional API calls: could hit rate limits on very large jobs
- Storage overhead: publication records for all auto-published summaries

### Trade-offs

- **2-second throttle vs. faster completion**: Prioritized API stability over speed
- **Silent skip vs. error on unconfigured**: Prioritized graceful degradation

## Future Improvements

1. **Configurable throttle**: Allow users to adjust delay (500ms - 10s range)
2. **Batch publish**: Group pages into batches for efficiency
3. **Parallel publish**: Publish while generating next summary (careful with rate limits)
4. **Publish retry**: Automatic retry for transient failures
5. **Auto-publish rules**: Trigger based on date patterns, content keywords, etc.

## References

- [ADR-099](./ADR-099-remote-platform-publishing.md): Remote Platform Publishing (Confluence MVP)
- [ADR-100](./ADR-100-confluence-content-enrichment.md): Confluence Content Enrichment
- [ADR-110](./ADR-110-bulk-confluence-publish-unpublish.md): Bulk Confluence Publish/Unpublish
- [ADR-006](./006-retrospective-summary-archive.md): Retrospective Summary Archive
