# QE Swarm Executive Summary - summarybot-ng
**Date:** March 13, 2026
**Swarm:** 7 specialized QE agents (Queen-coordinated)
**Scope:** Full codebase analysis (~141 Python source files, 67 test files, React/TS frontend)

---

## Overall Project Grade: C+ (70/100)

| Domain | Agent | Grade | Key Finding |
|--------|-------|-------|-------------|
| Code Quality | qe-code-reviewer | **C+ (68)** | Concurrency bug in config lock; duplicate core classes |
| Complexity | qe-code-complexity | **C+ (~72)** | CC=59 function in 2,732-line file; 7 critical hotspots |
| Security | qe-security-reviewer | **C+ (~73)** | 3 Critical vulns: HMAC bypass, OAuth CSRF, test auth bypass |
| Performance | qe-performance-reviewer | **C+ (~71)** | Global write lock; N+1 queries; unbounded fetches |
| Quality Experience | qe-qx-partner | **B- (72)** | `perspective` silently dropped; no onboarding; no confirm on reset |
| Product Factors | qe-product-factors | **B+ (78)** | Plaintext webhook secrets; PII retention; hardcoded deploy URL |
| Tests & Coverage | qe-coverage-specialist | **B- (~73)** | 83 untested modules; 2.9% integration; near-zero frontend tests |

---

## Top 10 Cross-Cutting Findings (Priority Order)

### P0 - Critical (Fix Immediately)

1. **CRIT-SEC: HMAC Body Verification Not Wired** - `verify_webhook_signature` exists but is never called on `/api/v1/ingest`. Forged payloads can inject arbitrary messages into the LLM pipeline.
   *File: `src/webhook_service/auth.py:296-317`, `src/feeds/ingest_handler.py`*

2. **CRIT-SEC: OAuth CSRF - Missing State Parameter** - Discord OAuth flow has no `state` parameter, enabling login CSRF attacks.
   *File: `src/dashboard/routes/auth.py:44`*

3. **CRIT-SEC: Test Auth Bypass in Production** - `TESTING=true` env var bypasses all authentication via `X-Test-Auth-Key` header.
   *File: `src/dashboard/auth.py:589-653`*

4. **CRIT-BUG: Broken Config Lock** - `asyncio.Lock()` instantiated inline per call creates a new lock each time - zero mutual exclusion on concurrent config saves.
   *File: `src/config/manager.py:73`*

### P1 - High (Fix This Sprint)

5. **PERF: Global Serializing Write Lock** - Every DB write serializes through a single `asyncio.Lock` with `pool_size=1`, neutralizing WAL mode benefits.
   *File: `src/data/sqlite/connection.py:152`*

6. **PERF: N+1 Query Explosion in Guild Listing** - 5 sequential queries per guild inside a loop. 10 guilds = 50+ sequential queries per dashboard page load.
   *File: `src/dashboard/routes/guilds.py:92-171`*

7. **SEC: SSRF in Webhook Test** - Webhook test endpoint sends HTTP requests to arbitrary URLs without private IP range filtering.
   *File: webhook test endpoint*

8. **DATA: Webhook Secrets Stored in Plaintext** - Same table that stores encrypted prompt tokens stores webhook secrets unencrypted.
   *File: `guild_configs` SQLite table*

### P2 - Medium (Plan for Next Sprint)

9. **QUALITY: `summaries.py` God File** - 2,732 lines (5.5x over 500-line limit), CC=59 function, 27 route handlers. Single biggest maintainability risk.
   *File: `src/dashboard/routes/summaries.py`*

10. **TEST: 83 Source Modules Untested** - Integration layer at 2.9%, frontend near-zero. Largest untested file is the 2,732-line `summaries.py`.

---

## Duplicate Class / DRY Violations (Cross-Agent Consensus)

All 3 code-focused agents independently identified:
- `SummaryLength` enum duplicated in `config/settings.py` and `models/summary.py`
- `SummaryOptions` dataclass duplicated with incompatible fields
- `JobStatus` enum defined in 3 separate files
- Config fetch pattern copy-pasted ~30 times across dashboard routes
- `limit=10000` used as COUNT substitute in 10+ locations

---

## Architecture Strengths (Positive Findings)

- Clean repository pattern with well-separated data layer
- Well-designed exception hierarchy with typed exceptions
- 18 forward-only database migrations
- ADR-documented design decisions
- 6-model LLM escalation chain with cost capping
- Job recovery on restart
- Professional test fixture infrastructure (`conftest.py`, `tests/utils/mocking.py`)
- Consistent Discord embed color semantics
- Rate limit feedback with exact reset times
- Skeleton loading on every dashboard page

---

## Recommended Action Plan

### Sprint 1 (Immediate - Security)
- [ ] Wire HMAC verification to ingest endpoints
- [ ] Add OAuth state parameter for CSRF protection
- [ ] Remove or gate test auth bypass (`TESTING=true`)
- [ ] Fix inline `asyncio.Lock()` in config manager
- [ ] Add private IP filtering to webhook test endpoint

### Sprint 2 (Performance & Data)
- [ ] Fix N+1 queries in guild listing (batch fetch)
- [ ] Replace `limit=10000` patterns with `COUNT(*)` queries
- [ ] Encrypt webhook secrets at rest
- [ ] Add PII anonymization/retention policy for `source_content`
- [ ] Fix `FEED_BASE_URL` hardcoding for multi-platform deploys

### Sprint 3 (Maintainability & Tests)
- [ ] Split `summaries.py` into 6-8 focused sub-modules
- [ ] Consolidate duplicate enums (`SummaryLength`, `JobStatus`, `SummaryOptions`)
- [ ] Extract config fetch pattern into shared helper
- [ ] Add integration tests for top 10 untested critical modules
- [ ] Add dashboard `perspective` field to summary generation request

### Sprint 4 (UX & Polish)
- [ ] Add guild onboarding wizard
- [ ] Add confirmation dialog to `/config reset`
- [ ] Implement autocomplete for schedule task IDs
- [ ] Split `Archive.tsx` (1,806 lines) into component files
- [ ] Add `parametrize` to structurally identical test cases

---

## Individual Reports

| Report | Path |
|--------|------|
| Code Quality | [code-quality-report.md](./code-quality-report.md) |
| Complexity | [complexity-report.md](./complexity-report.md) |
| Security | [security-report.md](./security-report.md) |
| Performance | [performance-report.md](./performance-report.md) |
| Quality Experience | [qx-report.md](./qx-report.md) |
| Product Factors (SFDIPOT) | [product-factors-report.md](./product-factors-report.md) |
| Tests & Coverage | [tests-report.md](./tests-report.md) |

---

*Generated by QE Queen Swarm - 7 agents, ~2,600 seconds total analysis time*
