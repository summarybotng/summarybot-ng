# V1 Legacy Requirements for V3

**Purpose**: This document captures incremental requirements discovered during V1 maintenance mode. V3 should implement these in its clean architecture.

**Namespace**: Requirements here use `LEG-XXX` prefix to distinguish from V3's ADR-119+ decisions.

---

## LEG-001: Global Rate Limit Coordination

**Status**: Required
**Discovered**: 2026-06-05
**Context**: Job `job_8db618fb` failed, suspected rate limiting from OpenRouter/Anthropic

### Problem

V1 creates a separate `ClaudeClient` instance per job. Each client has independent throttling (100ms interval, 3 retries). When multiple jobs run concurrently, they compete for API quota without awareness of each other.

### Current V1 Behavior

```python
# src/summarization/claude_client.py
self._min_request_interval = 0.1  # Per-instance, not global
self.max_retries = 3  # Job fails after 3 rate limit hits
```

### V3 Requirements

1. **Global token bucket**: Implement a process-wide rate limiter shared across all LLM requests
2. **Adaptive backoff**: Track rate limit responses and reduce request rate proactively
3. **Circuit breaker**: After N consecutive rate limits, pause all requests for M seconds
4. **Job queue with priority**: Scheduled jobs should yield to manual requests during rate limiting
5. **Rate limit telemetry**: Log rate limit events for monitoring dashboards

### Suggested V3 Implementation

```python
# v3/src/adapters/llm/rate_limiter.py
class GlobalRateLimiter:
    """Process-wide rate limiting for LLM APIs."""

    def __init__(self, requests_per_minute: int = 50):
        self._bucket = TokenBucket(requests_per_minute)
        self._circuit_open = False
        self._consecutive_failures = 0

    async def acquire(self, priority: int = 0) -> bool:
        """Acquire permission to make a request."""
        if self._circuit_open:
            raise CircuitOpenError(retry_after=self._circuit_retry_at)
        return await self._bucket.acquire(priority)

    def record_rate_limit(self, retry_after: int):
        """Record a rate limit response."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= 5:
            self._open_circuit(retry_after * 2)
```

### Acceptance Criteria

- [ ] Single LLM request queue per process
- [ ] Requests/minute configurable via environment
- [ ] Circuit breaker opens after 5 consecutive 429s
- [ ] Jobs surface "rate limited" status (not generic failure)
- [ ] Dashboard shows rate limit state

---

## LEG-002: Job Failure Classification

**Status**: Required
**Discovered**: 2026-06-05
**Context**: Job failures show generic "failed" without distinguishing transient vs permanent errors

### V3 Requirements

1. **Error taxonomy**: Classify failures as `rate_limited`, `quota_exceeded`, `invalid_request`, `service_unavailable`, `unknown`
2. **Retryable flag**: Jobs marked `rate_limited` or `service_unavailable` should be auto-retryable
3. **Failure reason in API**: Return `failure_reason` field in job status responses
4. **Automatic retry queue**: Rate-limited jobs re-enter queue with exponential delay

---

## LEG-003: OpenRouter-Specific Handling

**Status**: Required
**Discovered**: 2026-06-05
**Context**: OpenRouter has different rate limit headers and behavior than direct Anthropic API

### V3 Requirements

1. **Provider abstraction**: `LLMProvider` interface with provider-specific rate limit parsing
2. **OpenRouter headers**: Parse `x-ratelimit-remaining`, `x-ratelimit-reset` headers
3. **Credit awareness**: Check OpenRouter credit balance before starting large jobs
4. **Model availability**: Verify model exists before job start (avoid 404 mid-job)

---

## LEG-004: Dynamic Model Validation

**Status**: Required
**Discovered**: 2026-06-09
**Context**: Jobs failed with "All 7 generation attempts failed" because `anthropic/claude-3.5-sonnet` was removed from OpenRouter without notice

### Problem

V1 hardcodes model names in configuration:
- `fly.toml`: `OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"`
- `constants.py`: `VALID_MODELS` list with static model IDs
- `claude_client.py`: `MODEL_ALIASES` mapping to potentially deprecated models

When OpenRouter removes or renames a model, all requests fail with 404 until code is manually updated and redeployed.

### V1 Incident Timeline

```
1. OpenRouter removes anthropic/claude-3.5-sonnet
2. All summarization requests fail (model not found)
3. Engine retries 7 times across fallback chain
4. All fallbacks also reference deprecated model in aliases
5. Job marked "failed" with no specific error in logs
6. Manual investigation required to discover root cause
```

### V3 Requirements

1. **Startup model validation**: On boot, query `/api/v1/models` and validate configured model exists
2. **Fallback chain validation**: Verify all fallback models exist before accepting jobs
3. **Dynamic model discovery**: Cache available models, refresh periodically (hourly)
4. **Graceful degradation**: If primary model unavailable, auto-select best available alternative
5. **Health check endpoint**: `/health` should fail if no valid LLM model available
6. **Alerting**: Log ERROR when configured model not found (not just retry silently)

### Suggested V3 Implementation

```python
# v3/src/adapters/llm/model_registry.py
class ModelRegistry:
    """Dynamic model discovery and validation."""

    def __init__(self, provider: LLMProvider):
        self._provider = provider
        self._available_models: Set[str] = set()
        self._last_refresh: datetime = None
        self._refresh_interval = timedelta(hours=1)

    async def refresh(self) -> None:
        """Refresh available models from provider."""
        models = await self._provider.list_models()
        self._available_models = {m.id for m in models}
        self._last_refresh = datetime.utcnow()
        logger.info(f"Refreshed model registry: {len(self._available_models)} models available")

    async def validate_model(self, model_id: str) -> bool:
        """Check if model is available."""
        if self._needs_refresh():
            await self.refresh()
        return model_id in self._available_models

    async def get_best_available(self, preferences: List[str]) -> Optional[str]:
        """Get first available model from preference list."""
        if self._needs_refresh():
            await self.refresh()
        for model in preferences:
            if model in self._available_models:
                return model
        return None

# On startup
@app.on_event("startup")
async def validate_llm_config():
    registry = get_model_registry()
    await registry.refresh()

    configured_model = settings.OPENROUTER_MODEL
    if not await registry.validate_model(configured_model):
        available = await registry.get_best_available(MODEL_PREFERENCES)
        if available:
            logger.warning(f"Configured model {configured_model} unavailable, using {available}")
            settings.OPENROUTER_MODEL = available
        else:
            logger.error("No valid LLM models available - summarization will fail")
            raise RuntimeError("No valid LLM models")
```

### Acceptance Criteria

- [ ] Startup validates configured model exists
- [ ] Invalid model logged as ERROR (not silent retry)
- [ ] Auto-fallback to available model with warning
- [ ] Health check fails if no models available
- [ ] Model list refreshed periodically (configurable interval)

---

## LEG-005: Generation Error Logging

**Status**: Required
**Discovered**: 2026-06-09
**Context**: Job failures don't appear in error log, making debugging difficult

### Problem

When summarization fails:
1. `SummarizationError` is raised in `engine.py`
2. Error is caught somewhere in the call stack
3. Job is marked "failed" in database
4. **Error is NOT logged to error_logs table**
5. Dashboard shows "Summarization failed" but no details
6. Fly.io logs show normal HTTP traffic, no error context

### V1 Code Gap

```python
# src/summarization/engine.py:319
raise SummarizationError(
    message=f"All {tracker.attempt_count} generation attempts failed",
    error_code="RESILIENT_GENERATION_EXHAUSTED",
    context={...},
    retryable=False,
)

# This exception is caught but not logged to error tracker
```

### V3 Requirements

1. **Structured error logging**: All generation failures logged with:
   - Job ID
   - Model attempted
   - Error code
   - Retry count
   - Last error message
   - Full attempt tracker
2. **Error tracker integration**: Use `ErrorTracker.log_error()` for all failures
3. **Correlation IDs**: Link error log entry to job ID
4. **Attempt history**: Store individual attempt failures (not just final failure)
5. **Dashboard visibility**: Errors appear in dashboard error list with filtering

### Suggested V3 Implementation

```python
# v3/src/services/summary_service.py
async def generate(self, request: GenerateRequest) -> Result[Summary, GenerationError]:
    try:
        result = await self._generator.generate(...)
        return Ok(result)
    except SummarizationError as e:
        # Log to error tracker
        await self._error_tracker.log_error(
            error_type=ErrorType.SUMMARIZATION,
            severity=ErrorSeverity.ERROR,
            message=e.message,
            context={
                "job_id": request.job_id,
                "error_code": e.error_code,
                "attempts": e.context.get("attempts"),
                "last_error": e.context.get("last_error"),
                "models_tried": e.context.get("models_tried", []),
            },
            workspace_id=request.workspace_id,
        )
        return Err(GenerationError.from_exception(e))
```

### Acceptance Criteria

- [ ] All generation failures appear in error_logs table
- [ ] Error includes job_id, model, attempt count
- [ ] Dashboard filters can show summarization errors
- [ ] Individual retry attempts logged (not just final failure)
- [ ] Error severity distinguishes transient vs permanent

---

## How V3 Should Use This Document

1. **During planning**: Reference `LEG-XXX` requirements when designing the `adapters/llm/` module
2. **Traceability**: Link V3 code to `LEG-XXX` in comments/commits
3. **Completion**: Mark requirements with implementation status as V3 progresses

Example V3 commit:
```
feat(llm): Add global rate limiter (LEG-001)

Implements process-wide token bucket with circuit breaker.
```

---

*Last updated: 2026-06-09*
