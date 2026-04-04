# ADR-036: Consistent Timezone Handling

## Status

Accepted

## Context

The frontend application displays timestamps in many locations (jobs, summaries, schedules, errors, feeds, etc.). These timestamps come from the backend as ISO 8601 strings without timezone suffixes (e.g., `2024-01-15T10:30:00`), which JavaScript's `new Date()` interprets as local time rather than UTC.

This caused incorrect relative time displays like "in about 4 hours" when the event actually happened "just now", because the backend stores UTC timestamps but they were being parsed as local time.

## Decision

### 1. All Backend Timestamps Are UTC

The backend stores and returns all timestamps as UTC. ISO strings without timezone suffixes should be treated as UTC.

### 2. Use `formatRelativeTime()` for Relative Times

All relative time displays (e.g., "2 hours ago", "just now") must use the centralized `formatRelativeTime()` helper from `TimezoneContext`:

```typescript
import { formatRelativeTime } from "@/contexts/TimezoneContext";

// Good - uses helper that parses as UTC
<span>{formatRelativeTime(job.created_at)}</span>

// Bad - may misinterpret timezone
<span>{formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}</span>
```

### 3. Use `parseAsUTC()` for Date Objects

When you need a Date object (e.g., for `formatDateTime()` or date arithmetic), use the `parseAsUTC()` helper:

```typescript
import { parseAsUTC, useTimezone } from "@/contexts/TimezoneContext";

const { formatDateTime } = useTimezone();
const date = parseAsUTC(summary.created_at);
const formatted = formatDateTime(date); // Respects user's timezone setting
```

### 4. User Timezone for Absolute Times

Absolute time displays (e.g., "Jan 15, 2024 10:30 AM") use the user's selected timezone from `TimezoneContext`:

```typescript
const { formatDateTime, formatDate, formatTime } = useTimezone();

// These respect the user's timezone preference stored in localStorage
formatDateTime(summary.created_at)  // "Jan 15, 2024 10:30 AM"
formatDate(summary.created_at)      // "Jan 15, 2024"
formatTime(summary.created_at)      // "10:30 AM"
```

## Consequences

### Positive

- Consistent relative time display across all components
- No more "in X hours" when it should be "X minutes ago"
- Single source of truth for timezone handling
- User timezone preference is respected for absolute times

### Negative

- Must remember to use `formatRelativeTime()` instead of raw `formatDistanceToNow()`
- Requires importing from `TimezoneContext` in components that display times

## Implementation

### Files Updated

- `contexts/TimezoneContext.tsx` - Added `formatRelativeTime()` and exported `parseAsUTC()`
- `components/summaries/JobsTab.tsx` - Uses `formatRelativeTime`
- `components/summaries/StoredSummaryCard.tsx` - Uses `formatRelativeTime`
- `components/schedules/ScheduleCard.tsx` - Uses `formatRelativeTime`
- `components/schedules/RunHistoryDrawer.tsx` - Uses `formatRelativeTime`
- `components/feeds/FeedCard.tsx` - Uses `formatRelativeTime`
- `components/errors/ErrorCard.tsx` - Uses `formatRelativeTime`
- `components/errors/ErrorDetailDrawer.tsx` - Uses `formatRelativeTime`
- `components/layout/Header.tsx` - Uses `formatRelativeTime`
- `pages/Settings.tsx` - Uses `formatRelativeTime`
- `pages/PromptTemplates.tsx` - Uses `formatRelativeTime`

### API Reference

```typescript
// TimezoneContext exports
export function parseAsUTC(date: string | Date): Date
export function formatRelativeTime(
  date: string | Date,
  options?: { addSuffix?: boolean }
): string

// Hook exports
export function useTimezone(): {
  timezone: string;
  setTimezone: (tz: string) => void;
  formatDate: (date: string | Date, options?: Intl.DateTimeFormatOptions) => string;
  formatTime: (date: string | Date, options?: Intl.DateTimeFormatOptions) => string;
  formatDateTime: (date: string | Date, options?: Intl.DateTimeFormatOptions) => string;
}
```

## References

- date-fns `formatDistanceToNow`: https://date-fns.org/v2.30.0/docs/formatDistanceToNow
- Intl.DateTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
