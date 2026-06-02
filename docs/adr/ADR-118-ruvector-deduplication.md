# ADR-118: RuVector Deduplication During Rolling Schedule Updates

## Status
Accepted (Implemented)

## Context

RuVector knowledge units are extracted from summaries during the wiki ingestion pipeline (ADR-057). When rolling schedules (ADR-101) process summaries, the `on_summary_ingested` hook triggers knowledge unit extraction and storage.

### Problem

Duplicate knowledge units are being created when:

1. **Rolling schedule re-runs**: A schedule triggers summary generation for a period that was previously summarized (e.g., overlapping weekly windows)
2. **Re-processing**: Manual re-run of summary jobs or schedule triggers
3. **Concurrent processing**: Multiple workers processing the same summary

### Root Cause Analysis

The current implementation has three gaps:

1. **Random UUID generation**: `KnowledgeExtractor` creates units with `id=str(uuid.uuid4())`, generating new IDs on every invocation regardless of content
2. **No summary-level deduplication**: `RuVectorIngestIntegration.ingest_summary()` does not check if knowledge units already exist for a given `summary_id` before extraction
3. **Upsert mismatch**: `VectorStore.store_unit()` uses `ON CONFLICT(id)` but since IDs are always unique, this never triggers updates

### Current Flow (Problematic)

```
Summary Job → WikiIngestAgent.ingest_summary()
                    ↓
            RuVectorIngestHook.on_summary_ingested()
                    ↓
            KnowledgeExtractor.extract_from_summary()
                    ↓
            [NEW UUIDs generated] ← Problem: always new IDs
                    ↓
            VectorStore.store_units_batch()
                    ↓
            INSERT OR UPDATE (never updates due to new IDs)
```

### Contrast with Backfill

The `backfill_from_summaries()` method correctly handles this:

```sql
SELECT ... FROM stored_summaries ss
WHERE ss.guild_id = ?
  AND NOT EXISTS (
    SELECT 1 FROM wiki_knowledge_units ku
    WHERE ku.summary_id = ss.id
  )
```

This check is missing from the inline ingestion path.

## Decision

Implement a multi-layer deduplication strategy for RuVector knowledge units:

### Layer 1: Summary-Level Check (Guard Clause)

Before extracting knowledge units, check if units already exist for this `summary_id`:

```python
# In RuVectorIngestIntegration.ingest_summary()
async def ingest_summary(self, guild_id, summary_id, ...):
    # Check if KUs already exist for this summary
    existing = await self.vector_store.get_units_by_summary_id(guild_id, summary_id)
    if existing:
        logger.info(f"Skipping RuVector extraction for {summary_id}: {len(existing)} units exist")
        return ExtractionResult(units=existing, source_id=summary_id, skipped=True)

    # Proceed with extraction...
```

### Layer 2: Content-Based Deterministic IDs

Generate deterministic unit IDs based on content hash + source_id:

```python
import hashlib

def generate_unit_id(guild_id: str, source_id: str, content: str, unit_type: str) -> str:
    """Generate deterministic ID for deduplication."""
    key = f"{guild_id}:{source_id}:{unit_type}:{content}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]
```

This enables proper upsert behavior when the same content is extracted.

### Layer 3: Coherence Gate Enforcement

Make duplicate detection via `CoherenceGate` mandatory during ingestion (not just backfill):

```python
# In RuVectorIngestIntegration
self.coherence_gate = CoherenceGate(
    vector_store=self.vector_store,
    duplicate_threshold=0.95,  # High similarity = duplicate
)

# Before storing each unit
validation = await self.coherence_gate.validate(unit)
if validation.has_issue(CoherenceIssueType.DUPLICATE):
    logger.debug(f"Duplicate detected: {unit.id} similar to {validation.similar_unit_id}")
    continue  # Skip storage
```

### Implementation Priority

| Layer | Implementation | Impact | Complexity |
|-------|----------------|--------|------------|
| 1 | Summary-level guard | High - prevents most duplicates | Low |
| 2 | Deterministic IDs | Medium - enables proper upsert | Low |
| 3 | Coherence gate | Low - catches edge cases | Medium |

## Consequences

### Positive

- Prevents duplicate knowledge units during rolling schedule runs
- Reduces storage growth and embedding API costs
- Improves search result quality (no duplicate content)
- Maintains consistency between backfill and inline ingestion paths
- Deterministic IDs enable idempotent re-processing

### Negative

- Additional database query before extraction (Layer 1)
- Content hashing adds minor CPU overhead (Layer 2)
- Semantic duplicate detection requires embedding comparison (Layer 3)

### Migration

Existing duplicates can be cleaned up via:

```sql
-- Find duplicate content within same source
WITH duplicates AS (
  SELECT id, content, source_id, summary_id,
         ROW_NUMBER() OVER (PARTITION BY guild_id, summary_id, content ORDER BY created_at) as rn
  FROM wiki_knowledge_units
  WHERE summary_id IS NOT NULL
)
DELETE FROM wiki_knowledge_units
WHERE id IN (SELECT id FROM duplicates WHERE rn > 1);
```

## Implementation Plan

### Phase 1: Guard Clause (Immediate)

1. Add `get_units_by_summary_id()` method to `VectorStore`
2. Add check in `RuVectorIngestIntegration.ingest_summary()`
3. Add logging for skipped extractions

### Phase 2: Deterministic IDs

1. Update `KnowledgeExtractor` to accept optional ID generator
2. Implement content-based ID generation
3. Update unit creation to use deterministic IDs

### Phase 3: Coherence Gate Integration

1. Enable coherence gate during inline ingestion
2. Add duplicate detection metrics
3. Configure duplicate threshold via settings

## Files Affected

- `src/wiki/ruvector/ingest_integration.py` - Add guard clause
- `src/wiki/ruvector/knowledge_extractor.py` - Deterministic ID generation
- `src/wiki/ruvector/vector_store.py` - Add `get_units_by_summary_id()`
- `src/wiki/ruvector/coherence_gate.py` - Integration during ingestion

## Alternatives Considered

### Alternative 1: Delete Before Insert

Delete all existing KUs for a summary_id before re-extraction:

```python
await self.vector_store.delete_units_by_summary_id(guild_id, summary_id)
# Then extract and store new units
```

**Rejected**: This loses historical data and edges, and creates churn even when content is unchanged.

### Alternative 2: Unique Constraint on Content Hash

Add database constraint:

```sql
ALTER TABLE wiki_knowledge_units
ADD COLUMN content_hash TEXT GENERATED ALWAYS AS (md5(content)) STORED;
CREATE UNIQUE INDEX idx_ku_dedupe ON wiki_knowledge_units(guild_id, summary_id, content_hash);
```

**Rejected**: SQLite doesn't support generated columns in all versions; also doesn't handle semantic duplicates.

### Alternative 3: Skip Entirely if Summary Exists

Only process summaries that don't have any associated KUs:

**Partially Adopted**: This is Layer 1 of the chosen solution.

## References

- ADR-057: RuVector Knowledge Unit Store
- ADR-090: Summary-Based Knowledge Extraction
- ADR-101: Rolling Period Summaries
- ADR-112: Job Tracking and Metadata
