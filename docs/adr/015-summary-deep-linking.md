# ADR-015: Summary Deep Linking and Search

## Status
Proposed

## Context

Users need to:
1. Share direct links to specific summaries for discussion
2. Navigate directly to a summary by ID (shown in the UI per ADR-004 fix)
3. Search for summaries by title, content, date range, or other criteria
4. Bookmark or reference summaries in external tools

Currently, summaries can only be accessed by navigating through the guild → summaries list → clicking a card. There's no way to:
- Link directly to a summary
- Search within summaries
- Navigate by ID

## Decision

### 1. URL Structure

Implement deep-linkable URLs for summaries:

```
/guilds/{guild_id}/summaries/{summary_id}
```

**Examples:**
- `/guilds/123456789/summaries/sum_8d35d83ed123`
- `/guilds/123456789/summaries?search=standup`
- `/guilds/123456789/summaries?date=2024-02-22`

### 2. Route Changes

**New Routes:**
```typescript
// Direct summary view
/guilds/:id/summaries/:summaryId

// Summary list with search/filter
/guilds/:id/summaries?search=<query>&date=<date>&source=<source>
```

**Implementation:**
- Add route parameter for `summaryId`
- Auto-open detail sheet when `summaryId` is present in URL
- Update URL when opening/closing summary detail sheet
- Support back/forward navigation

### 3. Search Functionality

**Frontend:**
- Add search input to StoredSummariesTab
- Real-time filtering as user types
- Search across: title, summary_text, key_points

**Backend API Enhancement:**
```
GET /api/v1/guilds/{guild_id}/stored-summaries?search=<query>
```

**Search Fields:**
- `title` - Summary title
- `summary_text` - Full summary content
- `key_points` - Key points array (joined)
- `id` - Exact ID match (for navigation by ID)

### 4. Quick Navigation

**"Go to Summary" Feature:**
- Command palette or search box
- Accepts summary ID (full or partial)
- Accepts summary title fragment
- Keyboard shortcut: `Ctrl+K` or `Cmd+K`

**Implementation:**
```typescript
// Quick nav input
<Input
  placeholder="Search summaries or paste ID..."
  onKeyDown={(e) => {
    if (e.key === 'Enter') {
      navigateToSummary(value);
    }
  }}
/>
```

### 5. Copy Link Feature

Add "Copy Link" button to summary detail sheet:
```typescript
<Button onClick={() => {
  navigator.clipboard.writeText(
    `${window.location.origin}/guilds/${guildId}/summaries/${summary.id}`
  );
  toast({ title: "Link copied!" });
}}>
  <Link className="mr-2 h-4 w-4" />
  Copy Link
</Button>
```

### 6. API Changes

**New Endpoint - Search Summaries:**
```
GET /api/v1/guilds/{guild_id}/stored-summaries/search?q=<query>
```

Response includes relevance scoring and highlights.

**Enhanced List Endpoint:**
```
GET /api/v1/guilds/{guild_id}/stored-summaries?search=<query>&id=<id>
```

Parameters:
- `search` - Full-text search query
- `id` - Exact or prefix ID match
- `date_from` / `date_to` - Date range filter
- `source` - Filter by source type

## Implementation Plan

### Phase 1: Deep Linking (Core)
1. Add `/guilds/:id/summaries/:summaryId` route
2. Auto-open detail sheet from URL parameter
3. Update URL on sheet open/close
4. Add "Copy Link" button

### Phase 2: Search
1. Add search input to StoredSummariesTab
2. Implement backend search endpoint
3. Add debounced search with loading state
4. Highlight search matches in results

### Phase 3: Quick Navigation
1. Add command palette component
2. Implement keyboard shortcut
3. Support ID and title search
4. Add recent summaries to quick nav

## File Changes

### Frontend
- `src/frontend/src/App.tsx` - Add new route
- `src/frontend/src/components/summaries/StoredSummariesTab.tsx` - Search input, URL sync
- `src/frontend/src/hooks/useStoredSummaries.ts` - Search parameter support

### Backend
- `src/dashboard/routes/summaries.py` - Add search parameter to list endpoint
- `src/data/sqlite.py` - Full-text search implementation

## Consequences

### Positive
- Users can share and bookmark summaries
- Easier navigation for power users
- Better discoverability of past summaries
- Consistent with modern web app UX patterns

### Negative
- Additional complexity in routing
- Need to handle invalid/deleted summary IDs gracefully
- Search indexing may impact performance on large datasets

## Security Considerations

- Guild access check required before showing summary
- Summary IDs should not leak information
- Rate limiting on search endpoint to prevent abuse

## Related ADRs

- ADR-004: Grounded Summary Citations (summary ID display)
- ADR-005: Stored Summary Management
- ADR-008: Unified Summary Experience
