# ADR-012: Summaries UI Consolidation

**Status:** Implemented
**Date:** 2026-02-22
**Depends on:** ADR-008 (Unified Summary Experience)
**Supersedes:** Partial implementation of ADR-008 Section 3

---

## 1. Problem Statement

The current Summaries page has **three tabs** with confusing distinctions:

| Tab | Repository | Data Source | Features |
|-----|------------|-------------|----------|
| **History** | `SummaryRepository` | Generate button output | View details |
| **Archive** | Files on disk | `.md` + `.meta.json` files | Read-only |
| **Stored** | `StoredSummaryRepository` | Scheduled tasks + Archive generator | Push to channel, time grouping |

This creates confusion:
1. Users don't know where their summaries go
2. Same summary type appears in different tabs depending on how it was created
3. Features are inconsistent (time grouping only in Stored, push only in Stored)
4. Two separate database tables (`summaries` vs `stored_summaries`) for the same concept

**Current repository usage:**

| Action | Repository | Tab | Has Time Grouping |
|--------|------------|-----|-------------------|
| Generate button | `SummaryRepository` | History | No |
| Scheduled task | `StoredSummaryRepository` | Stored | Yes |
| Archive generation | `StoredSummaryRepository` | Stored | Yes |

**ADR-008 proposed unification but implementation diverged.**

---

## 2. Decision

Consolidate to **two tabs** with **one unified repository**:

### 2.1 New Tab Structure

```
┌─────────────────────────────────────────────────────────────────┐
│  Summaries                                     [Generate Summary]│
│  ───────────────────────────────────────────────────────────────│
│  [All Summaries] [Retrospective Jobs]                            │
│  ───────────────────────────────────────────────────────────────│
│                                                                  │
│  Source: [All ▾]  Time: [All ▾]  Length: [All ▾]                │
│  ───────────────────────────────────────────────────────────────│
│                                                                  │
│  ── Today ──────────────────────────────────────────────────────│
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ [Manual] #general • detailed • Feb 22, 10:30 AM          │  │
│  │ The team discussed deployment strategies and agreed...   │  │
│  │ 📬 47 msgs  👥 12  ⏱️ 2.3s  🪙 0.02 USD                  │  │
│  │                    [Push to Channel] [View] [⋮]          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ── Last 3 Days ────────────────────────────────────────────────│
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ [Scheduled] #support • brief • Feb 21, 6:00 PM           │  │
│  │ Support tickets focused on login issues and...           │  │
│  │ 📬 89 msgs  👥 8                                          │  │
│  │                    [Push to Channel] [View] [⋮]          │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ [Archive] server-wide • comprehensive • Feb 20           │  │
│  │ Retrospective analysis of Q1 planning discussions...     │  │
│  │ 📬 234 msgs  👥 15  📅 daily                              │  │
│  │                    [Push to Channel] [View] [⋮]          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Tab Definitions

| Tab | Purpose |
|-----|---------|
| **All Summaries** | Single view of all summaries regardless of source, with filtering |
| **Retrospective Jobs** | Archive generation job management (status, costs, gaps) |

### 2.3 Unified Repository

Merge `SummaryRepository` and `StoredSummaryRepository` into one:

```python
class UnifiedSummaryRepository:
    """Single repository for all summary types."""

    async def list(
        self,
        guild_id: str,
        source: Optional[SummarySource] = None,  # Filter by source
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        channel_id: Optional[str] = None,
        is_archived: bool = False,  # Soft-delete filter
        limit: int = 50,
        offset: int = 0,
    ) -> List[Summary]: ...

    async def save(self, summary: Summary) -> str: ...
    async def get(self, id: str) -> Optional[Summary]: ...
    async def update(self, id: str, **fields) -> bool: ...
    async def delete(self, id: str) -> bool: ...  # Soft delete
```

### 2.4 Source Badges

Visual badges distinguish summary origins:

| Source | Badge | Color |
|--------|-------|-------|
| `manual` | Manual | Blue |
| `scheduled` | Scheduled | Green |
| `archive` | Archive | Orange |
| `realtime` | (none) | - |

### 2.5 Consistent Features Everywhere

Every summary, regardless of source, has:
- ✅ View details (summary text, key points, action items)
- ✅ View generation metadata (model, tokens, cost, prompt source)
- ✅ Push to channel (any summary can be sent to Discord)
- ✅ Pin/Archive/Delete actions
- ✅ Time-based grouping (Today, Last 3 Days, This Week, Older)
- ✅ References with citations (ADR-004)

---

## 3. Database Migration

### 3.1 Consolidate Tables

```sql
-- Option A: Add missing columns to stored_summaries, deprecate summaries
ALTER TABLE stored_summaries ADD COLUMN IF NOT EXISTS channel_id VARCHAR(32);
ALTER TABLE stored_summaries ADD COLUMN IF NOT EXISTS scope VARCHAR(20);

-- Migrate data from summaries to stored_summaries
INSERT INTO stored_summaries (
    id, guild_id, channel_id, channel_name, title, summary_text,
    message_count, start_time, end_time, timezone, source, created_at, ...
)
SELECT
    id, guild_id, channel_id, channel_name,
    CONCAT('Summary ', DATE(start_time)), summary_text,
    message_count, start_time, end_time, timezone,
    'manual', created_at, ...
FROM summaries
ON CONFLICT (id) DO NOTHING;

-- Option B: Rename stored_summaries to unified_summaries
ALTER TABLE stored_summaries RENAME TO unified_summaries;
```

### 3.2 Single Repository

```python
# Before: Two functions
async def get_summary_repository() -> SummaryRepository: ...
async def get_stored_summary_repository() -> StoredSummaryRepository: ...

# After: One function
async def get_summary_repository() -> UnifiedSummaryRepository: ...
```

---

## 4. Frontend Changes

### 4.1 Remove History Tab

The History tab content merges into "All Summaries" with `source` filter.

### 4.2 Remove Archive Tab

Archive summaries appear in "All Summaries" with `source=archive` filter.
The "Retrospective Jobs" tab replaces the old Archive page for job management.

### 4.3 Unified Summary Card

All summaries use the same card component with:
- Source badge
- Channel/scope info
- Time info
- Stats (messages, participants, cost)
- Action buttons (Push, View, Menu)

```tsx
interface UnifiedSummaryCardProps {
  summary: Summary;
  onView: () => void;
  onPush: () => void;
  onPin: () => void;
  onArchive: () => void;
  onDelete: () => void;
}
```

### 4.4 Time Grouping

Apply `groupSummariesByRecency()` to all summaries in the unified view.

---

## 5. API Changes

### 5.1 Deprecate Separate Endpoints

```
# Deprecated
GET  /guilds/{guild_id}/summaries/stored
POST /guilds/{guild_id}/summaries/stored/{id}/push

# Unified
GET  /guilds/{guild_id}/summaries?source=all|manual|scheduled|archive
POST /guilds/{guild_id}/summaries/{id}/push  # Works for all sources
```

### 5.2 Source Filter

```
GET /guilds/{guild_id}/summaries?source=archive&limit=20

Response:
{
  "items": [...],
  "total": 45,
  "sources": {
    "manual": 12,
    "scheduled": 28,
    "archive": 45
  }
}
```

---

## 6. Implementation Plan

### Phase 1: Repository Consolidation
- [x] Create migration to add missing columns to `stored_summaries`
- [x] Migrate existing `summaries` data to `stored_summaries`
- [x] Create `UnifiedSummaryRepository` wrapping `StoredSummaryRepository`
- [x] Update all callers to use unified repository

### Phase 2: Backend API
- [x] Add `source` filter to `/summaries` endpoint (already existed)
- [x] Ensure Push endpoint works for all summary types
- [x] Update Generate endpoint to save to unified repository

### Phase 3: Frontend
- [x] Create unified `SummaryCard` component (StoredSummaryCard already handles all types)
- [x] Apply time grouping to unified view
- [x] Add source filter dropdown
- [x] Remove History/Archive tabs, keep All Summaries + Retrospective Jobs
- [x] Update navigation

### Phase 4: Cleanup
- [ ] Remove deprecated endpoints (optional - old endpoints still work for backwards compatibility)
- [ ] Remove old `SummaryRepository` implementation (kept for data migration during transition)
- [x] Update documentation

---

## 7. Consequences

### Positive
- **Simpler mental model**: One place for all summaries
- **Consistent features**: Push, view details, time grouping for all
- **Easier debugging**: One table, one repository
- **Better UX**: No confusion about where summaries appear

### Negative
- **Migration required**: Existing data needs consolidation
- **Breaking API changes**: Clients using `/summaries/stored` need updates

### Risks
- Data loss during migration (mitigated by backup + ON CONFLICT)
- Breaking existing scheduled tasks (mitigated by repository abstraction)

---

## 8. Alternatives Considered

### A. Keep Three Tabs, Add Time Grouping Everywhere
- Pros: No migration, smaller change
- Cons: Doesn't address fundamental confusion, duplicated code

### B. Keep Two Repositories, Unify at API Level
- Pros: No database migration
- Cons: Complex query logic, inconsistent behavior

### C. This Proposal (Chosen)
- Pros: Clean architecture, single source of truth
- Cons: Requires migration

---

## 9. References

- [ADR-008: Unified Summary Experience](./008-unified-summary-experience.md)
- [ADR-005: Summary Delivery Destinations](./005-summary-delivery-destinations.md)
- [ADR-006: Retrospective Summary Archive](./006-retrospective-summary-archive.md)
