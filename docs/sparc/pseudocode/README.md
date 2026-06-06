# SPARC Pseudocode Phase

**Project**: SummaryBot V3
**Phase**: 2 of 5 (Pseudocode)
**Status**: Complete

---

## Overview

This phase defines the algorithmic logic and data flows for V3's core modules. Pseudocode is implementation-agnostic and focuses on **what** the system does, not **how** it's coded.

## Documents

| # | Module | Description | Key Patterns |
|---|--------|-------------|--------------|
| 01 | [Domain Models](./01-domain-models.md) | Core entities and value objects | DDD, Invariants, Events |
| 02 | [Summary Service](./02-summary-service.md) | Summary generation orchestration | Result types, Pipeline |
| 03 | [Rate Limiter](./03-rate-limiter.md) | Global rate limiting (LEG-001) | Token Bucket, Circuit Breaker |
| 04 | [Schedule Executor](./04-schedule-executor.md) | Scheduled job processing | Cron, Concurrency control |
| 05 | [Auth Service](./05-auth-service.md) | Multi-provider authentication | OAuth, JWT, Identity linking |
| 06 | [Delivery Adapters](./06-delivery-adapters.md) | Multi-channel delivery | Adapter pattern, Retry |

## Key Design Decisions

### 1. Result Types Over Exceptions

```pseudocode
# Prefer explicit Result types
FUNCTION generate() -> Result<Summary, GenerationError>

# Over throwing exceptions for expected failures
FUNCTION generate() -> Summary  # throws GenerationError
```

### 2. Domain Events for Side Effects

```pseudocode
# Emit events, let handlers deal with side effects
AWAIT event_bus.publish(SummaryGenerated(...))

# Not inline side effects
AWAIT send_notification(...)  # Don't do this in service
```

### 3. Invariants in Domain Objects

```pseudocode
ENTITY Schedule:
    INVARIANT: destinations.length >= 1  # Enforced at construction
```

### 4. Ports/Adapters for Infrastructure

```pseudocode
# Service depends on abstract port
summary_service = SummaryService(
    summary_repo: SummaryRepository,  # Abstract
    ...
)

# Adapter implements port
class SqliteSummaryRepository(SummaryRepository):
    ...
```

## Traceability

| Requirement | Pseudocode |
|-------------|------------|
| LEG-001 (Rate Limits) | `03-rate-limiter.md` |
| LEG-002 (Failure Classification) | `02-summary-service.md` §6 |
| FUT-001..006 (Multi-Auth) | `05-auth-service.md` |
| PRD §4.1 (Summary Generation) | `02-summary-service.md` |
| PRD §4.2 (Scheduling) | `04-schedule-executor.md` |
| PRD §4.3 (Delivery) | `06-delivery-adapters.md` |

## Next Phase

**Architecture** (`docs/sparc/architecture/`):
- System diagrams
- Component boundaries
- API contracts
- Database schema
- Infrastructure topology

---

*Generated: 2026-06-06*
