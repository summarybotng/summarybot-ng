# ADR-044: Deferred Technical Debt Tracker

**Status:** Active (Living Document)
**Date:** 2026-04-12
**Purpose:** Central tracking of all deferred issues, TODOs, and technical debt

---

## 1. Overview

This ADR serves as a central tracker for all deferred technical issues across the SummaryBot-NG codebase. It documents:
- Known limitations from other ADRs
- Code-level TODOs that need resolution
- Architectural debt requiring future work
- Issue interactions and dependencies

**Update Policy:** This document should be updated when:
- A new TODO is added to code
- A deferred issue is resolved
- New interactions are discovered

---

## 2. Issue Registry

### 2.1 Critical (P1) - Blocks Core Functionality

| ID | Issue | Source | Status | Resolved In |
|----|-------|--------|--------|-------------|
| P1-001 | ~~Retry job doesn't execute~~ | ADR-013:2847 | **RESOLVED** | ADR-044 |
| P1-002 | Discord-only identity blocks non-Discord orgs | ADR-026:#1 | Open | - |
| P1-003 | No failure classification for jobs | ADR-042 | Proposed | - |
| P1-004 | No auto-retry for transient failures | ADR-042 | Proposed | - |

### 2.2 High (P2) - Significant Feature Gaps

| ID | Issue | Source | Status | Resolved In |
|----|-------|--------|--------|-------------|
| P2-001 | Source ownership/hijacking risk | ADR-026:#2 | Open | - |
| P2-002 | Silent parameter fallbacks | ADR-038 | Proposed | - |
| P2-003 | All-or-nothing guild access | ADR-026:#6 | Deferred to Phase 3 | - |
| P2-004 | No audit trail for actions | ADR-026:#9 | **Proposed** | ADR-045 |
| P2-005 | WhatsApp edited messages not tracked | ADR-026:#3 | Open | - |
| P2-006 | No unified cross-guild view | ADR-026:#13 | Deferred to Phase 4+ | - |
| P2-007 | Email delivery not implemented | ADR-030 | Proposed | - |
| P2-008 | Confluence export not implemented | ADR-029 | Proposed | - |

### 2.3 Medium (P3) - Quality/Polish Issues

| ID | Issue | Source | Status | Resolved In |
|----|-------|--------|--------|-------------|
| P3-001 | JWT revocation delay | ADR-026:#7 | Known tradeoff | - |
| P3-002 | Orphan source accumulation | ADR-026:#8 | Open | - |
| P3-003 | No source deletion (GDPR risk) | ADR-026:#10 | Open | - |
| P3-004 | Memory pressure on large imports | ADR-026:#5 | Partial | - |
| P3-005 | Timezone deduplication failures | ADR-026:#4 | Open | - |
| P3-006 | No real-time WhatsApp | ADR-026:#11 | Inherent limitation | - |
| P3-007 | WhatsApp context loss in exports | ADR-026:#12 | Inherent limitation | - |
| P3-008 | Primary guild deletion orphans sources | ADR-026:#14 | Open | - |
| P3-009 | Problem reporting system | ADR-039 | Proposed | - |
| P3-010 | Google Drive sync | ADR-007 | Proposed | - |

---

## 3. Code-Level TODOs

### 3.1 Resolved TODOs

| File | Line | TODO | Resolution | Date |
|------|------|------|------------|------|
| `summaries.py` | 2847 | Actually trigger job execution | Created `job_executor.py` service | 2026-04-12 |

### 3.2 Open TODOs

| File | Line | TODO | Priority | Assigned ADR |
|------|------|------|----------|--------------|
| `executor.py` | 615 | Implement actual cleanup logic with database | P3 | - |
| `persistence.py` | 396 | Implement database persistence | P2 | - |
| `webhook.py` | 41 | Implement actual webhook delivery using aiohttp | P2 | ADR-005 |
| `backends.py` | 251 | Implement Vault integration | P3 | - |
| `writer.py` | 116 | Validate references | P3 | ADR-004 |
| `endpoints.py` | 301 | Check user permissions based on guild_id/channel_id | P2 | - |
| `endpoints.py` | 314 | Fetch messages from Discord based on request parameters | P2 | - |
| `endpoints.py` | 395 | Implement summary retrieval from database | P2 | - |
| `endpoints.py` | 454 | Implement scheduling logic | P2 | - |
| `endpoints.py` | 507 | Implement schedule cancellation | P2 | - |

---

## 4. Interaction Chains

### 4.1 Identity → Multi-Platform Chain

```
P1-002: Discord-only identity
    │
    └──▶ Blocks ADR-043 (Slack) for Slack-first orgs
            │
            └──▶ Even if Slack is built, users without Discord can't log in
```

**Resolution Required Before:** ADR-043 implementation

### 4.2 Retry → Auto-Retry → Self-Healing Chain

```
P1-001: Retry doesn't execute ← RESOLVED
    │
    └──▶ P1-003: No failure classification
            │
            └──▶ P1-004: No auto-retry
                    │
                    └──▶ ADR-038: Self-healing can't recover from failures
```

**Current Status:** P1-001 resolved. P1-003 and P1-004 require ADR-042 implementation.

### 4.3 Source Ownership → Audit → Compliance Chain

```
P2-001: No source ownership verification
    │
    └──▶ P2-004: No audit trail
            │
            └──▶ P3-003: No source deletion
                    │
                    └──▶ GDPR "right to be forgotten" requires manual intervention
```

**Resolution:** Need unified audit log before enterprise deployment.

### 4.4 Silent Fallbacks → Problem Reporting → Quality Chain

```
P2-002: Silent parameter fallbacks
    │
    └──▶ P3-009: No problem reporting system
            │
            └──▶ Can't correlate user complaints with fallbacks
```

**Resolution:** ADR-038 and ADR-039 should be implemented together.

---

## 5. Proposed Resolution Phases

### Phase 1: Fix Broken Core (Target: 2-3 weeks)
- [x] P1-001: Fix retry_job execution ✓ (2026-04-12)
- [ ] P1-003: Implement failure classification (ADR-042)
- [ ] P1-004: Implement auto-retry worker (ADR-042)
- [ ] P2-004: Implement audit logging system (ADR-045) ← Proposed 2026-04-12

### Phase 2: Self-Healing & Observability (Target: 3-4 weeks)
- [ ] P2-002: Parameter validation (ADR-038)
- [ ] P3-009: Problem reporting (ADR-039)
- [ ] Silent fallback notifications

### Phase 3: Identity Expansion (Target: 4-6 weeks)
- [ ] P1-002: Add Slack OAuth as identity provider
- [ ] Add email/password fallback
- [ ] Unified organization model

### Phase 4: Multi-Platform (Target: 16-23 weeks per ADR-043)
- [ ] Slack integration (ADR-043)
- [ ] WhatsApp dedup improvements
- [ ] Thread handling

### Phase 5: Delivery Expansion (Target: 8-12 weeks)
- [ ] P2-007: Email delivery (ADR-030)
- [ ] P2-008: Confluence export (ADR-029)
- [ ] P3-010: Google Drive sync (ADR-007)

---

## 6. Resolution Log

### 2026-04-12: P1-001 Resolved

**Issue:** `retry_job` endpoint created job records but never triggered execution.

**Root Cause:** TODO comment at line 2847 in `summaries.py` - the execution code was never implemented.

**Solution:**
1. Created `src/dashboard/services/job_executor.py` with:
   - `execute_job()` - Central entry point for job execution
   - `_execute_manual_job()` - Handles MANUAL and SCHEDULED jobs
   - `_execute_regenerate_job()` - Handles REGENERATE jobs

2. Updated `retry_job` endpoint to call `execute_job()` after creating the job record.

**Files Changed:**
- `src/dashboard/services/job_executor.py` (new)
- `src/dashboard/services/__init__.py` (new)
- `src/dashboard/routes/summaries.py` (modified)

**Verification:**
- Retry button now actually executes the job
- Job status updates in real-time
- Failed jobs can be successfully retried

---

## 7. How to Add New Items

### Adding a Code TODO

When adding a TODO to code:
1. Add comment: `# TODO: Description (ADR-044:P<priority>-XXX)`
2. Add entry to Section 3.2 (Open TODOs)
3. If significant, add to Section 2 (Issue Registry)

### Resolving an Issue

When resolving:
1. Move from "Open" to "Resolved" in Section 2 or 3
2. Add resolution entry to Section 6 (Resolution Log)
3. Update any interaction chains in Section 4

### Adding New Interactions

When discovering issue interactions:
1. Document in Section 4 (Interaction Chains)
2. Note blocking relationships
3. Update resolution order in Section 5 if needed

---

## 8. References

- [ADR-013: Unified Job Tracking](./013-unified-job-tracking.md)
- [ADR-026: Multi-Platform Source Architecture](./026-multi-platform-source-architecture.md)
- [ADR-038: Self-Healing Parameter Validation](./ADR-038-self-healing-parameter-validation.md)
- [ADR-039: User Problem Reporting](./ADR-039-user-problem-reporting.md)
- [ADR-042: Intelligent Job Retry Strategy](./ADR-042-intelligent-job-retry.md)
- [ADR-043: Slack Workspace Integration](./ADR-043-slack-workspace-integration-feasibility.md)
- [ADR-045: Audit Logging System](./ADR-045-audit-logging-system.md)
