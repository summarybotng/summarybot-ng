# ADR-087: Wiki Ingestion Granularity - Cross-Channel vs. Temporal Strategies

## Status
Brainstorm

## Context

ADR-057 describes the RuVector-enhanced wiki with powerful capabilities:
- **HNSW Vector Index**: Semantic search understands meaning, not just keywords
- **GNN Knowledge Graph**: Automatic relationship discovery across pages
- **SONA Temporal Learning**: Self-improving relevance based on usage
- **Coherence Gate**: Validates content against existing knowledge

ADR-067 implements automatic wiki ingestion from **daily per-channel summaries**. Each channel generates a summary daily, which feeds the wiki independently. This creates accurate but potentially siloed knowledge.

**Question**: Given ADR-057's semantic capabilities, would **daily cross-channel summaries** or **weekly same-channel summaries** produce better wiki content? Or does RuVector's GNN make cross-channel synthesis redundant?

### Current Approach (ADR-067)

```
Day 1:
  #general summary    → Wiki ingest → topics/team-updates.md
  #engineering summary → Wiki ingest → topics/api-design.md
  #product summary    → Wiki ingest → topics/roadmap.md

Day 2:
  #general summary    → Wiki ingest → topics/team-updates.md (updated)
  #engineering summary → Wiki ingest → topics/api-design.md (updated)
  ...
```

**Characteristics:**
- **Granularity**: Per-channel, per-day
- **Cross-pollination**: None (channels don't see each other)
- **Freshness**: Immediate (same day)
- **Volume**: Many small ingestions
- **Context window**: Single channel, single day (~50-200 messages)

---

## Alternative Strategies

### Strategy A: Daily Cross-Channel Summaries

Generate one summary per day covering ALL channels, then ingest into wiki.

```
Day 1:
  All channels → Cross-Channel Summary → Wiki ingest
    "Today the team discussed the API migration (#engineering),
     which affects the Q2 roadmap (#product). Marketing needs
     updated messaging (#marketing) once the migration completes."

Day 2:
  All channels → Cross-Channel Summary → Wiki ingest
```

**Potential Benefits:**
- **Sees connections**: API discussion in #engineering relates to timeline in #product
- **Holistic synthesis**: One coherent narrative per day
- **Reduced volume**: 1 wiki update/day vs N channels × 1/day
- **Executive perspective**: Better for high-level wiki pages

**Potential Drawbacks:**
- **Loss of detail**: Individual channel nuances may be lost
- **Larger context**: Harder to summarize (10 channels × 100 msgs = 1000 msgs)
- **Mixed topics**: Unrelated discussions forced together
- **Cost**: More tokens per summary (but fewer summaries)

**Best For:**
- `wiki/log.md` (daily activity log)
- `wiki/decisions/` (cross-functional decisions)
- Small/medium workspaces (<10 active channels)

---

### Strategy B: Weekly Same-Channel Summaries

Generate weekly summaries per channel, capturing evolution over time.

```
Week 1:
  #engineering (Mon-Sun) → Weekly Summary → Wiki ingest
    "This week: Started API migration (Mon), hit auth blocker (Wed),
     resolved with OAuth refactor (Fri), PR merged (Sun)."

Week 2:
  #engineering (Mon-Sun) → Weekly Summary → Wiki ingest
```

**Potential Benefits:**
- **Temporal patterns**: Sees how topics evolve
- **Narrative arcs**: Beginning → middle → resolution
- **Reduced noise**: Daily chatter filtered out
- **Trend detection**: "Authentication has been discussed 3 weeks in a row"

**Potential Drawbacks:**
- **Staleness**: Wiki up to 7 days behind
- **Context explosion**: Week of messages may exceed context window
- **Lost urgency**: Time-sensitive items not captured promptly
- **Sampling required**: Can't process all messages, need smart selection

**Best For:**
- `wiki/topics/` (deep topic pages)
- `wiki/projects/` (project evolution)
- Technical documentation

---

### Strategy C: Hybrid Multi-Granularity

Use different granularities for different wiki sections.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    HYBRID INGESTION MODEL                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  DAILY CROSS-CHANNEL                    DAILY PER-CHANNEL           │
│  ┌──────────────────┐                   ┌──────────────────┐        │
│  │ All channels     │──────────────────▶│ wiki/log.md      │        │
│  │ combined         │                   │ (activity log)   │        │
│  └──────────────────┘                   └──────────────────┘        │
│           │                                                          │
│           │                             DAILY PER-CHANNEL           │
│           │                             ┌──────────────────┐        │
│           └────────────────────────────▶│ wiki/topics/     │        │
│                                         │ (topic pages)    │        │
│                                         └──────────────────┘        │
│                                                                      │
│  WEEKLY PER-CHANNEL                                                 │
│  ┌──────────────────┐                   ┌──────────────────┐        │
│  │ #engineering     │──────────────────▶│ wiki/projects/   │        │
│  │ weekly rollup    │                   │ (project docs)   │        │
│  └──────────────────┘                   └──────────────────┘        │
│                                                                      │
│  MONTHLY CROSS-CHANNEL                                              │
│  ┌──────────────────┐                   ┌──────────────────┐        │
│  │ All channels     │──────────────────▶│ wiki/reports/    │        │
│  │ monthly          │                   │ (monthly digest) │        │
│  └──────────────────┘                   └──────────────────┘        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ADR-057 Capabilities vs. Ingestion Granularity

### Does RuVector Make Cross-Channel Synthesis Redundant?

ADR-057's GNN can **automatically discover relationships** between wiki pages:

```python
# From ADR-057: GNN finds connections without explicit links
relationships = await self.ruvector.classify_edge(
    from_node=page.id,
    to_node=candidate.id,
    attention_heads=["topic_coherence", "temporal_proximity", "author_overlap"]
)
```

**Key Insight**: If per-channel summaries mention the same topic (e.g., "API migration"), RuVector's semantic search and GNN will:
1. Find both pages via HNSW similarity
2. Infer a `relates_to` edge between them
3. Surface both when queried

**However**, there are things the GNN **cannot** infer:
- **Causal relationships**: "Engineering discussed API migration → Product adjusted timeline"
- **Cross-functional decisions**: "After discussion in #engineering AND #product, we decided..."
- **Holistic narratives**: The story of what happened today across the org

### Where Each Strategy Excels with ADR-057

| Capability | Per-Channel (ADR-067) | Cross-Channel | Weekly |
|------------|----------------------|---------------|--------|
| **HNSW Semantic Search** | ✅ Finds similar topics | ✅ Same | ✅ Same |
| **GNN Auto-Discovery** | ✅ Infers topic links | ⚠️ Links pre-made | ⚠️ Links pre-made |
| **Causal Chains** | ❌ Siloed | ✅ LLM sees full context | ✅ Temporal context |
| **SONA Learning** | ✅ Per-topic signals | ✅ Per-day signals | ⚠️ Weekly granularity |
| **Coherence Gate** | ✅ Per-summary validation | ⚠️ Larger validation scope | ⚠️ Week of content |

**Conclusion**: ADR-057's capabilities handle **implicit** relationships well. But **explicit** cross-channel narratives require LLM synthesis before ingestion.

---

## Analysis: Which Strategy Produces Better Wiki Content?

### Dimension 1: Knowledge Discovery

| Strategy | Cross-Topic Links | Temporal Patterns | Detail Preservation |
|----------|-------------------|-------------------|---------------------|
| Daily per-channel (current) | ❌ Poor | ❌ Poor | ✅ Excellent |
| Daily cross-channel | ✅ Excellent | ❌ Poor | ⚠️ Medium |
| Weekly per-channel | ❌ Poor | ✅ Excellent | ⚠️ Medium |
| Hybrid | ✅ Excellent | ✅ Good | ✅ Good |

**Insight**: Current approach preserves detail but misses connections. Cross-channel finds relationships but loses temporal patterns.

### Dimension 2: Wiki Page Quality

| Wiki Section | Best Strategy | Why |
|--------------|---------------|-----|
| `log.md` | Daily cross-channel | Executive summary needs holistic view |
| `topics/` | Daily per-channel | Topics emerge from focused discussions |
| `decisions/` | Daily cross-channel | Decisions often span channels |
| `projects/` | Weekly per-channel | Projects evolve over days/weeks |
| `experts/` | Daily per-channel | Expertise shown in deep discussions |
| `questions/` | Daily per-channel | Q&A is channel-specific |

### Dimension 3: Practical Constraints

| Factor | Daily Per-Channel | Daily Cross-Channel | Weekly Per-Channel |
|--------|-------------------|---------------------|-------------------|
| **Context window** | ~4K tokens | ~40K tokens | ~100K tokens |
| **LLM cost/day** | $0.01 × N channels | $0.10 × 1 | $0.50 × N channels/week |
| **Latency** | Immediate | Same day | Up to 7 days |
| **Failure blast radius** | 1 channel | All channels | 1 channel/week |

---

## Proposed Enhancement: Layered Ingestion

Rather than replacing ADR-067, **add additional ingestion layers**:

### Layer 1: Daily Per-Channel (Current - Keep)
- Feeds: `topics/`, `experts/`, `questions/`
- Preserves detail and channel context
- No changes needed

### Layer 2: Daily Cross-Channel Synthesis (New)
- Feeds: `log.md`, `decisions/`
- Runs after all channel summaries complete
- Input: Today's channel summaries (not raw messages)
- Much smaller context (summaries, not messages)

```python
class CrossChannelSynthesizer:
    """
    Create daily cross-channel summary from individual channel summaries.
    """

    async def synthesize_day(
        self,
        guild_id: str,
        date: date,
    ) -> CrossChannelSummary:
        # 1. Fetch today's per-channel summaries
        summaries = await self.repo.find_by_guild(
            guild_id=guild_id,
            created_after=datetime.combine(date, time.min),
            created_before=datetime.combine(date, time.max),
        )

        # 2. Combine into cross-channel prompt
        combined_context = "\n\n".join([
            f"## {s.title}\n{s.summary_result.summary_text}"
            for s in summaries
        ])

        # 3. Generate cross-channel synthesis
        prompt = f"""
        Given today's channel summaries, identify:
        1. Cross-channel themes and connections
        2. Decisions that span multiple channels
        3. Action items with cross-functional impact

        Summaries:
        {combined_context}
        """

        return await self.llm.generate(prompt)
```

### Layer 3: Weekly Rollup (New)
- Feeds: `projects/`, monthly reports
- Runs every Sunday (or configurable)
- Input: Week's daily cross-channel summaries
- Even smaller context (7 daily summaries)

```python
class WeeklyRollup:
    """
    Create weekly rollup from daily cross-channel summaries.
    """

    async def rollup_week(
        self,
        guild_id: str,
        week_start: date,
    ) -> WeeklyDigest:
        # Fetch 7 daily cross-channel summaries
        daily_summaries = await self.get_week_summaries(guild_id, week_start)

        # Generate weekly narrative
        prompt = f"""
        Given this week's daily summaries, create a weekly digest:
        1. Key accomplishments
        2. Ongoing initiatives and their progress
        3. Emerging themes or concerns
        4. Notable decisions made

        {format_daily_summaries(daily_summaries)}
        """

        return await self.llm.generate(prompt)
```

---

## Cost Analysis

### Current (ADR-067)
```
10 channels × $0.01/summary × 30 days = $3/month
Wiki ingestions: 300/month
```

### With Layered Approach
```
Layer 1: 10 channels × $0.01 × 30 days = $3/month (unchanged)
Layer 2: $0.02/day × 30 days = $0.60/month (cross-channel)
Layer 3: $0.05/week × 4 weeks = $0.20/month (weekly)

Total: $3.80/month (+27%)
Wiki ingestions: 300 + 30 + 4 = 334/month
```

**Marginal cost for significantly richer wiki content.**

---

## Alternative Architecture: RuVector as Primary, Wiki as View

### The Inversion

Current architecture (ADR-067):
```
Summaries → Wiki pages (markdown) → RuVector indexes wiki
                    ↑
              Source of truth
```

Proposed inversion:
```
Summaries → RuVector Brain → Wiki pages generated as views
                  ↑
            Source of truth
```

### How It Would Work

```python
class RuVectorPrimaryStore:
    """
    RuVector holds all knowledge. Wiki pages are rendered views.
    """

    async def ingest_summary(self, summary: Summary):
        """Ingest directly to RuVector, not to markdown."""
        # 1. Extract knowledge units (claims, decisions, Q&A, etc.)
        units = await self.extract_knowledge_units(summary)

        # 2. Store each unit with full provenance
        for unit in units:
            await self.ruvector.store(
                content=unit.content,
                type=unit.type,  # claim, decision, question, action_item
                source_id=summary.id,
                source_channel=summary.channel_name,
                source_date=summary.created_at,
                embedding=await self.embed(unit.content),
            )

        # 3. GNN automatically builds relationships
        await self.ruvector.rebuild_edges()

    async def render_wiki_page(
        self,
        page_type: str,  # "topic", "daily_digest", "weekly_rollup", "decisions"
        params: dict,
    ) -> str:
        """Generate wiki page on-demand from RuVector."""

        if page_type == "topic":
            # Semantic query for all units related to topic
            units = await self.ruvector.search(
                query=params["topic"],
                limit=50,
                threshold=0.7,
            )
            return self.render_topic_page(params["topic"], units)

        elif page_type == "daily_digest":
            # Query by date, aggregate across channels
            units = await self.ruvector.query(
                filter={"source_date": params["date"]},
                group_by="source_channel",
            )
            return self.render_daily_digest(params["date"], units)

        elif page_type == "weekly_rollup":
            # Query date range, find patterns
            units = await self.ruvector.query(
                filter={"source_date": {"$gte": params["week_start"], "$lt": params["week_end"]}},
            )
            themes = await self.ruvector.cluster(units)
            return self.render_weekly_rollup(themes)

        elif page_type == "decisions":
            # Query by type
            units = await self.ruvector.query(
                filter={"type": "decision"},
                order_by="source_date",
            )
            return self.render_decisions_log(units)
```

### Multiple Views from Same Data

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         RUVECTOR BRAIN                                   │
│                     (Primary Knowledge Store)                            │
│                                                                          │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│   │ Summary  │  │ Summary  │  │ Summary  │  │ Summary  │               │
│   │ #general │  │ #eng     │  │ #product │  │ #support │               │
│   │ May 5    │  │ May 5    │  │ May 5    │  │ May 5    │               │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘               │
│        │             │             │             │                       │
│        └──────────┬──┴─────────────┴──┬──────────┘                       │
│                   ▼                   ▼                                  │
│            ┌─────────────────────────────────┐                           │
│            │     Knowledge Units + GNN       │                           │
│            │  (claims, decisions, Q&A, etc.) │                           │
│            └─────────────────────────────────┘                           │
│                            │                                             │
└────────────────────────────┼─────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  TOPIC VIEW   │   │  DAILY VIEW   │   │  WEEKLY VIEW  │
│               │   │               │   │               │
│ topics/       │   │ log.md        │   │ reports/      │
│ auth.md       │   │ May 5 digest  │   │ week-19.md    │
│ api-design.md │   │ cross-channel │   │ themes +      │
│ (on-demand)   │   │ narrative     │   │ progress      │
└───────────────┘   └───────────────┘   └───────────────┘
```

### Benefits of Inversion

| Aspect | Wiki-Primary (Current) | RuVector-Primary |
|--------|----------------------|------------------|
| **Source of truth** | Markdown files | Knowledge graph |
| **Cross-channel synthesis** | Explicit (Layer 2) | Query-time aggregation |
| **Temporal views** | Pre-generated | Generated on-demand |
| **Granularity** | Fixed at ingest | Flexible at render |
| **Storage** | Duplicated (md + vectors) | Single store |
| **Human edits** | Direct to markdown | Feed back to graph |
| **Git versioning** | ✅ Native | ⚠️ Needs export |

### Challenges

1. **Git Versioning**: Markdown in git is nice for history. RuVector needs explicit snapshotting.
2. **Human Edits**: If someone edits a wiki page, how does it propagate back?
3. **Caching**: Generate pages on every request? Pre-render common views?
4. **Offline Access**: Markdown works offline. RuVector requires the service.

### Hybrid: RuVector Primary with Markdown Cache

```python
class HybridWikiRenderer:
    """
    RuVector is primary. Markdown is cached rendering.
    """

    async def get_page(self, path: str) -> str:
        # 1. Check if cached markdown is fresh
        cache_meta = await self.get_cache_meta(path)
        if cache_meta and not self.is_stale(cache_meta):
            return await self.read_cached_markdown(path)

        # 2. Render from RuVector
        page_type, params = self.parse_path(path)
        content = await self.render_wiki_page(page_type, params)

        # 3. Cache as markdown (for git, offline, human review)
        await self.write_cached_markdown(path, content)

        return content

    async def on_human_edit(self, path: str, new_content: str):
        """Human edited the markdown directly."""
        # 1. Diff to find what changed
        old_content = await self.render_wiki_page(...)
        changes = self.diff(old_content, new_content)

        # 2. Create correction units in RuVector
        for change in changes:
            await self.ruvector.store(
                content=change.new_text,
                type="human_correction",
                corrects=change.old_text,
                source_id="human_edit",
                confidence=1.0,  # Human edits are authoritative
            )

        # 3. Re-render affected pages
        await self.invalidate_cache(path)
```

### Implications for ADR-087 Question

If RuVector is primary:

- **Daily per-channel** → Just store summaries with channel+date metadata
- **Daily cross-channel** → Query-time aggregation, no pre-synthesis needed
- **Weekly rollup** → Query-time clustering, render on demand

**The ingestion granularity question becomes moot** because granularity is a render-time choice, not an ingest-time choice.

---

## Recommendation

**Leverage ADR-057's capabilities** to minimize redundant synthesis:

### What ADR-057 Already Does Well
- **Topic Clustering**: GNN finds related pages across channels automatically
- **Semantic Search**: Users query "API migration" and find all related content
- **Relationship Inference**: Pages mentioning same entities get linked

### What Still Needs Explicit Synthesis
- **Daily Narrative**: "What happened today?" requires cross-channel view
- **Causal Chains**: "Discussion A led to decision B" needs LLM to see both
- **Executive Summary**: High-level digest for `log.md`

**Keep ADR-067 as-is**, but add:

1. **Daily cross-channel synthesis** (Layer 2)
   - Input: Per-channel summaries (not raw messages)
   - Output: `log.md` updates, `decisions/` pages
   - Runs: End of day (after all channel summaries)

2. **Weekly rollup** (Layer 3)
   - Input: 7 daily cross-channel summaries
   - Output: `projects/` updates, weekly digest
   - Runs: Sunday evening

3. **Monthly digest** (Layer 4, future)
   - Input: 4 weekly rollups
   - Output: Monthly reports, trend analysis
   - Runs: 1st of month

This **compositional approach** uses each layer's output as the next layer's input, keeping context windows manageable while building progressively richer synthesis.

---

## Success Metrics

| Metric | Current | With Layers |
|--------|---------|-------------|
| Cross-page links discovered | ~2/page | ~5/page |
| Time to find related info | ~30s | ~10s |
| Decision traceability | 40% | 80% |
| Wiki staleness (topics) | <1 day | <1 day |
| Wiki staleness (projects) | N/A | <7 days |

---

## Implementation Phases

### Phase 1: Daily Cross-Channel (2 weeks)
- [ ] Create `CrossChannelSynthesizer` class
- [ ] Scheduled job: end-of-day synthesis
- [ ] Update `log.md` template for cross-channel format
- [ ] Add `decisions/` auto-extraction

### Phase 2: Weekly Rollup (1 week)
- [ ] Create `WeeklyRollup` class
- [ ] Scheduled job: Sunday synthesis
- [ ] Project page templates
- [ ] Week-over-week comparison

### Phase 3: Evaluation (2 weeks)
- [ ] A/B test wiki quality (user survey)
- [ ] Measure search success rate
- [ ] Track cross-reference usage

---

## Consequences

### Positive
- Richer wiki with cross-channel insights
- Temporal patterns visible in weekly rollups
- Better executive/management view
- Compositional (layers build on each other)

### Negative
- Additional LLM costs (~27%)
- More scheduled jobs to maintain
- Potential for synthesis errors to compound

### Mitigations
- Layer 2+ use summaries, not raw messages (cheaper, smaller)
- Each layer is optional and toggleable per guild
- **ADR-057 Coherence Gate** validates cross-layer consistency
- **ADR-057 GNN** provides automatic relationship discovery as fallback if cross-channel synthesis is disabled

---

## References

- **[ADR-057: Compounding Wiki RuVector](./ADR-057-compounding-wiki-ruvector.md)** - Primary reference for wiki capabilities (HNSW, GNN, SONA, Coherence Gate)
- [ADR-056: Compounding Wiki Standard](./ADR-056-compounding-wiki-standard.md) - Baseline FTS5 implementation
- [ADR-061: Wiki Population Strategies](./ADR-061-wiki-population-strategies.md)
- [ADR-067: Automatic Wiki Ingestion](./ADR-067-automatic-wiki-ingestion.md) - Current per-channel approach
- [Karpathy's Compounding Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
