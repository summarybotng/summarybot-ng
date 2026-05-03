# ADR-084: Bulk Wiki Regeneration

## Status
Accepted

## Context

When summaries are ingested into the wiki system, they update individual wiki pages (daily pages, topic pages, etc.). However, the wiki synthesis (which creates comprehensive overview pages, timelines, and cross-references) only runs on a scheduled basis or when manually triggered for a single summary.

Users need the ability to:
1. **Auto-regenerate after bulk ingest**: When multiple summaries are ingested (e.g., from retrospective generation), trigger wiki synthesis automatically
2. **Bulk regenerate on demand**: Select multiple summaries and regenerate wiki pages for all of them
3. **Full wiki rebuild**: Regenerate the entire wiki from all ingested summaries

## Decision

### 1. Auto-Regeneration After Bulk Ingest

Add a "regenerate wiki" trigger after ingesting multiple summaries:

```python
# In wiki ingest flow
async def ingest_summaries(summaries: List[Summary], guild_id: str):
    ingested_count = 0
    for summary in summaries:
        await ingest_summary_to_wiki(summary)
        ingested_count += 1

    # Trigger regeneration if multiple summaries ingested
    if ingested_count >= BULK_INGEST_THRESHOLD:
        await queue_wiki_regeneration(guild_id, scope="affected", summary_ids=[s.id for s in summaries])
```

**Threshold**: Regeneration triggers after ingesting 3+ summaries in a batch.

### 2. Bulk Regenerate API

New endpoint for bulk regeneration:

```
POST /guilds/{guild_id}/wiki/regenerate
{
  "scope": "selected" | "date_range" | "full",
  "summary_ids": ["sum_123", "sum_456"],  // for scope="selected"
  "start_date": "2024-01-01",             // for scope="date_range"
  "end_date": "2024-01-31",
  "force": false                          // skip unchanged check
}
```

**Response**:
```json
{
  "task_id": "task_abc123",
  "summaries_queued": 15,
  "estimated_duration_seconds": 45
}
```

### 3. Database Schema

Add regeneration tracking:

```sql
-- Track wiki regeneration jobs
CREATE TABLE wiki_regeneration_jobs (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    scope TEXT NOT NULL,  -- 'selected', 'date_range', 'full'
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
    summary_count INTEGER NOT NULL,
    processed_count INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);
```

### 4. Frontend Integration

Add to Wiki settings page:
- "Regenerate Wiki" button with scope selection
- Progress indicator for regeneration jobs
- Summary selection for targeted regeneration

Add to Summaries page:
- Bulk action: "Regenerate Wiki" for selected summaries
- Shows regeneration status in summary list

### 5. Processing Strategy

**Incremental Regeneration** (default):
- Only regenerate pages affected by the selected summaries
- Track which pages were updated from which summaries
- Skip pages that haven't changed

**Full Regeneration** (force=true):
- Rebuild all wiki pages from scratch
- Clear existing synthesis cache
- Useful after schema changes or corruption

## Implementation Files

| File | Changes |
|------|---------|
| `src/data/migrations/084_wiki_regeneration.sql` | Add regeneration_jobs table |
| `src/wiki/regeneration.py` | Core regeneration logic |
| `src/dashboard/routes/wiki.py` | Add regeneration endpoint |
| `src/scheduling/delivery/dashboard.py` | Auto-trigger after bulk ingest |
| `src/frontend/src/pages/Wiki.tsx` | Regeneration UI |

## Consequences

### Positive
- Wiki stays up-to-date after bulk operations
- Users can fix wiki inconsistencies without manual intervention
- Supports both targeted and full regeneration
- Async processing prevents UI blocking

### Negative
- Regeneration consumes API credits (LLM calls for synthesis)
- Full regeneration can be slow for large wikis
- Need to handle concurrent regeneration requests

## Rate Limiting

- Max 1 regeneration job per guild at a time
- Full regeneration limited to once per hour
- Incremental regeneration limited to once per 5 minutes

## Related ADRs
- ADR-063: Wiki Synthesis System
- ADR-080: Wiki Perspective Filtering
