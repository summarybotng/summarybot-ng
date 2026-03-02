# ADR-025: Resilient Summary Generation with Multi-Model Retry

## Status
Proposed

## Context
Summary generation can fail in several ways:
- **Malformed responses**: Model outputs "[Unable to parse summary format...]"
- **JSON parsing errors**: Response doesn't match expected structure
- **Token truncation**: Response cut off at max_tokens
- **Model unavailability**: Requested model not available

Currently, failures result in degraded output shown to users. The summary `sum_57a526b3539d` (67 messages, 0 key points) exemplifies this - the model returned raw JSON instead of structured content, and the parser fell back to freeform extraction which failed.

### Existing Retry Mechanisms
The codebase has scattered retry logic:
- `ClaudeClient`: 3 retries for network/rate limit (exponential backoff)
- `ClaudeClient`: 6-model fallback chain on model unavailability
- `SummarizationEngine`: 1 retry with doubled max_tokens on truncation
- `SummarizationEngine`: 1 retry with JSON reminder on parse failure
- `ResponseParser`: JSON repair library, then freeform fallback

These mechanisms are independent and don't escalate to better models on quality failures.

## Decision
Implement a unified retry strategy with model escalation:

### 1. Up to 7 Total Attempts
Generation retries until success or 7 attempts exhausted.

### 2. Model Escalation Chain
Start with appropriate model for summary length, escalate on quality failures:

```
Tier 1 (brief):        anthropic/claude-3-haiku
                       anthropic/claude-3.5-haiku
Tier 2 (detailed):     anthropic/claude-3.5-sonnet
                       anthropic/claude-3.7-sonnet
Tier 3 (comprehensive): anthropic/claude-sonnet-4
Tier 4 (fallback):     anthropic/claude-sonnet-4.5
```

### 3. Retry Strategy by Failure Type

| Failure Type | First Action | Second Action |
|--------------|--------------|---------------|
| Token truncation | Double max_tokens (cap 16K) | Escalate model |
| JSON parse error | Add JSON reminder prompt | Escalate model |
| Malformed content | Escalate model immediately | - |
| Network/timeout | Retry same model (backoff) | - |
| Rate limit | Wait retry_after, same model | - |

### 4. Quality Detection
Detect failures requiring retry:
- `"[Unable to parse"` in summary_text
- `parsing_recovery.successful_step == "freeform_fallback"`
- `stop_reason == "max_tokens"`

### 5. Cost Protection
Cap total retry cost at $0.50 per generation (configurable).

### 6. Attempt Tracking in Metadata
Store all attempts in `SummaryResult.metadata["generation_attempts"]`:

```json
{
  "total_attempts": 3,
  "total_cost_usd": 0.0234,
  "total_tokens": 4521,
  "final_model": "anthropic/claude-3.5-sonnet",
  "attempts": [
    {
      "attempt": 1,
      "model": "anthropic/claude-3-haiku",
      "success": false,
      "retry_reason": "malformed",
      "retry_action": "escalate_model",
      "tokens": 1234,
      "cost_usd": 0.0012,
      "latency_ms": 2340
    },
    {
      "attempt": 2,
      "model": "anthropic/claude-3.5-sonnet",
      "success": true,
      "retry_reason": null,
      "retry_action": null,
      "tokens": 2000,
      "cost_usd": 0.0209,
      "latency_ms": 3120
    }
  ]
}
```

## Implementation

### New File: `src/summarization/retry_strategy.py`

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

class RetryReason(Enum):
    TRUNCATION = "truncation"
    JSON_PARSE_ERROR = "json_parse"
    MALFORMED_CONTENT = "malformed"
    RATE_LIMIT = "rate_limit"
    NETWORK_ERROR = "network"
    MODEL_UNAVAILABLE = "model_unavailable"
    TIMEOUT = "timeout"

class RetryAction(Enum):
    SAME_MODEL = "same_model"
    ESCALATE_MODEL = "escalate_model"
    INCREASE_TOKENS = "increase_tokens"
    ADD_PROMPT_HINT = "add_prompt_hint"

@dataclass
class GenerationAttempt:
    attempt_number: int
    model: str
    requested_model: str
    max_tokens: int
    success: bool
    retry_reason: Optional[RetryReason] = None
    retry_action: Optional[RetryAction] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    error_message: Optional[str] = None

@dataclass
class GenerationAttemptTracker:
    max_attempts: int = 7
    max_cost_usd: float = 0.50
    attempts: List[GenerationAttempt] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(a.cost_usd for a in self.attempts)

    @property
    def can_retry(self) -> bool:
        return (
            len(self.attempts) < self.max_attempts and
            self.total_cost < self.max_cost_usd
        )

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "total_attempts": len(self.attempts),
            "total_cost_usd": round(self.total_cost, 6),
            "total_tokens": sum(a.input_tokens + a.output_tokens for a in self.attempts),
            "final_model": self.attempts[-1].model if self.attempts else None,
            "attempts": [
                {
                    "attempt": a.attempt_number,
                    "model": a.model,
                    "success": a.success,
                    "retry_reason": a.retry_reason.value if a.retry_reason else None,
                    "retry_action": a.retry_action.value if a.retry_action else None,
                    "tokens": a.input_tokens + a.output_tokens,
                    "cost_usd": round(a.cost_usd, 6),
                    "latency_ms": a.latency_ms,
                }
                for a in self.attempts
            ]
        }
```

### Constants: `src/config/constants.py`

```python
MODEL_ESCALATION_CHAIN = [
    "anthropic/claude-3-haiku",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.7-sonnet",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-sonnet-4.5",
]

STARTING_MODEL_INDEX = {
    "brief": 0,
    "detailed": 2,
    "comprehensive": 4,
}
```

### Engine Integration: `src/summarization/engine.py`

Add `ResilientSummarizationEngine` class that wraps the existing engine with retry logic:

```python
class ResilientSummarizationEngine:
    async def generate_with_retry(
        self,
        messages: List[ProcessedMessage],
        options: SummaryOptions,
        context: SummarizationContext,
        ...
    ) -> Tuple[SummaryResult, GenerationAttemptTracker]:
        tracker = GenerationAttemptTracker()
        current_model = self._get_starting_model(options.summary_length)
        current_max_tokens = options.get_max_tokens_for_length()

        while tracker.can_retry:
            result = await self._single_attempt(...)

            quality_issue = self._detect_quality_issue(result)
            if not quality_issue:
                return result, tracker

            # Determine retry strategy
            action, current_model, current_max_tokens = \
                self._determine_retry_strategy(quality_issue, ...)

        raise SummarizationError("Max retries exceeded", ...)

    def _detect_quality_issue(self, result: SummaryResult) -> Optional[RetryReason]:
        if "[Unable to parse" in result.summary_text:
            return RetryReason.MALFORMED_CONTENT
        # ... other checks
```

## Consequences

### Positive
- **Higher success rate**: Quality failures trigger smarter models
- **Observability**: All attempts tracked in metadata
- **Cost protection**: Capped at $0.50 per generation
- **Graceful degradation**: Clear error instead of garbage output

### Negative
- **Increased latency**: Multiple attempts take longer
- **Increased cost**: Model escalation costs more (mitigated by cap)
- **Complexity**: More code paths to test

### Cost Implications

| Scenario | Cost Impact |
|----------|-------------|
| No retries (happy path) | Baseline |
| 1 retry (token increase) | +100% |
| Model escalation (haiku → sonnet) | +10x per attempt |
| Max 7 attempts hitting cap | $0.50 max |

## Test Cases

1. **Success on first attempt**: No retries, minimal cost
2. **Truncation recovery**: Double tokens, succeed
3. **Parse failure escalation**: haiku fails, sonnet succeeds
4. **Malformed content escalation**: Direct model upgrade
5. **Max retries exceeded**: Clear error after 7 attempts
6. **Cost cap respected**: Stop before exceeding $0.50
7. **Transient error recovery**: Network retry with backoff

## References
- ADR-022: Auto-retry truncated responses
- ADR-023: JSON parse error handling
- ADR-024: Service resilience
- Test case: `sum_57a526b3539d` (67 messages, malformed output)
