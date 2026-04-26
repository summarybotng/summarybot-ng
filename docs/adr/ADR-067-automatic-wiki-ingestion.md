# ADR-067: Automatic Wiki Ingestion

## Status
Implemented (2026-04-26)

## Context

Currently, wiki population is **manual only**:
1. User clicks "Populate Wiki" button
2. System fetches last N days of summaries
3. `WikiIngestAgent` processes each summary
4. Wiki pages are created/updated

This creates several problems:
- Wiki is always out of date until manually populated
- Users forget to populate after new summaries
- No real-time knowledge base updates
- Batch processing can be slow for large backlogs

### Current Flow

```
Summary Created → Stored in DB → (Manual) → Populate Wiki → Wiki Updated
                                    ↑
                              User must click
```

### Desired Flow

```
Summary Created → Stored in DB → Auto-Ingest → Wiki Updated (real-time)
```

---

## Decision

Implement automatic wiki ingestion triggered after each summary is stored, with background processing to avoid blocking summary delivery.

---

## Implementation

### Hook into Summary Storage

```python
# src/scheduling/delivery/dashboard.py

class DashboardDeliveryStrategy(DeliveryStrategy):
    async def deliver(self, summary, destination, context):
        # ... existing storage logic ...

        stored_summary = StoredSummary(...)
        await stored_repo.save(stored_summary)

        # NEW: Trigger wiki ingestion in background
        await self._trigger_wiki_ingestion(stored_summary, context)

        return DeliveryResult(success=True, ...)

    async def _trigger_wiki_ingestion(
        self,
        summary: StoredSummary,
        context: DeliveryContext,
    ):
        """Trigger wiki ingestion for newly stored summary."""
        try:
            from ...wiki.agents import WikiIngestAgent
            from ...data.repositories import get_wiki_repository

            wiki_repo = await get_wiki_repository()
            if not wiki_repo:
                logger.warning("Wiki repository not available, skipping ingestion")
                return

            agent = WikiIngestAgent(wiki_repo)

            # Extract data from summary
            result = summary.summary_result
            if not result:
                return

            # Run ingestion (consider background task for large summaries)
            await agent.ingest_summary(
                guild_id=summary.guild_id,
                summary_id=summary.id,
                summary_text=result.summary_text,
                key_points=result.key_points,
                action_items=[a.description for a in result.action_items],
                participants=[p.display_name for p in result.participants],
                technical_terms=[t.term for t in result.technical_terms],
                channel_name=summary.title or "Unknown",
                timestamp=summary.created_at,
                platform=getattr(context.scheduled_task, 'platform', 'discord'),
            )

            logger.info(f"Wiki ingested summary {summary.id}")

        except Exception as e:
            # Don't fail summary delivery if wiki ingestion fails
            logger.warning(f"Wiki ingestion failed for {summary.id}: {e}")
```

### Architecture Decision: In-Process with Retry

We evaluated three approaches for wiki ingestion:

| Approach | Latency | Cost | Complexity | Use Case |
|----------|---------|------|------------|----------|
| **In-Process (chosen)** | ~100ms | $0 | Low | Current scale |
| Task Queue | ~1-5s | $0 | Medium | High volume |
| Swarm Agent | ~5-15s | $0.001+/call | High | Semantic reasoning |

**Why In-Process?**

1. **Wiki ingestion is deterministic** - topic extraction, page updates, and link management don't require LLM reasoning. The `WikiIngestAgent` class performs rule-based operations.

2. **Volume is manageable** - summaries are generated at most every few minutes per guild, not per-second. No need for distributed workers.

3. **Background task prevents blocking** - `asyncio.create_task()` ensures delivery completes immediately while ingestion runs in parallel.

4. **Retry handles transient failures** - exponential backoff with jitter (3 retries, 1-30s delays) handles temporary database locks or connection issues.

5. **No infrastructure overhead** - no Redis, no queue workers, no additional monitoring systems needed.

**Upgrade Path**

- **Phase 1** (implemented): In-process with retry ✅
- **Phase 2** (when needed): Task queue for horizontal scaling
- **Phase 3** (if needed): Swarm agent for semantic conflict detection

### Retry Configuration

```python
WIKI_INGEST_MAX_RETRIES = 3      # Total attempts
WIKI_INGEST_BASE_DELAY = 1.0     # Initial delay (seconds)
WIKI_INGEST_MAX_DELAY = 30.0     # Maximum delay cap
WIKI_INGEST_JITTER = 0.5         # Randomization factor (0-1)
```

Delay calculation: `min(base * 2^attempt, max) + jitter`

Example delays: 1s → 2s → 4s (with random jitter added)

### Background Processing Option (Future)

For large summaries or high-volume workspaces, use background task:

```python
async def _trigger_wiki_ingestion(self, summary: StoredSummary, context: DeliveryContext):
    """Queue wiki ingestion as background task."""
    from ...scheduling.scheduler import get_scheduler

    scheduler = get_scheduler()
    if scheduler:
        # Queue for background processing
        await scheduler.queue_task(
            task_type="wiki_ingest",
            payload={
                "guild_id": summary.guild_id,
                "summary_id": summary.id,
            },
            priority="low",  # Don't block critical tasks
        )
    else:
        # Fallback to synchronous
        await self._ingest_summary_sync(summary, context)
```

### Configuration

```python
# src/config/settings.py

class WikiSettings:
    # Enable/disable automatic ingestion
    auto_ingest_enabled: bool = True

    # Minimum confidence to ingest (skip low-quality summaries)
    min_confidence_threshold: float = 0.5

    # Max concurrent ingestions
    max_concurrent_ingestions: int = 3

    # Delay before ingestion (allow summary edits)
    ingestion_delay_seconds: int = 30

    # Platforms to auto-ingest (empty = all)
    auto_ingest_platforms: List[str] = []
```

### Per-Workspace Toggle

```sql
-- Add to workspace/guild settings
ALTER TABLE guilds ADD COLUMN wiki_auto_ingest BOOLEAN DEFAULT TRUE;
```

```python
async def _trigger_wiki_ingestion(self, summary, context):
    # Check if auto-ingest is enabled for this workspace
    guild_settings = await get_guild_settings(summary.guild_id)
    if not guild_settings.get("wiki_auto_ingest", True):
        logger.debug(f"Auto-ingest disabled for guild {summary.guild_id}")
        return

    # ... proceed with ingestion
```

---

## Ingestion Improvements

### Platform-Aware Ingestion

```python
# src/wiki/agents/ingest_agent.py

async def ingest_summary(
    self,
    guild_id: str,
    summary_id: str,
    summary_text: str,
    key_points: List[str],
    action_items: List[str],
    participants: List[str],
    technical_terms: List[str],
    channel_name: str,
    timestamp: datetime,
    platform: str = "discord",  # NEW
) -> IngestResult:
    """Ingest a summary into the wiki with platform awareness."""

    # Include platform in source metadata
    source = WikiSource(
        id=f"summary-{summary_id}",
        guild_id=guild_id,
        source_type=WikiSourceType.SUMMARY,
        title=f"{platform.title()}: {channel_name} - {timestamp.strftime('%Y-%m-%d')}",
        content=summary_text,
        metadata={
            "platform": platform,
            "channel_name": channel_name,
            "timestamp": timestamp.isoformat(),
            "key_points": key_points,
        },
        ingested_at=utc_now_naive(),
    )

    # ... rest of ingestion logic
```

### Duplicate Detection

```python
async def ingest_summary(self, ...):
    # Check if already ingested
    existing = await self.repository.get_source(f"summary-{summary_id}")
    if existing:
        logger.debug(f"Summary {summary_id} already ingested, skipping")
        return IngestResult(
            source_id=f"summary-{summary_id}",
            success=True,
            pages_updated=[],
            pages_created=[],
        )

    # ... proceed with ingestion
```

---

## Monitoring

### Metrics

```python
# Track ingestion performance
wiki_ingestion_total = Counter(
    "wiki_ingestion_total",
    "Total wiki ingestions",
    ["status", "platform"]
)

wiki_ingestion_duration = Histogram(
    "wiki_ingestion_duration_seconds",
    "Wiki ingestion duration"
)

wiki_pages_affected = Counter(
    "wiki_pages_affected_total",
    "Wiki pages created/updated",
    ["action"]  # created, updated
)
```

### Dashboard Visibility

Add ingestion status to summary cards:
```tsx
<StoredSummaryCard summary={summary}>
  {summary.wiki_ingested ? (
    <Badge variant="success">Wiki Updated</Badge>
  ) : (
    <Badge variant="outline">Pending</Badge>
  )}
</StoredSummaryCard>
```

---

## Rollout Plan

### Phase 1: Foundation
1. Add `wiki_ingested` column to stored_summaries
2. Implement ingestion hook (disabled by default)
3. Add per-workspace toggle

### Phase 2: Testing
1. Enable for test workspace
2. Monitor performance and errors
3. Tune configuration

### Phase 3: Gradual Rollout
1. Enable for workspaces with <100 summaries/day
2. Monitor and adjust
3. Enable for all workspaces

### Phase 4: Optimization
1. Implement background queue
2. Add batch ingestion for high-volume
3. Add retry logic for failures

---

## Consequences

### Positive
- Wiki always up-to-date
- No manual intervention needed
- Real-time knowledge base
- Better user experience

### Negative
- Additional processing per summary
- More database writes
- Potential for ingestion lag during high volume

### Mitigations
- Background processing for heavy workloads
- Per-workspace disable option
- Graceful degradation (don't fail delivery)
- Rate limiting for very active workspaces

---

## Implementation Notes (2026-04-26)

### Files Modified

| File | Changes |
|------|---------|
| `src/data/migrations/057_wiki_auto_ingest.sql` | Created: adds `wiki_ingested`, `wiki_ingested_at` columns and guild `wiki_auto_ingest` setting |
| `src/models/stored_summary.py` | Added `wiki_ingested: bool` and `wiki_ingested_at: Optional[datetime]` fields |
| `src/data/sqlite/stored_summary_repository.py` | Updated INSERT query, added `mark_wiki_ingested()` and `find_not_wiki_ingested()` methods |
| `src/scheduling/delivery/dashboard.py` | Added `_trigger_wiki_ingestion()` method, called via `asyncio.create_task()` after save |
| `src/wiki/agents/ingest_agent.py` | Added `platform` parameter for platform-aware source titles |

### Key Implementation Details

1. **Background Processing**: Wiki ingestion runs as an async task via `asyncio.create_task()` to avoid blocking summary delivery.

2. **Retry with Exponential Backoff**: Up to 3 attempts with delays of ~1s, ~2s, ~4s (plus jitter). Prevents thundering herd and handles transient failures.

3. **Graceful Degradation**: All wiki ingestion errors are caught and logged - delivery never fails due to wiki issues. After max retries, error is logged but delivery succeeds.

4. **Per-Guild Toggle**: Checks `wiki_auto_ingest` column in guilds table (defaults to True if column doesn't exist).

5. **Tracking**: Each summary gets `wiki_ingested=True` and `wiki_ingested_at` timestamp after successful ingestion.

6. **Platform Awareness**: Source titles now include platform prefix (e.g., "Discord: #general - 2026-04-26").

### API Response Changes

`StoredSummary.to_list_item_dict()` and `to_dict()` now include:
```json
{
  "wiki_ingested": true,
  "wiki_ingested_at": "2026-04-26T12:30:00"
}
```

---

## References

- [ADR-056: Compounding Wiki Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-061: Wiki Population Strategies](./ADR-061-wiki-population-strategies.md)
