# ADR-057: Compounding Wiki - RuVector Enhanced Implementation

## Status
Proposed

## Context

Building on ADR-056 (Standard Compounding Wiki), this ADR describes an enhanced implementation leveraging RuVector's full capabilities:

- **HNSW Vector Index**: Sub-linear semantic search
- **GNN Knowledge Graph**: Automatic relationship discovery
- **SONA Temporal Learning**: Self-optimizing relevance
- **RuVector Brain**: Unified knowledge store with coherence validation

The standard implementation (ADR-056) uses SQLite FTS5 and explicit links. This version replaces keyword search with semantic understanding and manual cross-referencing with automatic graph inference.

## Decision

Implement the Compounding Wiki using RuVector Brain as the knowledge substrate, enabling:

1. **Semantic search** that understands intent, not just keywords
2. **Automatic relationship discovery** via GNN edge inference
3. **Self-improving relevance** through SONA temporal learning
4. **Coherence validation** to prevent hallucination accumulation
5. **Multi-modal knowledge** (text, code, diagrams)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                 COMPOUNDING WIKI + RUVECTOR BRAIN                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     SCHEMA LAYER                                 │   │
│  │  wiki-schema.md + ruvector-config.yaml                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     WIKI LAYER                                   │   │
│  │                                                                   │   │
│  │   wiki/                          ┌─────────────────────────┐    │   │
│  │   ├── index.md                   │                         │    │   │
│  │   ├── log.md                     │    RUVECTOR BRAIN       │    │   │
│  │   ├── topics/                    │                         │    │   │
│  │   ├── decisions/        ◀───────▶│  ┌─────────────────┐   │    │   │
│  │   ├── processes/                 │  │  HNSW Vectors   │   │    │   │
│  │   ├── experts/                   │  │  (embeddings)   │   │    │   │
│  │   └── questions/                 │  └─────────────────┘   │    │   │
│  │                                  │          │              │    │   │
│  │   Markdown files ◀──sync──▶      │          ▼              │    │   │
│  │   RuVector nodes                 │  ┌─────────────────┐   │    │   │
│  │                                  │  │   GNN Graph     │   │    │   │
│  │                                  │  │  (relationships)│   │    │   │
│  │                                  │  └─────────────────┘   │    │   │
│  │                                  │          │              │    │   │
│  │                                  │          ▼              │    │   │
│  │                                  │  ┌─────────────────┐   │    │   │
│  │                                  │  │  SONA Learner   │   │    │   │
│  │                                  │  │  (optimization) │   │    │   │
│  │                                  │  └─────────────────┘   │    │   │
│  │                                  │          │              │    │   │
│  │                                  │          ▼              │    │   │
│  │                                  │  ┌─────────────────┐   │    │   │
│  │                                  │  │ Coherence Gate  │   │    │   │
│  │                                  │  │ (validation)    │   │    │   │
│  │                                  │  └─────────────────┘   │    │   │
│  │                                  │                         │    │   │
│  │                                  └─────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     SOURCE LAYER (Immutable)                     │   │
│  │   sources/summaries/ + sources/archives/ + sources/documents/    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## RuVector-Enhanced Capabilities

### 1. Semantic Search (vs. Keyword Search)

**Standard (ADR-056)**:
```sql
-- Keyword matching only
SELECT * FROM wiki_fts WHERE wiki_fts MATCH 'authentication token'
-- Misses: "auth credentials", "login session", "OAuth bearer"
```

**RuVector Enhanced**:
```python
class SemanticWikiSearch:
    """
    Semantic search understands meaning, not just words.
    """

    async def search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[WikiPage]:
        # 1. Embed the query
        query_embedding = await self.ruvector.embed(query)

        # 2. HNSW approximate nearest neighbor search
        results = await self.ruvector.search(
            vector=query_embedding,
            limit=limit * 2,  # Over-fetch for re-ranking
            threshold=threshold
        )

        # 3. GNN-enhanced re-ranking (consider graph context)
        reranked = await self.ruvector.rerank_with_graph(
            query_embedding=query_embedding,
            candidates=results,
            graph_weight=0.3  # 30% graph, 70% vector
        )

        # 4. SONA feedback for learning
        await self.ruvector.learn(
            context="wiki_search",
            query=query,
            results=[r.id for r in reranked[:limit]]
        )

        return reranked[:limit]
```

**Result**: Query "how do we handle auth" finds pages about:
- `authentication.md` (direct match)
- `oauth-implementation.md` (semantic similarity)
- `session-management.md` (graph relationship)
- `security-decisions.md` (contextual relevance)

### 2. Automatic Relationship Discovery (vs. Manual Links)

**Standard (ADR-056)**:
```markdown
<!-- Manual links required -->
See also: [Authentication](authentication.md), [OAuth](oauth.md)
```

**RuVector Enhanced**:
```python
class AutomaticLinkDiscovery:
    """
    GNN infers relationships without explicit links.
    """

    async def discover_relationships(
        self,
        page: WikiPage
    ) -> List[Relationship]:
        # 1. Get page embedding
        embedding = await self.ruvector.get_embedding(page.id)

        # 2. Find semantically similar pages
        similar = await self.ruvector.search(
            vector=embedding,
            limit=20,
            exclude=[page.id]
        )

        # 3. GNN edge type classification
        relationships = []
        for candidate in similar:
            edge_type = await self.ruvector.classify_edge(
                from_node=page.id,
                to_node=candidate.id,
                attention_heads=["topic_coherence", "temporal_proximity", "author_overlap"]
            )

            if edge_type.confidence > 0.6:
                relationships.append(Relationship(
                    target=candidate,
                    type=edge_type.label,  # relates_to, depends_on, supersedes, contradicts
                    confidence=edge_type.confidence
                ))

        return relationships

    async def suggest_links_for_page(self, page_path: str) -> List[LinkSuggestion]:
        """
        Proactively suggest links during editing.
        """
        page = await self.get_page(page_path)
        relationships = await self.discover_relationships(page)

        # Filter to high-confidence, not-already-linked
        existing_links = set(page.outbound_links)
        suggestions = [
            LinkSuggestion(
                target=r.target.path,
                reason=f"{r.type} (confidence: {r.confidence:.0%})",
                snippet=r.target.summary[:100]
            )
            for r in relationships
            if r.target.path not in existing_links
        ]

        return sorted(suggestions, key=lambda s: s.confidence, reverse=True)[:5]
```

### 3. Self-Improving Relevance (SONA Temporal Learning)

```python
class SONAWikiLearning:
    """
    Wiki search improves automatically based on usage patterns.
    """

    # TIER 1: Immediate (per-query)
    async def on_search_result_click(
        self,
        query: str,
        clicked_page: str,
        position: int,
        dwell_time: float
    ):
        """User clicked a result - positive signal."""
        await self.ruvector.learn(
            context="immediate",
            signal={
                "type": "click",
                "query": query,
                "page": clicked_page,
                "position": position,
                "dwell_time": dwell_time,
                "relevance_boost": 1.0 + (0.1 * (10 - position))  # Higher boost for lower positions
            }
        )

    # TIER 2: Session (per-user)
    async def on_query_refinement(
        self,
        original_query: str,
        refined_query: str,
        user_id: str
    ):
        """User refined their search - learn intent patterns."""
        await self.ruvector.learn(
            context="session",
            signal={
                "type": "refinement",
                "from": original_query,
                "to": refined_query,
                "user": user_id,
                "pattern": "query_expansion" if len(refined_query) > len(original_query) else "query_focus"
            }
        )

    # TIER 3: Long-term (system-wide)
    async def on_page_update(
        self,
        page_id: str,
        update_type: str,  # content, links, merge
        trigger: str  # ingest, lint, manual
    ):
        """Track how knowledge evolves over time."""
        await self.ruvector.learn(
            context="long_term",
            signal={
                "type": "evolution",
                "page": page_id,
                "update_type": update_type,
                "trigger": trigger,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    async def get_relevance_boost(self, page_id: str) -> float:
        """
        SONA calculates relevance boost based on learned patterns:
        - Frequently accessed pages get higher base relevance
        - Recently updated pages get freshness boost
        - Pages with high dwell time get engagement boost
        """
        return await self.ruvector.get_sona_score(page_id)
```

### 4. Coherence Gate (Anti-Hallucination)

**The Problem**: LLMs reading their own generated content can accumulate hallucinations.

```python
class CoherenceGate:
    """
    Validates new wiki content against existing knowledge.
    Prevents hallucination accumulation.
    """

    async def validate_update(
        self,
        page: WikiPage,
        proposed_content: str,
        source: Source
    ) -> ValidationResult:
        # 1. Extract claims from proposed content
        claims = await self.extract_claims(proposed_content)

        # 2. For each claim, check coherence with existing wiki
        issues = []
        for claim in claims:
            # Find related content via semantic search
            related = await self.ruvector.search(
                vector=await self.ruvector.embed(claim.text),
                limit=10,
                threshold=0.8
            )

            # Check for contradictions
            for page in related:
                contradiction = await self.detect_contradiction(
                    claim=claim,
                    existing=page.content
                )
                if contradiction:
                    issues.append(CoherenceIssue(
                        type="contradiction",
                        claim=claim,
                        conflicts_with=page.path,
                        confidence=contradiction.confidence
                    ))

            # Verify claim has source support
            if not await self.verify_source_support(claim, source):
                issues.append(CoherenceIssue(
                    type="unsupported",
                    claim=claim,
                    message="Claim not supported by source document"
                ))

        # 3. Decision
        if any(i.type == "contradiction" and i.confidence > 0.9 for i in issues):
            return ValidationResult(
                approved=False,
                issues=issues,
                action="flag_for_human_review"
            )

        if any(i.type == "unsupported" for i in issues):
            return ValidationResult(
                approved=False,
                issues=issues,
                action="require_citation"
            )

        return ValidationResult(approved=True, issues=[])
```

### 5. Multi-Modal Knowledge

RuVector supports embedding different content types:

```python
class MultiModalWiki:
    """
    Wiki pages can contain text, code, and diagrams - all searchable.
    """

    async def embed_page(self, page: WikiPage) -> List[Embedding]:
        embeddings = []

        # 1. Text content
        text_chunks = self.chunk_text(page.content)
        for chunk in text_chunks:
            embeddings.append(await self.ruvector.embed(
                content=chunk,
                modality="text"
            ))

        # 2. Code blocks
        code_blocks = self.extract_code_blocks(page.content)
        for code in code_blocks:
            embeddings.append(await self.ruvector.embed(
                content=code.content,
                modality="code",
                language=code.language
            ))

        # 3. Diagrams (Mermaid, ASCII)
        diagrams = self.extract_diagrams(page.content)
        for diagram in diagrams:
            # Convert to description for embedding
            description = await self.describe_diagram(diagram)
            embeddings.append(await self.ruvector.embed(
                content=description,
                modality="diagram",
                original=diagram.content
            ))

        return embeddings

    async def search_code(self, query: str) -> List[CodeResult]:
        """
        Find code snippets semantically.
        "how to authenticate" → finds auth middleware code
        """
        return await self.ruvector.search(
            vector=await self.ruvector.embed(query),
            filter={"modality": "code"},
            limit=10
        )
```

---

## Enhanced Agent Workflows

### 1. Ingest with Graph Integration

```python
class RuVectorWikiIngest:
    """
    Ingest with automatic graph building and coherence validation.
    """

    async def ingest(self, source: Source) -> IngestResult:
        # 1. Standard ingest (ADR-056)
        summary = await self.summarize_source(source)

        # 2. Coherence check BEFORE updating wiki
        validation = await self.coherence_gate.validate(summary, source)
        if not validation.approved:
            return IngestResult(
                success=False,
                issues=validation.issues,
                action="human_review_required"
            )

        # 3. Update wiki pages
        updates = await self.update_wiki_pages(summary)

        # 4. Build graph edges automatically
        for page in updates:
            # Embed updated content
            embeddings = await self.embed_page(page)
            await self.ruvector.upsert(page.id, embeddings)

            # Discover and create graph edges
            relationships = await self.discover_relationships(page)
            for rel in relationships:
                await self.ruvector.add_edge(
                    from_node=page.id,
                    to_node=rel.target.id,
                    edge_type=rel.type,
                    weight=rel.confidence
                )

        # 5. SONA learning signal
        await self.ruvector.learn(
            context="ingest",
            signal={
                "source": source.id,
                "pages_updated": len(updates),
                "edges_created": sum(len(await self.discover_relationships(p)) for p in updates)
            }
        )

        return IngestResult(success=True, updates=updates)
```

### 2. Query with Graph Traversal

```python
class RuVectorWikiQuery:
    """
    Query with semantic search + graph exploration.
    """

    async def query(self, question: str) -> QueryResult:
        # 1. Semantic search for entry points
        entry_points = await self.semantic_search(question, limit=5)

        # 2. Graph traversal for related context
        context_pages = set()
        for entry in entry_points:
            # Traverse 2 hops in the knowledge graph
            neighbors = await self.ruvector.traverse(
                start=entry.id,
                max_depth=2,
                edge_types=["relates_to", "depends_on"],
                limit_per_hop=3
            )
            context_pages.update(neighbors)

        # 3. Synthesize answer with full context
        answer = await self.synthesize(
            question=question,
            primary_sources=entry_points,
            context=list(context_pages)
        )

        # 4. SONA: Track query for learning
        await self.ruvector.learn(
            context="query",
            signal={
                "question": question,
                "entry_points": [e.id for e in entry_points],
                "graph_expansion": len(context_pages)
            }
        )

        return QueryResult(
            answer=answer,
            primary_citations=entry_points,
            related_context=list(context_pages)
        )
```

### 3. Lint with Contradiction Detection

```python
class RuVectorWikiLint:
    """
    Lint with GNN-powered contradiction and coherence analysis.
    """

    async def lint(self) -> LintResult:
        issues = []

        # 1. GNN-based contradiction detection
        # Cluster pages and find outliers within clusters
        clusters = await self.ruvector.cluster_pages(
            algorithm="hdbscan",
            min_cluster_size=3
        )

        for cluster in clusters:
            # Find contradictions within semantically similar pages
            contradictions = await self.ruvector.detect_contradictions(
                page_ids=cluster.members,
                attention_head="claim_consistency"
            )
            issues.extend(contradictions)

        # 2. Graph-based orphan detection
        # Pages with no inbound edges (not connected to graph)
        orphans = await self.ruvector.find_orphans(
            min_inbound_edges=1
        )
        issues.extend([OrphanIssue(page=o) for o in orphans])

        # 3. Staleness via SONA temporal analysis
        # Pages not accessed and not updated
        stale = await self.ruvector.find_stale_nodes(
            max_age_days=30,
            min_access_count=0
        )
        issues.extend([StaleIssue(page=s) for s in stale])

        # 4. Coherence drift
        # Pages whose embeddings have drifted from cluster centroid
        drift = await self.ruvector.detect_drift(
            threshold=0.3
        )
        issues.extend([DriftIssue(page=d.page, drift=d.score) for d in drift])

        return LintResult(issues=issues)
```

---

## Comparison: Standard vs. RuVector

| Capability | Standard (ADR-056) | RuVector (ADR-057) |
|------------|-------------------|-------------------|
| **Search** | SQLite FTS5 (keyword) | HNSW semantic + GNN reranking |
| **Relationships** | Manual links | Automatic GNN discovery |
| **Contradiction Detection** | LLM pairwise comparison | GNN cluster analysis |
| **Relevance** | Static BM25 | SONA temporal learning |
| **Coherence** | Human review only | Coherence Gate validation |
| **Multi-modal** | Text only | Text + code + diagrams |
| **Query Understanding** | Keywords | Intent inference |
| **Staleness** | Timestamp-based | Access pattern + temporal |
| **Scalability** | ~10K pages | ~1M+ pages (HNSW) |

---

## RuVector Configuration

```yaml
# ruvector-config.yaml

brain:
  name: "summarybot-wiki"
  version: "1.0"

hnsw:
  dimensions: 1536  # text-embedding-3-small
  m: 16             # Max connections per node
  ef_construction: 200
  ef_search: 100
  metric: cosine

gnn:
  architecture: "gat"  # Graph Attention Network
  attention_heads:
    - topic_coherence
    - temporal_proximity
    - author_overlap
    - claim_consistency
  hidden_dim: 256
  num_layers: 3

sona:
  tiers:
    immediate:
      enabled: true
      decay_hours: 1
    session:
      enabled: true
      decay_hours: 24
    long_term:
      enabled: true
      decay_days: 30
  learning_rate: 0.01

coherence_gate:
  enabled: true
  contradiction_threshold: 0.85
  unsupported_claim_action: "flag"
  auto_reject_threshold: 0.95

embedding:
  model: "text-embedding-3-small"
  batch_size: 100
  modalities:
    - text
    - code
    - diagram
```

---

## Implementation Phases

### Phase 1: RuVector Integration (4 weeks)
- [ ] RuVector Brain setup and configuration
- [ ] Page embedding pipeline
- [ ] Basic semantic search
- [ ] Markdown ↔ RuVector sync

### Phase 2: Graph Intelligence (4 weeks)
- [ ] GNN edge classification
- [ ] Automatic relationship discovery
- [ ] Graph traversal for queries
- [ ] Contradiction detection

### Phase 3: SONA Learning (3 weeks)
- [ ] Click-through tracking
- [ ] Query refinement learning
- [ ] Relevance boost calculation
- [ ] Staleness detection

### Phase 4: Coherence & Safety (3 weeks)
- [ ] Coherence Gate implementation
- [ ] Claim extraction pipeline
- [ ] Source verification
- [ ] Human review workflow

---

## Success Metrics

| Metric | Standard (ADR-056) | RuVector Target |
|--------|-------------------|-----------------|
| Search relevance | 70% satisfaction | **90%** satisfaction |
| Query latency | 200ms p99 | **50ms** p99 (HNSW) |
| Auto-discovered links | 0 (manual only) | **5+ per page** |
| Contradiction detection | 50% recall | **85%** recall |
| Hallucination prevention | Manual review | **95%** auto-caught |

## Consequences

### Positive
- Semantic search understands intent, not just keywords
- Relationships emerge automatically from content
- System improves with usage (SONA)
- Hallucinations caught before they compound
- Scales to millions of pages

### Negative
- RuVector dependency and operational complexity
- Higher compute costs (embedding, GNN)
- More complex debugging
- Cold start requires initial training

### Mitigations
- Fallback to FTS5 if RuVector unavailable
- Batch embedding during off-peak hours
- Comprehensive observability
- Pre-trained models for common domains

## References

- [Karpathy's Compounding Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [ADR-056: Compounding Wiki Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-055: Knowledge Base Agents](./ADR-055-knowledge-base-agents.md)
- [ADR-052: RuVector Integration Vision](./ADR-052-ruvector-integration-vision.md)
- [RuVector Documentation](https://github.com/ruvnet/ruvector)
