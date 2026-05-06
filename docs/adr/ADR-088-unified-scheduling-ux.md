# ADR-088: Unified Multi-Platform Scheduling UX

## Status
Proposed

## Context

The scheduling system currently has several UX gaps:

1. **Platform Support Gap**: Backend supports WhatsApp scheduling via `WhatsAppFetcher` (ADR-081), but the frontend `ScheduleForm` only offers Discord and Slack options.

2. **Multi-Day Summary Scope**: ADR-087 introduces weekly continuity, but users still want the convenience of server-wide or category-scoped summaries for multi-day periods. Current scope selection (channel/category/guild) was designed for single-day summaries.

3. **Filtering Fragmentation**: Different views (Summaries, Archive, Wiki) have inconsistent filtering capabilities. Users need unified filtering by:
   - Platform (Discord, Slack, WhatsApp)
   - Scope (channel, category, server-wide)
   - Time granularity (hourly, daily, weekly)
   - Source type (scheduled, manual, realtime)

## Decision

### 1. Add WhatsApp to Platform Selector

**ScheduleForm Changes:**

```tsx
// Current: "discord" | "slack"
// Proposed: "discord" | "slack" | "whatsapp"

<SelectContent>
  <SelectItem value="discord">🎮 Discord</SelectItem>
  <SelectItem value="slack">💬 Slack</SelectItem>
  <SelectItem value="whatsapp">📱 WhatsApp</SelectItem>
</SelectContent>
```

**Conditional Scope Behavior:**

| Platform | Scope Options | Channel Source |
|----------|---------------|----------------|
| Discord | channel, category, guild | Discord channels via bot |
| Slack | channel, category*, guild | Slack channels via OAuth |
| WhatsApp | channel only** | Imported chats from DB |

*Slack categories = Slack channel groups
**WhatsApp has no hierarchy - each chat is independent

**WhatsApp Channel Selector:**

When `platform === "whatsapp"`, replace the Discord channel selector with a WhatsApp chat selector:

```tsx
{formData.platform === "whatsapp" ? (
  <WhatsAppChatSelector
    guildId={guildId}
    selectedChats={formData.channel_ids}
    onChange={(chatIds) => onChange({ ...formData, channel_ids: chatIds })}
  />
) : (
  <ScopeSelector ... />
)}
```

The `WhatsAppChatSelector` will:
- Fetch chats from `/api/guilds/{id}/whatsapp/chats`
- Show chat name, participant count, message count, last activity
- Allow multi-select for summarizing multiple chats together

### 2. Multi-Day Scope UX

For weekly/monthly schedules, users need server-wide or category summaries that span multiple days. The current system already supports this via `scope: "guild"` or `scope: "category"`, but the UX doesn't emphasize it for multi-day schedules.

**Proposed UX Flow:**

```
Schedule Type: [Daily] [Weekly] [Monthly]
                         ↓
              ┌─────────────────────────────────┐
              │ Weekly schedules can summarize: │
              │ ○ Single channel               │
              │ ○ Category (all channels)      │
              │ ● Entire server (recommended)  │
              │                                │
              │ [✓] Enable continuity          │
              │     (carry context week-to-week)│
              └─────────────────────────────────┘
```

**Smart Defaults:**
- Daily: Default to channel scope
- Weekly: Suggest guild/category scope, show continuity toggle
- Monthly: Default to guild scope

### 3. Unified Filtering Architecture

Create a shared `FilterCriteria` component used across all views:

```typescript
interface FilterCriteria {
  // Platform filters
  platforms: ("discord" | "slack" | "whatsapp")[];

  // Scope filters
  scopes: ("channel" | "category" | "guild")[];

  // Granularity filters
  granularities: ("hourly" | "daily" | "weekly" | "monthly")[];

  // Source filters
  sources: ("scheduled" | "manual" | "realtime" | "archive")[];

  // Time range
  dateRange: { start: Date; end: Date } | null;

  // Text search
  search: string;

  // Channel/chat filters
  channelIds: string[];

  // Tag filters (for stored summaries)
  tags: string[];
}
```

**Filter Bar Component:**

```
┌──────────────────────────────────────────────────────────────────┐
│ 🔍 Search...  │ Platform ▼ │ Scope ▼ │ Period ▼ │ More filters ▼ │
└──────────────────────────────────────────────────────────────────┘
```

**View-Specific Behavior:**

| View | Available Filters | Notes |
|------|-------------------|-------|
| Summaries | All | Primary browsing interface |
| Archive | Platform, Scope, Period, Date | Historical multi-day summaries |
| Wiki | Search, Platform, Tags | Knowledge-focused |
| Schedules | Platform, Scope, Active/Inactive | Schedule management |

### 4. Channel/Chat Picker Unification

Create a unified `SourceSelector` component that adapts to platform:

```tsx
interface SourceSelectorProps {
  platform: "discord" | "slack" | "whatsapp";
  guildId: string;
  scope: "channel" | "category" | "guild";
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}

function SourceSelector({ platform, guildId, scope, selectedIds, onChange }: SourceSelectorProps) {
  // Platform-specific data fetching and display
  if (platform === "whatsapp") {
    return <WhatsAppChatPicker guildId={guildId} ... />;
  }

  if (platform === "slack") {
    return <SlackChannelPicker guildId={guildId} scope={scope} ... />;
  }

  // Default: Discord
  return <DiscordChannelPicker guildId={guildId} scope={scope} ... />;
}
```

---

## Implementation Plan

### Phase 1: WhatsApp Scheduling (Priority: High)

1. **Frontend: Add WhatsApp to platform selector**
   - Update `ScheduleForm.tsx` platform type to include "whatsapp"
   - Add WhatsApp option to platform dropdown

2. **Frontend: Create WhatsAppChatSelector component**
   - New component: `src/frontend/src/components/schedules/WhatsAppChatSelector.tsx`
   - Fetch chats via existing `/api/guilds/{id}/whatsapp/chats` endpoint
   - Multi-select with chat metadata (name, messages, participants)

3. **Frontend: Conditional scope behavior**
   - When WhatsApp selected, hide category/guild scope options
   - Show WhatsApp chat selector instead of Discord channels

4. **Backend: Verify WhatsApp scheduling works**
   - Executor already handles `platform: "whatsapp"` via ADR-051
   - Test with existing WhatsApp imports

### Phase 2: Multi-Day Scope UX (Priority: Medium)

1. **Frontend: Smart scope suggestions**
   - When weekly/monthly selected, highlight guild scope
   - Add helper text explaining multi-day scope benefits

2. **Frontend: Scope info in schedule cards**
   - Show "Server-wide" or "Category: General" badges
   - Show channel count for multi-channel scopes

3. **Backend: No changes needed**
   - Scope system already supports guild/category for all schedule types

### Phase 3: Unified Filtering (Priority: Medium)

1. **Shared: Create FilterCriteria type**
   - `src/frontend/src/types/filters.ts` (already exists, extend it)

2. **Shared: Create FilterBar component**
   - `src/frontend/src/components/filters/FilterBar.tsx`
   - Reusable across Summaries, Archive, Wiki views

3. **Frontend: Migrate existing filters**
   - Summaries page: Replace custom filters with FilterBar
   - Archive page: Add platform/scope filters
   - Wiki page: Add source type filters

4. **Backend: Extend filter APIs**
   - Add `platform` filter to summary list endpoints
   - Add `scope` filter to archive endpoints

---

## API Endpoints

### Existing (no changes needed)

```
GET /api/guilds/{id}/whatsapp/chats
  → Returns list of imported WhatsApp chats with metadata

POST /api/guilds/{id}/schedules
  → Already accepts platform: "whatsapp"
```

### New/Extended

```
GET /api/guilds/{id}/summaries?platform=whatsapp&scope=channel
  → Filter summaries by platform and scope

GET /api/guilds/{id}/archive?platform=whatsapp
  → Filter archive by platform
```

---

## UX Mockups

### Schedule Creation - WhatsApp Selected

```
┌─────────────────────────────────────────────────────────────┐
│ Create Schedule                                        [X] │
├─────────────────────────────────────────────────────────────┤
│ Name: [Weekly Team Summary                              ]   │
│                                                             │
│ Platform: [📱 WhatsApp                              ▼]     │
│                                                             │
│ WhatsApp Chats:                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [✓] Team Chat          │ 1,234 msgs │ 12 participants  │ │
│ │ [ ] Project Alpha      │   456 msgs │  5 participants  │ │
│ │ [ ] Client Sync        │   789 msgs │  8 participants  │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Schedule: [Weekly ▼]  Day: [Sunday ▼]  Time: [09:00 ▼]     │
│                                                             │
│ [✓] Enable week-to-week continuity                         │
│     Each summary includes context from the previous week   │
│                                                             │
│                              [Cancel]  [Create Schedule]    │
└─────────────────────────────────────────────────────────────┘
```

### Summary List - Unified Filters

```
┌─────────────────────────────────────────────────────────────┐
│ Summaries                                                   │
├─────────────────────────────────────────────────────────────┤
│ 🔍 Search...  │ Platform ▼ │ Scope ▼ │ Source ▼ │ Date ▼   │
│               │ [✓] Discord│ [✓] All │ [✓] All │ Last 7d  │
│               │ [✓] Slack  │         │         │          │
│               │ [✓] WhatsApp│        │         │          │
├─────────────────────────────────────────────────────────────┤
│ 📱 WhatsApp: Team Chat — May 5, 09:00          Week 3 of 5 │
│    Summary of team discussions...                          │
│                                                             │
│ 🎮 Discord: #general, #engineering — May 5, 09:00  Server  │
│    Cross-channel summary of...                             │
│                                                             │
│ 💬 Slack: #dev-team — May 4, 18:00              Channel    │
│    Discussion about deployment...                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Consequences

### Positive
- **Complete platform coverage**: All three supported platforms schedulable via UI
- **Better multi-day UX**: Clear guidance for weekly/monthly scope selection
- **Consistent filtering**: Same filter patterns across all views
- **Discoverable features**: WhatsApp users can find scheduling easily

### Negative
- **Frontend complexity**: More conditional rendering based on platform
- **Testing burden**: Need to test all platform × scope combinations
- **Migration**: Existing schedules unaffected, but UI needs to handle legacy data

### Risks
- **WhatsApp scope confusion**: Users may expect category/guild scope
  - Mitigation: Clear messaging that WhatsApp chats are independent
- **Filter overload**: Too many filters may overwhelm users
  - Mitigation: Progressive disclosure (More Filters dropdown)

---

## References

- [ADR-051: Multi-Platform Support](./ADR-051-multi-platform-support.md)
- [ADR-081: WhatsApp Import Management](./ADR-081-whatsapp-import-management.md)
- [ADR-087: Wiki Ingestion Granularity](./ADR-087-wiki-ingestion-granularity.md)
- [ADR-011: Scope-Based Scheduling](./ADR-011-scope-based-scheduling.md)
