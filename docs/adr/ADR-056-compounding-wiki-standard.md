# ADR-056: Compounding Wiki - Standard Implementation

## Status
Proposed

## Context

summarybot-ng generates summaries from Discord and Slack conversations that are delivered and largely forgotten. Each summary exists in isolation - knowledge is extracted but doesn't compound over time.

Inspired by [Karpathy's Compounding Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), we propose building a **persistent, incrementally-maintained knowledge artifact** where an LLM agent doesn't just summarize conversations but actively builds and maintains a structured wiki that grows more valuable with each interaction.

The core insight: **knowledge should compound, not be re-derived**.

## Decision

Implement a Compounding Wiki system using standard technologies (markdown files, SQLite FTS, git) without specialized vector databases. This provides a foundation that can be enhanced with RuVector in the future (see ADR-057).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      COMPOUNDING WIKI ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     LAYER 3: SCHEMA                              │   │
│  │  wiki-schema.md - Structure, conventions, agent instructions     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     LAYER 2: THE WIKI                            │   │
│  │                                                                   │   │
│  │   wiki/                                                          │   │
│  │   ├── index.md          # Content catalog by category            │   │
│  │   ├── log.md            # Append-only operation log              │   │
│  │   ├── topics/           # Topic pages                            │   │
│  │   │   ├── authentication.md                                      │   │
│  │   │   ├── deployment.md                                          │   │
│  │   │   └── rate-limiting.md                                       │   │
│  │   ├── decisions/        # Architectural decisions                │   │
│  │   │   ├── 2024-01-use-postgres.md                               │   │
│  │   │   └── 2024-02-jwt-tokens.md                                 │   │
│  │   ├── processes/        # Documented workflows                   │   │
│  │   │   ├── deploy-to-production.md                               │   │
│  │   │   └── handle-incident.md                                    │   │
│  │   ├── experts/          # Who knows what                         │   │
│  │   │   └── expertise-map.md                                      │   │
│  │   └── questions/        # Open questions / knowledge gaps        │   │
│  │       └── unanswered.md                                         │   │
│  │                                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     LAYER 1: RAW SOURCES                         │   │
│  │                                                                   │   │
│  │   sources/                                                       │   │
│  │   ├── summaries/        # Generated summaries (immutable)        │   │
│  │   │   ├── 2024-01-15-backend-standup.md                         │   │
│  │   │   └── 2024-01-16-incident-postmortem.md                     │   │
│  │   ├── archives/         # Imported chat archives                 │   │
│  │   └── documents/        # External docs, RFCs, etc.              │   │
│  │                                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Workflows

### 1. Ingest Operation

When a new summary is generated, the Wiki Agent:

```python
class WikiIngestAgent:
    """
    Ingests new sources into the compounding wiki.
    """

    async def ingest(self, source: Source) -> IngestResult:
        # 1. Read and understand the source
        summary = await self.summarize_source(source)

        # 2. Identify affected wiki pages (10-15 typically)
        affected_pages = await self.identify_affected_pages(summary)

        # 3. Update each affected page
        updates = []
        for page in affected_pages:
            update = await self.update_page(page, source, summary)
            updates.append(update)

        # 4. Check for contradictions with existing knowledge
        contradictions = await self.detect_contradictions(updates)

        # 5. Create new pages if topics don't exist
        new_pages = await self.create_missing_pages(summary)

        # 6. Update cross-references
        await self.update_links(updates + new_pages)

        # 7. Append to operation log
        await self.append_log(
            operation="ingest",
            source=source.id,
            pages_updated=len(updates),
            pages_created=len(new_pages),
            contradictions=contradictions
        )

        return IngestResult(
            updates=updates,
            new_pages=new_pages,
            contradictions=contradictions
        )
```

**Example Flow**:

1. Summary mentions "We decided to use Redis for caching"
2. Agent updates `wiki/topics/caching.md` with Redis decision
3. Agent updates `wiki/decisions/2024-01-caching-strategy.md`
4. Agent updates `wiki/experts/expertise-map.md` (who participated)
5. Agent checks if this contradicts prior "use Memcached" mention
6. Agent adds cross-links between related pages
7. Agent logs the operation

### 2. Query Operation

Users query the wiki; valuable analysis becomes permanent:

```python
class WikiQueryAgent:
    """
    Answers questions using wiki knowledge.
    Valuable explorations become new wiki content.
    """

    async def query(self, question: str, user_id: str) -> QueryResult:
        # 1. Search wiki for relevant pages
        relevant_pages = await self.search_wiki(question)

        # 2. Synthesize answer with citations
        answer = await self.synthesize_answer(question, relevant_pages)

        # 3. Determine if this exploration is worth persisting
        if await self.is_valuable_exploration(question, answer):
            # File the analysis as a new wiki page
            new_page = await self.persist_exploration(question, answer)
            await self.append_log(
                operation="query_persist",
                question=question,
                new_page=new_page.path
            )

        # 4. Identify knowledge gaps
        gaps = await self.identify_gaps(question, answer)
        if gaps:
            await self.update_questions_page(gaps)

        return QueryResult(
            answer=answer,
            citations=relevant_pages,
            gaps=gaps
        )
```

### 3. Maintenance (Lint) Operation

Periodic wiki hygiene:

```python
class WikiMaintenanceAgent:
    """
    Audits and maintains wiki quality.
    """

    async def lint(self) -> LintResult:
        issues = []

        # 1. Find contradictions between pages
        contradictions = await self.find_contradictions()
        issues.extend(contradictions)

        # 2. Find orphaned pages (no inbound links)
        orphans = await self.find_orphans()
        issues.extend(orphans)

        # 3. Find missing cross-references
        missing_links = await self.find_missing_links()
        issues.extend(missing_links)

        # 4. Find stale content (not updated in 30+ days)
        stale = await self.find_stale_content()
        issues.extend(stale)

        # 5. Auto-fix what we can
        auto_fixed = await self.auto_fix(issues)

        # 6. Flag remaining issues for human review
        human_review = [i for i in issues if i not in auto_fixed]

        await self.append_log(
            operation="lint",
            issues_found=len(issues),
            auto_fixed=len(auto_fixed),
            needs_review=len(human_review)
        )

        return LintResult(
            issues=issues,
            auto_fixed=auto_fixed,
            needs_review=human_review
        )
```

---

## Search Implementation

Without RuVector, we use SQLite FTS5 for full-text search:

```sql
-- Wiki page index for full-text search
CREATE VIRTUAL TABLE wiki_fts USING fts5(
    path,
    title,
    content,
    topics,
    tokenize='porter unicode61'
);

-- Trigger to keep FTS in sync
CREATE TRIGGER wiki_fts_update AFTER UPDATE ON wiki_pages BEGIN
    DELETE FROM wiki_fts WHERE path = OLD.path;
    INSERT INTO wiki_fts(path, title, content, topics)
    VALUES (NEW.path, NEW.title, NEW.content, NEW.topics);
END;
```

```python
class WikiSearch:
    """
    Full-text search over wiki content using SQLite FTS5.
    """

    async def search(self, query: str, limit: int = 10) -> List[WikiPage]:
        # Use BM25 ranking
        results = await self.db.execute("""
            SELECT path, title, snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 32)
            FROM wiki_fts
            WHERE wiki_fts MATCH ?
            ORDER BY bm25(wiki_fts)
            LIMIT ?
        """, (query, limit))

        return [WikiPage.from_row(r) for r in results]
```

---

## Schema Definition

The wiki schema defines structure and agent behavior:

```markdown
# wiki-schema.md

## Wiki Structure

### Topic Pages (`wiki/topics/`)
- One page per major concept
- Include: definition, context, related topics, source citations
- Maximum 500 lines per page (split if larger)

### Decision Pages (`wiki/decisions/`)
- Format: `YYYY-MM-topic-slug.md`
- Include: context, decision, rationale, participants, alternatives considered
- Link to relevant topic pages

### Process Pages (`wiki/processes/`)
- Step-by-step workflows
- Include: prerequisites, steps, troubleshooting, related processes

### Expertise Map (`wiki/experts/`)
- Track who knows what based on contributions
- Update on every ingest

## Agent Instructions

### On Ingest
1. Always update 10-15 existing pages minimum
2. Flag contradictions prominently with `> ⚠️ CONTRADICTION:`
3. Add source citations in format `[source:id]`
4. Update expertise map based on participants

### On Query
1. Cite specific wiki pages in answers
2. Persist explorations that synthesize 3+ pages
3. Never invent information not in wiki

### On Lint
1. Run daily at 3am UTC
2. Auto-fix: orphaned pages (add to index), missing links
3. Flag for review: contradictions, stale content >30 days
```

---

## Database Schema

```sql
-- Wiki pages metadata
CREATE TABLE wiki_pages (
    id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    topics TEXT,  -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    source_refs TEXT,  -- JSON array of source IDs
    inbound_links INTEGER DEFAULT 0,
    outbound_links INTEGER DEFAULT 0
);

-- Page links (for orphan detection, link graph)
CREATE TABLE wiki_links (
    from_page TEXT NOT NULL,
    to_page TEXT NOT NULL,
    link_text TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (from_page, to_page),
    FOREIGN KEY (from_page) REFERENCES wiki_pages(path) ON DELETE CASCADE,
    FOREIGN KEY (to_page) REFERENCES wiki_pages(path) ON DELETE CASCADE
);

-- Operation log (append-only)
CREATE TABLE wiki_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    operation TEXT NOT NULL,  -- ingest, query, query_persist, lint
    details TEXT NOT NULL,  -- JSON
    agent_id TEXT
);

-- Contradictions (for human review)
CREATE TABLE wiki_contradictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_a TEXT NOT NULL,
    page_b TEXT NOT NULL,
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    detected_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    resolution TEXT,
    FOREIGN KEY (page_a) REFERENCES wiki_pages(path),
    FOREIGN KEY (page_b) REFERENCES wiki_pages(path)
);

-- Source documents (immutable)
CREATE TABLE wiki_sources (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,  -- summary, archive, document
    content TEXT NOT NULL,
    metadata TEXT,  -- JSON
    ingested_at TEXT DEFAULT (datetime('now')),
    guild_id TEXT
);

-- Indexes
CREATE INDEX idx_pages_updated ON wiki_pages(updated_at);
CREATE INDEX idx_pages_topics ON wiki_pages(topics);
CREATE INDEX idx_log_operation ON wiki_log(operation);
CREATE INDEX idx_sources_guild ON wiki_sources(guild_id);
```

---

## Integration with summarybot-ng

```
┌─────────────────────────────────────────────────────────────────┐
│                    SUMMARYBOT INTEGRATION                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Summary Generated                                              │
│         │                                                        │
│         ▼                                                        │
│   ┌─────────────────┐                                           │
│   │ Store Summary   │───────────────────────┐                   │
│   │ (existing flow) │                       │                   │
│   └─────────────────┘                       │                   │
│         │                                    │                   │
│         ▼                                    ▼                   │
│   ┌─────────────────┐              ┌─────────────────┐          │
│   │ Deliver to User │              │ Wiki Ingest     │          │
│   │ (Discord/Slack) │              │ Agent           │          │
│   └─────────────────┘              └─────────────────┘          │
│                                           │                      │
│                                           ▼                      │
│                                    ┌─────────────────┐          │
│                                    │ Update Wiki     │          │
│                                    │ (10-15 pages)   │          │
│                                    └─────────────────┘          │
│                                           │                      │
│   Dashboard                               ▼                      │
│   ┌─────────────────┐              ┌─────────────────┐          │
│   │ /wiki endpoint  │◀────────────│ Searchable Wiki │          │
│   │ (browse/search) │              │ Knowledge Base  │          │
│   └─────────────────┘              └─────────────────┘          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Limitations (Without RuVector)

| Capability | Standard Implementation | Limitation |
|------------|------------------------|------------|
| Search | SQLite FTS5 (keyword-based) | No semantic similarity |
| Contradiction Detection | LLM comparison | No vector clustering |
| Related Pages | Explicit links only | No automatic discovery |
| Expertise Inference | Rule-based from participation | No graph analysis |
| Knowledge Decay | Manual staleness tracking | No temporal learning |
| Query Understanding | Keyword matching | No intent inference |

These limitations are addressed in ADR-057 (RuVector implementation).

---

## Implementation Phases

### Phase 1: Foundation (3 weeks)
- [ ] Database schema migration
- [ ] Wiki directory structure
- [ ] Basic ingest agent (summary → wiki updates)
- [ ] SQLite FTS5 search

### Phase 2: Operations (3 weeks)
- [ ] Query agent with citations
- [ ] Exploration persistence
- [ ] Lint agent (contradictions, orphans)
- [ ] Operation logging

### Phase 3: Dashboard (2 weeks)
- [ ] Wiki browse UI
- [ ] Search interface
- [ ] Contradiction review queue
- [ ] Operation history

### Phase 4: Automation (2 weeks)
- [ ] Scheduled lint runs
- [ ] Summary auto-ingest hook
- [ ] Knowledge gap reporting

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Wiki pages | >500 after 3 months | Page count |
| Cross-references | >5 links per page avg | Link density |
| Search satisfaction | >70% click-through | Query logs |
| Contradiction resolution | <48h average | Time to resolve |
| Knowledge reuse | >30% queries cite wiki | Citation rate |

## Consequences

### Positive
- Knowledge compounds over time instead of being lost
- Organizational decisions become discoverable
- Expertise maps emerge automatically
- Single source of truth for team knowledge

### Negative
- Additional compute for ingest operations
- Risk of hallucination accumulation
- No semantic search (keyword-only)
- Limited automatic relationship discovery

### Mitigations
- Human review queue for contradictions
- Source citations required for all claims
- Regular lint operations
- Upgrade path to RuVector (ADR-057)

## References

- [Karpathy's Compounding Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [ADR-055: Knowledge Base Agents](./ADR-055-knowledge-base-agents.md)
- [ADR-057: Compounding Wiki with RuVector](./ADR-057-compounding-wiki-ruvector.md)
