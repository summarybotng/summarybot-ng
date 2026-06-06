# SPARC Architecture Phase

**Project**: SummaryBot V3
**Phase**: 3 of 5 (Architecture)
**Status**: Complete

---

## Documents

| # | Document | Description |
|---|----------|-------------|
| 01 | [System Overview](./01-system-overview.md) | Component diagram, data flows, layer boundaries |
| 02 | [API Contracts](./02-api-contracts.md) | REST endpoints, request/response schemas |
| 03 | [Database Schema](./03-database-schema.md) | SQLite tables, indexes, migration strategy |

---

## Key Architectural Decisions

### 1. Hexagonal Architecture (Ports & Adapters)

```
           ┌─────────────────────────────┐
           │         DOMAIN              │
           │  (Pure business logic)      │
           │                             │
           │   Entities    Ports         │
           │   Events      Errors        │
           └──────────┬──────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
   │ Service │   │ Service │   │ Service │
   │  Auth   │   │ Summary │   │Schedule │
   └────┬────┘   └────┬────┘   └────┬────┘
        │             │             │
   ┌────▼─────────────▼─────────────▼────┐
   │            ADAPTERS                  │
   │  SQLite  Discord  OpenRouter  SMTP  │
   └──────────────────────────────────────┘
```

### 2. Domain Independence

Domain layer has **zero** external dependencies:
- No SQLAlchemy
- No FastAPI
- No httpx
- No aiosqlite

Only Python stdlib + dataclasses.

### 3. Result Types

Services return `Result[T, E]` instead of raising exceptions:
- Makes error handling explicit
- Forces callers to handle failures
- Better for async/concurrent code

### 4. Event-Driven Side Effects

Services emit domain events; handlers perform side effects:
- Decouples core logic from notifications, metrics, delivery
- Easier to add new side effects without changing services
- Testable in isolation

---

## Layer Responsibilities

| Layer | Responsibility | Depends On |
|-------|----------------|------------|
| API | HTTP → Service calls, validation | Services |
| Services | Orchestration, transactions, events | Domain, Ports |
| Domain | Business rules, invariants | Nothing |
| Adapters | I/O implementations | Domain (implements ports) |

---

## Next Phase

**Refinement** (TDD Implementation):
- Write tests first (domain, services)
- Implement to pass tests
- 80% coverage gate enforced

---

*Generated: 2026-06-06*
