# ADR-055: Knowledge Base Agents - From Capture to Enrichment

## Status
Proposed

## Context

summarybot-ng captures vast amounts of organizational knowledge through Discord and Slack conversations. Currently, this knowledge exists only in ephemeral summaries - generated, delivered, and largely forgotten. The real value lies not in individual summaries but in the **accumulated wisdom** they represent.

With RuVector's self-learning capabilities (ADR-052), we can build a **living knowledge base** that:

1. **Captures** insights from chat platforms automatically
2. **Distills** raw conversation data into structured knowledge
3. **Enriches** through human feedback and validation
4. **Evolves** via SONA temporal learning

This ADR proposes a system of specialized agents that manage the complete knowledge lifecycle, powered by RuVector Brain.

## Decision

Implement a knowledge base system with four agent roles operating across three phases:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE LIFECYCLE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   CAPTURE              DISTILLATION              ENRICHMENT             │
│   ───────              ────────────              ──────────             │
│                                                                          │
│   ┌─────────┐         ┌─────────────┐          ┌───────────────┐       │
│   │ Message │         │   Pattern   │          │    Human      │       │
│   │ Stream  │────────▶│  Extractor  │─────────▶│  Curator      │       │
│   └─────────┘         └─────────────┘          └───────────────┘       │
│        │                    │                         │                 │
│        ▼                    ▼                         ▼                 │
│   ┌─────────┐         ┌─────────────┐          ┌───────────────┐       │
│   │ Summary │         │  Knowledge  │          │   Feedback    │       │
│   │ Archive │────────▶│  Synthesizer│─────────▶│   Integrator  │       │
│   └─────────┘         └─────────────┘          └───────────────┘       │
│                             │                         │                 │
│                             ▼                         ▼                 │
│                    ┌─────────────────────────────────────────┐         │
│                    │           RUVECTOR BRAIN                │         │
│                    │  ┌─────────┐  ┌─────────┐  ┌─────────┐  │         │
│                    │  │  HNSW   │  │   GNN   │  │  SONA   │  │         │
│                    │  │ Vectors │  │  Graph  │  │ Learner │  │         │
│                    │  └─────────┘  └─────────┘  └─────────┘  │         │
│                    └─────────────────────────────────────────┘         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Capture

### Knowledge Capture Agent

**Purpose**: Extract knowledge signals from raw conversation streams

**Inputs**:
- Real-time messages from Discord/Slack (via platform fetchers)
- Generated summaries (stored_summaries table)
- User reactions and engagement signals

**Extraction Targets**:

| Signal Type | Description | Example |
|-------------|-------------|---------|
| Decisions | Explicit choices made | "We'll use PostgreSQL for this" |
| Learnings | Insights shared | "Turns out the API has a 100 req/s limit" |
| Questions | Unanswered knowledge gaps | "Does anyone know how to configure X?" |
| Expertise | Who knows what | User A consistently answers auth questions |
| Processes | Repeated workflows | "First we PR, then deploy to staging..." |
| Warnings | Pitfalls to avoid | "Don't use that endpoint, it's deprecated" |

**Implementation**:

```python
class KnowledgeCaptureAgent:
    """
    Extracts knowledge signals from conversation streams.

    Uses lightweight classification to identify knowledge-bearing messages
    without processing every message through expensive LLM calls.
    """

    async def process_message_batch(
        self,
        messages: List[ProcessedMessage],
        guild_id: str
    ) -> List[KnowledgeSignal]:
        # Stage 1: Fast filtering (WASM classifier)
        candidates = await self.classify_knowledge_potential(messages)

        # Stage 2: Signal extraction (only high-potential messages)
        signals = []
        for msg in candidates:
            if msg.knowledge_score > 0.7:
                signal = await self.extract_signal(msg)
                signals.append(signal)

        # Stage 3: Context linking
        return await self.link_to_context(signals, guild_id)

    async def process_summary(
        self,
        summary: StoredSummary
    ) -> List[KnowledgeSignal]:
        """
        Summaries are pre-distilled - extract structured knowledge:
        - Key decisions from summary text
        - Action items as process knowledge
        - Participants as expertise signals
        """
        return await self.extract_from_summary(summary)
```

**Output Schema**:

```yaml
knowledge_signal:
  id: uuid
  signal_type: decision|learning|question|expertise|process|warning
  content: "The extracted knowledge"
  confidence: 0.0-1.0
  source:
    platform: discord|slack
    guild_id: "..."
    channel_id: "..."
    message_id: "..."
    timestamp: ISO-8601
  participants:
    - user_id: "..."
      role: author|contributor|validator
  context:
    thread_id: "..."
    related_signals: [...]
```

---

## Phase 2: Distillation

### Knowledge Distillation Agent

**Purpose**: Transform raw signals into structured, searchable knowledge atoms

**Process**:

```
Raw Signals (noisy, redundant, contextual)
              │
              ▼
    ┌─────────────────────┐
    │  Deduplication      │  Remove near-duplicates via vector similarity
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Canonicalization   │  Normalize to standard form
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Contextualization  │  Add organizational context
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Vectorization      │  Generate embeddings for search
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Graph Integration  │  Link to knowledge graph
    └─────────────────────┘
              │
              ▼
Knowledge Atoms (clean, structured, connected)
```

**Knowledge Atom Schema**:

```yaml
knowledge_atom:
  id: uuid
  type: fact|procedure|expertise|decision|warning

  # Core content
  statement: "Canonical knowledge statement"
  summary: "One-line description"
  detail: "Extended explanation if available"

  # Provenance
  derived_from:
    - signal_id: "..."
      contribution_weight: 0.0-1.0
  first_observed: ISO-8601
  last_reinforced: ISO-8601
  observation_count: N

  # Classification
  topics: ["authentication", "api-design", ...]
  domain: "engineering|product|operations|..."
  scope: guild|channel|global

  # Confidence & Quality
  confidence: 0.0-1.0
  quality_score: 0.0-1.0
  human_validated: boolean
  contradictions: [...]

  # Vectors (stored in RuVector)
  embedding_id: "ruvector://..."

  # Graph relationships
  relates_to: [atom_ids...]
  supersedes: [atom_ids...]
  depends_on: [atom_ids...]
```

**GNN Integration**:

```python
class KnowledgeGraphBuilder:
    """
    Builds and maintains the knowledge graph using RuVector GNN layer.
    """

    async def integrate_atom(self, atom: KnowledgeAtom) -> None:
        # 1. Generate embedding
        embedding = await self.ruvector.embed(atom.statement)

        # 2. Find related atoms (HNSW search)
        related = await self.ruvector.search(
            embedding,
            limit=20,
            threshold=0.75
        )

        # 3. Determine relationship types (GNN inference)
        edges = await self.classify_relationships(atom, related)

        # 4. Update graph
        await self.ruvector.add_node(
            id=atom.id,
            embedding=embedding,
            metadata=atom.to_metadata(),
            edges=edges
        )

        # 5. Trigger SONA learning
        await self.ruvector.learn(
            context="knowledge_integration",
            signal={"atom_id": atom.id, "edges": len(edges)}
        )
```

---

## Phase 3: Enrichment

### Human Curation Agent

**Purpose**: Surface knowledge for human validation and enrichment

**Interaction Patterns**:

```
┌───────────────────────────────────────────────────────────────┐
│                    HUMAN ENRICHMENT LOOPS                      │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  1. VALIDATION                                                 │
│     ┌─────────────┐    "Is this accurate?"    ┌─────────────┐│
│     │  Knowledge  │◀──────────────────────────│   Human     ││
│     │    Atom     │──────────────────────────▶│  Curator    ││
│     └─────────────┘    ✓ Confirm / ✗ Reject   └─────────────┘│
│                                                                │
│  2. DISAMBIGUATION                                             │
│     ┌─────────────┐    "Which is correct?"    ┌─────────────┐│
│     │ Conflicting │◀──────────────────────────│   Human     ││
│     │   Atoms     │──────────────────────────▶│  Curator    ││
│     └─────────────┘    A / B / Both / Neither └─────────────┘│
│                                                                │
│  3. ELABORATION                                                │
│     ┌─────────────┐    "Can you add context?" ┌─────────────┐│
│     │  Sparse     │◀──────────────────────────│   Human     ││
│     │   Atom      │──────────────────────────▶│  Expert     ││
│     └─────────────┘    + Additional details   └─────────────┘│
│                                                                │
│  4. EXPERTISE MAPPING                                          │
│     ┌─────────────┐    "Who knows about X?"   ┌─────────────┐│
│     │   Topic     │◀──────────────────────────│   Team      ││
│     │   Cluster   │──────────────────────────▶│  Members    ││
│     └─────────────┘    @alice @bob            └─────────────┘│
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

**Curation Queue**:

```python
class CurationQueueManager:
    """
    Manages the queue of knowledge atoms requiring human attention.
    Prioritizes based on impact and uncertainty.
    """

    async def get_next_item(
        self,
        curator_id: str,
        expertise: List[str] = None
    ) -> CurationItem:
        # Priority scoring
        # 1. High-impact decisions with low confidence
        # 2. Contradictions between trusted sources
        # 3. Frequently accessed but unvalidated atoms
        # 4. Expertise gaps in critical domains

        return await self.queue.pop_highest_priority(
            filter_domains=expertise
        )

    async def process_feedback(
        self,
        item_id: str,
        curator_id: str,
        feedback: CurationFeedback
    ) -> None:
        # Update atom based on feedback
        atom = await self.get_atom(item_id)

        if feedback.action == "validate":
            atom.human_validated = True
            atom.confidence = min(1.0, atom.confidence + 0.2)

        elif feedback.action == "reject":
            atom.confidence = max(0.0, atom.confidence - 0.3)
            if atom.confidence < 0.3:
                await self.archive_atom(atom)

        elif feedback.action == "elaborate":
            await self.merge_elaboration(atom, feedback.content)

        # Feed back to SONA for learning
        await self.ruvector.learn(
            context="human_curation",
            signal={
                "curator_id": curator_id,
                "action": feedback.action,
                "atom_type": atom.type,
                "domain": atom.domain
            }
        )
```

**Dashboard Integration**:

```
┌─────────────────────────────────────────────────────────────┐
│  Knowledge Curation Dashboard                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  📊 Knowledge Health                                         │
│  ├── Total Atoms: 1,234                                      │
│  ├── Validated: 856 (69%)                                    │
│  ├── Pending Review: 142                                     │
│  └── Conflicts: 12                                           │
│                                                              │
│  🔥 Needs Attention                                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ "The rate limit for external API is 50 req/min"      │  │
│  │ 🏷️ api-integration  📈 High Impact  ⚠️ Unvalidated   │  │
│  │ [✓ Validate] [✗ Reject] [📝 Edit] [❓ Unsure]        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  💡 Recent Insights                                          │
│  • Authentication: 23 new atoms this week                    │
│  • Top expert: @alice (47 contributions)                     │
│  • Trending: "deployment procedures"                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## RuVector Brain Architecture

The central knowledge store leveraging RuVector's full capabilities:

```
┌─────────────────────────────────────────────────────────────────┐
│                       RUVECTOR BRAIN                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    HNSW VECTOR INDEX                     │   │
│  │  • Knowledge atom embeddings                             │   │
│  │  • Sub-linear similarity search                          │   │
│  │  • Multi-tenant isolation (per guild)                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    GNN KNOWLEDGE GRAPH                   │   │
│  │  Nodes: Knowledge atoms, Users, Topics, Channels         │   │
│  │  Edges: relates_to, authored_by, expert_in, supersedes   │   │
│  │                                                          │   │
│  │  Attention Mechanisms:                                   │   │
│  │  • Topic coherence (do atoms form consistent clusters?)  │   │
│  │  • Expertise inference (who knows what?)                 │   │
│  │  • Contradiction detection (conflicting atoms)           │   │
│  │  • Evolution tracking (how knowledge changes)            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    SONA TEMPORAL LEARNING                │   │
│  │                                                          │   │
│  │  Immediate (per-query):                                  │   │
│  │  • Click-through on search results → relevance signal    │   │
│  │  • Time-to-action after viewing → utility signal         │   │
│  │                                                          │   │
│  │  Session (per-user):                                     │   │
│  │  • Query refinement patterns → intent modeling           │   │
│  │  • Cross-reference navigation → relationship discovery   │   │
│  │                                                          │   │
│  │  Long-term (system-wide):                                │   │
│  │  • Curation outcomes → quality prediction                │   │
│  │  • Knowledge decay (stale atoms) → freshness scoring     │   │
│  │  • Domain evolution → ontology adaptation                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    COHERENCE GATE                        │   │
│  │  • Validates new atoms against existing knowledge        │   │
│  │  • Detects potential hallucinations from LLM extraction  │   │
│  │  • Flags contradictions for human review                 │   │
│  │  • Enforces consistency constraints                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agent Definitions

### 1. Knowledge Capture Agent

```yaml
# .claude/agents/v3/knowledge-capture.md
role: Knowledge Capture Agent
purpose: Extract knowledge signals from conversation streams

responsibilities:
  - Monitor message streams for knowledge-bearing content
  - Process summaries for structured knowledge extraction
  - Identify expertise signals from participation patterns
  - Track questions as knowledge gaps
  - Detect decisions and their rationale

triggers:
  - New summary generated
  - Batch of messages processed
  - User engagement signals (reactions, replies)

outputs:
  - KnowledgeSignal records
  - Expertise mappings
  - Knowledge gap identifications
```

### 2. Knowledge Distillation Agent

```yaml
# .claude/agents/v3/knowledge-distiller.md
role: Knowledge Distillation Agent
purpose: Transform raw signals into structured knowledge atoms

responsibilities:
  - Deduplicate similar knowledge signals
  - Canonicalize to standard knowledge forms
  - Generate vector embeddings
  - Build knowledge graph relationships
  - Identify contradictions and conflicts

triggers:
  - New knowledge signals captured
  - Periodic consolidation (hourly)
  - Graph integrity checks (daily)

outputs:
  - KnowledgeAtom records
  - Graph edges
  - Contradiction reports
```

### 3. Human Curation Agent

```yaml
# .claude/agents/v3/knowledge-curator.md
role: Human Curation Agent
purpose: Facilitate human validation and enrichment

responsibilities:
  - Prioritize atoms for human review
  - Present validation interfaces
  - Process feedback into atom updates
  - Route to domain experts
  - Track curator contributions

triggers:
  - Low-confidence high-impact atoms
  - Detected contradictions
  - Explicit curation requests
  - Periodic expert review queues

outputs:
  - Validation status updates
  - Elaboration merges
  - Expertise confirmations
```

### 4. Knowledge Query Agent

```yaml
# .claude/agents/v3/knowledge-query.md
role: Knowledge Query Agent
purpose: Answer questions using the knowledge base

responsibilities:
  - Semantic search across knowledge atoms
  - Graph traversal for related knowledge
  - Expertise routing ("who knows about X?")
  - Knowledge gap detection
  - Answer synthesis from multiple atoms

triggers:
  - User search queries
  - Summary generation (context retrieval)
  - Automated knowledge lookups
  - Bot commands (/know, /expert, /learn)

outputs:
  - Search results with confidence
  - Synthesized answers
  - Expert recommendations
  - Gap reports
```

---

## Database Schema

```sql
-- Knowledge signals (raw captures)
CREATE TABLE knowledge_signals (
    id TEXT PRIMARY KEY,
    signal_type TEXT NOT NULL,  -- decision, learning, question, expertise, process, warning
    content TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_platform TEXT NOT NULL,
    source_guild_id TEXT NOT NULL,
    source_channel_id TEXT,
    source_message_id TEXT,
    source_timestamp TEXT NOT NULL,
    participants TEXT NOT NULL,  -- JSON array
    context TEXT,  -- JSON object
    created_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT
);

-- Knowledge atoms (distilled knowledge)
CREATE TABLE knowledge_atoms (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,  -- fact, procedure, expertise, decision, warning
    statement TEXT NOT NULL,
    summary TEXT,
    detail TEXT,
    topics TEXT NOT NULL,  -- JSON array
    domain TEXT,
    scope TEXT DEFAULT 'guild',
    confidence REAL NOT NULL,
    quality_score REAL,
    human_validated BOOLEAN DEFAULT FALSE,
    first_observed TEXT NOT NULL,
    last_reinforced TEXT,
    observation_count INTEGER DEFAULT 1,
    embedding_id TEXT,  -- RuVector reference
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Atom provenance (which signals contributed)
CREATE TABLE atom_provenance (
    atom_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    contribution_weight REAL DEFAULT 1.0,
    PRIMARY KEY (atom_id, signal_id),
    FOREIGN KEY (atom_id) REFERENCES knowledge_atoms(id) ON DELETE CASCADE,
    FOREIGN KEY (signal_id) REFERENCES knowledge_signals(id) ON DELETE CASCADE
);

-- Knowledge graph edges
CREATE TABLE knowledge_edges (
    id INTEGER PRIMARY KEY,
    from_atom_id TEXT NOT NULL,
    to_atom_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,  -- relates_to, supersedes, depends_on, contradicts
    weight REAL DEFAULT 1.0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (from_atom_id) REFERENCES knowledge_atoms(id) ON DELETE CASCADE,
    FOREIGN KEY (to_atom_id) REFERENCES knowledge_atoms(id) ON DELETE CASCADE
);

-- Expertise mappings
CREATE TABLE user_expertise (
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    confidence REAL NOT NULL,
    contribution_count INTEGER DEFAULT 0,
    last_contribution TEXT,
    PRIMARY KEY (user_id, guild_id, topic)
);

-- Curation queue
CREATE TABLE curation_queue (
    id INTEGER PRIMARY KEY,
    atom_id TEXT NOT NULL,
    priority REAL NOT NULL,
    reason TEXT NOT NULL,  -- low_confidence, contradiction, high_impact, stale
    assigned_to TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    FOREIGN KEY (atom_id) REFERENCES knowledge_atoms(id) ON DELETE CASCADE
);

-- Curation history (for SONA learning)
CREATE TABLE curation_history (
    id INTEGER PRIMARY KEY,
    atom_id TEXT NOT NULL,
    curator_id TEXT NOT NULL,
    action TEXT NOT NULL,  -- validate, reject, elaborate, merge, supersede
    feedback TEXT,  -- JSON with details
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (atom_id) REFERENCES knowledge_atoms(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_signals_guild ON knowledge_signals(source_guild_id);
CREATE INDEX idx_signals_type ON knowledge_signals(signal_type);
CREATE INDEX idx_atoms_topics ON knowledge_atoms(topics);
CREATE INDEX idx_atoms_domain ON knowledge_atoms(domain);
CREATE INDEX idx_atoms_confidence ON knowledge_atoms(confidence);
CREATE INDEX idx_expertise_topic ON user_expertise(topic);
CREATE INDEX idx_queue_priority ON curation_queue(priority DESC);
```

---

## Implementation Phases

### Phase 1: Foundation (4 weeks)

- [ ] Database schema migration
- [ ] Knowledge signal extraction from summaries
- [ ] Basic knowledge atom creation
- [ ] RuVector HNSW integration for search

### Phase 2: Distillation (4 weeks)

- [ ] Signal deduplication pipeline
- [ ] Knowledge graph edge classification
- [ ] Contradiction detection
- [ ] GNN integration for relationship inference

### Phase 3: Enrichment (4 weeks)

- [ ] Curation queue UI in dashboard
- [ ] Validation workflow implementation
- [ ] SONA feedback integration
- [ ] Expertise mapping from curation patterns

### Phase 4: Intelligence (4 weeks)

- [ ] Knowledge query agent
- [ ] Bot commands (/know, /expert)
- [ ] Summary context retrieval
- [ ] Knowledge gap reporting

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Knowledge capture rate | >100 atoms/week/guild | Signal extraction volume |
| Distillation accuracy | >85% | Human validation of auto-atoms |
| Curation participation | >50% active users | Curators / total users |
| Search relevance | >80% satisfaction | Click-through + feedback |
| Query latency | <200ms p99 | RuVector search performance |
| Knowledge freshness | <30 days average age | Last reinforced timestamp |

## Consequences

### Positive

- Organizational knowledge becomes searchable and persistent
- Expertise becomes discoverable across the organization
- Decisions are traceable to their rationale
- Knowledge gaps are identified proactively
- System improves automatically via SONA learning

### Negative

- Increased storage and compute requirements
- Privacy considerations for knowledge attribution
- Risk of surfacing outdated or incorrect information
- Curation overhead for users

### Mitigations

- Tiered storage with embedding compression (REFRAG)
- Configurable attribution visibility
- Confidence scoring and staleness detection
- Gamification and async curation workflows

## References

- [ADR-052: RuVector Integration Vision](./ADR-052-ruvector-integration-vision.md)
- [ADR-054: Operational Agents](./ADR-054-operational-agents.md)
- [RuVector Documentation](https://github.com/ruvnet/ruvector)
- [SONA Temporal Learning](https://github.com/ruvnet/ruvector#sona)
