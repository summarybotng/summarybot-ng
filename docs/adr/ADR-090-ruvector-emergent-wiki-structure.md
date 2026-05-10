# ADR-090: RuVector Emergent Wiki Structure

## Status

Accepted (Updated 2026-05-10 with Section 7: Data Origin Optimization)

## Context

The current wiki generation pipeline follows a **categorize-then-accumulate** pattern:

```
Messages → Summaries → Topic Extraction → Wiki Pages → Synthesis
```

This approach has several limitations observed in production:

1. **Irrelevant content accumulation** - Topic extraction is keyword/heuristic-based, causing pages to include tangentially related content that doesn't belong
2. **Fragmented knowledge** - Related discussions across channels/times end up on separate pages
3. **Rigid structure** - Pages created from extraction rules, not from actual content relationships
4. **Synthesis struggles** - LLM must make sense of loosely related raw updates

RuVector (ADR-057) introduced semantic knowledge units with embeddings. Currently RuVector indexes existing wiki content. This ADR proposes inverting the relationship: **let RuVector's semantic clustering determine wiki structure**.

## Decision

Implement an **accumulate-then-structure** approach where wiki pages emerge from semantic clusters of knowledge units.

### New Pipeline

```
Messages → Summaries → Knowledge Units → Semantic Clustering → Pages emerge
                            ↓
                    [Vector embeddings]
                            ↓
                    [HNSW similarity graph]
                            ↓
                    [Community detection]
                            ↓
                    [Page synthesis from cluster]
```

### Core Concepts

#### 1. Knowledge Unit Ingestion

Every summary immediately produces knowledge units (facts, decisions, concepts, action items) stored with embeddings. No topic extraction or page assignment at this stage.

```python
# Current: Summary → Topic Extraction → Page Assignment → Store
# New: Summary → Knowledge Units → Store (page assignment deferred)

async def ingest_summary(summary: Summary) -> List[KnowledgeUnit]:
    units = await extractor.extract_units(summary)
    await vector_store.store_units(units)
    # No page assignment yet - that happens during clustering
    return units
```

#### 2. Semantic Clustering

Periodically (or on-demand), cluster knowledge units by semantic similarity using the embedding space.

```python
@dataclass
class KnowledgeCluster:
    id: str
    guild_id: str
    centroid: List[float]  # Average embedding
    unit_ids: List[str]
    coherence_score: float  # How tightly clustered
    suggested_title: str    # LLM-generated from representative units
    suggested_path: str
    created_at: datetime

async def cluster_guild_knowledge(guild_id: str) -> List[KnowledgeCluster]:
    """
    Cluster all knowledge units for a guild.

    Algorithm:
    1. Load all unit embeddings
    2. Build similarity graph (edges where similarity > threshold)
    3. Run community detection (Louvain, Leiden, or label propagation)
    4. Filter clusters by minimum size
    5. Generate titles from cluster centroids
    """
    units = await vector_store.get_all_units(guild_id)

    # Build similarity graph
    graph = build_similarity_graph(units, threshold=0.65)

    # Detect communities
    communities = detect_communities(graph, resolution=1.0)

    # Convert to clusters
    clusters = []
    for community_units in communities:
        if len(community_units) >= MIN_CLUSTER_SIZE:
            cluster = await build_cluster(community_units)
            clusters.append(cluster)

    return clusters
```

#### 3. Page Generation from Clusters

Each cluster becomes a wiki page candidate. The page content is synthesized from the cluster's knowledge units.

```python
async def generate_page_from_cluster(cluster: KnowledgeCluster) -> WikiPage:
    """
    Generate a wiki page from a knowledge cluster.

    The LLM receives only semantically related units,
    producing more coherent synthesis than current approach.
    """
    units = await vector_store.get_units(cluster.unit_ids)

    # Sort by date for narrative flow
    units.sort(key=lambda u: u.source_date)

    # Generate synthesis from coherent unit set
    synthesis = await llm.synthesize_page(
        title=cluster.suggested_title,
        units=units,
        style="wiki_article",
    )

    return WikiPage(
        path=cluster.suggested_path,
        title=cluster.suggested_title,
        synthesis=synthesis,
        source_units=cluster.unit_ids,
        cluster_id=cluster.id,
    )
```

#### 4. Incremental Updates

When new summaries arrive:

```python
async def on_new_summary(summary: Summary):
    # 1. Extract and store knowledge units
    new_units = await ingest_summary(summary)

    # 2. Find nearest existing clusters
    for unit in new_units:
        nearest = await vector_store.find_nearest_cluster(unit)

        if nearest and nearest.similarity > MERGE_THRESHOLD:
            # Add to existing cluster
            await add_unit_to_cluster(unit, nearest.cluster)
            await mark_page_stale(nearest.cluster.page_id)
        else:
            # Unit is orphan - may form new cluster later
            await mark_unit_unclustered(unit)

    # 3. Periodically re-cluster orphans
    if should_recluster():
        await recluster_orphans(summary.guild_id)
```

#### 5. Cluster Evolution

Clusters (and thus pages) can:
- **Grow**: New units join existing cluster
- **Split**: Large cluster divides into sub-topics
- **Merge**: Similar clusters combine
- **Dissolve**: Cluster falls below minimum size

```python
async def evolve_clusters(guild_id: str):
    """
    Periodic cluster maintenance.
    """
    clusters = await get_clusters(guild_id)

    for cluster in clusters:
        # Check if cluster should split
        if cluster.size > MAX_CLUSTER_SIZE:
            sub_clusters = await split_cluster(cluster)
            for sub in sub_clusters:
                await generate_page_from_cluster(sub)

        # Check coherence degradation
        if cluster.coherence_score < MIN_COHERENCE:
            await recluster_units(cluster.unit_ids)

    # Check for mergeable clusters
    merge_candidates = await find_similar_clusters(guild_id, threshold=0.8)
    for c1, c2 in merge_candidates:
        await merge_clusters(c1, c2)
```

### Schema Changes

```sql
-- New table for clusters
CREATE TABLE wiki_clusters (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    suggested_title TEXT,
    suggested_path TEXT,
    centroid_embedding BLOB,  -- Average embedding
    coherence_score REAL,
    unit_count INTEGER,
    page_id TEXT,  -- Generated page, if any
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (page_id) REFERENCES wiki_pages(id)
);

-- Link units to clusters
ALTER TABLE wiki_knowledge_units ADD COLUMN cluster_id TEXT;
ALTER TABLE wiki_knowledge_units ADD COLUMN is_clustered INTEGER DEFAULT 0;

-- Track cluster lineage for splits/merges
CREATE TABLE wiki_cluster_history (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    event_type TEXT,  -- 'split', 'merge', 'create', 'dissolve'
    source_cluster_ids TEXT,  -- JSON array
    result_cluster_ids TEXT,  -- JSON array
    created_at TEXT
);
```

### Configuration

```python
@dataclass
class ClusteringConfig:
    # Similarity threshold for edge creation
    similarity_threshold: float = 0.65

    # Minimum units to form a page-worthy cluster
    min_cluster_size: int = 5

    # Maximum units before considering split
    max_cluster_size: int = 100

    # Minimum coherence to maintain cluster
    min_coherence: float = 0.5

    # How often to re-cluster (hours)
    recluster_interval: int = 24

    # Community detection algorithm
    algorithm: str = "louvain"  # or "leiden", "label_propagation"

    # Resolution parameter for community detection
    resolution: float = 1.0
```

### Title Generation

Cluster titles are generated from representative units:

```python
async def generate_cluster_title(units: List[KnowledgeUnit]) -> str:
    """
    Generate a descriptive title for a cluster.

    Uses the most central units (closest to centroid) as representatives.
    """
    # Get top 5 units closest to centroid
    representatives = get_representative_units(units, n=5)

    prompt = f"""
    These knowledge units form a coherent topic cluster:

    {format_units(representatives)}

    Generate a concise, descriptive title (2-5 words) that captures
    the common theme. Return only the title, no explanation.
    """

    return await llm.complete(prompt)
```

### API Changes

```python
# New endpoints
POST /api/v1/guilds/{guild_id}/wiki/cluster
  # Trigger clustering for a guild

GET /api/v1/guilds/{guild_id}/wiki/clusters
  # List current clusters with stats

POST /api/v1/guilds/{guild_id}/wiki/clusters/{cluster_id}/generate
  # Generate page from specific cluster

GET /api/v1/guilds/{guild_id}/wiki/unclustered
  # View orphan units not yet in clusters
```

### Migration Path

1. **Phase 1**: Run clustering on existing knowledge units (from current RuVector backfill)
2. **Phase 2**: Generate pages from clusters, compare to existing pages
3. **Phase 3**: Offer "Reorganize Wiki" action that replaces topic-extracted pages with cluster-derived pages
4. **Phase 4**: Switch new content to cluster-first pipeline

## Consequences

### Positive

1. **Higher relevance** - Pages contain only semantically related content
2. **Emergent structure** - Topics surface from data, not predefined rules
3. **Better synthesis** - LLM works with coherent unit sets
4. **Natural deduplication** - Similar content clusters together
5. **Cross-cutting themes** - Discovers connections across channels/time
6. **Adaptive organization** - Structure evolves as knowledge grows

### Negative

1. **Computational cost** - Clustering is O(n log n) to O(n^2) depending on algorithm
2. **Delayed structure** - Need minimum units before meaningful clusters form
3. **Title instability** - Cluster titles may shift as content evolves
4. **Path changes** - Reorganization breaks existing links
5. **Complexity** - More moving parts than current pipeline

### Neutral

1. **Different mental model** - Users see emergent vs curated structure
2. **Requires tuning** - Clustering parameters affect results significantly

## Alternatives Considered

### A. Hybrid: Keep topic extraction, use clusters for refinement

Extract topics as today, but use clustering to:
- Validate topic assignments
- Suggest merges/splits
- Filter irrelevant content from pages

**Rejected**: Doesn't solve the fundamental issue of heuristic-based categorization.

### B. LLM-based page assignment

For each summary, ask LLM which existing page(s) it belongs to.

**Rejected**: Expensive (LLM call per summary), doesn't discover new topics organically.

### C. User-defined taxonomy

Let users define page structure, route content manually.

**Rejected**: Doesn't scale, requires ongoing curation effort.

## Implementation Phases

### Phase 1: Clustering Infrastructure (Week 1-2)
- [ ] Add cluster schema
- [ ] Implement similarity graph construction
- [ ] Implement community detection (start with Louvain)
- [ ] Add cluster title generation

### Phase 2: Page Generation (Week 2-3)
- [ ] Implement cluster → page synthesis
- [ ] Add cluster management API
- [ ] Build cluster visualization UI

### Phase 3: Incremental Updates (Week 3-4)
- [ ] Implement unit → cluster assignment on ingest
- [ ] Add cluster evolution (split/merge)
- [ ] Implement stale page detection

### Phase 4: Migration & Rollout (Week 4-5)
- [ ] Build migration tooling
- [ ] A/B comparison UI (old vs new structure)
- [ ] Gradual rollout with feature flag

## Integration with ADR-077: Wiki Curator Agent

ADR-077 defines an AI Curator Agent for wiki maintenance. With cluster-based structure, the Curator's responsibilities shift:

### Curator Skills Remapped to Clusters

| ADR-077 Skill | Cluster-Based Implementation |
|---------------|------------------------------|
| **Topic Merger** | Becomes **Cluster Merger** - detect when two clusters should combine based on centroid proximity and overlapping content |
| **Quality Assessor** | Assess **cluster coherence** - score how well units in a cluster relate to each other |
| **Cross-Linker** | Becomes **edge weight optimizer** - strengthen edges between related clusters |
| **Contradiction Resolver** | Detect conflicts **within clusters** - easier since units are already semantically related |
| **Content Pruner** | Remove **outlier units** from clusters - units that don't belong |
| **Gap Detector** | Identify **sparse regions** in embedding space - topics with few units |

### Synergies

1. **Clustering provides structure, Curator maintains quality**
   - Clustering: "These 50 units form a coherent topic"
   - Curator: "But 3 units are outliers, 2 contradict each other"

2. **Curator can trigger re-clustering**
   - If curator detects many merge suggestions → resolution parameter too high
   - If curator detects many gaps → resolution parameter too low

3. **Cluster metadata improves curation**
   - Coherence score guides quality assessment
   - Cluster age guides staleness detection
   - Unit count guides depth assessment

### Updated Curation Flow

```python
async def curate_clusters(guild_id: str):
    """Curation working on cluster-based wiki."""

    clusters = await get_clusters(guild_id)

    for cluster in clusters:
        # 1. Quality: Check cluster coherence
        if cluster.coherence_score < 0.6:
            await flag_for_review(cluster, "low_coherence")

        # 2. Outliers: Find units that don't belong
        outliers = await find_outlier_units(cluster)
        for unit in outliers:
            await move_to_better_cluster_or_orphan(unit)

        # 3. Contradictions: Easier within semantic cluster
        conflicts = await find_contradictions(cluster.unit_ids)
        for conflict in conflicts:
            await queue_conflict_resolution(conflict)

        # 4. Staleness: Check cluster activity
        if cluster.last_unit_added > timedelta(days=90):
            await flag_as_potentially_stale(cluster)

    # 5. Merge candidates: Clusters with high inter-similarity
    merge_pairs = await find_similar_clusters(guild_id, threshold=0.85)
    for c1, c2 in merge_pairs:
        await queue_merge_suggestion(c1, c2)

    # 6. Gap detection: Sparse embedding regions
    gaps = await find_embedding_gaps(guild_id)
    for gap in gaps:
        await flag_potential_missing_topic(gap)
```

### Curator-Driven Cluster Operations

The Curator can perform cluster operations:

```python
class ClusterCurationActions:
    """Curation actions specific to cluster-based wiki."""

    async def merge_clusters(self, c1_id: str, c2_id: str) -> KnowledgeCluster:
        """Merge two clusters into one, regenerate page."""

    async def split_cluster(self, cluster_id: str, split_criteria: str) -> List[KnowledgeCluster]:
        """Split cluster by criteria (time, sub-topic, etc.)."""

    async def evict_unit(self, unit_id: str, cluster_id: str):
        """Remove unit from cluster, mark as orphan for re-clustering."""

    async def force_cluster_unit(self, unit_id: str, cluster_id: str):
        """Manually assign unit to cluster (curator override)."""

    async def adjust_resolution(self, guild_id: str, direction: str):
        """Suggest resolution parameter change based on cluster quality."""
```

### UI Integration

The curation UI (ADR-077) shows cluster-aware views:

```
Wiki Curation Dashboard
├── Cluster Health
│   ├── Low Coherence Clusters (3) ⚠️
│   ├── Oversized Clusters (1) → suggest split
│   └── Near-Duplicate Clusters (2) → suggest merge
├── Unit Issues
│   ├── Outlier Units (7) → reassign or orphan
│   └── Contradicting Units (2) → resolve
├── Structure Suggestions
│   ├── Merge: "Authentication" + "Auth Setup" (92% similar)
│   └── Split: "Infrastructure" has 2 sub-clusters detected
└── Coverage Gaps
    └── Embedding region near "deployment" has few units
```

## Section 7: Data Origin Optimization

### Problem: Redundant LLM Processing

The current implementation has a critical inefficiency:

```
CURRENT FLOW (Sub-optimal):
Discord Messages
      ↓
Claude Summarization (LLM #1) ──→ stored_summaries
      ↓
Topic Extraction (heuristics)
      ↓
wiki_sources table
      ↓
[User clicks "360° Generate"]
      ↓
KnowledgeExtractor (LLM #2) ←── REDUNDANT CALL
      ↓
wiki_knowledge_units
```

**The Problem**: We're calling Claude twice:
1. First to summarize messages
2. Then to "extract knowledge units" from already-summarized text

This is wasteful and loses fidelity. By the time content reaches `wiki_sources`, information has already been distilled.

### Solution: Inline KU Extraction

Extract knowledge units **during summarization**, not after:

```
OPTIMAL FLOW:
Discord Messages
      ↓
Claude Summarization ──┬──→ stored_summaries (for display)
   (single LLM call)   │
                       └──→ Knowledge Units (extracted inline)
                                  ↓
                           Embeddings (async)
                                  ↓
                           wiki_knowledge_units
                                  ↓
                           HNSW Index
                                  ↓
                           Semantic Clustering
                                  ↓
                           Wiki Pages EMERGE
```

### Implementation Changes

#### 1. Extend Summarization Prompt

Modify the summarization prompt to return structured output:

```python
# src/summarization/prompts.py
SUMMARY_WITH_KU_EXTRACTION = """
Summarize the following messages and extract atomic knowledge units.

Messages:
{messages}

Return JSON:
{
  "summary": "The narrative summary text...",
  "key_points": ["point 1", "point 2"],
  "action_items": ["action 1"],
  "knowledge_units": [
    {
      "content": "Atomic fact or decision",
      "type": "claim|decision|question|action_item|context|definition",
      "confidence": 0.95
    }
  ]
}
"""
```

#### 2. Dual-Write in Summarization Pipeline

```python
# src/summarization/engine.py
async def summarize_messages(messages: List[Message]) -> SummaryResult:
    # Single LLM call extracts both summary AND knowledge units
    response = await claude.complete(
        SUMMARY_WITH_KU_EXTRACTION.format(messages=format_messages(messages))
    )

    result = parse_response(response)

    # Store summary (existing flow)
    await store_summary(result.summary, result.key_points, result.action_items)

    # Store knowledge units (new - happens automatically)
    if result.knowledge_units:
        await ruvector.store_units_batch(
            guild_id=guild_id,
            units=result.knowledge_units,
            source_id=summary_id,
            source_type="summary",
        )

    return result
```

#### 3. Remove Manual "360° Generate" Button

The button becomes unnecessary because:
- KUs are extracted at summarization time (automatic)
- No separate extraction step needed
- Users see KUs immediately

Replace with:
- **"Re-extract KUs"** - Only for historical content migration
- **"Cluster Now"** - Trigger clustering on-demand

#### 4. Schema: Track Extraction Source

```sql
-- Track whether KUs came from inline extraction or backfill
ALTER TABLE wiki_knowledge_units ADD COLUMN extraction_source TEXT DEFAULT 'inline';
-- Values: 'inline' (during summarization), 'backfill' (from wiki_sources), 'manual'

-- Index for finding units that need re-extraction
CREATE INDEX idx_ku_extraction_source ON wiki_knowledge_units(guild_id, extraction_source);
```

### Migration Strategy

#### Phase 0: Enable Inline Extraction (Week 1) - ✅ COMPLETE
- [x] Modify summarization prompt to return KUs (`src/summarization/prompt_builder.py:CITATION_INSTRUCTIONS`)
- [x] Parse KUs in response parser (`src/summarization/response_parser.py:InlineKnowledgeUnit`)
- [x] Store KUs in `SummaryResult.knowledge_units` (`src/models/summary.py`)
- [x] Add KU storage to summarization pipeline (`src/summarization/engine.py:_store_knowledge_units_in_ruvector`)
- [x] Feature flag: `RUVECTOR_INLINE_EXTRACTION=true` (env var check in engine.py)
- [x] Database migration for extraction_source column (`092_inline_ku_extraction.sql`)
- [x] KnowledgeUnit model updated with `extraction_source` and `summary_id` fields
- [ ] Enable feature flag in production

#### Phase 1: Backfill Historical Content (Week 2) - ✅ COMPLETE
- [x] Add `backfill_from_summaries()` method to `RuVectorBackfill`
- [x] Support two modes: fast conversion (no LLM) and LLM extraction
- [x] Mark units as `extraction_source='backfill'`
- [x] API endpoint: `POST /ruvector/guilds/{id}/backfill-summaries`
- [ ] Run backfill for production guilds

#### Phase 2: Deprecate Manual Extraction (Week 3) - ✅ COMPLETE
- [x] Mark `POST /process-page` endpoint as deprecated in OpenAPI
- [x] Update UI: "RuVector" button → "Re-extract KUs (Admin)" with muted styling
- [x] Update empty state to inform users KUs are extracted automatically
- [x] Keep admin functionality for debugging/re-processing

#### Phase 3: Remove wiki_sources Dependency (Week 4)
- [ ] KU-based wiki pages don't need wiki_sources
- [ ] Archive wiki_sources table (don't delete)
- [ ] Update wiki synthesis to read from KUs

### Cost Analysis

| Approach | LLM Calls | Tokens | Cost/1000 summaries |
|----------|-----------|--------|---------------------|
| Current (double) | 2 per summary | ~4000 | $12.00 |
| Inline extraction | 1 per summary | ~2500 | $7.50 |
| **Savings** | **50%** | **37%** | **$4.50** |

### Configuration

```python
@dataclass
class RuVectorInlineConfig:
    # Enable inline KU extraction during summarization
    inline_extraction_enabled: bool = True

    # Minimum confidence to store a KU
    min_ku_confidence: float = 0.5

    # Maximum KUs per summary (prevent explosion)
    max_kus_per_summary: int = 20

    # Generate embeddings synchronously or queue
    embedding_mode: str = "async"  # "sync" | "async"

    # Auto-cluster after N new KUs
    auto_cluster_threshold: int = 50
```

### Deprecation Timeline

| Component | Current State | Target State | Timeline |
|-----------|---------------|--------------|----------|
| `KnowledgeExtractor.extract_from_summary()` | Active | Deprecated | Week 3 |
| `POST /process-page` endpoint | Active | Admin-only | Week 3 |
| "360° Generate" button | Visible | Removed | Week 3 |
| `wiki_sources` table | Active | Read-only archive | Week 4 |
| `RuVectorIngestHook` | Optional | Mandatory | Week 2 |

## References

- [ADR-057: RuVector Knowledge Graph](./ADR-057-ruvector-knowledge-graph.md)
- [ADR-063: Wiki Synthesis](./ADR-063-wiki-synthesis.md)
- [ADR-077: AI Wiki Curator Agent](./ADR-077-ai-wiki-curator-agent.md)
- [Louvain Community Detection](https://en.wikipedia.org/wiki/Louvain_method)
- [Leiden Algorithm](https://www.nature.com/articles/s41598-019-41695-z)
- [HNSW for Approximate Nearest Neighbors](https://arxiv.org/abs/1603.09320)
