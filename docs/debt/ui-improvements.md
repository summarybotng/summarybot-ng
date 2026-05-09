# UI Improvements - Technical Debt

Created: 2026-05-09

## Accessibility (Priority: High)

### Critical WCAG Level A Issues
1. **Missing ARIA labels on icon-only buttons** - Refresh, Star ratings, pagination buttons
2. **Missing keyboard navigation** - Clickable table rows/cards have `onClick` but no `onKeyDown`
3. **Missing form labels** - Filter inputs in AuditLog, Summaries lack `htmlFor` associations

### Major WCAG Level AA Issues
1. **No focus indicators** - Custom clickable elements (StarRating, table rows) lack `focus-visible` styles
2. **No screen reader support** - Only 1 `sr-only` instance; no `aria-live` for dynamic updates

### Fixes Needed
```tsx
// 1. Add aria-label to icon buttons
<Button aria-label="Refresh data"><RefreshCw /></Button>

// 2. Add keyboard support to clickable rows
<TableRow
  onClick={handler}
  onKeyDown={(e) => e.key === 'Enter' && handler()}
  tabIndex={0}
  role="button"
/>

// 3. Associate labels with inputs
<label htmlFor="user-name-filter">User name</label>
<Input id="user-name-filter" ... />
```

## Copy Summary Link (Priority: Medium)

Add a "Copy Link" action to SummaryActions component:
- Add `onCopyLink` handler to `SummaryActionHandlers` interface
- Add clipboard API call with `navigator.clipboard.writeText()`
- Add Link icon from lucide-react
- Show toast on successful copy

URL format: `/guilds/{guildId}/summaries/{summaryId}`

## Google Drive Sync Navigation (Priority: Low)

Currently accessible via: **Sidebar → Retrospective → Google Drive Sync section**

Consider:
1. Add link in Settings page under "Integrations" section
2. Add Cloud icon indicator in sidebar when Drive is configured
3. Rename "Retrospective" to "Archive & Sync" for clarity

## Lightbox/Modal Scrollability (Priority: Medium)

Audit all Dialog/Sheet/Modal components to ensure:
- Content is scrollable when exceeding viewport height
- Use `overflow-y-auto` or `ScrollArea` component
- Test with long content (e.g., summary details with many key points)

Known areas to check:
- Summary detail view
- Push to channel dialog
- Email delivery dialog
- Settings modals

## Audit Log User Consistency (Priority: Medium)

Some audit events have `user_name: NULL` while other events for the same `user_id` have the correct name.

Example: User ID `605061444035149845` has 146 events with NULL name and 277 with "martincleaver."

Fix options:
1. **Backfill**: Update NULL user_names by looking up from events with known names
2. **Lookup on display**: If user_name is NULL, lookup from Discord/other sources
3. **Click-through**: Add ability to click user_id to see all events for that user

## Audit Log User Click-Through (Priority: Low)

Add ability to:
1. Click on a user name/ID in audit log to filter by that user
2. Navigate to a "User Activity" page showing all events for that user
3. Show user details panel with: total events, event types, recent activity

## Summary Detail Metadata Display (Priority: Medium)

Summary detail view should show additional fields:
- `continuity_week_number` (if present)
- `previous_summary_id` (with link if present)
- `archive_granularity` (daily/weekly/monthly)
- Full metadata from `summary_json`

Currently these fields exist in DB but aren't shown in the UI detail view.
