# ADR-067: Automatic Wiki Ingestion

## Status
Proposed

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

### Background Processing Option

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

## References

- [ADR-056: Compounding Wiki Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-061: Wiki Population Strategies](./ADR-061-wiki-population-strategies.md)
