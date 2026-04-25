# ADR-061: Wiki Population Strategies

## Status
Proposed

## Context

ADR-056 defines the Compounding Wiki architecture, but doesn't specify how the wiki gets populated. There are several potential strategies, each with different trade-offs for latency, completeness, and resource usage.

## Decision

Support multiple population strategies, starting with manual backfill and evolving toward real-time ingestion.

---

## Population Strategies

### 1. Manual Backfill (Initial Implementation)

**Description**: Admin triggers a one-time import of historical summaries.

```
┌─────────────────────────────────────────────────────────────────┐
│  Dashboard: Wiki Settings                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Wiki Population                                                 │
│  ──────────────────────────────────────────────────────────────  │
│                                                                  │
│  Current Status: 0 pages, 0 sources                             │
│                                                                  │
│  [Populate from last 30 days]  [Populate from all summaries]   │
│                                                                  │
│  ⚠️ This may take several minutes for large guilds              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Simple to implement
- User controls when population happens
- Can be rate-limited to avoid API costs

**Cons**:
- Requires manual action
- One-time only (doesn't keep wiki updated)

**Use Case**: Initial wiki seeding, testing

---

### 2. Real-time Ingestion (Future)

**Description**: Wiki updates automatically when summaries are generated.

```
Summary Generated
      │
      ▼
┌─────────────────┐
│ Store Summary   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Deliver Summary │────▶│ Wiki Ingest     │
│ (async)         │     │ Agent           │
└─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │ Update 10-15    │
                        │ Wiki Pages      │
                        └─────────────────┘
```

**Pros**:
- Wiki always up-to-date
- No manual intervention needed
- Knowledge compounds immediately

**Cons**:
- Adds latency to summary generation
- LLM costs per summary
- More complex error handling

**Use Case**: Production continuous operation

---

### 3. Scheduled Batch Processing (Future)

**Description**: Periodic job processes unprocessed summaries.

```
┌─────────────────────────────────────────────────────────────────┐
│  Scheduled Job: Wiki Sync (daily at 3am UTC)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Query summaries where wiki_ingested = false                 │
│  2. For each summary:                                            │
│     a. Run WikiIngestAgent                                       │
│     b. Mark wiki_ingested = true                                │
│  3. Run WikiMaintenanceAgent.lint()                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Predictable resource usage
- Batching reduces LLM costs
- Can run during off-peak hours

**Cons**:
- Wiki not immediately updated
- Delay between summary and wiki update

**Use Case**: Cost-sensitive deployments

---

### 4. Event-Driven with Queue (Future)

**Description**: Summary events are queued for async wiki processing.

```
Summary Generated ──▶ Redis Queue ──▶ Wiki Worker
                          │
                          ▼
                    ┌───────────┐
                    │ Retry on  │
                    │ Failure   │
                    └───────────┘
```

**Pros**:
- Decoupled from summary generation
- Automatic retry on failure
- Scalable with multiple workers

**Cons**:
- Requires queue infrastructure
- More operational complexity

**Use Case**: High-volume deployments

---

## Implementation Phases

### Phase 1: Manual Backfill (This ADR)
- [x] Database schema (ADR-056)
- [ ] Populate endpoint: `POST /guilds/{id}/wiki/populate`
- [ ] Progress tracking for long-running population
- [ ] UI button in wiki settings

### Phase 2: Real-time Hook
- [ ] Add wiki ingest after summary storage
- [ ] Make ingest async (don't block summary delivery)
- [ ] Add `wiki_ingested` flag to stored_summaries

### Phase 3: Maintenance Automation
- [ ] Scheduled lint job
- [ ] Contradiction detection
- [ ] Stale content alerts

### Phase 4: Advanced Options
- [ ] Selective population (by channel, date range)
- [ ] Re-population (refresh existing pages)
- [ ] Import from external sources (Notion, Confluence)

---

## API Design

### Populate Endpoint

```python
@router.post("/guilds/{guild_id}/wiki/populate")
async def populate_wiki(
    guild_id: str,
    body: PopulateRequest,
    user: dict = Depends(get_current_user),
) -> PopulateResponse:
    """
    Populate wiki from historical summaries.

    Request:
        days: int = 30  # How far back to look

    Response:
        job_id: str
        summaries_found: int
        estimated_pages: int
    """
```

### Population Status

```python
@router.get("/guilds/{guild_id}/wiki/populate/status")
async def get_populate_status(guild_id: str) -> PopulateStatus:
    """
    Get status of ongoing population job.

    Response:
        status: "idle" | "running" | "completed" | "failed"
        progress: { processed: int, total: int }
        pages_created: int
        pages_updated: int
        errors: List[str]
    """
```

---

## Resource Considerations

| Strategy | LLM Calls | Latency Impact | Infra Required |
|----------|-----------|----------------|----------------|
| Manual Backfill | Batch | None | None |
| Real-time | Per summary | +2-5s | None |
| Scheduled Batch | Batch | None | Cron |
| Event Queue | Per summary | None | Redis |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Backfill completion | <5 min for 100 summaries |
| Pages per summary | 10-15 average |
| Ingest errors | <1% |

## Consequences

### Positive
- Flexible population options for different needs
- Can start simple and evolve
- Clear upgrade path

### Negative
- Multiple code paths to maintain
- Need to track ingestion state

## References

- [ADR-056: Compounding Wiki Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-058: Wiki Rendering](./ADR-058-wiki-rendering.md)
