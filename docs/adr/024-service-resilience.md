# ADR-024: Service Resilience and Availability

## Status
Proposed

## Date
2026-02-28

## Context

The SummaryBot-NG service occasionally becomes unresponsive on Fly.dev. Symptoms include:
- API requests timing out
- UI showing "Failed to Create" even when operations succeed
- Schedule creation appearing to fail but actually succeeding
- Server stops responding during heavy operations

### Current Architecture

```
[Fly.dev Single Machine]
    ├── FastAPI (web server)
    ├── Discord Bot (websocket)
    ├── Background Tasks (asyncio)
    ├── SQLite Database (file)
    └── Scheduled Jobs (APScheduler)
```

### Observed Failure Modes

1. **Memory Pressure**: Long summarization tasks consume memory, causing OOM
2. **Blocking Operations**: Synchronous DB writes block the event loop
3. **No Health Checks**: Fly doesn't know when the service is degraded
4. **Single Point of Failure**: One machine, no redundancy
5. **Connection Exhaustion**: Discord + API clients compete for connections
6. **Background Task Accumulation**: Failed tasks pile up, consuming resources

## Options Considered

### Option 1: Health Checks + Auto-Restart

**Approach:** Add proper health endpoints that Fly.dev can monitor.

```python
@app.get("/health")
async def health_check():
    checks = {
        "database": await check_db_connection(),
        "discord": check_discord_connection(),
        "memory": check_memory_usage(),
        "tasks": check_background_tasks(),
    }

    healthy = all(checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "healthy" if healthy else "degraded", "checks": checks}
    )
```

**fly.toml:**
```toml
[[services.http_checks]]
  interval = "15s"
  timeout = "5s"
  grace_period = "30s"
  method = "GET"
  path = "/health"

[processes]
  app = "python -m src.main"

[[vm]]
  memory = "1gb"
  cpu_kind = "shared"
  cpus = 1
```

**Pros:**
- Simple to implement
- Fly automatically restarts unhealthy instances
- Quick win

**Cons:**
- Doesn't prevent failures, just recovers from them
- Restart causes brief downtime

### Option 2: Request Timeouts + Circuit Breakers

**Approach:** Prevent cascading failures with timeouts and circuit breakers.

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def call_claude_api(prompt: str) -> str:
    async with asyncio.timeout(30):  # 30 second max
        return await claude_client.create_summary(prompt)
```

**Pros:**
- Prevents resource exhaustion
- Fails fast when dependencies are down
- Better user experience (immediate error vs. hanging)

**Cons:**
- May abort valid long-running operations
- Need to tune thresholds per endpoint

### Option 3: Background Task Queue (Redis/Celery)

**Approach:** Move heavy operations to a separate worker process.

```
[Web Process]                [Worker Process]
     │                              │
     └── Enqueue Task ──────────────┤
                                    │
                                    ├── Summarization
                                    ├── Archive Jobs
                                    └── Discord Fetches
```

**Pros:**
- Web server stays responsive
- Can scale workers independently
- Tasks survive web restarts
- Better observability

**Cons:**
- Significant architecture change
- Adds Redis dependency
- More complex deployment

### Option 4: Database Connection Pooling

**Approach:** Use connection pooling to prevent exhaustion.

```python
# Current: Single SQLite connection
# Proposed: Connection pool with limits

from sqlalchemy.pool import QueuePool

engine = create_engine(
    "sqlite:///data/summarybot.db",
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)
```

**Pros:**
- Prevents connection exhaustion
- Better concurrent performance
- Easy to implement

**Cons:**
- SQLite has limited concurrency benefits
- May need PostgreSQL for full benefit

### Option 5: Graceful Degradation

**Approach:** When under pressure, degrade non-critical features.

```python
class LoadShedder:
    def __init__(self, thresholds):
        self.thresholds = thresholds

    def should_accept(self, request_type: str) -> bool:
        memory_pct = psutil.virtual_memory().percent

        if memory_pct > 90:
            return request_type in ["health", "critical"]
        elif memory_pct > 80:
            return request_type != "archive_job"
        return True
```

**Pros:**
- Keeps core functionality working under load
- Prevents total outages

**Cons:**
- Complex to implement correctly
- Users may be confused by partial functionality

## Decision

**Recommended: Phased Implementation**

### Phase 1: Quick Wins (Immediate)
1. Add `/health` endpoint with proper checks
2. Configure Fly.dev health checks in fly.toml
3. Add request timeouts to all external calls
4. Increase memory allocation if needed

### Phase 2: Stability (Short-term)
1. Add circuit breakers for Claude API calls
2. Implement request queue for heavy operations
3. Add memory monitoring and alerting
4. Cap concurrent background tasks

### Phase 3: Scalability (Medium-term)
1. Evaluate Redis + worker queue architecture
2. Consider PostgreSQL for better concurrency
3. Add horizontal scaling (multiple Fly machines)
4. Implement proper job persistence

## Implementation

### Phase 1 Files to Change

**src/dashboard/health.py** (new):
```python
import psutil
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/health")
async def health():
    memory = psutil.virtual_memory()

    checks = {
        "memory_percent": memory.percent,
        "memory_available_mb": memory.available // (1024 * 1024),
        "uptime_seconds": (datetime.utcnow() - START_TIME).total_seconds(),
    }

    # Check database
    try:
        from ..data.repositories import get_stored_summary_repository
        repo = await get_stored_summary_repository()
        await repo.count()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Check Discord
    from . import get_discord_bot
    bot = get_discord_bot()
    checks["discord"] = "connected" if bot and bot.is_ready() else "disconnected"

    # Determine overall health
    is_healthy = (
        checks["memory_percent"] < 90 and
        checks["database"] == "ok" and
        checks["discord"] == "connected"
    )

    return {
        "status": "healthy" if is_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }

@router.get("/health/live")
async def liveness():
    """Simple liveness probe - just confirms the process is running."""
    return {"status": "alive"}

@router.get("/health/ready")
async def readiness():
    """Readiness probe - confirms the service can handle requests."""
    # Check critical dependencies
    from . import get_discord_bot
    bot = get_discord_bot()

    if not bot or not bot.is_ready():
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "Discord bot not connected"}
        )

    return {"status": "ready"}
```

**fly.toml** additions:
```toml
[checks]
  [checks.health]
    port = 8080
    type = "http"
    interval = "15s"
    timeout = "5s"
    grace_period = "30s"
    method = "GET"
    path = "/health/ready"

[[vm]]
  memory = "1gb"
```

**Request timeout wrapper:**
```python
import asyncio
from functools import wraps

def with_timeout(seconds: float):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                raise HTTPException(504, f"Request timed out after {seconds}s")
        return wrapper
    return decorator

# Usage:
@router.post("/generate")
@with_timeout(120)  # 2 minute max
async def generate_summary(...):
    ...
```

## Consequences

### Positive
- Service recovers automatically from failures
- Users get faster error feedback instead of timeouts
- Better visibility into service health
- Foundation for future scaling

### Negative
- Additional monitoring overhead
- May need to increase Fly.dev costs (more memory)
- Some complexity added to codebase

### Neutral
- Health checks become part of deployment process
- Need to monitor and tune thresholds over time

## Metrics to Track

- `health_check_failures_total` - Count of failed health checks
- `request_timeout_total` - Count of timed-out requests
- `memory_usage_percent` - Memory utilization over time
- `background_task_queue_size` - Number of pending tasks
- `circuit_breaker_trips_total` - Count of circuit breaker activations

## References

- [Fly.dev Health Checks](https://fly.io/docs/reference/configuration/#services-http_checks)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [12-Factor App: Disposability](https://12factor.net/disposability)
