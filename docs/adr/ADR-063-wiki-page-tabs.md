# ADR-063: Wiki Page Tabs (Updates + Synthesis)

## Status
Proposed (Extends ADR-058)

## Context

Currently, wiki pages display all content in a single view that mixes raw updates from summaries with synthesized knowledge. As pages accumulate updates from multiple sources, they become:

1. **Long and repetitive** - Each ingest appends "## Update from summary-xxx" sections
2. **Hard to scan** - Users must read through all updates to understand the current state
3. **Unsynthesized** - No AI-generated summary of the accumulated knowledge

Users need both:
- **Audit trail** - See exactly what each source contributed (provenance)
- **Quick understanding** - Get a synthesized view of current knowledge

## Decision

Implement a **two-tab layout** for wiki page content:

### Tab 1: Synthesis (Default)
An LLM-generated summary that:
- Consolidates all updates into coherent prose
- Resolves contradictions (noting them if unresolved)
- Maintains source citations inline
- Updates on each page edit/ingest

### Tab 2: Updates (Raw)
The current append-only content showing:
- Each update section with source ID
- Original timestamps
- Full provenance chain
- Useful for debugging and auditing

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Wiki Page: Authentication                                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐ ┌─────────────────┐                                │
│  │ 📝 Synthesis    │ │ 📋 Updates      │                                │
│  │    (active)     │ │                 │                                │
│  └─────────────────┴─┴─────────────────┘                                │
│                                                                          │
│  # Authentication                                                        │
│                                                                          │
│  Our system uses JWT tokens with 15-minute expiry and 7-day             │
│  refresh tokens. OAuth 2.0 handles third-party integrations.            │
│  [📄 3 sources]                                                          │
│                                                                          │
│  ## Key Points                                                           │
│  - Access tokens: 15 minute expiry                                       │
│  - Refresh tokens: 7 day expiry                                         │
│  - OAuth 2.0 for external providers                                      │
│                                                                          │
│  ## Experts                                                              │
│  @alice (authentication), @bob (OAuth)                                  │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│  Last synthesized: 2 hours ago │ 3 sources │ 8 links                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

vs. Updates tab:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Wiki Page: Authentication                                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐ ┌─────────────────┐                                │
│  │ 📝 Synthesis    │ │ 📋 Updates      │                                │
│  │                 │ │    (active)     │                                │
│  └─────────────────┴─┴─────────────────┘                                │
│                                                                          │
│  # Authentication                                                        │
│                                                                          │
│  *Topic created from summary analysis*                                  │
│                                                                          │
│  ## Update from summary-a28017df-5b4d-44cf-838c-b8d5d7ef6706           │
│                                                                          │
│  Key Points:                                                             │
│  - Access tokens: 15 minute expiry [source:summary-a28017df...]        │
│  - Refresh tokens: 7 day expiry [source:summary-a28017df...]           │
│                                                                          │
│  ## Update from summary-sum_bea2129d5a12                                │
│                                                                          │
│  Key Points:                                                             │
│  - OAuth 2.0 implementation decided [source:summary-sum_bea...]        │
│  - @alice to lead authentication work [source:summary-sum_bea...]      │
│                                                                          │
│  ## Update from summary-7c442069-a4a4-4262-b8a3-70553288fdf8           │
│                                                                          │
│  Key Points:                                                             │
│  - Added MFA support discussion [source:summary-7c442069...]            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Model Changes

### WikiPage Table Extension

```sql
ALTER TABLE wiki_pages ADD COLUMN synthesis TEXT;
ALTER TABLE wiki_pages ADD COLUMN synthesis_updated_at TEXT;
ALTER TABLE wiki_pages ADD COLUMN synthesis_source_count INTEGER DEFAULT 0;
```

### WikiPage Model

```python
@dataclass
class WikiPage:
    id: str
    guild_id: str
    path: str
    title: str
    content: str              # Raw updates (append-only)
    synthesis: Optional[str]  # LLM-generated summary
    synthesis_updated_at: Optional[datetime]
    synthesis_source_count: int
    topics: List[str]
    source_refs: List[str]
    # ... existing fields
```

---

## Synthesis Generation

### Trigger Conditions

Synthesis regenerates when:
1. New content ingested (after ingest completes)
2. Manual "Regenerate" button clicked
3. Contradiction resolved
4. Scheduled batch job (nightly for stale pages)

### Synthesis Prompt

```python
SYNTHESIS_PROMPT = """
You are summarizing a wiki page about "{title}" for a software team.

The page contains multiple updates from different summaries. Synthesize these
into a coherent, well-organized document that:

1. Consolidates duplicate/overlapping information
2. Presents the most current understanding
3. Notes any unresolved contradictions with [⚠️ Conflict: ...]
4. Preserves source citations as [📄 N sources] for traceability
5. Organizes into logical sections (Overview, Key Points, Related, etc.)

Keep the synthesis concise but complete. Write in present tense.

## Raw Updates to Synthesize:

{content}

## Output Format:

Write clean Markdown. Group related information. Use bullet points for lists.
End with "---" followed by synthesis metadata.
"""
```

### Synthesis Response Schema

```python
@dataclass
class SynthesisResult:
    synthesis: str
    source_count: int
    conflicts_found: int
    topics_extracted: List[str]
    confidence: float  # 0-1 based on source agreement
```

---

## Frontend Implementation

### WikiPageView Component Update

```tsx
function WikiPageView({ page }: { page: WikiPage }) {
  const [activeTab, setActiveTab] = useState<"synthesis" | "updates">("synthesis");
  const { toast } = useToast();

  // Regenerate synthesis mutation
  const regenerateMutation = useMutation({
    mutationFn: () => api.post(`/guilds/${guildId}/wiki/pages/${page.path}/synthesize`),
    onSuccess: () => {
      queryClient.invalidateQueries(["wiki-page", guildId, page.path]);
      toast({ title: "Synthesis regenerated" });
    },
  });

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Breadcrumb>...</Breadcrumb>

      {/* Title and Actions */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{page.title}</h1>
        <div className="flex gap-2">
          {activeTab === "synthesis" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => regenerateMutation.mutate()}
              disabled={regenerateMutation.isPending}
            >
              <RefreshCw className={cn("h-4 w-4 mr-1", regenerateMutation.isPending && "animate-spin")} />
              Regenerate
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleShare}>
            <Link2 className="h-4 w-4 mr-1" />
            Share
          </Button>
        </div>
      </div>

      {/* Tab Navigation */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "synthesis" | "updates")}>
        <TabsList>
          <TabsTrigger value="synthesis" className="gap-2">
            <Sparkles className="h-4 w-4" />
            Synthesis
            {page.synthesis && (
              <Badge variant="secondary" className="ml-1 text-xs">
                {page.synthesis_source_count} sources
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="updates" className="gap-2">
            <FileText className="h-4 w-4" />
            Updates
            <Badge variant="outline" className="ml-1 text-xs">
              {page.source_refs.length}
            </Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="synthesis">
          {page.synthesis ? (
            <Card>
              <CardContent className="pt-6">
                <article className="prose dark:prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {page.synthesis}
                  </ReactMarkdown>
                </article>
                <div className="mt-4 pt-4 border-t text-sm text-muted-foreground">
                  Last synthesized: {formatRelative(page.synthesis_updated_at)}
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <Sparkles className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="font-medium mb-2">No synthesis yet</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Generate an AI summary of all updates on this page
                </p>
                <Button onClick={() => regenerateMutation.mutate()}>
                  <Sparkles className="h-4 w-4 mr-2" />
                  Generate Synthesis
                </Button>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="updates">
          <Card>
            <CardContent className="pt-6">
              <article className="prose dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {processedContent}
                </ReactMarkdown>
              </article>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Page info cards */}
      ...
    </div>
  );
}
```

---

## API Endpoints

### New Endpoint: Synthesize Page

```python
@router.post("/guilds/{guild_id}/wiki/pages/{path:path}/synthesize")
async def synthesize_page(
    guild_id: str,
    path: str,
    background_tasks: BackgroundTasks,
) -> SynthesizeResponse:
    """
    Trigger synthesis regeneration for a wiki page.

    Returns immediately with task_id for polling,
    or waits for completion if sync=true query param.
    """
    page = await wiki_repo.get_page(guild_id, path)
    if not page:
        raise HTTPException(404, "Page not found")

    # Generate synthesis
    synthesis_result = await synthesize_wiki_page(page)

    # Update page
    page.synthesis = synthesis_result.synthesis
    page.synthesis_updated_at = datetime.utcnow()
    page.synthesis_source_count = synthesis_result.source_count
    await wiki_repo.save_page(page)

    return SynthesizeResponse(
        success=True,
        synthesis_length=len(synthesis_result.synthesis),
        source_count=synthesis_result.source_count,
        conflicts_found=synthesis_result.conflicts_found,
    )
```

### Updated Get Page Response

```python
class WikiPageResponse(BaseModel):
    id: str
    path: str
    title: str
    content: str                    # Raw updates
    synthesis: Optional[str]        # AI summary
    synthesis_updated_at: Optional[datetime]
    synthesis_source_count: int
    topics: List[str]
    source_refs: List[str]
    inbound_links: int
    outbound_links: int
    confidence: int
    created_at: datetime
    updated_at: datetime
```

---

## Migration Strategy

### Phase 1: Schema + UI (This ADR)
1. Add synthesis columns to wiki_pages table
2. Update WikiPage model
3. Add tabs to WikiPageView component
4. Add /synthesize endpoint

### Phase 2: Background Synthesis
1. Trigger synthesis after ingest completes
2. Add synthesis to populate workflow
3. Nightly job for stale pages (>7 days since synthesis)

### Phase 3: Incremental Synthesis
1. Only re-synthesize changed sections
2. Cache synthesis chunks
3. Streaming synthesis for long pages

---

## Implementation Order

```
1. 064_wiki_synthesis.sql           - Add synthesis columns
2. src/wiki/models.py               - Update WikiPage model
3. src/wiki/synthesis.py            - Synthesis generation logic
4. src/data/sqlite/wiki_repository.py - Repository updates
5. src/dashboard/routes/wiki.py     - API endpoint
6. src/frontend/src/pages/Wiki.tsx  - Tab UI
7. src/wiki/agents/ingest_agent.py  - Trigger on ingest
```

---

## Consequences

### Positive
- Clean, readable synthesized view by default
- Full provenance preserved in Updates tab
- Reduces cognitive load when browsing wiki
- AI handles consolidation of overlapping updates
- Users can regenerate on demand

### Negative
- Additional LLM cost per synthesis
- Synthesis may miss nuance in raw updates
- Need to handle synthesis failures gracefully

### Mitigations
- Cache synthesis, only regenerate on changes
- Always show Updates tab as fallback
- Include "Last synthesized" timestamp for transparency
- Allow manual regeneration if synthesis is stale

---

## References

- [ADR-056: Compounding Wiki - Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-058: Wiki Rendering](./ADR-058-wiki-rendering.md)
- [ADR-060: Wiki Curation Model](./ADR-060-wiki-curation-model.md)
