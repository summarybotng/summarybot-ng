# ADR-062: Summary Repository Architecture Alignment

## Status
Accepted

## Context

The codebase has two distinct summary repository patterns that emerged organically:

1. **SummaryRepository** (legacy) - Defined in `src/data/base.py` line 54
2. **StoredSummaryRepository** (ADR-005) - Defined in `src/data/base.py` line 710

These two patterns have divergent APIs that have caused repeated coding errors during feature development, including:
- Using wrong method signatures (`search()` vs `find_by_guild()`)
- Using wrong field names (`content` vs `summary_text`)
- Using wrong filter parameters (`start_date` vs `start_time`)
- Assuming one repository's interface when coding against the other

This ADR documents the purpose of each, recommends alignment strategies, and establishes conventions to prevent future errors.

---

## Decision

### Both Repositories Are Needed

The two repositories serve different purposes and both are required:

| Repository | Purpose | Lifecycle |
|------------|---------|-----------|
| **SummaryRepository** | Ephemeral summaries (not persisted long-term) | Short-lived cache |
| **StoredSummaryRepository** | Persistent summaries with metadata | Long-term storage |

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    Summary Generation Flow                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Messages → SummarizationEngine → SummaryResult                  │
│                                        │                          │
│                                        ▼                          │
│                            ┌─────────────────────┐               │
│                            │ SummaryRepository   │  (ephemeral)  │
│                            │ - Quick lookup      │               │
│                            │ - Not persisted     │               │
│                            └─────────────────────┘               │
│                                        │                          │
│                                        ▼                          │
│                       ┌────────────────────────────┐             │
│                       │ StoredSummaryRepository    │  (persistent)│
│                       │ - Long-term storage        │             │
│                       │ - Rich metadata            │             │
│                       │ - FTS search               │             │
│                       │ - Wiki population source   │             │
│                       └────────────────────────────┘             │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## API Comparison

### SummaryRepository (Legacy)

```python
class SummaryRepository(ABC):
    async def save(self, result: SummaryResult) -> str
    async def get(self, summary_id: str) -> Optional[SummaryResult]
    async def find_summaries(self, criteria: SearchCriteria) -> List[SummaryResult]
    async def delete(self, summary_id: str) -> bool
```

**SearchCriteria** fields:
- `start_time: Optional[datetime]`
- `end_time: Optional[datetime]`
- `channel_id: Optional[str]`
- `guild_id: Optional[str]`
- `min_messages: Optional[int]`
- `limit: int = 10`

### StoredSummaryRepository (ADR-005)

```python
class StoredSummaryRepository(ABC):
    async def save(self, summary: StoredSummary) -> str
    async def get(self, summary_id: str) -> Optional[StoredSummary]
    async def find_by_guild(
        self,
        guild_id: str,
        limit: int = 20,
        offset: int = 0,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        # ... many more filters
    ) -> List[StoredSummary]
    async def search(self, guild_id: str, query: str, limit: int = 10) -> List[StoredSummary]
    async def delete(self, summary_id: str) -> bool
```

---

## Key Differences

| Aspect | SummaryRepository | StoredSummaryRepository |
|--------|-------------------|------------------------|
| **Primary Model** | `SummaryResult` | `StoredSummary` |
| **Find Method** | `find_summaries(criteria)` | `find_by_guild(guild_id, ...)` |
| **Date Filter** | `start_time` / `end_time` | `created_after` / `created_before` |
| **Search** | N/A | `search(guild_id, query)` |
| **Pagination** | `limit` in criteria | `limit` + `offset` params |
| **FTS Support** | No | Yes (ADR-020) |
| **Metadata** | Minimal | Rich (tags, pins, archive info) |

---

## Alignment Recommendations

### 1. Use StoredSummaryRepository for New Features

All new features requiring summary access should use `StoredSummaryRepository`:

```python
# Good - Use StoredSummaryRepository
from ...data.repositories import get_stored_summary_repository

stored_repo = await get_stored_summary_repository()
summaries = await stored_repo.find_by_guild(
    guild_id=guild_id,
    created_after=cutoff_date,
    limit=100,
)
```

### 2. Access SummaryResult via StoredSummary

When you need `SummaryResult` fields, access them through `StoredSummary.summary_result`:

```python
# StoredSummary wraps SummaryResult
stored_summary = await stored_repo.get(summary_id)

# Access the underlying SummaryResult
text = stored_summary.summary_result.summary_text  # Not .content!
points = stored_summary.summary_result.key_points
participants = stored_summary.summary_result.participants
```

### 3. Field Name Reference

| Need | StoredSummary | SummaryResult |
|------|--------------|---------------|
| Summary text | `stored.summary_result.summary_text` | `result.summary_text` |
| Key points | `stored.summary_result.key_points` | `result.key_points` |
| Participants | `stored.summary_result.participants` | `result.participants` |
| Participant name | - | `participant.display_name` |
| Action item | - | `action_item.description` |
| Technical term | - | `tech_term.term` |

### 4. Import Conventions

Establish consistent imports to avoid confusion:

```python
# For persistent summaries (most common use case)
from src.data.repositories import get_stored_summary_repository

# For ephemeral/legacy summaries only
from src.data import get_summary_repository  # Legacy, use sparingly
```

---

## Migration Path

### Phase 1: Documentation (This ADR)
- Document the two patterns
- Establish conventions

### Phase 2: Wrapper Methods (Optional)
Add convenience methods to StoredSummaryRepository for common legacy patterns:

```python
# Add to StoredSummaryRepository
async def find_summaries(self, criteria: SearchCriteria) -> List[StoredSummary]:
    """Legacy-compatible find method."""
    return await self.find_by_guild(
        guild_id=criteria.guild_id,
        created_after=criteria.start_time,
        created_before=criteria.end_time,
        limit=criteria.limit,
    )
```

### Phase 3: Deprecation (Future)
- Add deprecation warnings to SummaryRepository
- Migrate remaining usages to StoredSummaryRepository

---

## Consequences

### Positive
- Clear documentation prevents repeated coding errors
- Single source of truth for persistent summaries
- Consistent API for new features

### Negative
- Two patterns remain in codebase (necessary for now)
- Requires developer awareness of the distinction

### Risks
- Developers may still confuse the two patterns
- Legacy code may continue using SummaryRepository

---

## References

- [ADR-005: Stored Summary Model](./ADR-005-stored-summary-model.md)
- [ADR-020: Summary Full-Text Search](./ADR-020-summary-fts.md)
- `src/data/base.py` - Repository interfaces
- `src/data/sqlite/stored_summary_repository.py` - SQLite implementation
- `src/models/summary.py` - SummaryResult model
- `src/models/stored_summary.py` - StoredSummary model
