# RuVector Knowledge System

## Overview

RuVector is a vector-based knowledge extraction and retrieval system that transforms conversation summaries into queryable knowledge units. It operates alongside the traditional wiki system, providing semantic search capabilities over organizational knowledge.

## Core Concept

### The Knowledge Unit Model

Traditional summarization produces prose - human-readable paragraphs that capture the essence of conversations. RuVector takes a different approach: it decomposes summaries into atomic **knowledge units**.

A knowledge unit is a single, self-contained piece of information with:
- **Content**: The actual knowledge (a claim, decision, question, or action item)
- **Type**: Classification (claim, decision, question, action_item, context)
- **Source**: Where it came from (summary ID, channel, date)
- **Embedding**: A 1536-dimensional vector representation for semantic search
- **Confidence**: How reliable the extraction is (0-1 scale)

### Example Transformation

**Input Summary:**
> "The team decided to migrate from PostgreSQL to SQLite for the embedded deployment. John will create the migration scripts by Friday. There was discussion about whether to use an ORM, but no conclusion was reached."

**Output Knowledge Units:**

| Type | Content | Confidence |
|------|---------|------------|
| decision | Team decided to migrate from PostgreSQL to SQLite for embedded deployment | 0.95 |
| action_item | John will create migration scripts by Friday | 0.90 |
| question | Whether to use an ORM (unresolved) | 0.85 |
| context | Discussion was about database technology choices | 0.80 |

## Architecture

### Data Flow

```
Discord/WhatsApp Messages
         │
         ▼
    ┌─────────────┐
    │   Summary   │  ← LLM generates prose summary
    │  Generator  │
    └─────────────┘
         │
         ▼
    ┌─────────────┐
    │    Wiki     │  ← Traditional wiki pages (prose)
    │   Ingest    │
    │   Agent     │
    └──────┬──────┘
           │
           │ (dual-write when enabled)
           ▼
    ┌─────────────┐
    │  RuVector   │  ← Knowledge unit extraction
    │   Ingest    │
    │    Hook     │
    └──────┬──────┘
           │
           ▼
    ┌─────────────────────────────────────┐
    │         RuVector Storage            │
    │  ┌─────────────────────────────┐    │
    │  │   wiki_knowledge_units      │    │
    │  │   - content (text)          │    │
    │  │   - unit_type (enum)        │    │
    │  │   - embedding (1536-dim)    │    │
    │  │   - source metadata         │    │
    │  └─────────────────────────────┘    │
    │  ┌─────────────────────────────┐    │
    │  │   wiki_edges                │    │
    │  │   - from_unit_id            │    │
    │  │   - to_unit_id              │    │
    │  │   - edge_type               │    │
    │  │   - weight                  │    │
    │  └─────────────────────────────┘    │
    └─────────────────────────────────────┘
```

### Components

#### 1. Knowledge Extractor
Parses summary text and extracts discrete knowledge units. Uses pattern matching and LLM assistance to identify:
- **Claims**: Factual statements ("We use React for the frontend")
- **Decisions**: Choices made by the team ("Decided to use JWT for auth")
- **Questions**: Unresolved topics ("Should we add caching?")
- **Action Items**: Tasks assigned to people ("Alice will review the PR")
- **Context**: Background information ("This relates to the Q3 roadmap")

#### 2. Embedding Generator
Converts knowledge unit text into vector embeddings using OpenAI's `text-embedding-3-small` model (1536 dimensions). These embeddings enable semantic similarity search.

#### 3. Vector Store
SQLite-based storage for knowledge units and their embeddings. Supports:
- Batch insertion with upsert semantics
- Similarity search using cosine distance
- Filtering by guild, channel, date range, unit type

#### 4. Edge Inference Engine
Automatically discovers relationships between knowledge units:
- **relates_to**: General topical relationship
- **depends_on**: One unit requires another
- **contradicts**: Units that conflict
- **supersedes**: Newer information replacing old
- **supports**: Evidence for a claim

#### 5. SONA Learning System
Tracks user interactions to learn relevance:
- Search clicks and refinements
- Dwell time on results
- Explicit feedback signals
- Used to re-rank search results over time

## Database Schema

### wiki_knowledge_units
```sql
CREATE TABLE wiki_knowledge_units (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    content TEXT NOT NULL,
    unit_type TEXT NOT NULL,  -- claim, decision, question, action_item, context
    source_id TEXT NOT NULL,  -- Reference to summary
    source_type TEXT NOT NULL,  -- summary, message, archive, human_edit
    source_channel TEXT,
    source_date TEXT,
    embedding BLOB,  -- 1536-dim float32 vector
    embedding_model TEXT DEFAULT 'text-embedding-3-small',
    confidence REAL DEFAULT 1.0,
    summary_id TEXT,  -- Direct link to stored_summary
    extraction_source TEXT DEFAULT 'manual',  -- manual, auto, backfill
    created_at TEXT,
    updated_at TEXT
);
```

### wiki_edges
```sql
CREATE TABLE wiki_edges (
    id INTEGER PRIMARY KEY,
    guild_id TEXT NOT NULL,
    from_unit_id TEXT NOT NULL,
    to_unit_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,  -- relates_to, depends_on, contradicts, supersedes, supports
    weight REAL DEFAULT 1.0,
    inferred_by TEXT DEFAULT 'gnn',  -- gnn, manual, coherence_gate
    created_at TEXT
);
```

### wiki_learning_signals
```sql
CREATE TABLE wiki_learning_signals (
    id INTEGER PRIMARY KEY,
    guild_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,  -- search_click, dwell, refinement, feedback, page_view
    unit_id TEXT,
    context TEXT NOT NULL,  -- JSON with query, results, position, etc.
    user_id TEXT,
    created_at TEXT
);
```

## Features

### 1. Semantic Search
Query knowledge by meaning, not just keywords:
- "What decisions were made about authentication?" finds units about JWT, OAuth, sessions
- "Who is responsible for the API?" finds action items mentioning API work
- Results ranked by embedding similarity

### 2. Knowledge Graph Navigation
Explore connected knowledge:
- Start with one unit, follow edges to related units
- Visualize decision chains and their supporting context
- Identify contradictions between old and new information

### 3. Temporal Queries
Filter knowledge by time:
- "What did we decide last month?"
- "Show me unresolved questions from Q1"
- Track how knowledge evolves over time

### 4. Source Traceability
Every unit links back to its source:
- Click through to the original summary
- See the full context of when knowledge was captured
- Audit trail for compliance

### 5. Coherence Validation
Quality gates for new knowledge:
- Detect contradictions with existing units
- Flag low-confidence extractions for review
- Prevent knowledge drift

### 6. Ingestion Tracking
Know what has been processed:
- `vector_ingested` flag on summaries
- `vector_unit_count` shows extraction yield
- Find gaps in knowledge coverage

## Configuration

### Guild Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `wiki_auto_ingest` | true | Enable wiki page generation |
| `wiki_ingest_to_vectors` | false | Enable RuVector dual-write |

### Enabling RuVector

1. Navigate to Wiki settings in the dashboard
2. Toggle "Ingest to Vectors" on
3. New summaries will automatically extract knowledge units
4. Run backfill to process existing summaries

## Tradeoffs

### RuVector vs Traditional Wiki

| Aspect | Wiki Pages | RuVector |
|--------|------------|----------|
| **Format** | Prose paragraphs | Atomic units |
| **Search** | Full-text keyword | Semantic similarity |
| **Navigation** | Hierarchical pages | Graph traversal |
| **Readability** | Human-optimized | Machine-optimized |
| **Updates** | Append to pages | Add new units |
| **Contradictions** | Manual detection | Automatic flagging |
| **Storage** | Text only | Text + embeddings |
| **Query cost** | Fast (index lookup) | Slower (vector similarity) |

### When to Use Each

**Use Wiki Pages when:**
- Users need to read and understand context
- Information is frequently accessed by humans
- Narrative flow matters
- Storage cost is a concern

**Use RuVector when:**
- Searching for specific facts across large history
- Building automated knowledge retrieval (RAG)
- Detecting contradictions or knowledge gaps
- Answering questions programmatically

### Combined Approach (Recommended)

Enable both systems (dual-write mode):
- Wiki pages for human consumption
- RuVector for machine queries and semantic search
- Same source data, different access patterns

## API Integration

### Querying Knowledge Units

```python
# Search by semantic similarity
results = await vector_store.search_similar(
    guild_id="123",
    query_embedding=embed("authentication decisions"),
    limit=10,
    unit_types=["decision", "claim"]
)

# Get units from a specific summary
units = await vector_store.get_units_by_summary(
    summary_id="sum_abc123"
)

# Find contradictions
contradictions = await coherence_gate.find_contradictions(
    guild_id="123",
    new_unit=unit
)
```

### Checking Ingestion Status

```python
# Check if summary was vectorized
summary = await repo.get(summary_id)
if summary.vector_ingested:
    print(f"Vectorized: {summary.vector_unit_count} units")
    print(f"At: {summary.vector_ingested_at}")

# Find summaries pending vectorization
pending = await repo.find_not_vector_ingested(guild_id)
```

## Performance Characteristics

### Extraction
- ~500ms per summary (LLM extraction)
- Batched embedding generation
- Async edge inference

### Storage
- ~6KB per unit (content + embedding)
- Indexed by guild, source, type, date
- SQLite with WAL mode for concurrency

### Search
- ~50ms for similarity search (small corpus)
- Linear scan over embeddings (no ANN index yet)
- Future: HNSW index for sub-linear search

## Future Enhancements

### Planned
1. **HNSW Index**: Sub-linear similarity search for large corpora
2. **Raw Message Ingestion**: Extract units directly from messages (higher granularity)
3. **Cross-Guild Knowledge**: Shared knowledge bases across organizations
4. **Human Curation UI**: Review and edit extracted units
5. **RAG Integration**: Use units as context for LLM responses

### Under Consideration
1. **Prose Derivation**: Generate summaries from knowledge units (inverse of current flow)
2. **Knowledge Decay**: Reduce confidence of old, unvalidated units
3. **Multi-Modal Units**: Support for images, code snippets, diagrams

## Glossary

- **Knowledge Unit**: An atomic piece of extractable information
- **Embedding**: Vector representation of text for similarity comparison
- **Edge**: Relationship between two knowledge units
- **Dual-Write**: Simultaneously writing to wiki pages and RuVector
- **Coherence Gate**: Validation layer that checks new knowledge for conflicts
- **SONA**: Self-Organizing Neural Architecture for relevance learning
- **Backfill**: Processing historical summaries to populate RuVector

## Related Documentation

- ADR-057: RuVector Foundation
- ADR-088: Wiki Vector Ingestion Toggle
- ADR-090: Dual-Write Mode
- ADR-093: Vector Ingestion Tracking
