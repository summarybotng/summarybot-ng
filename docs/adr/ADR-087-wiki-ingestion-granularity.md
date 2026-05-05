# ADR-087: Wiki Ingestion Granularity - Cross-Channel vs. Temporal Strategies

## Status
Proposed

## Decision

**Implement RuVector as the primary knowledge store. Ingest from raw chat with channel continuity. Wiki pages become rendered views.**

This supersedes the original question (daily per-channel vs cross-channel vs weekly):
1. **Ingestion granularity** becomes a render-time choice, not ingest-time
2. **Channel continuity** (longitudinal with weekly checkpoints) beats daily cross-channel stitching
3. **Raw messages** are the preferred source; summaries are fallback for older content

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

**Implement RuVector-primary architecture. Ingest from raw chat content with channel continuity.**

### Reframing the Question

The original framing compared:
- Daily per-channel summaries
- Daily cross-channel summaries
- Weekly same-channel summaries

But this comparison is unfair. **Daily cross-channel stitching** is the wrong approach to compare against. The better comparison is:

| Approach | What it does | Problem |
|----------|--------------|---------|
| Daily cross-channel | Horizontal stitching across channels each day | Loses thread continuity |
| **Channel continuity** | Follow conversations longitudinally with periodic checkpoints | ✅ Preserves context |

### The Channel Continuity Model

```
Week 1                          Week 2                          Week 3
┌─────────────────────┐        ┌─────────────────────┐        ┌─────────────────────┐
│ #engineering        │        │ #engineering        │        │ #engineering        │
│                     │        │                     │        │                     │
│ Mon: API discussion │        │ Mon: (continues)    │        │ Mon: (continues)    │
│ Tue: Auth debate    │───────▶│ Tue: Auth resolved  │───────▶│ Tue: Auth shipped   │
│ ...                 │        │ ...                 │        │ ...                 │
│                     │        │                     │        │                     │
│ ┌─────────────────┐ │        │ ┌─────────────────┐ │        │                     │
│ │ Week 1 Summary  │─┼────────┼▶│ Context carried │ │        │                     │
│ │ (checkpoint)    │ │        │ │ forward         │ │        │                     │
│ └─────────────────┘ │        │ └─────────────────┘ │        │                     │
└─────────────────────┘        └─────────────────────┘        └─────────────────────┘
```

The **end-of-week summary** acts as a continuity checkpoint:
- Carries context forward to next week
- No need to re-read all historical messages
- Topics spanning weeks maintain coherence
- Avoids artificial daily boundaries

### Why Ingest from Raw Chat Content

| Factor | From Summaries | From Raw Chat |
|--------|---------------|---------------|
| Signal fidelity | Lossy (summarized) | Full context |
| Thread continuity | Fragmented by daily cuts | Natural conversation flow |
| Cross-references | Lost ("as John said...") | Preserved |
| Semantic clustering | Topics split by days | Topics cluster naturally |

**Summaries become a fallback** for content beyond API retention, not the primary source.

### Ingestion Priority

```
1. Raw messages (where available)
   └─ Discord: ~90 days via API
   └─ Slack: varies by plan
   └─ WhatsApp: full archives imported

2. End-of-week continuity checkpoints
   └─ Carry context forward without infinite history
   └─ Enable longitudinal coherence

3. Stored summaries (fallback)
   └─ For content beyond API retention
   └─ Better than nothing
```

### What Changes from ADR-067

| ADR-067 (Current) | RuVector-Primary + Continuity |
|-------------------|-------------------------------|
| Daily summaries → Wiki pages | Raw messages → Knowledge units |
| Daily boundaries | Conversation/thread boundaries |
| Cross-channel synthesis jobs | Query-time aggregation |
| FTS5 keyword search | HNSW semantic search |
| Markdown source of truth | RuVector source of truth |
| No continuity mechanism | Weekly checkpoints carry context |

### Migration Path

1. **Implement RuVector foundation** (ADR-057)
2. **Ingest WhatsApp archives** (full longitudinal history available)
3. **Fetch Discord/Slack recent history** (API limits apply)
4. **Use summaries as fallback** for older content
5. **Add weekly continuity checkpoints** for ongoing ingestion
6. **Build view renderers** for wiki pages on demand

---

## Success Metrics

| Metric | Current (ADR-067) | RuVector-Primary |
|--------|-------------------|------------------|
| Cross-page links discovered | ~2/page (manual) | ~5/page (GNN auto) |
| Search relevance | 70% (FTS5 keyword) | 90% (HNSW semantic) |
| Time to find related info | ~30s | ~10s |
| Query flexibility | Fixed pages | Any granularity on demand |
| Scheduled synthesis jobs | 1/channel/day + cross-channel | 0 (query-time) |
| Storage duplication | wiki_pages + summaries | Single knowledge store + cache |

---

## Implementation Phases

### Phase 1: RuVector Foundation (ADR-057)
- [ ] Implement vector store with HNSW index
- [ ] Knowledge unit extraction from summaries
- [ ] Embedding pipeline (text-embedding-3-small)
- [ ] Basic semantic search

### Phase 2: Wiki View Renderers
- [ ] `render_topic_page(topic)` - semantic query + format
- [ ] `render_daily_digest(date)` - date filter + cross-channel aggregate
- [ ] `render_weekly_rollup(week)` - date range + clustering
- [ ] `render_decisions_log()` - type filter

### Phase 3: Hybrid Cache Layer
- [ ] Markdown generation from RuVector queries
- [ ] Staleness tracking (invalidate on new ingests)
- [ ] Human edit feedback loop to RuVector
- [ ] Git export for version history

### Phase 4: Migration & Deprecation
- [ ] Backfill existing wiki sources to RuVector
- [ ] Parallel operation (both stores)
- [ ] Flip source of truth
- [ ] Remove pre-synthesis scheduled jobs

---

## Consequences

### Positive
- **Single source of truth** - RuVector holds all knowledge, no sync issues
- **Flexible granularity** - Daily/weekly/topic views generated on demand
- **No pre-synthesis jobs** - Simpler scheduling, no cascading failures
- **Semantic search** - HNSW understands intent, not just keywords
- **Automatic relationships** - GNN discovers connections without explicit links
- **Coherence validation** - Gate prevents hallucination accumulation

### Negative
- **RuVector dependency** - Must implement ADR-057 first
- **Compute costs shift** - From scheduled synthesis to query-time rendering
- **Cache invalidation** - Must track when to regenerate markdown
- **Migration complexity** - Existing wiki data needs backfill to RuVector

### Mitigations
- **Hybrid cache** - Markdown persists for offline/git, regenerated on staleness
- **Progressive migration** - Run both stores in parallel during transition
- **Render caching** - Cache popular views, invalidate on new ingests
- **Backfill tooling** - Script to embed existing wiki sources into RuVector

---

## References

- **[ADR-057: Compounding Wiki RuVector](./ADR-057-compounding-wiki-ruvector.md)** - Primary reference for wiki capabilities (HNSW, GNN, SONA, Coherence Gate)
- [ADR-056: Compounding Wiki Standard](./ADR-056-compounding-wiki-standard.md) - Baseline FTS5 implementation
- [ADR-061: Wiki Population Strategies](./ADR-061-wiki-population-strategies.md)
- [ADR-067: Automatic Wiki Ingestion](./ADR-067-automatic-wiki-ingestion.md) - Current per-channel approach
- [Karpathy's Compounding Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
