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

*Last updated: 2026-06-05*
