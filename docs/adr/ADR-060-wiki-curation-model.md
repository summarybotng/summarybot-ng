# ADR-060: Wiki Curation Model - Human + AI Collaboration

## Status
Proposed (Depends on ADR-056/057)

## Context

### The Wiki Paradox

Traditional wikis are **human-curated** - people write, edit, verify, and take responsibility for content. Wikipedia's model relies on human editors debating and reaching consensus.

The Compounding Wiki (ADR-056/057) is **AI-generated** - an LLM extracts knowledge from chat conversations and maintains wiki pages automatically. This raises fundamental questions:

1. **Editability**: People expect wikis to be editable, but AI keeps updating pages
2. **Authority**: Who "owns" the content - humans or the AI?
3. **Trust**: How do readers know what's reliable?
4. **Drift**: Can AI-generated content accumulate errors over time?

### The Tension

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         THE WIKI TENSION                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   TRADITIONAL WIKI                    COMPOUNDING WIKI                   │
│   ────────────────                    ────────────────                   │
│                                                                          │
│   Human writes content                AI extracts from chat              │
│   Human verifies accuracy             AI flags contradictions            │
│   Human resolves disputes             AI synthesizes answers             │
│   Human maintains freshness           AI updates on every ingest         │
│                                                                          │
│   👤 High quality, low throughput     🤖 High throughput, variable quality│
│                                                                          │
│   ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   THE QUESTION: How do we get the best of both?                         │
│                                                                          │
│   • AI does the heavy lifting (extraction, synthesis, linking)          │
│   • Humans provide judgment (validation, correction, enrichment)        │
│   • System learns from human feedback                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Decision

Implement a **layered curation model** where:

1. **AI is the primary author** - Extracts and maintains content
2. **Humans are curators** - Validate, correct, and enrich
3. **Curation is visible** - Every piece of content shows its trust level
4. **System learns** - Human feedback improves future extraction

---

## Curation Layers

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CURATION LAYERS                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Layer 3: HUMAN-AUTHORED                                               │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  Content written directly by humans                              │  │
│   │  • Manual wiki edits                                             │  │
│   │  • Google Drive edits (ADR-059)                                  │  │
│   │  • Expert elaborations                                           │  │
│   │  Trust: ████████████████████ 100%                               │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                    │                                     │
│                                    ▼                                     │
│   Layer 2: HUMAN-VALIDATED                                              │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  AI-generated content that humans have reviewed                  │  │
│   │  • Marked as "verified" by expert                                │  │
│   │  • Contradiction resolved                                        │  │
│   │  • Minor corrections applied                                     │  │
│   │  Trust: ██████████████░░░░░░ 85%                                │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                    │                                     │
│                                    ▼                                     │
│   Layer 1: AI-GENERATED                                                 │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  Automatically extracted from chat summaries                     │  │
│   │  • Has source citations                                          │  │
│   │  • Not yet human-reviewed                                        │  │
│   │  • May contain errors                                            │  │
│   │  Trust: ██████████░░░░░░░░░░ 60-80% (confidence varies)         │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Trust Indicators

Every wiki page and claim shows its curation status:

### Page-Level Trust

```
┌─────────────────────────────────────────────────────────────────────────┐
│  # Authentication                                                        │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  🟢 Verified                                                     │   │
│  │  This page was reviewed by @alice on Jan 20, 2024.              │   │
│  │  7 of 8 claims are validated. 1 pending review.                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Our system uses JWT tokens with OAuth 2.0...                           │
└─────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│  # New API Design                                                        │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  🟡 Unverified                                                   │   │
│  │  This page was auto-generated from 3 summaries.                 │   │
│  │  No human has reviewed it yet.                                  │   │
│  │  [✓ Mark as Reviewed]                                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  The new API will use GraphQL...                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│  # Rate Limiting                                                         │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  🔴 Needs Attention                                              │   │
│  │  This page has 2 unresolved contradictions.                     │   │
│  │  Conflicting claims from Jan 15 and Jan 22 summaries.           │   │
│  │  [Review Conflicts]                                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Rate limiting is set to... [CONFLICT: 100 req/min vs 50 req/min]      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Claim-Level Trust

```markdown
# Authentication

Our system uses JWT tokens [✓ verified by @alice] with OAuth 2.0
[✓ verified by @bob] for third-party integrations.

## Token Lifecycle

- Access tokens: 15 minute expiry [source: security-review-jan-22]
- Refresh tokens: 7 day expiry [⚠️ unverified - needs review]
```

---

## Curation Workflows

### 1. Validation Queue

High-priority items that need human review:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📋 Curation Queue                                          12 items    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  🔴 HIGH PRIORITY                                                        │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ⚡ Contradiction: Rate Limiting                                 │   │
│  │                                                                   │   │
│  │  Claim A (Jan 15): "Rate limit is 100 requests/minute"          │   │
│  │  Claim B (Jan 22): "We reduced rate limit to 50 requests/min"   │   │
│  │                                                                   │   │
│  │  Suggested experts: @devops-lead, @api-team                     │   │
│  │                                                                   │   │
│  │  [Use A] [Use B] [Both Valid (context differs)] [Needs Research]│   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ⚡ External Edit: Authentication                                │   │
│  │                                                                   │   │
│  │  @alice edited this page in Google Drive.                       │   │
│  │  Changes: Added "Session timeout is 30 minutes"                 │   │
│  │                                                                   │   │
│  │  [Accept Edit] [Reject] [Review Diff]                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  🟡 MEDIUM PRIORITY                                                      │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  📄 Unverified Page: New API Design                             │   │
│  │                                                                   │   │
│  │  Auto-generated 3 days ago. 5 claims, 0 verified.               │   │
│  │  High confidence (87%) but no human review.                     │   │
│  │                                                                   │   │
│  │  [Review Page] [Mark Verified] [Assign to Expert]               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2. Inline Editing

Users can suggest edits without disrupting AI updates:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  # Rate Limiting                                        [Edit] [History]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Rate limiting is set to 100 requests per minute per client IP.        │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ✏️ Edit Mode                                                    │   │
│  │                                                                   │   │
│  │  Rate limiting is set to [100] requests per minute per          │   │
│  │  [client IP].                                                    │   │
│  │  ─────────────────────────────────                              │   │
│  │  Change to: 50 requests per minute per user ID                  │   │
│  │                                                                   │   │
│  │  Reason: Updated in Jan 22 meeting [optional source link]       │   │
│  │                                                                   │   │
│  │  [Submit Edit]  [Cancel]                                        │   │
│  │                                                                   │   │
│  │  ℹ️ Your edit will be marked as human-authored and take        │   │
│  │  precedence over AI-generated content.                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3. Expert Assignment

Route topics to the right people:

```python
class ExpertRouter:
    """
    Routes curation items to relevant experts.
    """

    async def route_for_review(self, item: CurationItem) -> List[str]:
        # Get topic from item
        topics = await self.extract_topics(item)

        # Find experts (from ADR-055 Expertise Mapper)
        experts = []
        for topic in topics:
            topic_experts = await expertise_mapper.get_experts(
                topic=topic,
                guild_id=item.guild_id,
                min_confidence=0.7
            )
            experts.extend(topic_experts)

        # Dedupe and rank
        ranked = self.rank_by_availability_and_expertise(experts)

        # Notify top experts
        for expert in ranked[:3]:
            await self.notify_expert(expert, item)

        return [e.user_id for e in ranked[:3]]
```

---

## Content Precedence Rules

When content conflicts, apply these rules:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CONTENT PRECEDENCE RULES                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Priority Order (highest to lowest):                                    │
│                                                                          │
│   1. HUMAN-AUTHORED (Direct edits)                                      │
│      │ Human explicitly wrote this content                              │
│      │ Always preserved unless another human changes it                 │
│      │                                                                   │
│   2. HUMAN-VALIDATED (Reviewed AI content)                              │
│      │ AI wrote it, human confirmed it                                  │
│      │ AI won't overwrite without flagging                             │
│      │                                                                   │
│   3. HIGH-CONFIDENCE AI (>90% confidence)                               │
│      │ Multiple sources agree                                           │
│      │ Recent and consistent                                            │
│      │                                                                   │
│   4. LOW-CONFIDENCE AI (<90% confidence)                                │
│      │ Single source or old                                             │
│      │ May be overwritten by new AI updates                            │
│      │                                                                   │
│   ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   Conflict Resolution:                                                   │
│                                                                          │
│   Human vs Human      → Flag for discussion                             │
│   Human vs AI         → Human wins (AI content marked as superseded)   │
│   AI vs AI (same src) → Newer wins                                      │
│   AI vs AI (diff src) → Flag contradiction for human review            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Content Versioning

Track the full history of changes:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Page History: authentication.md                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Jan 25, 2024 - 2:30 PM                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  👤 @alice edited via Google Drive                              │   │
│  │  + Added: "Session timeout is 30 minutes for security"         │   │
│  │  Status: Human-authored                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Jan 22, 2024 - 10:15 AM                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  🤖 AI updated from "security-review-jan-22" summary            │   │
│  │  ~ Changed: Token expiry from "30 min" to "15 min"              │   │
│  │  Status: AI-generated (verified by @alice)                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Jan 15, 2024 - 3:45 PM                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  🤖 AI created from "backend-standup-jan-15" summary            │   │
│  │  + Initial page creation                                        │   │
│  │  Status: AI-generated (unverified)                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  [Compare Versions] [Restore Previous]                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Learning from Curation

Human feedback improves AI extraction:

```python
class CurationLearner:
    """
    Learns from human curation decisions to improve AI extraction.
    """

    async def learn_from_validation(
        self,
        claim: str,
        action: str,  # validated, rejected, corrected
        correction: Optional[str] = None
    ):
        if action == 'validated':
            # Positive signal - extraction was correct
            await self.reinforce_extraction_pattern(claim)

        elif action == 'rejected':
            # Negative signal - shouldn't have extracted this
            await self.penalize_extraction_pattern(claim)

        elif action == 'corrected':
            # Learning opportunity - extraction was close but wrong
            await self.learn_correction_pattern(claim, correction)

    async def learn_from_contradiction_resolution(
        self,
        claim_a: str,
        claim_b: str,
        resolution: str  # use_a, use_b, both_valid, neither
    ):
        if resolution == 'use_a':
            # Claim A was correct, B was wrong
            await self.update_source_reliability(claim_a, boost=True)
            await self.update_source_reliability(claim_b, boost=False)

        elif resolution == 'both_valid':
            # Learn context differentiation
            await self.learn_context_patterns(claim_a, claim_b)

    async def apply_learnings(self):
        """
        Apply accumulated learnings to improve future extraction.
        Used by SONA (ADR-057) for temporal learning.
        """
        await self.ruvector.learn(
            context='curation_feedback',
            signals=self.accumulated_signals
        )
```

---

## Database Schema

```sql
-- Curation status for pages
CREATE TABLE wiki_curation (
    page_path TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    curation_level TEXT NOT NULL,  -- human_authored, human_validated, ai_generated
    confidence REAL,
    verified_by TEXT,  -- user_id
    verified_at TEXT,
    claims_total INTEGER DEFAULT 0,
    claims_verified INTEGER DEFAULT 0,
    claims_disputed INTEGER DEFAULT 0,
    last_human_edit TEXT,
    last_ai_edit TEXT,
    PRIMARY KEY (page_path, guild_id)
);

-- Claim-level curation
CREATE TABLE wiki_claim_curation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_path TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_hash TEXT NOT NULL,  -- For deduplication
    curation_level TEXT NOT NULL,
    confidence REAL,
    verified_by TEXT,
    verified_at TEXT,
    source_id TEXT,
    FOREIGN KEY (page_path, guild_id) REFERENCES wiki_curation(page_path, guild_id)
);

-- Curation queue
CREATE TABLE wiki_curation_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    item_type TEXT NOT NULL,  -- contradiction, unverified_page, external_edit, stale_content
    priority TEXT NOT NULL,  -- high, medium, low
    page_path TEXT,
    claim_text TEXT,
    details TEXT,  -- JSON with context
    assigned_to TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    resolution TEXT  -- JSON with decision
);

-- Curation history (for learning)
CREATE TABLE wiki_curation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    curator_id TEXT NOT NULL,
    action TEXT NOT NULL,  -- validate, reject, correct, resolve_contradiction
    page_path TEXT,
    claim_text TEXT,
    original_content TEXT,
    new_content TEXT,
    metadata TEXT,  -- JSON
    created_at TEXT DEFAULT (datetime('now'))
);

-- Page versions
CREATE TABLE wiki_page_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_path TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    change_type TEXT NOT NULL,  -- ai_ingest, human_edit, ai_update, merge
    changed_by TEXT,  -- user_id or 'ai'
    source_id TEXT,  -- If from summary
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_curation_level ON wiki_curation(curation_level);
CREATE INDEX idx_curation_queue_priority ON wiki_curation_queue(priority, created_at);
CREATE INDEX idx_curation_history_curator ON wiki_curation_history(curator_id);
CREATE INDEX idx_page_versions_path ON wiki_page_versions(page_path, guild_id);
```

---

## Gamification (Optional)

Encourage curation participation:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🏆 Curation Leaderboard                                     This Week  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. @alice          42 validations    🥇                                │
│  2. @bob            38 validations    🥈                                │
│  3. @carol          25 validations    🥉                                │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  Your Stats                                                              │
│  • Validations this week: 12                                            │
│  • Contradictions resolved: 3                                           │
│  • Pages enriched: 5                                                    │
│  • Expertise areas: authentication, api-design                          │
│                                                                          │
│  🎯 Next badge: "Domain Expert" (8 more validations in api-design)     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Trust Display (2 weeks)
- [ ] Page-level trust indicators
- [ ] Curation status badges
- [ ] Version history view

### Phase 2: Curation Queue (2 weeks)
- [ ] Queue UI
- [ ] Contradiction resolution workflow
- [ ] External edit review

### Phase 3: Inline Editing (2 weeks)
- [ ] Edit mode UI
- [ ] Change tracking
- [ ] Precedence enforcement

### Phase 4: Learning (2 weeks)
- [ ] Feedback collection
- [ ] SONA integration
- [ ] Extraction improvement

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Verified content | >70% of pages | Curation level distribution |
| Curation velocity | <48h for high priority | Queue age |
| Human edits retained | >95% | Edit preservation rate |
| Contradiction resolution | <24h average | Time to resolve |
| Learning impact | +5% extraction accuracy | Before/after comparison |

## Consequences

### Positive
- Clear trust signals for readers
- Human expertise preserved
- AI does heavy lifting
- System improves over time
- Accountability for content

### Negative
- Curation overhead for users
- Complex precedence rules
- Potential for curation fatigue
- Learning requires volume

### Mitigations
- Gamification encourages participation
- Expert routing reduces individual burden
- Batch curation for efficiency
- Start with high-impact pages

## References

- [ADR-056: Compounding Wiki - Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-057: Compounding Wiki - RuVector](./ADR-057-compounding-wiki-ruvector.md)
- [ADR-055: Knowledge Base Agents](./ADR-055-knowledge-base-agents.md)
- [ADR-059: Wiki External Sync](./ADR-059-wiki-external-sync.md)
- [Wikipedia: Editorial oversight](https://en.wikipedia.org/wiki/Wikipedia:Editorial_oversight)
- [Karpathy's Compounding Wiki (Discussion)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
