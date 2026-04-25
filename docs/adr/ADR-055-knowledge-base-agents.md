# ADR-055: Knowledge Base Agents - Enhancement Layer

## Status
Proposed (Depends on ADR-056/057)

## Context

summarybot-ng captures vast amounts of organizational knowledge through Discord and Slack conversations. The Compounding Wiki (ADR-056/057) provides the persistent, incrementally-maintained knowledge artifact where this knowledge lives.

This ADR defines **enhancement agents** that add capabilities on top of the wiki:

1. **Signal Classification** - Tag wiki content by knowledge type
2. **Expertise Mapping** - Track who knows what
3. **Gap Detection** - Identify missing knowledge
4. **Provenance Tracking** - Link claims to source conversations

## Relationship to Compounding Wiki

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE STACK                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              ADR-055: ENHANCEMENT LAYER                          │   │
│   │                                                                   │   │
│   │   Signal Classifier │ Expertise Mapper │ Gap Detector           │   │
│   │                                                                   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              ADR-056/057: COMPOUNDING WIKI                       │   │
│   │                                                                   │
│   │   Wiki Pages │ Ingest Agent │ Query Agent │ Lint Agent          │   │
│   │                                                                   │   │
│   │   ┌─────────────────────────────────────────────────────────┐   │   │
│   │   │  RuVector Brain (HNSW + GNN + SONA + Coherence Gate)    │   │   │
│   │   └─────────────────────────────────────────────────────────┘   │   │
│   │                                                                   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              SOURCES (Immutable)                                 │   │
│   │                                                                   │   │
│   │   Summaries │ Archives │ Documents                              │   │
│   │                                                                   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### What the Wiki Provides (ADR-056/057)

| Capability | Wiki Component |
|------------|----------------|
| Knowledge storage | Wiki pages (markdown) |
| Capture from summaries | Wiki Ingest Agent |
| Semantic search | HNSW + FTS5 |
| Relationship discovery | GNN / manual links |
| Contradiction detection | Coherence Gate / Lint |
| Human review | Wiki maintenance workflow |

### What This ADR Adds

| Capability | Enhancement Agent |
|------------|-------------------|
| Signal type tagging | Signal Classifier |
| Who knows what | Expertise Mapper |
| Missing knowledge | Gap Detector |
| Source → claim linking | Provenance Tracker |

## Decision

Implement four enhancement agents that enrich wiki content with metadata and intelligence not provided by the base wiki system.

---

## Enhancement Agent 1: Signal Classifier

**Purpose**: Classify wiki content by knowledge signal type

### Signal Types

| Type | Description | Example | Wiki Location |
|------|-------------|---------|---------------|
| Decision | Explicit choice made | "We'll use PostgreSQL" | `wiki/decisions/` |
| Learning | Insight discovered | "API has 100 req/s limit" | `wiki/topics/` |
| Process | Workflow or procedure | "First PR, then staging" | `wiki/processes/` |
| Warning | Pitfall to avoid | "Don't use deprecated endpoint" | `wiki/topics/` (flagged) |
| Question | Unanswered gap | "How do we configure X?" | `wiki/questions/` |
| Expertise | Domain knowledge | Auth answers from @alice | `wiki/experts/` |

### Implementation

```python
class SignalClassifierAgent:
    """
    Enriches wiki pages with signal type metadata.
    Hooks into Wiki Ingest Agent post-processing.
    """

    async def classify_page_content(
        self,
        page: WikiPage
    ) -> List[SignalAnnotation]:
        """
        Analyze wiki page content and add signal annotations.
        """
        annotations = []

        # Extract claims/statements from page
        claims = await self.extract_claims(page.content)

        for claim in claims:
            # Classify each claim
            signal_type = await self.classify_claim(claim)

            annotations.append(SignalAnnotation(
                page_path=page.path,
                claim_text=claim.text,
                signal_type=signal_type,
                confidence=signal_type.confidence,
                line_range=(claim.start_line, claim.end_line)
            ))

        # Store annotations
        await self.store_annotations(annotations)

        return annotations

    async def on_wiki_ingest(self, ingest_result: IngestResult):
        """
        Hook: Called after Wiki Ingest Agent updates pages.
        """
        for page in ingest_result.updated_pages:
            await self.classify_page_content(page)
```

### Storage (Enhancement Table)

```sql
-- Signal annotations on wiki content
CREATE TABLE wiki_signal_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_path TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    signal_type TEXT NOT NULL,  -- decision, learning, process, warning, question, expertise
    confidence REAL NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (page_path) REFERENCES wiki_pages(path) ON DELETE CASCADE
);

CREATE INDEX idx_annotations_type ON wiki_signal_annotations(signal_type);
CREATE INDEX idx_annotations_page ON wiki_signal_annotations(page_path);
```

---

## Enhancement Agent 2: Expertise Mapper

**Purpose**: Track who knows what based on wiki contributions and source participation

### Expertise Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXPERTISE GRAPH                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Users                 Topics                Wiki Pages         │
│   ─────                 ──────                ──────────         │
│                                                                  │
│   @alice ───expert_in───▶ authentication ◀───covers─── auth.md  │
│      │                          │                                │
│      │                          │                                │
│      └──contributed_to──────────┼───────────────────▶ oauth.md  │
│                                 │                                │
│   @bob ───learning──────▶ rate-limiting ◀───covers─── api.md   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation

```python
class ExpertiseMapperAgent:
    """
    Builds expertise map from wiki contributions and source participation.
    """

    async def update_expertise_from_source(
        self,
        source: WikiSource,
        affected_pages: List[WikiPage]
    ):
        """
        When a source is ingested, extract expertise signals.
        """
        # Get participants from source (summary)
        participants = source.metadata.get("participants", [])

        for participant in participants:
            user_id = participant["user_id"]
            role = participant.get("role", "contributor")

            # Determine topics from affected pages
            for page in affected_pages:
                topics = self.extract_topics(page)

                for topic in topics:
                    await self.update_expertise(
                        user_id=user_id,
                        topic=topic,
                        contribution_type=role,
                        source_id=source.id
                    )

    async def update_expertise(
        self,
        user_id: str,
        topic: str,
        contribution_type: str,
        source_id: str
    ):
        """
        Update user expertise score for a topic.
        """
        current = await self.get_expertise(user_id, topic)

        # Expertise grows with contributions
        weight = {
            "author": 1.0,      # Wrote the message
            "validator": 0.8,   # Confirmed/approved
            "contributor": 0.5, # Participated in discussion
            "mentioned": 0.2    # Was referenced
        }.get(contribution_type, 0.3)

        new_confidence = min(1.0, current.confidence + (weight * 0.1))

        await self.store_expertise(
            user_id=user_id,
            topic=topic,
            confidence=new_confidence,
            contribution_count=current.count + 1,
            last_source=source_id
        )

    async def get_experts(
        self,
        topic: str,
        limit: int = 5
    ) -> List[ExpertiseRecord]:
        """
        Who knows about this topic?
        """
        return await self.db.execute("""
            SELECT user_id, confidence, contribution_count
            FROM user_expertise
            WHERE topic = ? OR topic IN (
                SELECT related_topic FROM topic_relations WHERE topic = ?
            )
            ORDER BY confidence DESC, contribution_count DESC
            LIMIT ?
        """, (topic, topic, limit))
```

### Storage (Enhancement Table)

```sql
-- User expertise mappings
CREATE TABLE user_expertise (
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    contribution_count INTEGER DEFAULT 0,
    last_contribution TEXT,
    first_seen TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, guild_id, topic)
);

-- Topic relationships (for expertise inference)
CREATE TABLE topic_relations (
    topic TEXT NOT NULL,
    related_topic TEXT NOT NULL,
    relation_type TEXT NOT NULL,  -- parent, sibling, related
    weight REAL DEFAULT 1.0,
    PRIMARY KEY (topic, related_topic)
);

CREATE INDEX idx_expertise_topic ON user_expertise(topic);
CREATE INDEX idx_expertise_confidence ON user_expertise(confidence DESC);
```

---

## Enhancement Agent 3: Gap Detector

**Purpose**: Identify missing knowledge, unanswered questions, and stale content

### Gap Types

| Gap Type | Description | Detection Method |
|----------|-------------|------------------|
| Unanswered Question | Question signal with no answer | Signal type = question, no linked answer |
| Missing Topic | Referenced but no wiki page | Broken link detection |
| Stale Content | Not updated or accessed | Timestamp + access patterns |
| Shallow Coverage | Topic mentioned but sparse | Word count + link density |
| Contradiction | Conflicting claims | Coherence Gate flags |

### Implementation

```python
class GapDetectorAgent:
    """
    Identifies knowledge gaps in the wiki.
    """

    async def detect_gaps(self) -> GapReport:
        """
        Full gap analysis across wiki.
        """
        gaps = []

        # 1. Unanswered questions
        questions = await self.find_unanswered_questions()
        gaps.extend(questions)

        # 2. Missing topics (broken links)
        missing = await self.find_broken_links()
        gaps.extend(missing)

        # 3. Stale content
        stale = await self.find_stale_pages(days=30)
        gaps.extend(stale)

        # 4. Shallow coverage
        shallow = await self.find_shallow_pages(min_words=100, min_links=2)
        gaps.extend(shallow)

        # 5. Unresolved contradictions (from Coherence Gate)
        contradictions = await self.get_unresolved_contradictions()
        gaps.extend(contradictions)

        return GapReport(
            gaps=gaps,
            by_type=self.group_by_type(gaps),
            priority_ranked=self.rank_by_priority(gaps)
        )

    async def find_unanswered_questions(self) -> List[Gap]:
        """
        Questions in wiki without corresponding answers.
        """
        questions = await self.db.execute("""
            SELECT a.page_path, a.claim_text, a.created_at
            FROM wiki_signal_annotations a
            WHERE a.signal_type = 'question'
            AND NOT EXISTS (
                SELECT 1 FROM wiki_pages p
                WHERE p.content LIKE '%' || SUBSTR(a.claim_text, 1, 50) || '%'
                AND p.path != a.page_path
                AND p.updated_at > a.created_at
            )
        """)

        return [
            Gap(
                type="unanswered_question",
                location=q["page_path"],
                description=q["claim_text"],
                age_days=(datetime.now() - q["created_at"]).days,
                priority=self.calculate_priority(q)
            )
            for q in questions
        ]

    async def suggest_experts_for_gap(self, gap: Gap) -> List[str]:
        """
        Who might be able to fill this gap?
        """
        # Extract topics from gap
        topics = await self.extract_topics(gap.description)

        # Find experts
        experts = []
        for topic in topics:
            topic_experts = await self.expertise_mapper.get_experts(topic, limit=3)
            experts.extend(topic_experts)

        return list(set(experts))[:5]
```

### Storage (Enhancement Table)

```sql
-- Detected knowledge gaps
CREATE TABLE wiki_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_type TEXT NOT NULL,  -- unanswered_question, missing_topic, stale, shallow, contradiction
    location TEXT NOT NULL,  -- page path or topic
    description TEXT NOT NULL,
    priority REAL NOT NULL,  -- 0.0-1.0
    suggested_experts TEXT,  -- JSON array of user_ids
    detected_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    resolved_by TEXT
);

CREATE INDEX idx_gaps_type ON wiki_gaps(gap_type);
CREATE INDEX idx_gaps_priority ON wiki_gaps(priority DESC);
```

---

## Enhancement Agent 4: Provenance Tracker

**Purpose**: Link wiki claims back to source conversations

### Provenance Model

```
Source (Summary)              Wiki Claim                  Provenance Link
────────────────              ──────────                  ───────────────

summary_2024-01-15.md    ──▶  "Use JWT for auth"    ◀──  confidence: 0.95
  │                              (auth.md:45)              source_quote: "Let's
  │                                                        use JWT tokens"
  │                                                        participants: [@alice]
  │
  └──────────────────────▶  "Refresh every 15min"  ◀──  confidence: 0.87
                               (auth.md:52)              source_quote: "refresh
                                                         should be ~15 minutes"
```

### Implementation

```python
class ProvenanceTrackerAgent:
    """
    Links wiki claims to source documents.
    Enables "where did this come from?" queries.
    """

    async def track_provenance(
        self,
        source: WikiSource,
        updates: List[WikiUpdate]
    ):
        """
        After wiki ingest, link new content to source.
        """
        for update in updates:
            # Find claims that were added/modified
            new_claims = self.diff_claims(
                old_content=update.old_content,
                new_content=update.new_content
            )

            for claim in new_claims:
                # Find supporting evidence in source
                evidence = await self.find_evidence(claim, source)

                if evidence:
                    await self.store_provenance(
                        page_path=update.page_path,
                        claim_text=claim.text,
                        claim_line=claim.line,
                        source_id=source.id,
                        source_quote=evidence.quote,
                        confidence=evidence.confidence,
                        participants=evidence.participants
                    )

    async def get_claim_sources(
        self,
        page_path: str,
        claim_text: str
    ) -> List[ProvenanceRecord]:
        """
        Where did this claim come from?
        """
        return await self.db.execute("""
            SELECT source_id, source_quote, confidence, participants, created_at
            FROM wiki_provenance
            WHERE page_path = ? AND claim_text LIKE ?
            ORDER BY confidence DESC
        """, (page_path, f"%{claim_text[:50]}%"))

    async def verify_claim(self, claim: str) -> VerificationResult:
        """
        Check if a claim has source support.
        """
        provenance = await self.get_claim_sources_by_text(claim)

        if not provenance:
            return VerificationResult(
                verified=False,
                reason="No source provenance found"
            )

        # Check source freshness
        newest = max(p.created_at for p in provenance)
        age_days = (datetime.now() - newest).days

        return VerificationResult(
            verified=True,
            sources=provenance,
            confidence=max(p.confidence for p in provenance),
            freshness="fresh" if age_days < 30 else "stale",
            participants=list(set(p for prov in provenance for p in prov.participants))
        )
```

### Storage (Enhancement Table)

```sql
-- Claim to source provenance
CREATE TABLE wiki_provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_path TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_line INTEGER,
    source_id TEXT NOT NULL,
    source_quote TEXT,
    confidence REAL NOT NULL,
    participants TEXT,  -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (page_path) REFERENCES wiki_pages(path) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES wiki_sources(id) ON DELETE CASCADE
);

CREATE INDEX idx_provenance_page ON wiki_provenance(page_path);
CREATE INDEX idx_provenance_source ON wiki_provenance(source_id);
```

---

## Integration with Wiki Agents

### Hook Points

```python
class WikiEnhancementHooks:
    """
    Integration hooks between wiki agents and enhancement agents.
    """

    def __init__(self):
        self.signal_classifier = SignalClassifierAgent()
        self.expertise_mapper = ExpertiseMapperAgent()
        self.gap_detector = GapDetectorAgent()
        self.provenance_tracker = ProvenanceTrackerAgent()

    async def on_ingest_complete(self, result: IngestResult):
        """
        Called after Wiki Ingest Agent finishes.
        """
        # Run enhancements in parallel
        await asyncio.gather(
            self.signal_classifier.classify_pages(result.updated_pages),
            self.expertise_mapper.update_from_source(result.source, result.updated_pages),
            self.provenance_tracker.track(result.source, result.updates)
        )

    async def on_query(self, query: str, results: List[WikiPage]):
        """
        Called after Wiki Query Agent returns results.
        """
        # Enrich results with expertise info
        for result in results:
            result.experts = await self.expertise_mapper.get_experts_for_page(result.path)
            result.provenance_summary = await self.provenance_tracker.summarize(result.path)

    async def on_lint_complete(self, lint_result: LintResult):
        """
        Called after Wiki Lint Agent finishes.
        """
        # Add gap detection to lint results
        gaps = await self.gap_detector.detect_gaps()
        lint_result.knowledge_gaps = gaps
```

---

## Dashboard Extensions

### Expertise View

```
┌─────────────────────────────────────────────────────────────┐
│  🧠 Expertise Map                                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Topic: authentication                                       │
│  ┌────────────────────────────────────────────────────────┐│
│  │  @alice  ████████████████████░░  92% (47 contributions) ││
│  │  @bob    ████████░░░░░░░░░░░░░░  41% (12 contributions) ││
│  │  @carol  █████░░░░░░░░░░░░░░░░░  28% (8 contributions)  ││
│  └────────────────────────────────────────────────────────┘│
│                                                              │
│  Related Topics: oauth, jwt, sessions, security             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Gap Report View

```
┌─────────────────────────────────────────────────────────────┐
│  🕳️ Knowledge Gaps                                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ⚠️ HIGH PRIORITY                                            │
│  ┌────────────────────────────────────────────────────────┐│
│  │ Unanswered: "How do we handle token refresh in mobile?"││
│  │ 📍 wiki/topics/authentication.md:234                    ││
│  │ 📅 Open for 12 days                                     ││
│  │ 👤 Suggested: @alice, @david                            ││
│  │ [Assign] [Answer] [Dismiss]                             ││
│  └────────────────────────────────────────────────────────┘│
│                                                              │
│  📊 Gap Summary                                              │
│  • Unanswered questions: 8                                   │
│  • Missing topics: 3                                         │
│  • Stale pages (>30d): 12                                   │
│  • Shallow coverage: 5                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Provenance View

```
┌─────────────────────────────────────────────────────────────┐
│  📜 Claim Provenance                                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Claim: "JWT tokens should refresh every 15 minutes"        │
│  Location: wiki/topics/authentication.md:52                  │
│                                                              │
│  Sources:                                                    │
│  ┌────────────────────────────────────────────────────────┐│
│  │ 📄 summary_2024-01-15-backend-standup.md               ││
│  │    "@alice: refresh should be ~15 minutes max"          ││
│  │    Confidence: 95%                                      ││
│  │    Participants: @alice, @bob                           ││
│  └────────────────────────────────────────────────────────┘│
│  ┌────────────────────────────────────────────────────────┐│
│  │ 📄 summary_2024-01-22-security-review.md               ││
│  │    "confirmed 15-minute refresh window"                 ││
│  │    Confidence: 87%                                      ││
│  │    Participants: @alice, @carol                         ││
│  └────────────────────────────────────────────────────────┘│
│                                                              │
│  ✅ Verified by 2 sources | Last updated: 3 days ago        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Foundation (2 weeks)
- [ ] Enhancement tables migration
- [ ] Hook integration with Wiki Ingest Agent
- [ ] Basic signal classification

### Phase 2: Expertise (2 weeks)
- [ ] Expertise extraction from sources
- [ ] Topic relationship inference
- [ ] "Who knows about X?" query

### Phase 3: Gaps & Provenance (2 weeks)
- [ ] Gap detection pipeline
- [ ] Provenance tracking
- [ ] Dashboard extensions

**Total: 6 weeks** (vs. 16 weeks standalone)

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Signal classification accuracy | >90% | Human validation |
| Expertise map coverage | >80% of active users | Users with expertise records |
| Gap detection recall | >85% | Gaps found / actual gaps |
| Provenance coverage | >70% of claims | Claims with source links |
| Query enrichment | +15% satisfaction | A/B test with/without |

## Consequences

### Positive
- Leverages all wiki infrastructure (no duplication)
- Focused scope (4 agents vs. original design)
- Faster implementation (6 weeks vs. 16 weeks)
- Clear separation of concerns

### Negative
- Dependent on ADR-056/057 being implemented first
- Enhancement tables add schema complexity
- Hook coordination requires careful testing

### Mitigations
- Implement ADR-056 (standard wiki) first as foundation
- Use database views to simplify queries across tables
- Integration tests for hook chains

## References

- [ADR-056: Compounding Wiki - Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-057: Compounding Wiki - RuVector](./ADR-057-compounding-wiki-ruvector.md)
- [ADR-052: RuVector Integration Vision](./ADR-052-ruvector-integration-vision.md)
- [ADR-054: Operational Agents](./ADR-054-operational-agents.md)
