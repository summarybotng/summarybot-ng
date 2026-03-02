# ADR-027: Retrospective Coverage View

## Status
PROPOSED

## Context

The current Archive/Retrospective page at `/guilds/{id}/archive` is **ineffective** for its primary purpose: helping users understand their summary coverage and fill gaps.

### Current Problems

#### 1. Source-Centric When Users Think Date-Centric

The current view is organized around "Sources" (Discord guilds, WhatsApp groups), but users' mental model is:

> "What days am I missing summaries for?"

Not:

> "What sources do I have and what are their gaps?"

#### 2. Scan-Then-Expand Pattern Creates Friction

Current flow:
1. Click on a source to expand it
2. Wait for scan API call
3. See gaps list
4. Click "Generate" button
5. Fill out complex dialog with dates

This is **5+ steps** to fill a gap. Should be **1-2 clicks**.

#### 3. Gap List is Text-Only

Current gaps display:
```
2026-02-15 - 2026-02-20  [missing]  5 days
2026-02-25 - 2026-02-25  [failed]   1 day
```

Problems:
- No visual representation of coverage over time
- No context about message activity (were there messages to summarize?)
- No indication of gap size relative to total history
- Can't quickly select which gaps to fill

#### 4. No Visual Calendar

The Summaries page has a calendar view showing which days have summaries. The Archive page should have a similar view showing:
- Which days have summaries (complete)
- Which days are missing
- Which days had no activity (don't need summaries)
- Which days failed

#### 5. Generate Dialog is Overwhelming

Current dialog has 10+ options:
- Source type
- Scope (guild/channel/category)
- Start date
- End date
- Summary type
- Perspective
- Skip existing
- Regenerate failed
- Force regenerate
- Max cost

Most users want: **"Fill the gaps with sensible defaults"**

#### 6. No Context About Message Activity

The gap list doesn't show whether there were actually messages on those days. A "gap" on a day with no messages shouldn't be treated the same as a gap on a busy day.

#### 7. WhatsApp Workflow is Unclear

For WhatsApp sources:
1. Must import first
2. Then can generate
3. But the UI doesn't guide this workflow

### User Stories Not Served

1. **"Show me my summary coverage at a glance"** - No visual overview
2. **"Fill all my gaps with one click"** - Too many steps
3. **"What will this cost?"** - Cost shown only after clicking through dialogs
4. **"Which days had the most activity?"** - No activity heatmap
5. **"Why is this day marked as failed?"** - No error details inline

## Decision

Reimagine the Archive page as a **Coverage Dashboard** focused on visual representation and quick actions.

## Design

### Primary View: Coverage Calendar

Replace the source-centric view with a **calendar heatmap** showing coverage status:

```
┌─────────────────────────────────────────────────────────────────┐
│  Coverage Dashboard                              [Quick Fill ▼] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ◀ February 2026                                          ▶     │
│                                                                 │
│  Sun   Mon   Tue   Wed   Thu   Fri   Sat                       │
│  ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐                    │
│  │   │ │   │ │   │ │   │ │   │ │   │ │ 1 │                     │
│  │   │ │   │ │   │ │   │ │   │ │   │ │ ● │  ← Green: Complete  │
│  └───┘ └───┘ └───┘ └───┘ └───┘ └───┘ └───┘                    │
│  ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐                    │
│  │ 2 │ │ 3 │ │ 4 │ │ 5 │ │ 6 │ │ 7 │ │ 8 │                     │
│  │ ● │ │ ○ │ │ ● │ │ ◐ │ │ ✕ │ │ - │ │ - │  ← Mixed states    │
│  └───┘ └───┘ └───┘ └───┘ └───┘ └───┘ └───┘                    │
│                                                                 │
│  Legend:                                                        │
│  ● Complete  ◐ Outdated  ○ Missing  ✕ Failed  - No activity   │
│                                                                 │
│  ─────────────────────────────────────────                     │
│  Selected: Feb 3, Feb 6 (2 days)              [Generate $0.02] │
└─────────────────────────────────────────────────────────────────┘
```

### Coverage States

| State | Color | Icon | Meaning |
|-------|-------|------|---------|
| Complete | Green | ● | Summary exists and is current |
| Outdated | Yellow | ◐ | Summary exists but prompt version is old |
| Missing | White/Blue outline | ○ | No summary, but messages exist |
| Failed | Red | ✕ | Generation attempted but failed |
| No Activity | Gray | - | No messages on this day |
| Selected | Blue highlight | □ | User selected for generation |

### Interaction Model

#### Click to Select
- Click a day to select it for generation
- Shift+click for range selection
- Click "Missing" legend item to select all missing days

#### Hover for Details
```
┌─────────────────────────────────┐
│ February 6, 2026                │
│ Status: Failed                  │
│ Error: Token limit exceeded     │
│ Messages: 847                   │
│ Last attempt: 2 hours ago       │
│ ─────────────────────────────── │
│ [Retry]  [View Details]         │
└─────────────────────────────────┘
```

#### Quick Actions

**"Quick Fill" Dropdown:**
- Fill all missing (X days) - $Y.YY
- Fill this week's gaps - $Y.YY
- Fill this month's gaps - $Y.YY
- Retry all failed - $Y.YY

### Simplified Generation Flow

#### One-Click Generation

When days are selected, show inline action bar:
```
┌─────────────────────────────────────────────────────────────────┐
│ 5 days selected (Feb 3, 6, 10-12)         ~$0.15 estimated      │
│                                                                 │
│ [Generate with Defaults]    [Customize...]    [Clear Selection] │
└─────────────────────────────────────────────────────────────────┘
```

**"Generate with Defaults"** uses:
- Summary type: detailed
- Perspective: general
- Model: claude-3.5-sonnet
- Skip existing: true
- Regenerate failed: true

**"Customize..."** opens a simplified dialog with just the options that matter.

### Activity Heatmap (Optional Enhancement)

Overlay message activity on the calendar:
```
┌───┐
│ 3 │  ← Day number
│▓▓▓│  ← Activity bar (height = message count)
│ ○ │  ← Coverage status
└───┘
```

This helps users prioritize: a missing day with 500 messages is more important than one with 5.

### Multi-Source View

For guilds with WhatsApp linked:

```
┌─────────────────────────────────────────────────────────────────┐
│  Platform: [All ▼] [Discord ▼] [WhatsApp: ai-code ▼]           │
├─────────────────────────────────────────────────────────────────┤
│  Combined coverage showing all sources...                       │
│  Or filtered to specific source...                              │
└─────────────────────────────────────────────────────────────────┘
```

### Stats Summary

Above the calendar, show at-a-glance stats:
```
┌─────────────────────────────────────────────────────────────────┐
│  Coverage: 87%     │  Complete: 156  │  Missing: 12  │  Failed: 3 │
│  ████████████░░    │                 │               │            │
└─────────────────────────────────────────────────────────────────┘
```

### Import Flow Integration

For sources requiring import (WhatsApp):
```
┌─────────────────────────────────────────────────────────────────┐
│  WhatsApp: ai-code                                              │
│  ─────────────────────────────────────────────────────────────  │
│  Last import: Feb 15, 2026 (covers Jan 1 - Feb 15)             │
│  To generate summaries for later dates, import newer data.      │
│                                                                 │
│  [Import More Data]                                             │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation

### Phase 1: Coverage Calendar (MVP)

1. **New API endpoint**: `GET /api/v1/guilds/{id}/coverage`
   - Returns per-day coverage status for date range
   - Includes message counts, summary status, error info

2. **Coverage Calendar component**
   - Month view with coverage states
   - Click to select days
   - Hover for details

3. **Inline generation bar**
   - Shows selected days and estimated cost
   - One-click generate with defaults

### Phase 2: Enhanced Interaction

4. **Activity heatmap overlay**
   - Message count visualization
   - Helps prioritize gaps

5. **Quick Fill actions**
   - Pre-computed options with costs
   - One-click fill patterns

### Phase 3: Multi-Source Support

6. **Source filter**
   - View coverage by platform
   - Combined or per-source view

7. **Import integration**
   - Inline import prompts for WhatsApp
   - Clear workflow guidance

## API Design

### Coverage Endpoint

```
GET /api/v1/guilds/{guild_id}/coverage?year=2026&month=2&source=all

Response:
{
  "period": { "year": 2026, "month": 2 },
  "stats": {
    "total_days": 28,
    "complete": 20,
    "missing": 5,
    "failed": 2,
    "no_activity": 1,
    "coverage_percent": 87.5
  },
  "days": [
    {
      "date": "2026-02-01",
      "status": "complete",
      "summary_id": "sum_abc123",
      "message_count": 234,
      "sources": ["discord:123"]
    },
    {
      "date": "2026-02-02",
      "status": "missing",
      "message_count": 156,
      "sources": ["discord:123", "whatsapp:ai-code"]
    },
    {
      "date": "2026-02-03",
      "status": "failed",
      "error": "Token limit exceeded",
      "last_attempt": "2026-02-03T15:30:00Z",
      "message_count": 847,
      "sources": ["discord:123"]
    },
    {
      "date": "2026-02-04",
      "status": "no_activity",
      "message_count": 0,
      "sources": []
    }
  ],
  "quick_fills": [
    {
      "label": "Fill all missing",
      "days": 5,
      "estimated_cost_usd": 0.15
    },
    {
      "label": "Retry all failed",
      "days": 2,
      "estimated_cost_usd": 0.08
    }
  ]
}
```

### Generate from Selection

```
POST /api/v1/guilds/{guild_id}/generate-selection
{
  "dates": ["2026-02-02", "2026-02-03", "2026-02-10"],
  "options": {
    "summary_type": "detailed",
    "perspective": "general",
    "retry_failed": true
  }
}
```

## Migration

The existing Archive page remains functional during migration:

1. **Phase 1**: Add Coverage tab alongside existing Sources tab
2. **Phase 2**: Make Coverage the default view
3. **Phase 3**: Deprecate Sources tab (keep as "Advanced" option)

## Alternatives Considered

### A: Keep Source-Centric View, Improve UX

Improve the existing source → scan → gaps flow with:
- Auto-scan on page load
- Inline gap visualization
- Simplified generate dialog

**Rejected**: Doesn't address the fundamental mental model mismatch.

### B: Gantt-Style Timeline View

Show coverage as horizontal bars across time:
```
Discord:  ████░░██████░███
WhatsApp: ░░░░████████████
```

**Rejected**: Less intuitive than calendar, harder to select specific days.

### C: List View with Filters

Show all days as a filterable list:
```
[ ] Feb 1 - Complete - 234 messages
[ ] Feb 2 - Missing - 156 messages
[x] Feb 3 - Failed - 847 messages
```

**Considered for mobile**: May be useful as an alternative view for small screens.

## Success Metrics

1. **Time to fill gaps**: < 10 seconds from page load to generation started
2. **Click count**: Max 3 clicks to fill all gaps
3. **User comprehension**: Can answer "what's my coverage?" in < 5 seconds
4. **Cost visibility**: Users see cost before generating

## Open Questions

1. **Year view?** Should we support a full-year heatmap (like GitHub contributions)?
2. **Keyboard navigation?** Arrow keys to navigate, Enter to select?
3. **Bulk selection patterns?** "Select all Mondays" for weekly summaries?
4. **Real-time updates?** WebSocket for generation progress on calendar?

## Related ADRs

- ADR-017: Summary Calendar View (existing calendar component to reuse)
- ADR-026: Multi-Platform Source Architecture (source filtering)
- ADR-006: Retrospective Summary Archive (original archive design)

## References

- GitHub contribution graph (inspiration for heatmap)
- Google Calendar (interaction patterns)
- Stripe Dashboard (quick action patterns)
