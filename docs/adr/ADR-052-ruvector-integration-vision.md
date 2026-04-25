# ADR-052: RuVector Integration Vision

## Status
Proposed

## Context

summarybot-ng is a multi-platform messaging summarization service supporting Discord and Slack (ADR-051). As the system grows, we need:

1. **Semantic Search**: Find summaries by meaning, not just keywords
2. **Agent Memory**: Persistent context across QE agent sessions
3. **Self-Learning**: System that improves with usage patterns
4. **Edge Deployment**: Local inference for privacy-sensitive deployments

[RuVector](https://github.com/ruvnet/ruvector) is a high-performance, self-learning vector database with GNN capabilities that could address these needs.

## RuVector Capabilities

### Core Features
- **HNSW Vector Search**: Sub-linear similarity search at scale
- **Graph Neural Networks**: 39 attention mechanisms for relational reasoning
- **SONA**: Self-Optimizing Neural Architecture for continuous improvement
- **ruvllm**: Local LLM inference without cloud dependencies
- **Multi-Platform**: WASM, PostgreSQL extension, rvLite for edge

### Relevant Components
| Component | Application |
|-----------|-------------|
| Vector Engine | Semantic summary search |
| GNN Layer | Conversation topology modeling |
| Temporal Learning | Query pattern optimization |
| rvLite | Edge/offline summarization |
| Coherence Gate | Hallucination prevention |

## Proposed Integration Phases

### Phase 1: Semantic Summary Search
**Goal**: Enable "find summaries about X" across all stored content

```
User Query: "discussions about authentication"
           ↓
    RuVector HNSW Search
           ↓
    Top-K Similar Summaries
           ↓
    Ranked Results with Scores
```

**Implementation**:
- Embed summary_text using sentence transformers
- Store vectors in RuVector with metadata (guild_id, channel_ids, created_at)
- Query API: `GET /guilds/{id}/summaries/search?q=semantic+query`
- Self-learning improves relevance over time

### Phase 2: Agent Memory System
**Goal**: Persistent memory for QE agents across sessions

```
QE Agent Session
    ↓
Learn Pattern (e.g., "coverage gaps in auth module")
    ↓
Store in RuVector: {
  pattern: "coverage-gap",
  context: embedded_vector,
  confidence: 0.95,
  learned_at: timestamp
}
    ↓
Future Sessions Query Similar Patterns
```

**Benefits**:
- Cross-session learning for QE fleet
- Pattern deduplication via similarity
- Automatic knowledge consolidation

### Phase 3: Conversation Graph Analysis
**Goal**: Model relationships between users, channels, and topics

```
Discord/Slack Messages
    ↓
GNN Processing (Graph Attention Network)
    ↓
Derived Insights:
- Key influencers per channel
- Topic clusters
- Cross-channel connections
- Sentiment trajectories
```

**Use Cases**:
- Smart channel recommendations for summaries
- Influence-weighted action item assignment
- Topic drift detection in scheduled summaries

### Phase 4: Edge Summarization
**Goal**: Local summarization for privacy-sensitive deployments

```
Enterprise Deployment
    ↓
rvLite + ruvllm (on-premise)
    ↓
Local Inference:
- No cloud API calls
- Data never leaves network
- Full offline capability
```

**Architecture**:
```
┌─────────────────────────────────────────┐
│           Enterprise Network            │
│  ┌─────────────┐    ┌───────────────┐  │
│  │ summarybot  │───▶│   rvLite      │  │
│  │   -ng       │    │   + ruvllm    │  │
│  └─────────────┘    └───────────────┘  │
│         │                   │           │
│         ▼                   ▼           │
│  ┌─────────────┐    ┌───────────────┐  │
│  │  Slack/     │    │ Local Vector  │  │
│  │  Discord    │    │    Search     │  │
│  └─────────────┘    └───────────────┘  │
└─────────────────────────────────────────┘
```

### Phase 5: Self-Optimizing Pipeline
**Goal**: System learns optimal summarization strategies

```
Usage Patterns Observed:
- User edits summaries (quality signal)
- Summaries pushed to channels (value signal)
- Search refinements (relevance signal)
           ↓
SONA Temporal Learning
           ↓
Automatic Adjustments:
- Prompt template selection
- Summary length optimization
- Key point extraction tuning
```

## Technical Integration

### Database Schema Extension

```sql
-- Vector embeddings for summaries
CREATE TABLE summary_vectors (
    summary_id TEXT PRIMARY KEY REFERENCES stored_summaries(id),
    embedding BLOB NOT NULL,  -- RuVector format
    model_version TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent memory patterns
CREATE TABLE agent_patterns (
    id TEXT PRIMARY KEY,
    pattern_type TEXT NOT NULL,
    embedding BLOB NOT NULL,
    confidence REAL DEFAULT 0.5,
    usage_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP
);
```

### API Extensions

```python
# Semantic search endpoint
@router.get("/guilds/{guild_id}/summaries/semantic-search")
async def semantic_search(
    guild_id: str,
    query: str,
    limit: int = 10,
    threshold: float = 0.7
) -> List[SemanticSearchResult]:
    # Embed query
    query_vector = await ruvector.embed(query)

    # Search with self-learning feedback
    results = await ruvector.search(
        vector=query_vector,
        filter={"guild_id": guild_id},
        limit=limit,
        min_score=threshold,
        learn=True  # SONA feedback
    )

    return results
```

### WASM Browser Integration

```typescript
// Client-side semantic search preview
import { RuVectorWasm } from '@ruvector/wasm';

const ruvector = await RuVectorWasm.init();

// Local embedding + search (no server round-trip)
const results = await ruvector.search({
  query: userInput,
  index: cachedSummaryVectors,
  topK: 5
});
```

## Migration Path

1. **Current State**: SQLite FTS5 for keyword search
2. **Phase 1**: Add RuVector alongside FTS5 (dual search)
3. **Phase 2**: Migrate to RuVector primary, FTS5 fallback
4. **Phase 3**: Full RuVector with GNN and self-learning
5. **Phase 4**: Edge deployment options

## Dependencies

- RuVector: MIT licensed, Rust-based
- Embedding model: sentence-transformers or local
- WASM runtime: Modern browsers
- rvLite: For edge deployments

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Performance regression | Benchmark against FTS5 baseline |
| Model size (edge) | Quantized models, lazy loading |
| Learning drift | Coherence gate validation |
| Data migration | Incremental vectorization |

## Success Metrics

- Semantic search relevance: >80% user satisfaction
- Query latency: <100ms p99
- Agent memory recall: >90% pattern retrieval
- Edge inference: <500ms summary generation

## Decision

**Proposed** - Pending team review and proof-of-concept

## References

- [RuVector GitHub](https://github.com/ruvnet/ruvector)
- [ADR-051: Platform Message Fetcher Abstraction](./ADR-051-platform-message-fetcher-abstraction.md)
- [HNSW Algorithm](https://arxiv.org/abs/1603.09320)
- [SONA Architecture](https://github.com/ruvnet/ruvector#sona)
