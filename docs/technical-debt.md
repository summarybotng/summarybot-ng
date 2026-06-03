# Technical Debt Review: SummaryBot-NG

**Review Date:** 2026-06-02
**Review Type:** Brutal Honesty (Linus + Ramsay Mode)
**Calibration:** Level 2 (Harsh)
**Scope:** Full Codebase Architecture

---

## Executive Summary

This codebase works. It probably works well enough for current load. But it's built on technical debt that compounds daily. The fundamental problem: shipped fast, promised to fix later, and "later" never came.

**Total Weighted Score: 12** (threshold for "needs immediate attention": 6)

---

## Critical Findings

### 1. GOD FILES - The 5,574 Line Abomination

**Severity:** CRITICAL (weight: 3)

**What's Broken:**
```
src/dashboard/routes/summaries.py  → 5,574 lines, 46+ functions
src/dashboard/routes/archive.py    → 4,051 lines
src/dashboard/routes/wiki.py       → 2,277 lines
src/scheduling/executor.py         → 1,539 lines
```

**Why It's Wrong:**
This isn't a route file, it's a monolithic application crammed into a single file. `summaries.py` alone has:
- Summary CRUD
- Job management
- Confluence publishing
- Email delivery
- DM delivery
- Bulk operations
- Calendar views
- Search functionality
- Database debugging

One file. 46 endpoints. Zero separation of concerns.

Every change to Confluence publishing risks breaking email delivery because they share 5,000 lines of context.

**What Correct Looks Like:**
```
routes/
├── summaries/
│   ├── crud.py         # CRUD operations (~200 lines)
│   ├── search.py       # Search endpoints (~150 lines)
│   ├── bulk.py         # Bulk operations (~200 lines)
│   ├── delivery.py     # Push/email/DM (~300 lines)
│   ├── confluence.py   # Confluence integration (~250 lines)
│   └── jobs.py         # Job management (~200 lines)
```

---

### 2. In-Memory State in Production Code

**Severity:** CRITICAL (weight: 3)

**What's Broken:**
```python
# src/dashboard/routes/summaries.py:74
# In-memory task tracking (replace with proper task queue in production)
_generation_tasks: dict[str, dict] = {}
```

```python
# src/dashboard/auth.py:71
# In-memory session store (replace with database in production)
```

```python
# src/dashboard/routes/events.py:20
# Event queues per guild (in production, use Redis pub/sub)
```

**Why It's Wrong:**
Comments admitting the code isn't production-ready, then deployed to production. In-memory task tracking means:
- Server restart = lost jobs
- Multiple workers = race conditions
- No persistence = no recovery

**What Correct Looks Like:**
Use Celery, RQ, or the SQLite-based job tracking already in `summary_job_repository.py`. The code exists - use it everywhere.

---

### 3. Migration Numbering Gaps (64 files, jumps to 118)

**Severity:** HIGH (weight: 2)

**What's Broken:**
```
094_summary_scope_metadata.sql
095_confluence_publishing.sql
096_rolling_period_summaries.sql
...
112_whatsapp_coverage_gaps.sql  ← JUMPED FROM 98 to 112
...
118_ruvector_deduplicate_existing.sql
```

**Why It's Wrong:**
- Migration numbers 099-111 are missing
- Creates deployment chaos when migrations are applied out of order
- Schema versioning is useless if versions have gaps

**What Correct Looks Like:**
Sequential migrations. For feature branches, use timestamps not sequential numbers:
```
20260601_001_confluence_publishing.sql
20260601_002_confluence_options.sql
```

---

### 4. Test Coverage Ratio: ~36% File Coverage

**Severity:** HIGH (weight: 2)

**What's Broken:**
- 256 Python source files
- 92 test files
- Rough coverage: ~36% file coverage (assuming 1:1 mapping)

Most critical files have 0 dedicated tests:
- `summaries.py` (5,574 lines) - No dedicated test file
- `archive.py` (4,051 lines) - No dedicated test file
- `executor.py` (1,539 lines) - Partial coverage at best

118 database migrations with no migration tests.

**What Correct Looks Like:**
Minimum 80% line coverage, 90% for critical paths.

---

### 5. 18+ Stale TODOs in Production Code

**Severity:** MEDIUM (weight: 1)

**What's Broken:**
```python
# TODO: Implement actual webhook delivery using aiohttp
# TODO: Implement database persistence
# TODO: Implement actual cleanup logic with database
# TODO: Integrate with actual LLM for synthesis
# TODO: Implement AI synthesis when synthesize=True
# TODO: Implement Vault integration
```

**Why It's Wrong:**
TODOs are promises to your future self. Some have been there since codebase start.

`# TODO: Implement database persistence` in a persistence file means the feature doesn't work.

**What Correct Looks Like:**
Every TODO becomes a tracked issue or gets deleted:
```python
# TODO(JIRA-1234): Implement database persistence
```

---

### 6. Repository Pattern Half-Implemented

**Severity:** MEDIUM (weight: 1)

**What's Broken:**
- `src/data/base.py` with abstract repository interfaces - Good
- 28 SQLite implementations - Good
- Routes directly calling repositories AND doing business logic - Bad

```python
# src/dashboard/routes/summaries.py - 200 lines of business logic in route handler
async def regenerate_stored_summary(...):
    # Business logic that should be in a service
```

**Why It's Wrong:**
Routes should be thin (parse request → call service → return response). Instead, routes ARE the services. This makes testing impossible without spinning up the entire HTTP layer.

**What Correct Looks Like:**
```python
# Route (thin)
@router.post("/regenerate")
async def regenerate(request: Request, service: SummaryService = Depends()):
    return await service.regenerate(request.summary_id)

# Service (business logic)
class SummaryService:
    async def regenerate(self, summary_id: str):
        # 200 lines of actual logic, testable without HTTP
```

---

## Summary Scorecard

| Finding | Severity | Weight |
|---------|----------|--------|
| God files (5,574 line monsters) | CRITICAL | 3 |
| In-memory state in production | CRITICAL | 3 |
| Migration gaps (94→112→118) | HIGH | 2 |
| ~36% test file coverage | HIGH | 2 |
| 18+ stale TODOs | MEDIUM | 1 |
| Half-implemented repository pattern | MEDIUM | 1 |

**Total Weighted Score: 12** (threshold for "needs immediate attention": 6)

---

## What's Good

- ADR documentation is excellent (118 decisions tracked)
- Model layer is clean
- Migration system exists (even if numbering is broken)
- Test infrastructure exists (even if coverage is low)
- Repository pattern foundation is solid

---

## Recommended Actions (Priority Order)

### Immediate (Week 1-2)

1. **Replace in-memory task tracking** with existing `SummaryJobRepository`
   - Files: `src/dashboard/routes/summaries.py:74`, `src/dashboard/auth.py:71`, `src/dashboard/routes/events.py:20`
   - Impact: Stability, crash recovery

2. **Add tests for critical paths**
   - `src/scheduling/executor.py`
   - `src/summarization/engine.py`
   - Large route files

### Short-term (Month 1)

3. **Split `summaries.py`** into 6-8 focused modules
   - Each module < 500 lines
   - Clear separation of concerns
   - Independent testability

4. **Fix migration numbering**
   - Audit what's missing (099-111)
   - Renumber or fill gaps

### Ongoing

5. **Convert TODOs to issues or delete them**
   - No uncommitted TODOs without ticket numbers

6. **Extract business logic from routes to services**
   - Thin routes, fat services
   - Enable unit testing without HTTP

---

## Files Requiring Attention

| File | Lines | Issue | Priority |
|------|-------|-------|----------|
| `src/dashboard/routes/summaries.py` | 5,574 | God file, needs split | P0 |
| `src/dashboard/routes/archive.py` | 4,051 | God file, needs split | P0 |
| `src/dashboard/routes/wiki.py` | 2,277 | Large, consider split | P1 |
| `src/scheduling/executor.py` | 1,539 | Complex, needs tests | P1 |
| `src/dashboard/auth.py` | 811 | In-memory sessions | P0 |
| `src/dashboard/routes/events.py` | - | In-memory queues | P1 |

---

## Metrics to Track

| Metric | Current | Target |
|--------|---------|--------|
| Largest file (lines) | 5,574 | < 500 |
| Test file coverage | ~36% | 80% |
| Stale TODOs | 18+ | 0 |
| In-memory production state | 3 locations | 0 |
| Migration gaps | Yes | No |

---

*Review conducted 2026-06-02. This review attacks the work, not the worker.*
