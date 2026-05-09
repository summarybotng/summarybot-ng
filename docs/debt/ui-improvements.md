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
