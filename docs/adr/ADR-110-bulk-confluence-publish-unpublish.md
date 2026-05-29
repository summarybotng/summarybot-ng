# ADR-110: Bulk Confluence Publish/Unpublish

## Status
IMPLEMENTED (2026-05-29)

## Context

Users with many summaries need the ability to publish or unpublish them to Confluence in bulk, rather than one at a time. This is particularly important for:

1. **Initial migration**: Publishing historical summaries to Confluence
2. **Cleanup**: Removing outdated summaries from Confluence
3. **Bulk updates**: Re-publishing summaries after template or format changes

### Constraints

1. **Confluence API Rate Limits**: Confluence Cloud has rate limits (typically ~30 requests/minute for standard tier)
2. **Long-running operations**: Bulk operations on hundreds of summaries can take several minutes
3. **Partial failures**: Some summaries may fail while others succeed
4. **Version conflicts**: Pages may have been modified externally since last publish

## Decision

### Architecture

Implement bulk Confluence publish/unpublish as **background jobs** with:
- Configurable throttling between requests (default 2000ms)
- Task ID for progress polling
- Support for both explicit ID lists and filter-based selection
- Detailed error tracking per summary

### API Design

#### Bulk Publish Endpoint

```
POST /guilds/{guild_id}/stored-summaries/bulk-confluence-publish
```

Request:
```json
{
  "summary_ids": ["id1", "id2"],  // OR use filters
  "filters": {
    "source": "scheduled",
    "created_after": "2026-01-01T00:00:00Z"
  },
  "force": false,              // Overwrite external changes
  "timezone": "America/New_York",
  "throttle_ms": 2000          // Delay between requests (500-30000)
}
```

Response:
```json
{
  "task_id": "bulk_cfpub_abc123",
  "queued_count": 50,
  "skipped_count": 5,
  "skipped_ids": ["id3", "id4"],
  "skipped_reasons": {
    "id3": "No content to publish",
    "id4": "Not found or wrong guild"
  }
}
```

#### Bulk Unpublish Endpoint

```
POST /guilds/{guild_id}/stored-summaries/bulk-confluence-unpublish
```

Request:
```json
{
  "summary_ids": ["id1", "id2"],
  "delete_pages": false,       // Actually delete from Confluence
  "throttle_ms": 2000
}
```

#### Task Status Endpoint

```
GET /guilds/{guild_id}/bulk-confluence-task/{task_id}
```

Response:
```json
{
  "task_id": "bulk_cfpub_abc123",
  "status": "processing",      // processing, completed, failed
  "type": "bulk_confluence_publish",
  "completed": 25,
  "total": 50,
  "successful": 24,
  "failed": 1,
  "errors": ["id5: Conflict - page modified externally"],
  "started_at": "2026-05-29T10:00:00Z",
  "completed_at": null
}
```

### Throttling Strategy

```
Default: 2000ms between requests
Minimum: 500ms (prevents API abuse)
Maximum: 30000ms (reasonable upper bound)

For 100 summaries at 2000ms throttle:
- Estimated time: ~3.5 minutes
- Confluence API load: ~28 requests/minute (within limits)
```

### Error Handling

| Error Type | Handling |
|------------|----------|
| Summary not found | Skip, add to skipped_reasons |
| No content | Skip, add to skipped_reasons |
| Not published (unpublish) | Skip, add to skipped_reasons |
| Version conflict | Fail unless force=true |
| API error | Log, increment failed count, continue |
| Network timeout | Log error, continue to next |

### Unpublish Options

1. **Tracking only** (`delete_pages: false`):
   - Remove publication records from database
   - Leave pages in Confluence
   - Use case: Clean up tracking without affecting Confluence

2. **Full delete** (`delete_pages: true`):
   - Delete actual pages from Confluence
   - Remove publication records
   - Use case: Complete cleanup

## Implementation

### Files Created/Modified

| File | Change |
|------|--------|
| `src/dashboard/models.py` | Add BulkConfluencePublish/Unpublish request/response models |
| `src/dashboard/routes/summaries.py` | Add bulk publish/unpublish/status endpoints |
| `src/services/confluence.py` | Add `delete_page()` method |
| `src/frontend/src/hooks/useStoredSummaries.ts` | Add mutation and query hooks |
| `src/frontend/src/components/summaries/BulkActionBar.tsx` | Add Publish/Unpublish buttons and dialogs |
| `src/frontend/src/components/summaries/StoredSummariesTab.tsx` | Pass Confluence config to BulkActionBar |

### Confluence Service Addition

```python
async def delete_page(self, page_id: str) -> ConfluencePublishResult:
    """Delete a page from Confluence.

    Returns success=True if page was deleted or already doesn't exist.
    """
    response = await client.delete(f"/pages/{page_id}")

    if response.status_code == 204:
        return ConfluencePublishResult(success=True)
    elif response.status_code == 404:
        # Already deleted - consider success
        return ConfluencePublishResult(success=True)
    else:
        return ConfluencePublishResult(success=False, error=response.text)
```

### Background Job Pattern

```python
async def run_bulk_publish():
    for idx, summary_id in enumerate(queued_ids):
        try:
            # Publish logic
            result = await confluence_service.publish_summary(...)

            if result.success:
                _generation_tasks[task_id]["successful"] += 1
            else:
                _generation_tasks[task_id]["failed"] += 1
                _generation_tasks[task_id]["errors"].append(f"{summary_id}: {result.error}")

        except Exception as e:
            _generation_tasks[task_id]["errors"].append(f"{summary_id}: {str(e)}")
            _generation_tasks[task_id]["failed"] += 1

        _generation_tasks[task_id]["completed"] = idx + 1

        # Throttle between requests
        if idx < len(queued_ids) - 1:
            await asyncio.sleep(throttle_ms / 1000.0)

    _generation_tasks[task_id]["status"] = "completed"

asyncio.create_task(run_bulk_publish())
```

### Frontend UI

The BulkActionBar shows Publish/Unpublish buttons when:
- Confluence is configured for the guild (`confluenceConfigured` prop)
- At least one summary is selected

Confirmation dialogs include:
- **Publish**: "Force update" checkbox for overwriting external changes
- **Unpublish**: "Delete pages from Confluence" checkbox for full cleanup

## Consequences

### Positive

- Users can efficiently manage large numbers of Confluence publications
- Rate limiting prevents API abuse and failures
- Background jobs don't block the UI
- Progress tracking provides visibility into long operations
- Filter support enables "select all matching" workflows

### Negative

- Background tasks stored in memory (lost on restart)
- No retry logic for failed items (must re-run manually)
- Limited to 500 summaries per bulk operation

### Future Improvements

1. **Persistent job storage**: Store tasks in database for restart resilience
2. **Automatic retry**: Retry failed items with exponential backoff
3. **Batch pagination**: Handle >500 summaries across multiple batches
4. **Webhook notifications**: Notify when bulk job completes
5. **Cancel support**: Allow canceling in-progress jobs

## Test Cases

```python
class TestBulkConfluenceOperations:
    """ADR-110: Bulk Confluence publish/unpublish tests."""

    @pytest.mark.asyncio
    async def test_bulk_publish_queues_summaries(self, client, guild_with_confluence):
        """Bulk publish returns task_id and queued count."""
        response = await client.post(
            f"/guilds/{guild_with_confluence.id}/stored-summaries/bulk-confluence-publish",
            json={"summary_ids": ["sum1", "sum2", "sum3"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"].startswith("bulk_cfpub_")
        assert data["queued_count"] == 3

    @pytest.mark.asyncio
    async def test_bulk_publish_skips_invalid_summaries(self, client, guild):
        """Summaries without content are skipped."""
        response = await client.post(
            f"/guilds/{guild.id}/stored-summaries/bulk-confluence-publish",
            json={"summary_ids": ["nonexistent"]}
        )
        data = response.json()
        assert data["queued_count"] == 0
        assert data["skipped_count"] == 1
        assert "nonexistent" in data["skipped_reasons"]

    @pytest.mark.asyncio
    async def test_bulk_unpublish_removes_records(self, client, published_summaries):
        """Unpublish removes publication records."""
        response = await client.post(
            f"/guilds/{published_summaries[0].guild_id}/stored-summaries/bulk-confluence-unpublish",
            json={"summary_ids": [s.id for s in published_summaries], "delete_pages": False}
        )
        data = response.json()
        assert data["queued_count"] == len(published_summaries)

    @pytest.mark.asyncio
    async def test_task_status_tracks_progress(self, client, guild, task_id):
        """Task status endpoint returns progress."""
        response = await client.get(
            f"/guilds/{guild.id}/bulk-confluence-task/{task_id}"
        )
        data = response.json()
        assert "completed" in data
        assert "total" in data
        assert "status" in data

    @pytest.mark.asyncio
    async def test_throttling_respects_minimum(self, client, guild):
        """Throttle_ms below 500 is rejected."""
        response = await client.post(
            f"/guilds/{guild.id}/stored-summaries/bulk-confluence-publish",
            json={"summary_ids": ["sum1"], "throttle_ms": 100}
        )
        assert response.status_code == 422  # Validation error
```

## References

- [ADR-099](./ADR-099-remote-platform-publishing.md): Remote Platform Publishing (Confluence MVP)
- [ADR-100](./ADR-100-confluence-content-enrichment.md): Confluence Content Enrichment
- [ADR-018](./ADR-018-bulk-operations.md): Bulk Operations (Delete/Regenerate pattern)
