# ADR-040: Jobs Navigation Rethink

## Status
Implemented

## Context

Currently, Jobs are accessible as a tab within the Summaries page (ADR-013):

```
Summaries Page
├── [All Summaries] tab
├── [Jobs] tab          ← Current location
└── [Retrospective] tab
```

**Problems with current placement:**

1. **Discovery**: Jobs are hidden within the Summaries page - users must navigate to Summaries first, then click the Jobs tab
2. **Cross-cutting concern**: Jobs span multiple features (summaries, retrospectives, scheduled tasks) but are nested under one feature
3. **Quick access**: When a job fails, users want quick access to check status without navigating through Summaries
4. **Mental model**: Jobs represent background work/processing - they're a system-wide concern, not summary-specific

**User feedback patterns:**
- "Where do I see if my scheduled summary ran?"
- "I clicked Generate but can't find where it went"
- "How do I check if retrospective jobs are still running?"

## Decision

Move Jobs to the left navigation sidebar as a top-level navigation item.

### New Navigation Structure

```
Left Sidebar
├── Overview
├── Channels
├── Summaries        ← Simplified: All Summaries + Retrospective Setup
├── Jobs             ← NEW: Promoted to top-level
├── Schedules
├── Prompts
├── Webhooks
├── Feeds
├── Errors
├── Retrospective
└── Settings
```

### UI Changes

#### 1. GuildSidebar.tsx - Add Jobs nav item

```tsx
const navItems = [
  { icon: LayoutDashboard, label: "Overview", path: "" },
  { icon: Hash, label: "Channels", path: "/channels" },
  { icon: FileText, label: "Summaries", path: "/summaries" },
  { icon: Briefcase, label: "Jobs", path: "/jobs", showBadge: true },  // NEW
  { icon: Calendar, label: "Schedules", path: "/schedules" },
  // ... rest
];
```

#### 2. Jobs Badge - Show active job count

Similar to Errors badge, show count of running/failed jobs:

```tsx
{showBadge && activeJobCount > 0 && (
  <Badge variant={hasFailedJobs ? "destructive" : "secondary"}>
    {activeJobCount}
  </Badge>
)}
```

#### 3. New Jobs Page

Create dedicated `/guilds/{id}/jobs` page with:

```tsx
function JobsPage() {
  return (
    <div className="space-y-6">
      <PageHeader>
        <h1>Jobs</h1>
        <p>Background tasks and generation status</p>
      </PageHeader>

      {/* Quick stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard title="Running" count={runningCount} />
        <StatCard title="Completed (24h)" count={completedCount} />
        <StatCard title="Failed" count={failedCount} variant="destructive" />
        <StatCard title="Pending" count={pendingCount} />
      </div>

      {/* Jobs list with filters */}
      <JobsTab guildId={guildId} />
    </div>
  );
}
```

#### 4. Summaries Page - Simplified

Remove Jobs tab from Summaries page, keep focus on content:

```tsx
<Tabs>
  <TabsTrigger value="all">All Summaries</TabsTrigger>
  <TabsTrigger value="retrospective">Retrospective Setup</TabsTrigger>
</Tabs>
```

### Benefits

1. **Quick access**: One click to see all background jobs
2. **Visibility**: Badge shows active/failed jobs at a glance
3. **Cleaner Summaries page**: Focused on viewing summaries, not monitoring jobs
4. **Consistent mental model**: Jobs as system-wide feature, not summary-specific
5. **Error correlation**: Jobs failures naturally visible alongside Errors in nav

### Cross-linking

From Summaries page, link to Jobs:
```tsx
{activeTaskId && (
  <Link to={`/guilds/${id}/jobs`}>
    View in Jobs →
  </Link>
)}
```

From Jobs page, link to resulting summary:
```tsx
{job.summary_id && (
  <Button asChild variant="ghost">
    <Link to={`/guilds/${id}/summaries?highlight=${job.summary_id}`}>
      View Summary
    </Link>
  </Button>
)}
```

## Implementation Phases

### Phase 1: Add Jobs to Navigation
- [x] Add Jobs nav item to GuildSidebar
- [x] Create `/guilds/{id}/jobs` route
- [x] Create JobsPage component (reuse JobsTab)

### Phase 2: Jobs Badge
- [x] Add useActiveJobCount hook
- [x] Show badge with running/failed count
- [x] Badge color: secondary for running, destructive if any failed

### Phase 3: Simplify Summaries
- [x] Remove Jobs tab from Summaries page
- [x] Add "View in Jobs" link when generating
- [ ] Update ADR-012 to reflect change

### Phase 4: Jobs Page Enhancements
- [x] Add quick stats cards
- [x] Add job type filter (manual, scheduled, retrospective)
- [ ] Add date range filter
- [x] Real-time updates via polling

## Key Files

- `src/frontend/src/pages/Jobs.tsx` - Jobs page with stats cards
- `src/frontend/src/hooks/useJobs.ts` - useActiveJobCount hook
- `src/frontend/src/components/layout/GuildSidebar.tsx` - Jobs nav item with badge
- `src/frontend/src/App.tsx` - Jobs route
- `src/frontend/src/pages/Summaries.tsx` - Jobs tab removed, "View in Jobs" link added

## Consequences

### Positive
- Jobs more discoverable and accessible
- Cleaner separation of concerns
- Better visibility of system status
- Consistent with other top-level features (Errors, Schedules)

### Negative
- Breaking change in navigation (users familiar with current location)
- Additional page to maintain
- Need to update documentation/guides

### Neutral
- JobsTab component can be reused
- No backend changes required

## Related ADRs
- ADR-012: Summaries UI Consolidation
- ADR-013: Unified Job Tracking

## Migration Notes

1. Add deprecation notice to old Jobs tab location (if keeping temporarily)
2. Update user documentation
3. Consider redirect from old URL pattern if bookmarked
