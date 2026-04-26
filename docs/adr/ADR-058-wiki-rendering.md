# ADR-058: Wiki Rendering

## Status
Proposed (Depends on ADR-056/057)

## Context

ADR-056/057 define the Compounding Wiki data model and agent workflows. This ADR addresses **how users view and interact with the wiki** in the summarybot-ng dashboard.

The wiki needs to be:
- Browsable (navigate by category)
- Searchable (keyword and AI-powered)
- Contextual (linked from summaries)
- Accessible (quick access from anywhere)

Note: External sync (Google Drive) is covered in ADR-059. Curation model is covered in ADR-060.

## Decision

Implement a hybrid rendering approach:

1. **Wiki tab** - Full browse and search interface
2. **Summary integration** - Wiki updates shown on each summary
3. **Quick search** - Cmd+K access from anywhere
4. **Bot commands** - Search from Discord/Slack

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         WIKI RENDERING LAYER                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                     USER INTERFACES                              │   │
│   │                                                                   │   │
│   │   Dashboard                Slack/Discord           API           │   │
│   │   ┌─────────┐              ┌─────────┐            ┌─────────┐   │   │
│   │   │ Wiki UI │              │ /wiki   │            │ REST    │   │   │
│   │   │ Tab     │              │ command │            │ /wiki/* │   │   │
│   │   └────┬────┘              └────┬────┘            └────┬────┘   │   │
│   │        │                        │                      │        │   │
│   └────────┼────────────────────────┼──────────────────────┼────────┘   │
│            │                        │                      │            │
│            ▼                        ▼                      ▼            │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                     RENDERING ENGINE                             │   │
│   │                                                                   │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │   │
│   │   │  Markdown   │  │  Search     │  │  Citation               │ │   │
│   │   │  Renderer   │  │  Synthesizer│  │  Resolver               │ │   │
│   │   └─────────────┘  └─────────────┘  └─────────────────────────┘ │   │
│   │                                                                   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                     WIKI DATA (ADR-056/057)                      │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Dashboard Layout

### Navigation Structure

```
Dashboard
├── Summaries
├── Schedules
├── Archive
├── 📚 Wiki                    ◀── New tab
│   ├── Browse                 (tree view)
│   ├── Search                 (AI-powered)
│   ├── Recent Changes         (activity feed)
│   └── Needs Review           (curation queue)
├── Jobs
└── Settings
```

### Wiki Tab

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📚 Wiki                                              [🔍 Search...]    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐  ┌────────────────────────────────────────────────┐  │
│  │ Navigation   │  │                                                │  │
│  │              │  │  # Authentication                              │  │
│  │ 📁 Topics    │  │                                                │  │
│  │  ├ auth      │  │  Our system uses JWT tokens with OAuth 2.0    │  │
│  │  ├ caching   │  │  for third-party integrations.                │  │
│  │  ├ deploy    │  │                                                │  │
│  │  └ api       │  │  ## Token Lifecycle                           │  │
│  │              │  │                                                │  │
│  │ 📁 Decisions │  │  - Access tokens: 15 minute expiry            │  │
│  │  ├ 2024-01   │  │  - Refresh tokens: 7 day expiry               │  │
│  │  └ 2024-02   │  │                                                │  │
│  │              │  │  > 📄 Source: [backend-standup-jan-15]        │  │
│  │ 📁 Processes │  │                                                │  │
│  │  ├ deploy    │  │  ## Related                                   │  │
│  │  └ incident  │  │  - [OAuth Implementation](oauth.md)           │  │
│  │              │  │  - [Session Management](sessions.md)          │  │
│  │ 👥 Experts   │  │                                                │  │
│  │              │  │  ────────────────────────────────────────────  │  │
│  │ ❓ Questions │  │                                                │  │
│  │              │  │  📊 12 sources │ Updated 2d ago │ 8 links     │  │
│  │ 📋 Recent    │  │  👤 Experts: @alice, @bob                     │  │
│  └──────────────┘  └────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Page View Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Wiki > Topics > Authentication                          [Edit] [Share] │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  # Authentication                                                        │
│                                                                          │
│  Our system uses JWT tokens with OAuth 2.0 for third-party              │
│  integrations. [source:summary-2024-01-15]                              │
│                                                                          │
│  ## Token Lifecycle                                                      │
│                                                                          │
│  - Access tokens: 15 minute expiry [source:security-review-jan-22]     │
│  - Refresh tokens: 7 day expiry                                         │
│                                                                          │
│  > ⚠️ This section has a pending contradiction.                        │
│  > Previous claim: "30 minute expiry" [Review]                          │
│                                                                          │
│  ## Related Pages                                                        │
│  • [OAuth Implementation](oauth.md)                                     │
│  • [Session Management](sessions.md)                                    │
│  • [Security Decisions 2024-01](decisions/2024-01-jwt.md)              │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  📊 Page Info                                                            │
│  ┌──────────────┬──────────────┬──────────────┬──────────────────────┐ │
│  │ Sources: 3   │ Links: 8     │ Updated: 2d  │ Confidence: 94%      │ │
│  └──────────────┴──────────────┴──────────────┴──────────────────────┘ │
│                                                                          │
│  👤 Topic Experts                                                        │
│  [@alice 92%] [@bob 67%] [@carol 45%]                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Search Interface

### AI-Powered Search

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🔍 Search Wiki                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  How do we handle rate limiting?                             [⏎] │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  💡 AI Answer                                                    │   │
│  │                                                                   │   │
│  │  Rate limiting is set to 100 requests/minute per client IP.     │   │
│  │  Exceeded requests receive HTTP 429 with Retry-After header.    │   │
│  │  Redis is used for distributed rate tracking.                   │   │
│  │                                                                   │   │
│  │  Sources: [rate-limiting.md] [decisions/2024-01-redis.md]       │   │
│  │                                                                   │   │
│  │  [👍] [👎] [📝 Save to wiki]                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  📄 Relevant Pages                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  rate-limiting.md                              Updated 5d ago    │   │
│  │  API rate limiting configuration and strategies...              │   │
│  │  🏷️ api, infrastructure    👤 @alice, @bob                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Cmd+K Quick Search

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│     ┌───────────────────────────────────────────────────────────────┐   │
│     │  🔍  authentication                                            │   │
│     ├───────────────────────────────────────────────────────────────┤   │
│     │                                                                │   │
│     │  📚 Wiki Pages                                                 │   │
│     │  ├─ topics/authentication.md                                  │   │
│     │  ├─ topics/oauth.md                                           │   │
│     │  └─ decisions/2024-01-jwt-tokens.md                          │   │
│     │                                                                │   │
│     │  📄 Summaries                                                  │   │
│     │  ├─ Backend Standup - Jan 15 (mentions auth)                 │   │
│     │  └─ Security Review - Jan 22                                  │   │
│     │                                                                │   │
│     │  👤 Experts                                                    │   │
│     │  └─ @alice (92% confidence)                                   │   │
│     │                                                                │   │
│     │  Press Enter to search, ↑↓ to navigate                       │   │
│     └───────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Summary Integration

Each summary displays wiki updates it triggered:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Summary: Backend Standup - Jan 15, 2024                    [Regenerate]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ## Summary                                                              │
│  Team discussed caching strategy and decided on Redis...                │
│                                                                          │
│  ## Key Points                                                           │
│  • Decided to use Redis for caching (replacing Memcached)               │
│  • Rate limiting set to 100 req/min                                     │
│  • @alice will handle OAuth implementation                              │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  📚 Knowledge Captured                                      [View all →]│
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  This summary updated 8 wiki pages:                              │   │
│  │                                                                   │   │
│  │  📝 Modified:                                                    │   │
│  │  • [topics/caching.md] - Added Redis decision                   │   │
│  │  • [topics/rate-limiting.md] - Updated to 100 req/min           │   │
│  │  • [experts/expertise-map.md] - @alice → OAuth                  │   │
│  │                                                                   │   │
│  │  ✨ Created:                                                     │   │
│  │  • [decisions/2024-01-redis-caching.md]                         │   │
│  │                                                                   │   │
│  │  ⚠️ Needs Review: 1                                              │   │
│  │  • [caching.md] conflicts with previous Memcached mention       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Bot Commands

### Discord/Slack Integration

```
/wiki search <query>      - Search the wiki
/wiki page <path>         - Show a wiki page summary
/wiki ask <question>      - AI answers from wiki content
/wiki recent              - Show recent changes
/wiki expert <topic>      - Who knows about this topic?
```

### Example Interactions

```
User: /wiki ask How do we deploy to production?

Bot:  📚 Wiki Answer

      To deploy to production:
      1. Create PR and get approval
      2. Merge to main branch
      3. CI/CD pipeline triggers automatically
      4. Monitor Datadog for errors

      Sources:
      • [Deploy to Production](dashboard.com/wiki/processes/deploy.md)
      • [CI/CD Pipeline](dashboard.com/wiki/topics/cicd.md)

      👤 Experts: @devops-lead, @bob
```

```
User: /wiki expert authentication

Bot:  👤 Authentication Experts

      @alice     ████████████████░░░░  92% (47 contributions)
      @bob       █████████░░░░░░░░░░░  52% (18 contributions)
      @carol     ████░░░░░░░░░░░░░░░░  28% (8 contributions)

      Recent activity: @alice answered auth question 2 days ago
```

---

## Frontend Components

### WikiPage Component

```tsx
// src/frontend/src/components/wiki/WikiPage.tsx

interface WikiPageProps {
  page: WikiPage;
  sources: WikiSource[];
  relatedPages: WikiPage[];
  experts: UserExpertise[];
  contradictions: Contradiction[];
}

export function WikiPage({ page, sources, relatedPages, experts, contradictions }: WikiPageProps) {
  return (
    <div className="wiki-page">
      {/* Breadcrumb */}
      <Breadcrumb>
        <BreadcrumbItem href="/wiki">Wiki</BreadcrumbItem>
        <BreadcrumbItem href={`/wiki/${page.category}`}>{page.category}</BreadcrumbItem>
        <BreadcrumbItem>{page.title}</BreadcrumbItem>
      </Breadcrumb>

      {/* Title + Actions */}
      <header className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">{page.title}</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <Edit className="h-4 w-4 mr-1" /> Suggest Edit
          </Button>
          <Button variant="outline" size="sm">
            <Share className="h-4 w-4 mr-1" /> Share
          </Button>
        </div>
      </header>

      {/* Contradictions banner */}
      {contradictions.length > 0 && (
        <Alert variant="warning" className="mb-4">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Review Needed</AlertTitle>
          <AlertDescription>
            This page has {contradictions.length} conflicting claim(s).
            <Button variant="link" size="sm">Review</Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Markdown content with citations */}
      <article className="prose dark:prose-invert max-w-none">
        <WikiMarkdown
          content={page.content}
          sources={sources}
          onCitationClick={(id) => setSelectedSource(id)}
        />
      </article>

      {/* Sidebar info */}
      <aside className="mt-8 pt-6 border-t grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Sources" value={sources.length} />
        <Stat label="Links" value={page.inbound_links + page.outbound_links} />
        <Stat label="Updated" value={formatRelative(page.updated_at)} />
        <Stat label="Confidence" value={`${page.confidence}%`} />
      </aside>

      {/* Related pages */}
      <section className="mt-6">
        <h3 className="font-semibold mb-2">Related Pages</h3>
        <div className="flex flex-wrap gap-2">
          {relatedPages.map(p => (
            <Badge key={p.path} variant="secondary" asChild>
              <Link to={`/wiki/${p.path}`}>{p.title}</Link>
            </Badge>
          ))}
        </div>
      </section>

      {/* Experts */}
      <section className="mt-6">
        <h3 className="font-semibold mb-2">Topic Experts</h3>
        <div className="flex gap-3">
          {experts.map(e => (
            <ExpertBadge key={e.user_id} expert={e} />
          ))}
        </div>
      </section>
    </div>
  );
}
```

### Source Citation Component

```tsx
// Inline citation with hover preview
function SourceCitation({ sourceId, sources }: Props) {
  const source = sources.find(s => s.id === sourceId);

  return (
    <HoverCard>
      <HoverCardTrigger asChild>
        <span className="inline-flex items-center gap-1 text-xs bg-blue-100 dark:bg-blue-900 px-1.5 py-0.5 rounded cursor-help">
          <FileText className="h-3 w-3" />
          {source?.shortName || sourceId}
        </span>
      </HoverCardTrigger>
      <HoverCardContent className="w-80">
        <div className="space-y-2">
          <h4 className="font-medium">{source?.title}</h4>
          <p className="text-sm text-muted-foreground">
            {source?.excerpt}
          </p>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{formatDate(source?.created_at)}</span>
            <Link to={`/summaries/${sourceId}`} className="text-blue-500">
              View source →
            </Link>
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
```

---

## Source Reference Link Formats

Wiki pages contain source citations that link back to original summaries. These are rendered as clickable links in the UI.

### Supported Formats

| Format | Example | Description |
|--------|---------|-------------|
| UUID | `[source:summary-a28017df-5b4d-44cf-838c-b8d5d7ef6706]` | Standard UUID format |
| Legacy | `[source:summary-sum_bea2129d5a12]` | Legacy `sum_` prefix format |
| Update Header | `## Update from summary-{id}` | Section headers from ingest |

### Regex Pattern

The frontend uses `[\w-]+` to match any alphanumeric source ID:

```typescript
// src/frontend/src/pages/Wiki.tsx
const processedContent = page.content
  .replace(/\[source:(summary-[\w-]+)\]/g, '[📄 source](?source=$1)')
  .replace(/## Update from (summary-[\w-]+)/g, '## 📝 Update from [$1](?source=$1)');
```

### Link Resolution

Source links navigate to `/guilds/{guild_id}/wiki?source={source_id}` which shows:
1. All wiki pages referencing that source
2. A "View Summary" button linking to `/guilds/{guild_id}/summaries?view={summary_uuid}`

The summary UUID is extracted by removing the `summary-` prefix from the source ID.

---

## API Endpoints

```python
# src/dashboard/routes/wiki.py

router = APIRouter(prefix="/guilds/{guild_id}/wiki", tags=["wiki"])

@router.get("/pages")
async def list_pages(
    guild_id: str,
    category: Optional[str] = None,
    limit: int = 50
) -> List[WikiPageSummary]:
    """List wiki pages, optionally filtered by category."""

@router.get("/pages/{path:path}")
async def get_page(guild_id: str, path: str) -> WikiPageDetail:
    """Get a wiki page with full metadata."""

@router.get("/search")
async def search_wiki(
    guild_id: str,
    q: str,
    synthesize: bool = True,
    limit: int = 10
) -> WikiSearchResult:
    """Search wiki with optional AI synthesis."""

@router.get("/recent")
async def recent_changes(guild_id: str, days: int = 7) -> List[WikiChange]:
    """Get recently updated pages."""

@router.get("/tree")
async def get_tree(guild_id: str) -> WikiTree:
    """Get navigation tree structure."""

@router.post("/pages/{path:path}/suggest-edit")
async def suggest_edit(
    guild_id: str,
    path: str,
    body: SuggestEditRequest
) -> SuggestEditResponse:
    """Submit an edit suggestion for human review."""
```

---

## Implementation Phases

### Phase 1: Basic Rendering (2 weeks)
- [ ] Wiki tab with navigation tree
- [ ] Page view with markdown rendering
- [ ] Source citations display
- [ ] Basic keyword search (FTS5)

### Phase 2: AI Search (2 weeks)
- [ ] AI-synthesized answers
- [ ] Answer feedback (thumbs up/down)
- [ ] "Save to wiki" flow
- [ ] Cmd+K quick search

### Phase 3: Summary Integration (1 week)
- [ ] Wiki updates section on summaries
- [ ] Link from summary to affected pages
- [ ] Contradiction highlighting

### Phase 4: Bot Commands (1 week)
- [ ] /wiki search
- [ ] /wiki ask
- [ ] /wiki expert
- [ ] /wiki recent

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Wiki page views | >50/week | Dashboard analytics |
| Search queries | >20/week | Query logs |
| AI answer satisfaction | >75% | Thumbs up/down |
| Time to find answer | <30 seconds | User sessions |

## Consequences

### Positive
- Wiki accessible directly in dashboard
- AI search reduces time to find information
- Summary → wiki link shows knowledge capture
- Bot commands provide access without leaving chat

### Negative
- Additional frontend complexity
- AI synthesis requires compute
- Need to handle rendering edge cases

### Mitigations
- Progressive enhancement (basic works without AI)
- Cache AI synthesis results
- Comprehensive markdown test cases

## References

- [ADR-056: Compounding Wiki - Standard](./ADR-056-compounding-wiki-standard.md)
- [ADR-057: Compounding Wiki - RuVector](./ADR-057-compounding-wiki-ruvector.md)
- [ADR-059: Wiki External Sync](./ADR-059-wiki-external-sync.md)
- [ADR-060: Wiki Curation Model](./ADR-060-wiki-curation-model.md)
