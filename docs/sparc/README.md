# SPARC Methodology: SummaryBot V3

**Status**: Specification, Pseudocode, Architecture complete
**Remaining**: Refinement (TDD), Completion (deployment)

---

## Phases

| # | Phase | Status | Documents |
|---|-------|--------|-----------|
| 1 | **Specification** | ✅ Complete | `docs/PRD-rewrite.md`, `docs/PRD-rewrite-appendix-endpoints.md` |
| 2 | **Pseudocode** | ✅ Complete | `docs/sparc/pseudocode/` (6 modules) |
| 3 | **Architecture** | ✅ Complete | `docs/sparc/architecture/` (3 documents) |
| 4 | **Refinement** | 🔲 Pending | V3 implements with TDD |
| 5 | **Completion** | 🔲 Pending | V3 deploys |

---

## Quick Navigation

### Specification
- [PRD-rewrite.md](../PRD-rewrite.md) - 120+ functional requirements
- [PRD-rewrite-appendix-endpoints.md](../PRD-rewrite-appendix-endpoints.md) - 253 API endpoints
- [v1-legacy-requirements.md](../v1-legacy-requirements.md) - Runtime issues (LEG-XXX)

### Pseudocode
- [01-domain-models.md](./pseudocode/01-domain-models.md) - Entities, value objects, events
- [02-summary-service.md](./pseudocode/02-summary-service.md) - Generation pipeline
- [03-rate-limiter.md](./pseudocode/03-rate-limiter.md) - LEG-001 implementation
- [04-schedule-executor.md](./pseudocode/04-schedule-executor.md) - Cron processing
- [05-auth-service.md](./pseudocode/05-auth-service.md) - Multi-provider OAuth
- [06-delivery-adapters.md](./pseudocode/06-delivery-adapters.md) - Discord, Email, etc.

### Architecture
- [01-system-overview.md](./architecture/01-system-overview.md) - Component diagram
- [02-api-contracts.md](./architecture/02-api-contracts.md) - REST API spec
- [03-database-schema.md](./architecture/03-database-schema.md) - SQLite schema

### Implementation Guide
- [V3-IMPLEMENTATION-GUIDE.md](../V3-IMPLEMENTATION-GUIDE.md) - Start here for V3

---

## For V3 Session

1. Read `V3-IMPLEMENTATION-GUIDE.md` first
2. Implement LEG-001 (rate limiter) early - it's critical
3. Follow pseudocode algorithms
4. Use TDD (London school, mock-first)
5. Create ADR-119+ for your decisions

---

*V1 maintenance session - 2026-06-06*
