# ADR-069: Wiki and Jobs UX Improvements

## Status
Proposed (2026-04-27)

## Context

After observing the wiki and jobs pages in production, several UX issues have been identified that reduce discoverability and clarity.

### Observations

#### Wiki Pages - What Works Well

1. **Synthesis/Updates tabs** (ADR-063): Clear separation of AI-generated synthesis vs raw updates
2. **Breadcrumb navigation**: Good orientation within category hierarchy
3. **Source count badges**: Quick visibility of page authority
4. **Star ratings** (ADR-065): User feedback on synthesis quality
5. **Wiki browser filters** (ADR-064): Filtering by source count, synthesis, rating

#### Wiki Pages - What Needs Improvement

1. **Navigation tree ignores filters**: WikiBrowser has powerful filters, but WikiNavTree shows all pages regardless. Users filtering for "pages with >1 sources" still see single-source pages in nav.

2. **Source reference cards lack metadata**: When viewing a source reference (`?source=summary-xxx`), only shows source ID and page count. Missing:
   - Platform (Discord, WhatsApp, Telegram)
   - Date of original summary
   - Channels included
   - Summary scope (server, category, channel)

3. **Links to/from disconnect**: Pages show "Links to:" and "Linked from:" but:
   - Links are often to non-existent pages (wiki agent creates outbound links optimistically)
   - No indication which links are "live" vs "orphan"
   - Links in content may not match the links panel

4. **Default filter should emphasize quality**: Single-source pages often have thin content. Default should filter to pages with substance (>1 sources).

#### Jobs Page - What Works Well

1. **Status badges**: Clear visual indication of job state
2. **Progress bars**: Real-time progress for running jobs
3. **Auto-refresh**: Active jobs refresh automatically
4. **Pause/Resume buttons** (ADR-068): Job control for long-running tasks

#### Jobs Page - What Needs Improvement

1. **Job description buried**: Platform, channels, date range are in a muted box. Users can't quickly see "what was this job?"

2. **Wiki backfill jobs lack context**: Only shows progress numbers, not what's being backfilled

3. **No job title/description**: Jobs are identified by type badge and ID fragment, not by meaningful description like "Daily Discord Summary" or "Server #general backfill"

---

## Decision

### 1. Unified Filter State for Wiki Navigation

Share filter state between WikiBrowser and WikiNavTree:

```tsx
// WikiNavTree now accepts filters prop
<WikiNavTree
  tree={tree}
  currentPath={pagePath}
  filters={filters}  // Same filters as WikiBrowser
/>
```

Navigation tree hides pages that don't match current filters.

### 2. Default Filter: min_sources >= 2

Change default WikiBrowser filter from `{}` to `{ min_sources: 2 }`:

```tsx
const [filters, setFilters] = useState<WikiFilters>({
  min_sources: 2,  // Default to pages with substance
  sort_by: "updated_at",
  sort_order: "desc",
});
```

Add "Show all" button to remove this filter.

### 3. Enhanced Source Reference Card

Add full metadata to source reference display:

```tsx
<Card className="border-primary/50">
  <CardHeader>
    <CardTitle>Source: Discord Server Summary</CardTitle>
  </CardHeader>
  <CardContent>
    <div className="grid grid-cols-2 gap-4">
      <div>
        <span className="text-muted-foreground">Platform</span>
        <div className="flex items-center gap-2">
          <DiscordIcon /> Discord
        </div>
      </div>
      <div>
        <span className="text-muted-foreground">Date</span>
        <div>April 3, 2026</div>
      </div>
      <div>
        <span className="text-muted-foreground">Scope</span>
        <div>Server (44 channels)</div>
      </div>
      <div>
        <span className="text-muted-foreground">Channels</span>
        <div>#general, #dev, +42 more</div>
      </div>
    </div>
  </CardContent>
</Card>
```

### 4. Prominent Job Description

Restructure JobCard to lead with job description:

```tsx
<Card>
  {/* NEW: Job title/description as header */}
  <div className="flex items-center gap-3 p-4 border-b">
    <JobTypeIcon job_type={job.job_type} />
    <div>
      <h3 className="font-medium">{generateJobTitle(job)}</h3>
      <p className="text-sm text-muted-foreground">
        {generateJobDescription(job)}
      </p>
    </div>
    <div className="ml-auto flex gap-2">
      <StatusBadge status={job.status} />
    </div>
  </div>
  {/* Rest of card content */}
</Card>
```

Job title generator:
```typescript
function generateJobTitle(job: Job): string {
  switch (job.job_type) {
    case "wiki_backfill":
      return "Wiki Knowledge Base Backfill";
    case "manual":
      return job.server_name
        ? `${job.server_name} Summary`
        : "Manual Summary";
    case "scheduled":
      return job.granularity === "daily"
        ? "Daily Summary"
        : `${job.granularity} Summary`;
    case "retrospective":
      return `Retrospective: ${formatDateRange(job.date_range)}`;
    default:
      return "Summary Job";
  }
}

function generateJobDescription(job: Job): string {
  const parts: string[] = [];

  // Platform
  if (job.source_key?.includes("discord")) parts.push("Discord");
  else if (job.source_key?.includes("whatsapp")) parts.push("WhatsApp");

  // Channels
  if (job.channel_ids?.length) {
    parts.push(`${job.channel_ids.length} channels`);
  }

  // Date range
  if (job.date_range?.start && job.date_range?.end) {
    parts.push(formatDateRange(job.date_range));
  }

  // Scope
  if (job.scope) parts.push(`${job.scope} scope`);

  return parts.join(" · ") || "Processing...";
}
```

### 5. Link Status Indicators

Add visual indicators for link validity:

```tsx
{page.linked_pages_from.map((link) => (
  <Link
    to={`/guilds/${guildId}/wiki/${link.path}`}
    className={`
      ${link.exists ? "text-primary" : "text-muted-foreground line-through"}
    `}
  >
    {link.exists ? <FileText /> : <FileQuestion />}
    {link.title}
  </Link>
))}
```

Backend returns `exists: boolean` for each linked page.

---

## Implementation

### Phase 1: Quick Wins (This PR)

1. Default WikiBrowser to `min_sources: 2`
2. Add prominent job title/description to JobCard
3. Pass filters to WikiNavTree for filtering

### Phase 2: Backend Changes (Follow-up)

1. Extend source reference API to return full summary metadata
2. Add `exists` field to linked pages response
3. Add job description field to summary_jobs table

---

## Consequences

### Positive
- Users see quality content by default (multi-source pages)
- Jobs are immediately identifiable by description
- Navigation respects user's filter preferences
- Source references provide full context

### Negative
- Single-source pages less discoverable (mitigated by "Show all" button)
- More data in API responses for source metadata
- Job description generation adds complexity

---

## References

- [ADR-064: Wiki Navigation Filters](./ADR-064-wiki-navigation-filters.md)
- [ADR-063: Wiki Page Tabs](./ADR-063-wiki-page-tabs.md)
- [ADR-068: Wiki Backfill Jobs](./ADR-068-wiki-backfill-jobs.md)
