# Pseudocode: Global Rate Limiter

**SPARC Phase**: Pseudocode
**Module**: `v3/src/adapters/llm/rate_limiter.py`
**Implements**: LEG-001 (Global Rate Limit Coordination)

---

## 1. Token Bucket Algorithm

```pseudocode
CLASS TokenBucket:
    """
    Token bucket for rate limiting with priority queuing.
    Tokens replenish at a fixed rate up to max capacity.
    """

    PROPERTIES:
        capacity: Integer          # Max tokens (burst limit)
        refill_rate: Float         # Tokens per second
        tokens: Float              # Current available tokens
        last_refill: DateTime      # Last refill timestamp
        lock: AsyncLock            # Thread safety

    CONSTRUCTOR(requests_per_minute: Integer):
        capacity = requests_per_minute
        refill_rate = requests_per_minute / 60.0  # Per second
        tokens = capacity  # Start full
        last_refill = NOW()
        lock = AsyncLock()

    ASYNC FUNCTION acquire(cost: Integer = 1, timeout: Float = 30.0) -> Boolean:
        """Acquire tokens, blocking until available or timeout."""

        deadline = NOW() + timeout.seconds

        ASYNC WITH lock:
            WHILE TRUE:
                refill()

                IF tokens >= cost:
                    tokens -= cost
                    RETURN TRUE

                IF NOW() >= deadline:
                    RETURN FALSE

                # Calculate wait time for enough tokens
                tokens_needed = cost - tokens
                wait_seconds = tokens_needed / refill_rate
                wait_seconds = min(wait_seconds, (deadline - NOW()).seconds)

                AWAIT sleep(wait_seconds)

    FUNCTION refill():
        """Refill tokens based on elapsed time."""
        now = NOW()
        elapsed = (now - last_refill).total_seconds()
        tokens_to_add = elapsed * refill_rate
        tokens = min(capacity, tokens + tokens_to_add)
        last_refill = now

    FUNCTION available() -> Float:
        """Get current available tokens (read-only)."""
        refill()
        RETURN tokens
```

## 2. Circuit Breaker

```pseudocode
CLASS CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failure threshold exceeded, requests fail fast
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    ENUM State:
        CLOSED
        OPEN
        HALF_OPEN

    PROPERTIES:
        state: State = CLOSED
        failure_count: Integer = 0
        success_count: Integer = 0
        failure_threshold: Integer = 5      # Open after N failures
        success_threshold: Integer = 2      # Close after N successes in half-open
        open_timeout: Integer = 60          # Seconds before half-open
        last_failure_time: Optional<DateTime>
        lock: AsyncLock

    ASYNC FUNCTION allow_request() -> Boolean:
        """Check if request should be allowed."""

        ASYNC WITH lock:
            MATCH state:
                CLOSED:
                    RETURN TRUE

                OPEN:
                    IF NOW() >= (last_failure_time + open_timeout.seconds):
                        state = HALF_OPEN
                        success_count = 0
                        RETURN TRUE
                    RETURN FALSE

                HALF_OPEN:
                    # Allow limited requests to test recovery
                    RETURN TRUE

    ASYNC FUNCTION record_success():
        """Record successful request."""

        ASYNC WITH lock:
            failure_count = 0

            IF state == HALF_OPEN:
                success_count += 1
                IF success_count >= success_threshold:
                    state = CLOSED
                    LOG.info("Circuit breaker CLOSED - service recovered")

    ASYNC FUNCTION record_failure(retry_after: Optional<Integer> = NULL):
        """Record failed request."""

        ASYNC WITH lock:
            failure_count += 1
            last_failure_time = NOW()

            IF state == HALF_OPEN:
                # Immediately re-open on failure during testing
                state = OPEN
                open_timeout = retry_after OR open_timeout
                LOG.warning(f"Circuit breaker OPEN - half-open test failed")

            ELIF state == CLOSED AND failure_count >= failure_threshold:
                state = OPEN
                open_timeout = retry_after OR 60
                LOG.warning(f"Circuit breaker OPEN - threshold exceeded")

    FUNCTION is_open() -> Boolean:
        RETURN state == OPEN

    FUNCTION get_retry_after() -> Integer:
        IF state != OPEN:
            RETURN 0
        remaining = (last_failure_time + open_timeout.seconds) - NOW()
        RETURN max(0, remaining.seconds)
```

## 3. Global Rate Limiter (LEG-001)

```pseudocode
CLASS GlobalRateLimiter:
    """
    Process-wide rate limiter for LLM API requests.
    Implements LEG-001: Global Rate Limit Coordination.

    Features:
    - Token bucket for request rate limiting
    - Circuit breaker for failure protection
    - Priority queuing (manual > scheduled)
    - Provider-specific limits
    """

    PROPERTIES:
        buckets: Dict<String, TokenBucket>      # Per-provider buckets
        circuit: CircuitBreaker
        priority_queue: PriorityQueue<PendingRequest>
        metrics: RateLimitMetrics
        config: RateLimitConfig

    CONSTRUCTOR(config: RateLimitConfig):
        self.config = config
        self.circuit = CircuitBreaker(
            failure_threshold=config.circuit_failure_threshold,
            open_timeout=config.circuit_open_timeout
        )
        self.buckets = {}
        self.priority_queue = PriorityQueue()
        self.metrics = RateLimitMetrics()

        # Initialize per-provider buckets
        FOR provider, limits IN config.provider_limits:
            buckets[provider] = TokenBucket(limits.requests_per_minute)

    ASYNC FUNCTION acquire(
        provider: String = "default",
        priority: Priority = Priority.NORMAL,
        timeout: Float = 30.0
    ) -> Result<Unit, RateLimitError>:
        """
        Acquire permission to make an LLM request.

        Args:
            provider: LLM provider (openrouter, anthropic, etc.)
            priority: Request priority (MANUAL > NORMAL > LOW)
            timeout: Max wait time in seconds

        Returns:
            Ok if acquired, Error with retry_after if rate limited
        """

        # Step 1: Check circuit breaker
        IF circuit.is_open():
            metrics.record_circuit_rejection()
            RETURN Error(RateLimitError(
                reason="circuit_open",
                retry_after=circuit.get_retry_after()
            ))

        # Step 2: Get or create provider bucket
        IF provider NOT IN buckets:
            buckets[provider] = TokenBucket(config.default_requests_per_minute)

        bucket = buckets[provider]

        # Step 3: Try to acquire with priority
        IF priority == Priority.MANUAL:
            # Manual requests get immediate attempt
            acquired = AWAIT bucket.acquire(cost=1, timeout=timeout)
        ELSE:
            # Lower priority waits for manual requests
            AWAIT yield_to_higher_priority(priority)
            acquired = AWAIT bucket.acquire(cost=1, timeout=timeout)

        IF NOT acquired:
            metrics.record_timeout()
            RETURN Error(RateLimitError(
                reason="bucket_exhausted",
                retry_after=calculate_retry_after(bucket)
            ))

        metrics.record_acquired(provider, priority)
        RETURN Ok()

    ASYNC FUNCTION record_success(provider: String):
        """Record successful API call."""
        AWAIT circuit.record_success()
        metrics.record_success(provider)

    ASYNC FUNCTION record_rate_limit(provider: String, retry_after: Integer):
        """Record rate limit response from API."""
        AWAIT circuit.record_failure(retry_after)
        metrics.record_rate_limit(provider, retry_after)

        # Adaptive: reduce bucket capacity temporarily
        IF provider IN buckets:
            buckets[provider].reduce_capacity_temporarily(
                factor=0.5,
                duration=retry_after
            )

    FUNCTION get_status() -> RateLimitStatus:
        """Get current rate limit status for monitoring."""
        RETURN RateLimitStatus(
            circuit_state=circuit.state,
            circuit_retry_after=circuit.get_retry_after(),
            buckets={
                provider: BucketStatus(
                    available=bucket.available(),
                    capacity=bucket.capacity
                )
                FOR provider, bucket IN buckets
            },
            metrics=metrics.get_snapshot()
        )
```

## 4. Configuration

```pseudocode
DATACLASS RateLimitConfig:
    # Per-provider limits
    provider_limits: Dict<String, ProviderLimit> = {
        "openrouter": ProviderLimit(requests_per_minute=50),
        "anthropic": ProviderLimit(requests_per_minute=40),
        "default": ProviderLimit(requests_per_minute=30)
    }

    # Circuit breaker
    circuit_failure_threshold: Integer = 5
    circuit_open_timeout: Integer = 60

    # Priority weights
    priority_weights: Dict<Priority, Integer> = {
        Priority.MANUAL: 100,   # Immediate
        Priority.NORMAL: 50,    # Standard
        Priority.LOW: 10        # Background jobs
    }

    # From environment
    @classmethod
    FUNCTION from_env() -> RateLimitConfig:
        RETURN RateLimitConfig(
            provider_limits={
                "openrouter": ProviderLimit(
                    requests_per_minute=env_int("OPENROUTER_RPM", 50)
                ),
                "anthropic": ProviderLimit(
                    requests_per_minute=env_int("ANTHROPIC_RPM", 40)
                )
            },
            circuit_failure_threshold=env_int("CIRCUIT_FAILURE_THRESHOLD", 5),
            circuit_open_timeout=env_int("CIRCUIT_OPEN_TIMEOUT", 60)
        )
```

## 5. Metrics

```pseudocode
CLASS RateLimitMetrics:
    """Metrics for rate limit monitoring and alerting."""

    PROPERTIES:
        requests_acquired: Counter
        requests_rejected: Counter
        circuit_rejections: Counter
        rate_limit_hits: Counter
        wait_time_histogram: Histogram

    FUNCTION record_acquired(provider: String, priority: Priority):
        requests_acquired.inc(labels={provider, priority.name})

    FUNCTION record_circuit_rejection():
        circuit_rejections.inc()
        requests_rejected.inc(labels={reason="circuit_open"})

    FUNCTION record_rate_limit(provider: String, retry_after: Integer):
        rate_limit_hits.inc(labels={provider})
        # Expose to dashboard
        EMIT_METRIC("llm_rate_limit", {
            provider: provider,
            retry_after: retry_after,
            timestamp: NOW()
        })

    FUNCTION get_snapshot() -> MetricsSnapshot:
        RETURN MetricsSnapshot(
            total_acquired=requests_acquired.value(),
            total_rejected=requests_rejected.value(),
            circuit_rejections=circuit_rejections.value(),
            rate_limit_hits=rate_limit_hits.value(),
            avg_wait_time=wait_time_histogram.avg()
        )
```

## 6. Integration with SummaryService

```pseudocode
# In v3/src/services/summary_service.py

CLASS SummaryService:
    CONSTRUCTOR(
        ...,
        rate_limiter: GlobalRateLimiter  # Injected singleton
    ):
        self.rate_limiter = rate_limiter

    ASYNC FUNCTION generate(request: GenerateRequest) -> Result<Summary, Error>:
        # Determine priority
        priority = MATCH request.trigger_type:
            TriggerType.MANUAL => Priority.MANUAL
            TriggerType.API => Priority.NORMAL
            TriggerType.SCHEDULED => Priority.LOW

        # Acquire rate limit permission
        acquire_result = AWAIT rate_limiter.acquire(
            provider=get_provider(request.model),
            priority=priority,
            timeout=30.0
        )

        IF acquire_result.is_error:
            RETURN Error(RateLimitedError(
                retry_after=acquire_result.error.retry_after,
                reason=acquire_result.error.reason
            ))

        # Make LLM call
        TRY:
            result = AWAIT llm_generator.generate(...)
            AWAIT rate_limiter.record_success(provider)
            RETURN Ok(result)
        CATCH RateLimitError as e:
            AWAIT rate_limiter.record_rate_limit(provider, e.retry_after)
            RETURN Error(e)
```

---

*Next: `04-schedule-executor.md`*
