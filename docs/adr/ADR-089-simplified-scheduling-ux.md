# ADR-089: Unified Summary Creation UX

## Status
Accepted (Phases 1-4 implemented, Phases 5-6 pending)

## Context

### Problem 1: Three Separate Flows

We have three separate UIs for creating summaries that share 80% of the same fields:

| Flow | Location | Purpose |
|------|----------|---------|
| **Generate Now** | Summaries page dialog | Immediate summary of recent messages |
| **Schedule** | Schedules page form | Recurring future summaries |
| **Retrospective** | Archive page | Historical period summaries |

Each duplicates:
- Platform selection (Discord/Slack/WhatsApp)
- Channel/scope selection
- Summary options (length, perspective)

Users must learn three different UIs for essentially the same task.

### Problem 2: Complex Forms

The current schedule creation form has grown organically and now presents too many options at once:

- Platform selection (Discord, Slack, WhatsApp)
- Scope selection (channel, category, guild) - varies by platform
- Schedule timing (type, time, days, timezone)
- Destinations (dashboard, Discord channel, webhook, email, DM)
- Summary options (length, perspective, min messages)
- Prompt templates
- Continuity toggle (weekly only)

**Problems:**

1. **Cognitive overload**: 15+ form fields visible at once
2. **Platform confusion**: Scope/channel selectors change based on platform
3. **Hidden dependencies**: Continuity only matters for weekly, categories don't exist for WhatsApp
4. **No guidance**: User must understand all options upfront
5. **Mobile unfriendly**: Long scrolling form

## Decision

### Unified "Create Summary" Flow

Merge all three flows into **one wizard** with a branching "When" step:

```
┌─────────────────────────────────────────────────────────────┐
│                    + Create Summary                         │
│                                                             │
│  One entry point for all summary creation:                  │
│  • Generate now (last N hours)                              │
│  • Schedule recurring (daily/weekly/monthly)                │
│  • Retrospective (specific past dates)                      │
└─────────────────────────────────────────────────────────────┘
```

**Benefits:**
- Single mental model: "I want a summary" → one button
- Shared components reduce code duplication
- Consistent experience across all summary types
- Easier to discover features (users see all options)

### 3-Step Wizard

Replace the monolithic form with a **3-step wizard** using progressive disclosure and smart defaults.

### Step 1: What to Summarize

```
┌─────────────────────────────────────────────────────────────┐
│ What would you like to summarize?                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │     🎮      │  │     💬      │  │     📱      │         │
│  │   Discord   │  │    Slack    │  │  WhatsApp   │         │
│  │  channels   │  │  channels   │  │   chats     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Select channels:                                           │
│  ○ All server channels                                      │
│  ○ A category    [Engineering ▼]                           │
│  ● Specific channels                                        │
│     [✓] #general                                           │
│     [✓] #engineering                                       │
│     [ ] #random                                            │
│                                                             │
│                                        [Cancel] [Next →]    │
└─────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Platform cards are visually prominent, easy to tap on mobile
- Channel selection adapts to platform (WhatsApp shows chats, no categories)
- "All server" is the simplest option, shown first
- Defaults to most common choice per platform

### Step 2: When (Branching Point)

This is where the three flows converge into one UI:

```
┌─────────────────────────────────────────────────────────────┐
│ When do you want this summary?                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │       ⚡        │  │       🔄        │  │      📅     │ │
│  │      Now        │  │    Recurring    │  │    Past     │ │
│  │   Last 24hrs    │  │  Schedule it    │  │   Dates     │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Option A: Now (Generate Immediately)

```
│  ⚡ Generate Now                                            │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Time range:                                                │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   │
│  │  4 hr  │ │  8 hr  │ │ 24 hr  │ │ 48 hr  │ │ Custom │   │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘   │
│                                                             │
│                                   [← Back] [Generate →]     │
```

#### Option B: Recurring (Schedule)

```
│  🔄 Schedule Recurring                                      │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Frequency:                                                 │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐               │
│  │ Daily  │ │ Weekly │ │Monthly │ │ Custom │               │
│  └────────┘ └────────┘ └────────┘ └────────┘               │
│                                                             │
│  Time: [09:00 ▼]     Timezone: [America/Toronto ▼]         │
│                                                             │
│  [If weekly: Day picker]   [If monthly: Date picker]       │
│                                                             │
│  Name: [Weekly #general summary            ]                │
│                                                             │
│                                   [← Back] [Next →]         │
```

#### Option C: Past Dates (Retrospective)

```
│  📅 Past Period                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Date range:                                                │
│  From: [May 1, 2024    📅]  To: [May 7, 2024    📅]        │
│                                                             │
│  Or quick select:                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │Last week │ │Last month│ │Last 90d  │ │  Custom  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                             │
│  Granularity: [○ One summary] [● Daily summaries]          │
│                                                             │
│                                   [← Back] [Generate →]     │
```

**Behavior:**
- Three clear paths from one decision point
- "Now" and "Past" go directly to generation (skip Step 3 delivery for non-scheduled)
- "Recurring" continues to Step 3 for delivery configuration
- Visual cards make the choice obvious

### Step 3: Delivery & Options (Scheduled Only)

For "Now" and "Past" flows, skip to generation with defaults.
For "Recurring" schedules, configure delivery:

```
┌─────────────────────────────────────────────────────────────┐
│ Delivery & Options                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Where should we deliver each summary?                      │
│                                                             │
│  [✓] Dashboard (always on)                                  │
│                                                             │
│  [ ] Post to Discord channel  [#summaries ▼]               │
│  [ ] Send webhook             [https://...    ]            │
│  [ ] Email                    [team@...       ]            │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  [▼ Advanced options]                                       │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Summary length: [Detailed ▼]                            ││
│  │ Perspective:    [General ▼] or [Custom template ▼]     ││
│  │ Min messages:   [5]                                     ││
│  │ [✓] Week-to-week continuity (carries context forward)  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│                              [← Back] [Create Schedule]     │
└─────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Dashboard always enabled (core value prop)
- Other destinations as opt-in checkboxes
- Advanced options collapsed by default
- Continuity checkbox only shown for weekly schedules
- Prompt templates in advanced section

### Flow Summary

```
                    ┌──────────────┐
                    │  + Create    │
                    │   Summary    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Step 1:     │
                    │  What        │
                    │  (platform   │
                    │  + channels) │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Step 2:     │
                    │  When        │
                    └──────┬───────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼─────┐   ┌──────▼──────┐   ┌─────▼─────┐
    │    Now    │   │  Recurring  │   │   Past    │
    │  (4-48hr) │   │  (schedule) │   │  (dates)  │
    └─────┬─────┘   └──────┬──────┘   └─────┬─────┘
          │                │                │
          │         ┌──────▼──────┐         │
          │         │  Step 3:    │         │
          │         │  Delivery   │         │
          │         └──────┬──────┘         │
          │                │                │
    ┌─────▼─────┐   ┌──────▼──────┐   ┌─────▼─────┐
    │ Generate  │   │   Create    │   │ Generate  │
    │   Now     │   │  Schedule   │   │   Past    │
    └───────────┘   └─────────────┘   └───────────┘
```

---

## Smart Defaults

| Context | Default |
|---------|---------|
| Platform | Discord (most common) |
| Scope | Channel (simplest) |
| Schedule | Daily at 9am user's timezone |
| Destinations | Dashboard only |
| Length | Detailed |
| Min messages | 5 |
| Continuity | Off |

**Auto-detection:**
- Timezone from browser
- If guild has WhatsApp imports, show WhatsApp prominently
- If weekly + server-wide, suggest enabling continuity

---

## Component Architecture

```
src/frontend/src/components/summary-wizard/
├── SummaryWizard.tsx            # Main wizard container (unified entry point)
├── steps/
│   ├── WhatStep.tsx             # Step 1: Platform + channels
│   ├── WhenStep.tsx             # Step 2: Now/Recurring/Past (branching)
│   ├── WhenNowOptions.tsx       # Time range for immediate generation
│   ├── WhenScheduleOptions.tsx  # Frequency, time, day for recurring
│   ├── WhenPastOptions.tsx      # Date range for retrospective
│   ├── DeliveryStep.tsx         # Step 3: Destinations + options (scheduled only)
│   └── WizardProgress.tsx       # Step indicator with branch awareness
├── shared/
│   ├── PlatformCard.tsx         # Platform selection cards
│   ├── ChannelSelector.tsx      # Unified channel/chat picker
│   ├── WhatsAppChatSelector.tsx # Existing, moved here
│   └── SummaryOptions.tsx       # Length, perspective, templates
└── index.ts                     # Exports SummaryWizard as default
```

**Entry Points:**

Replace current scattered entry points with one:

| Current | Proposed |
|---------|----------|
| Summaries page "Generate" button | Opens `SummaryWizard` |
| Schedules page "Create Schedule" button | Opens `SummaryWizard` |
| Archive page "Generate Retrospective" | Opens `SummaryWizard` (pre-selects "Past") |

**Edit Mode:**
- Editing existing schedule opens wizard pre-populated
- Or: Keep full form as "Advanced Edit" for power users

---

## Migration Path

### Phase 1: Build Unified Wizard
- Create `SummaryWizard` component with all three paths
- Keep existing UIs working in parallel
- Feature flag to toggle new wizard

### Phase 2: Replace Entry Points
- Summaries "Generate" → Opens wizard (Now pre-selected)
- Schedules "Create" → Opens wizard (Recurring pre-selected)
- Archive "Retrospective" → Opens wizard (Past pre-selected)
- Remove old dialogs/forms

### Phase 3: Edit Mode
- Edit schedule → Opens wizard pre-populated
- Keep "Advanced Edit" link for full form
- Remove standalone pages (Schedules becomes list-only)

### Phase 4: Polish
- Animations between steps
- Keyboard navigation (Enter/Escape/Tab)
- Mobile optimization
- Persist wizard state across page reloads

---

## Mobile Considerations

```
┌─────────────────────┐
│ What to summarize   │
│ ═══════════════════ │
│                     │
│  ┌───────────────┐  │
│  │      🎮       │  │
│  │    Discord    │  │
│  └───────────────┘  │
│                     │
│  ┌───────────────┐  │
│  │      💬       │  │
│  │     Slack     │  │
│  └───────────────┘  │
│                     │
│  ┌───────────────┐  │
│  │      📱       │  │
│  │   WhatsApp    │  │
│  └───────────────┘  │
│                     │
│ ─────────────────── │
│ Select channels...  │
│                     │
│        [Next →]     │
└─────────────────────┘
```

- Full-width cards on mobile
- Steps as full screens
- Bottom-anchored navigation
- Collapsible channel list

---

## Accessibility

- Step indicator with aria-current
- Focus management between steps
- Keyboard: Enter to proceed, Escape to go back
- Screen reader: "Step 1 of 3: What to summarize"

---

## Consequences

### Positive
- **Single mental model**: "Create Summary" does everything
- **Less code duplication**: One wizard replaces three dialogs
- **Simpler onboarding**: New users guided through process
- **Discoverable features**: Users see Now/Recurring/Past options together
- **Fewer errors**: Can't misconfigure incompatible options
- **Mobile-friendly**: Each step fits on screen
- **Faster for common cases**: Smart defaults reduce clicks

### Negative
- **More clicks for power users**: 3 steps vs 1 form
  - Mitigation: "Quick create" option or keyboard shortcuts
- **Significant refactor**: Consolidating three flows into one
  - Mitigation: Feature flag, parallel operation during migration
- **Testing burden**: More UI states to test
  - Mitigation: Shared components reduce total test surface

### Risks
- **Over-simplification**: Some users want all options visible
  - Mitigation: Keep "Advanced Edit" mode with full form
- **Wizard fatigue**: Too many steps feels slow
  - Mitigation: Only 2-3 steps depending on path, each focused
- **Feature discovery regression**: Users who knew where Archive was might be confused
  - Mitigation: "Past Dates" option clearly visible in Step 2

---

## Page Structure Changes

### Before (Current)

```
/guilds/:id/
├── summaries      # List + "Generate Now" dialog
├── schedules      # List + "Create Schedule" dialog
├── archive        # Sources + "Generate Retrospective" dialog
└── ...
```

Three separate pages with overlapping functionality.

### After (Proposed)

```
/guilds/:id/
├── summaries      # All summaries (scheduled, manual, archive)
│   └── + Create   # Opens unified SummaryWizard
├── schedules      # Just the schedule list (no create dialog)
│   └── Edit       # Opens SummaryWizard pre-populated
└── ...
```

Archive page becomes a "Sources" page (import management), not summary generation.

### Navigation

```
┌─────────────────────────────────────────────────────────────┐
│  Summaries  │  Schedules  │  Sources  │  Wiki  │  ...      │
└─────────────────────────────────────────────────────────────┘
       │              │            │
       │              │            └── Import WhatsApp, Slack OAuth, etc.
       │              │
       │              └── List of recurring schedules (view/edit/delete)
       │
       └── All summaries + [+ Create Summary] button
                                    │
                                    └── Opens SummaryWizard
```

---

## Alternatives Considered

### 1. Keep Separate Flows, Just Simplify Each
Improve each dialog individually without merging.
- Pro: Less refactoring, incremental improvement
- Con: Still three UIs to learn, code duplication remains

### 2. Accordion Form
Collapse sections instead of wizard steps.
- Pro: Single page, familiar pattern
- Con: Still overwhelming, unclear order, doesn't solve unification

### 3. Conversational UI
Chat-like interface to configure summary.
- Pro: Very guided, feels modern
- Con: Slower, harder to edit, unfamiliar

### 4. Template-First
Start with templates: "Weekly team sync", "Daily standup recap"
- Pro: One-click for common cases
- Con: Still need custom flow, maintenance burden, limits flexibility

**Decision**: Unified wizard balances simplicity, guidance, and flexibility while eliminating redundancy.

---

## Feature Parity Gaps

The SummaryWizard must reach feature parity with the existing ScheduleForm. The following features are missing or incomplete:

### Critical Gaps

#### 1. Time Range Hours (Lookback Period)

The backend supports `time_range_hours` (how far back to fetch messages when a schedule runs), but neither UI exposes this:

```tsx
// WhenStep RecurringOptions should include:
<div>
  <Label>Look back period</Label>
  <Select value={state.lookbackHours} onValueChange={...}>
    <SelectItem value="8">8 hours</SelectItem>
    <SelectItem value="24">24 hours (default)</SelectItem>
    <SelectItem value="48">48 hours</SelectItem>
    <SelectItem value="168">7 days</SelectItem>
    <SelectItem value="custom">Custom</SelectItem>
  </Select>
  <p className="text-xs text-muted-foreground">
    How many hours of messages to include in each summary
  </p>
</div>
```

**Common patterns:**
- Daily at 9am → 24 hours (covers previous day)
- Twice daily (9am, 5pm) → 8 hours each
- Weekly → 168 hours (7 days)

#### 2. Discord DM Delivery (ADR-047)

ScheduleForm supports sending summaries via Discord DM to a specific user. Missing from wizard:

```tsx
// DeliveryStep should include:
<div className="flex items-start gap-3 p-3 rounded-md border">
  <Checkbox checked={state.destinations.discordDm} ... />
  <div className="flex-1 space-y-2">
    <div className="flex items-center gap-2">
      <MessageCircle className="h-4 w-4" />
      <span className="font-medium">Discord DM</span>
    </div>
    {state.destinations.discordDm && (
      <Input
        placeholder="Discord User ID (e.g., 123456789012345678)"
        value={state.destinations.discordDmUserId}
        onChange={...}
      />
    )}
  </div>
</div>
```

#### 3. Interval-Based Schedules

ScheduleForm supports high-frequency schedules not in wizard:

| Schedule Type | In ScheduleForm | In Wizard |
|---------------|-----------------|-----------|
| fifteen-minutes | ✅ | ❌ |
| hourly | ✅ | ❌ |
| every-4-hours | ✅ | ❌ |
| once | ✅ | ❌ |
| daily | ✅ | ✅ |
| weekly | ✅ | ✅ |
| monthly | ✅ | ✅ |

Add to WhenStep RecurringOptions:

```tsx
const frequencies = [
  { value: "fifteen-minutes", label: "Every 15 min" },
  { value: "hourly", label: "Hourly" },
  { value: "every-4-hours", label: "Every 4 hours" },
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
  { value: "once", label: "Once" },
];
```

Note: For interval schedules (fifteen-minutes, hourly, every-4-hours), hide the time picker since they run on intervals, not at specific times.

#### 4. Push Single Summary

Users need ability to push an existing stored summary to destinations on-demand. This is NOT part of schedule creation but should be accessible from summary detail view:

```
┌─────────────────────────────────────────────────────────────┐
│ Summary: Weekly #general - May 5, 2024                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ [Summary content...]                                        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Push to:                                                    │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            │
│ │ Discord │ │  Slack  │ │  Email  │ │ Webhook │            │
│ │    #    │ │    #    │ │   ✉️    │ │   🔗    │            │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘            │
│                                                             │
│ [Select destination and push]                               │
└─────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Add "Push to..." dropdown/dialog to `StoredSummaryDetailSheet`
- Options: Discord channel, Slack channel, Email addresses, Webhook URL
- Calls existing push endpoints (`POST /summaries/{id}/push`)

### Minor Gaps

#### 5. Privacy Warnings (ADR-046)

ScheduleForm shows warnings when private Discord channels are selected. Add to WhatStep:

```tsx
{privacyWarnings.length > 0 && (
  <Alert variant="warning">
    <AlertTriangle className="h-4 w-4" />
    <AlertTitle>Privacy Notice</AlertTitle>
    <AlertDescription>
      This includes {privacyWarnings.length} private channel(s).
      Summaries will be visible to all guild members.
    </AlertDescription>
  </Alert>
)}
```

#### 6. Dynamic Perspectives

Perspectives should be fetched dynamically, not hardcoded. The wizard currently has:
- general, technical, executive, action-focused

ScheduleForm has:
- general, developer, marketing, executive, support

**Solution:** Fetch perspectives from API and merge with custom prompt templates:

```tsx
const { data: perspectives } = usePerspectives(guildId);
const { data: promptTemplates } = usePromptTemplates(guildId);

// Render dynamically
<SelectContent>
  {perspectives?.map((p) => (
    <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
  ))}
  {promptTemplates?.length > 0 && (
    <>
      <div className="px-2 py-1.5 text-xs text-muted-foreground">
        Custom Templates
      </div>
      {promptTemplates.map((t) => (
        <SelectItem key={t.id} value={`template:${t.id}`}>
          {t.name}
        </SelectItem>
      ))}
    </>
  )}
</SelectContent>
```

### Types Update

Add to `types.ts`:

```typescript
export interface WizardState {
  // ... existing fields ...

  // Add to When: Recurring options
  lookbackHours: number;  // time_range_hours

  // Add to Delivery destinations
  destinations: {
    // ... existing ...
    discordDm: boolean;
    discordDmUserId: string;
  };
}

export type ScheduleFrequency =
  | "fifteen-minutes"
  | "hourly"
  | "every-4-hours"
  | "daily"
  | "weekly"
  | "monthly"
  | "once";
```

---

## Implementation Estimate

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 | WhatStep, WhenStep, DeliveryStep, WizardProgress, integration | ✅ Done |
| Phase 2 | Feature parity: lookback hours, interval schedules, Discord DM | ✅ Done |
| Phase 3 | Push single summary to destinations | ✅ Done (existing) |
| Phase 4 | Dynamic perspectives, privacy warnings | ✅ Done |
| Phase 5 | Edit mode migration, animations | ❌ Pending |
| Phase 6 | Mobile polish, accessibility audit | ❌ Pending |

### Phase 2 Details (Feature Parity)

1. **WizardState types** - Add `lookbackHours`, `discordDm`, `discordDmUserId`, expand `ScheduleFrequency`
2. **WhenStep** - Add lookback hours selector, interval schedule options
3. **DeliveryStep** - Add Discord DM destination

### Phase 3 Details (Push Summary)

1. **StoredSummaryDetailSheet** - Add "Push to..." action
2. **PushSummaryDialog** - Select destination type and target
3. **API integration** - Call `POST /summaries/{id}/push`

---

## References

- [ADR-088: Unified Scheduling UX](./ADR-088-unified-scheduling-ux.md) - Previous iteration
- [ADR-011: Scope-Based Scheduling](./ADR-011-scope-based-scheduling.md) - Scope model
- [ADR-051: Multi-Platform Support](./ADR-051-multi-platform-support.md) - Platform abstraction
- [ADR-087: Weekly Continuity](./ADR-087-wiki-ingestion-granularity.md) - Continuity feature
