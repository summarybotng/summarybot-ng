# V3 Implementation Guide

**For**: Claude session building SummaryBot V3
**From**: V1 maintenance session
**Date**: 2026-06-06

---

## Quick Start

```bash
# 1. Read these documents in order:
docs/PRD-rewrite.md                        # Full requirements (120+ FRs)
docs/v1-legacy-requirements.md             # LEG-XXX runtime issues
docs/v2-rebuild-plan.md                    # 10-week plan
docs/sparc/pseudocode/README.md            # Algorithm designs
docs/sparc/architecture/01-system-overview.md  # Component diagram
```

## What V1 Provides

| Document | Purpose |
|----------|---------|
| `docs/PRD-rewrite.md` | Complete specification with Section 13 Future Requirements |
| `docs/PRD-rewrite-appendix-endpoints.md` | All 253 endpoints to implement |
| `docs/technical-debt.md` | What NOT to repeat (brutal honesty review) |
| `docs/v2-rebuild-plan.md` | Directory structure, CI, migration scripts |
| `docs/v1-legacy-requirements.md` | Runtime issues discovered in maintenance (LEG-XXX) |
| `docs/sparc/pseudocode/*.md` | Algorithm designs for core modules |
| `docs/sparc/architecture/*.md` | System diagrams, API contracts, DB schema |

---

## Critical Requirements

### LEG-001: Global Rate Limiter (MUST IMPLEMENT)

V1 jobs fail due to per-instance rate limiting. V3 MUST have:

```python
# v3/src/adapters/llm/rate_limiter.py
class GlobalRateLimiter:
    """Process-wide singleton with:
    - TokenBucket (configurable requests/minute)
    - CircuitBreaker (opens after 5 consecutive 429s)
    - Priority queue (MANUAL > NORMAL > LOW)
    """
```

See: `docs/sparc/pseudocode/03-rate-limiter.md`

### LEG-002: Job Failure Classification

Jobs must surface failure_reason:
- `rate_limited` (retryable)
- `quota_exceeded` (not retryable)
- `service_unavailable` (retryable)
- `invalid_request` (not retryable)

### Architecture Rules (CI-enforced)

```yaml
# .github/workflows/ci.yml
- No file > 300 lines
- No function > 30 lines
- 80% test coverage minimum
- Domain has zero external dependencies
```

---

## Directory Structure

```
summarybot-v3/
├── src/
│   ├── api/                 # FastAPI routes (thin)
│   │   └── routes/
│   ├── domain/              # Pure business logic (NO I/O)
│   │   ├── models/
│   │   ├── events.py
│   │   ├── errors.py
│   │   └── ports.py         # Repository interfaces
│   ├── services/            # Orchestration layer
│   ├── adapters/            # Infrastructure implementations
│   │   ├── repositories/sqlite/
│   │   ├── platforms/       # Discord, Slack, WhatsApp
│   │   ├── llm/             # OpenRouter + rate limiter
│   │   └── delivery/        # Discord, Email, Webhook, Confluence
│   └── shared/              # Config, logging, utils
└── tests/
    ├── unit/domain/         # Fast, no I/O
    ├── unit/services/
    └── integration/
```

---

## Implementation Order

### Week 1: Foundation
1. `uv init` with dependencies
2. CI pipeline (coverage gates, file size checks)
3. `src/domain/ports.py` - All repository interfaces
4. `src/domain/models/` - Workspace, Summary, Schedule, User

### Week 2: Rate Limiter (LEG-001)
1. `src/adapters/llm/rate_limiter.py` - TokenBucket + CircuitBreaker
2. Unit tests for rate limiter
3. `src/adapters/llm/openrouter.py` - LLM adapter with rate limiter

### Week 3: Core Services
1. `src/services/summary_service.py` - Generation pipeline
2. `src/services/auth_service.py` - OAuth + JWT
3. SQLite repositories

### Week 4: Scheduling
1. `src/services/schedule_service.py` - Executor loop
2. Delivery adapters (Discord, Email, Webhook)

### Week 5+: API, Frontend, Migration
1. FastAPI routes
2. React frontend (can port from V1)
3. Migration scripts from V1 database

---

## Key Design Patterns

### 1. Result Types (Not Exceptions)

```python
# Good
async def generate(self, request: GenerateRequest) -> Result[Summary, GenerationError]:
    if not messages:
        return Err(InsufficientMessagesError(count=0))
    return Ok(summary)

# Caller
result = await service.generate(request)
if result.is_err():
    return ErrorResponse(result.error.message)
```

### 2. Domain Events

```python
# Service emits event
await self.event_bus.publish(SummaryGenerated(
    summary_id=summary.id,
    cost_usd=summary.cost_usd
))

# Handlers react (delivery, notifications, metrics)
@event_handler(SummaryGenerated)
async def on_summary_generated(event: SummaryGenerated):
    await delivery_service.deliver_if_scheduled(event.summary_id)
```

### 3. Dependency Injection

```python
# In src/api/deps.py
def get_summary_service(
    summary_repo: SummaryRepository = Depends(get_summary_repo),
    rate_limiter: GlobalRateLimiter = Depends(get_rate_limiter),
    ...
) -> SummaryService:
    return SummaryService(summary_repo, rate_limiter, ...)
```

---

## V1 → V3 Data Migration

```python
# v3/scripts/migrate_v1.py

V1_TO_V3_MAPPING = {
    "guilds": None,  # Becomes workspace + platform_connection
    "stored_summaries": "summaries",
    "summary_schedules": "schedules",
    "confluence_publications": "delivery_logs",
}

# Guild → Workspace transformation
workspace = Workspace(
    id=f"ws-{guild.guild_id}",
    name=guild.name,
    connections=[PlatformConnection(
        platform="discord",
        platform_id=guild.guild_id,
        ...
    )]
)
```

---

## ADR Namespace

- **ADR-001 to ADR-118**: V1 decisions (read-only reference)
- **ADR-119+**: V3 decisions (yours to create)
- **LEG-XXX**: V1 legacy requirements to implement

When implementing a LEG requirement, reference it:
```
git commit -m "feat(llm): Add global rate limiter (LEG-001)"
```

---

## Environment Variables

```bash
# Required
DATABASE_URL=sqlite:///./summarybot-v3.db
SECRET_KEY=<random-32-bytes>
ENCRYPTION_KEY=<random-32-bytes>

# LLM
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_RPM=50  # Requests per minute

# OAuth (per provider)
DISCORD_CLIENT_ID=...
DISCORD_CLIENT_SECRET=...
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...

# Optional
CIRCUIT_FAILURE_THRESHOLD=5
CIRCUIT_OPEN_TIMEOUT=60
```

---

## Testing Strategy

### Unit Tests (Fast, No I/O)
```python
# tests/unit/domain/test_summary.py
def test_summary_has_pending_actions():
    summary = Summary(action_items=[ActionItem(completed=False)])
    assert summary.has_pending_actions is True
```

### Integration Tests (Real DB)
```python
# tests/integration/repositories/test_summary_repo.py
async def test_save_and_retrieve():
    repo = SqliteSummaryRepository(":memory:")
    await repo.save(summary)
    result = await repo.get_by_id(summary.id)
    assert result == summary
```

### Coverage Gate
```yaml
pytest --cov=src --cov-fail-under=80
```

---

## Deployment

```bash
# Fly.io (same as V1)
flyctl deploy --app summarybot-v3

# Or new app
flyctl launch --name summarybot-v3
```

---

## Questions for V3 to Decide

1. **Postgres vs SQLite**: V1 uses SQLite. Consider Postgres for:
   - Better concurrent write performance
   - Native JSON operators
   - Full-text search

2. **Message Queue**: For schedule execution:
   - In-process (asyncio, like V1)
   - External (Redis, Celery)

3. **Frontend**: Port V1 React app or rebuild?

---

## Contact

V1 maintenance session has context on:
- Why specific design decisions were made
- What runtime issues led to LEG requirements
- Historical ADR rationale

If you need clarification, the docs folder is the source of truth.

---

*Good luck with V3!*
