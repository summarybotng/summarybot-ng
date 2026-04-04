# ADR-035: Summary Date Selection and Generation Filters

**Status:** Accepted
**Date:** 2026-04-04
**Depends on:** ADR-012 (Summaries UI Consolidation), ADR-034 (Guild Prompt Templates)

---

## 1. Context

Users generating manual summaries and browsing stored summaries have expressed two needs:

### 1.1 Manual Summary Date Selection

Currently, the "Generate Summary" dialog only offers relative time ranges:
- Last 1 hour, 6 hours, 12 hours, 24 hours, 48 hours, 7 days

Users want to:
- Select specific start and end dates (e.g., "March 15-20")
- Generate summaries for past periods without calculating relative offsets
- Match the date picker UX already available in the summary filters

### 1.2 Summary Filtering by Generation Settings

The stored summaries list has extensive filters (date, source, platform, content counts, grounding) but lacks:
- **Summary length** — Filter by brief/detailed/comprehensive
- **Perspective** — Filter by the perspective used (general, developer, marketing, etc.)

These are valuable for users who:
- Want to find all "executive" summaries for stakeholder reports
- Need to locate "detailed" summaries for technical review
- Compare how different perspectives summarized the same period

---

## 2. Decision

### 2.1 Enhanced Generate Summary Dialog

Replace the relative time range selector with a comprehensive date/time picker:

```
┌─────────────────────────────────────────────┐
│ Generate Summary                            │
├─────────────────────────────────────────────┤
│ Time Range                                  │
│ ┌───────────────────────────────────────┐   │
│ │ ○ Quick Presets                       │   │
│ │   [Last 24h] [Last 7d] [Today]       │   │
│ │                                       │   │
│ │ ○ Custom Date Range                   │   │
│ │   From: [Mar 15, 2026  ▼] [09:00 ▼]  │   │
│ │   To:   [Mar 20, 2026  ▼] [17:00 ▼]  │   │
│ └───────────────────────────────────────┘   │
│                                             │
│ [Other existing options...]                 │
└─────────────────────────────────────────────┘
```

**Key Features:**
- **Quick presets** remain for convenience (1h, 6h, 12h, 24h, 48h, 7d)
- **Custom date range** with calendar pickers for start/end
- **Optional time selection** for precise control (defaults to 00:00-23:59)
- Reuse existing `DateRangeSelector` component from `SummaryFilters.tsx`

### 2.2 Summary Generation Metadata Storage

Store generation settings in stored summaries for filtering:

```sql
-- Migration 035: Add generation settings columns
ALTER TABLE stored_summaries ADD COLUMN summary_length TEXT;  -- 'brief' | 'detailed' | 'comprehensive'
ALTER TABLE stored_summaries ADD COLUMN perspective TEXT;     -- 'general' | 'developer' | etc.
ALTER TABLE stored_summaries ADD COLUMN prompt_template_id TEXT;  -- ADR-034 template ID if used

CREATE INDEX idx_stored_summaries_generation
ON stored_summaries(guild_id, summary_length, perspective);
```

### 2.3 Enhanced Summary Filters

Add generation settings to the `SummaryFilters` component:

```typescript
// Extended FilterState
interface FilterState {
  // ...existing filters...

  // Generation settings filters (new)
  summaryLength?: 'brief' | 'detailed' | 'comprehensive';
  perspective?: string;  // Includes built-in + custom template names
}
```

**UI Addition to main filter row:**

```
Source: [All Sources ▼]  Platform: [All ▼]  Length: [All ▼]  Perspective: [All ▼]  [Date Range]
```

### 2.4 API Changes

#### Generate Request (already has prompt_template_id from ADR-034)

```typescript
interface GenerateSummaryRequest {
  scope: 'channel' | 'category' | 'guild';
  channel_ids?: string[];
  category_id?: string;
  time_range: {
    type: 'relative' | 'absolute';  // NEW: Support absolute dates
    // Relative (existing)
    value?: number;  // hours or days
    // Absolute (new)
    start?: string;  // ISO datetime
    end?: string;    // ISO datetime
  };
  options?: SummaryOptionsResponse;
  prompt_template_id?: string;
}
```

#### Stored Summaries List Endpoint

```
GET /guilds/{guild_id}/stored-summaries
Query params:
  ...existing params...
  summary_length: Filter by length (brief|detailed|comprehensive)
  perspective: Filter by perspective name
```

### 2.5 Response Updates

Include generation settings in summary responses:

```typescript
interface StoredSummaryResponse {
  // ...existing fields...

  // Generation settings (new)
  summary_length?: string;
  perspective?: string;
  prompt_template_id?: string;
  prompt_template_name?: string;  // Resolved name for display
}
```

---

## 3. Implementation Plan

### Phase 1: Backend Foundation
1. Create migration `035_generation_settings.sql`
2. Update `StoredSummary` model with new fields
3. Update repository to store/query generation settings
4. Update API to accept absolute time ranges

### Phase 2: Generate Dialog Enhancement
1. Add `DateRangeSelector` to generate dialog
2. Add radio toggle between "Quick Presets" and "Custom Range"
3. Update request building to handle absolute dates
4. Store generation settings when saving summary

### Phase 3: Filter Enhancement
1. Add `summaryLength` and `perspective` to `FilterState`
2. Add filter dropdowns to `SummaryFilters` UI
3. Update API calls to include new filter params
4. Add filter badges for active generation filters

---

## 4. UI Mockups

### 4.1 Generate Dialog - Time Range Section

```
┌─ Time Range ──────────────────────────────────────┐
│                                                    │
│  Quick:  [1h] [6h] [12h] [24h] [48h] [7d]        │
│                                                    │
│  ─── or ───                                        │
│                                                    │
│  Custom Range:                                     │
│  ┌────────────────┐    ┌────────────────┐         │
│  │ From           │    │ To             │         │
│  │ [📅 Apr 1     ]│    │ [📅 Apr 3     ]│         │
│  │ [🕐 00:00    ]│    │ [🕐 23:59    ]│         │
│  └────────────────┘    └────────────────┘         │
│                                                    │
└────────────────────────────────────────────────────┘
```

### 4.2 Summary Filters - Extended Row

```
Source: [All Sources ▼]  Platform: [All ▼]  Length: [All Lengths ▼]  Perspective: [All ▼]  [📅 Date Range]  [⚙ Filters (3)]
```

### 4.3 Filter Badges

```
Active filters: [Length: Detailed ✕] [Perspective: Executive ✕] [Date: Apr 1-3 ✕]
```

---

## 5. Data Model Changes

### 5.1 StoredSummary Model

```python
@dataclass
class StoredSummary:
    # ...existing fields...

    # Generation settings (ADR-035)
    summary_length: Optional[str] = None    # 'brief' | 'detailed' | 'comprehensive'
    perspective: Optional[str] = None        # 'general' | 'developer' | custom name
    prompt_template_id: Optional[str] = None # ADR-034 template ID
```

### 5.2 Frontend Types

```typescript
interface StoredSummary {
  // ...existing fields...

  summary_length?: 'brief' | 'detailed' | 'comprehensive';
  perspective?: string;
  prompt_template_id?: string;
  prompt_template_name?: string;
}

interface FilterState {
  // ...existing filters...
  summaryLength?: 'brief' | 'detailed' | 'comprehensive';
  perspective?: string;
}
```

---

## 6. Migration Strategy

### 6.1 New Summaries
- All new summaries will have `summary_length` and `perspective` populated

### 6.2 Existing Summaries
- Leave `summary_length` and `perspective` as `NULL`
- Filter UI shows "Unknown" or excludes NULL values from filter counts
- Optional: Backfill job to infer settings from metadata

---

## 7. Consequences

### Positive
- Users can generate summaries for exact date ranges
- Easier to find summaries by generation style
- Enables "give me all executive summaries from Q1" queries
- Consistent date picker UX across generate and filter

### Negative
- Adds two columns to stored_summaries table
- Existing summaries won't have generation metadata
- Filter UI grows wider (but collapsible)

### Neutral
- Custom template names in perspective filter need refresh when templates change
- Time zone handling for absolute dates needs careful implementation

---

## 8. Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `src/data/migrations/035_generation_settings.sql` | Database schema |

### Modified Files
| File | Changes |
|------|---------|
| `src/models/stored_summary.py` | Add generation fields |
| `src/data/sqlite/stored_summary_repository.py` | Store/query new fields |
| `src/dashboard/routes/summaries.py` | Handle absolute dates, store settings |
| `src/dashboard/models.py` | Update request/response models |
| `src/frontend/src/types/index.ts` | Add TypeScript types |
| `src/frontend/src/pages/Summaries.tsx` | Add date picker to generate dialog |
| `src/frontend/src/components/summaries/SummaryFilters.tsx` | Add length/perspective filters |
| `src/frontend/src/hooks/useStoredSummaries.ts` | Add filter params |

---

## 9. Verification

### Unit Tests
- Absolute date range parsing
- Generation settings storage/retrieval
- Filter query building with new params

### Integration Tests
- Generate summary with custom date range
- Filter by summary_length
- Filter by perspective
- Combination filters

### Manual Testing
1. Generate summary for "March 15-20, 2026"
2. Verify settings stored in database
3. Filter summaries by "detailed" length
4. Filter by "executive" perspective
5. Verify filter badges show correctly
