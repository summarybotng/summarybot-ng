# ADR-024: Resilient Summary Generation with Multi-Model Retry

## Status
Accepted

## Context
Summary generation can fail due to various issues:
- **Malformed responses**: LLM returns "[Unable to parse...]" or freeform fallback text
- **JSON parsing errors**: Invalid JSON structure that json_repair cannot fix
- **Token truncation**: Response exceeds max_tokens and is cut off
- **Model unavailability**: Requested model not available on OpenRouter

Currently, failures result in degraded output (freeform fallback summaries). Users have requested up to 7 retry attempts with model escalation and attempt tracking in metadata for observability.

## Decision
Implement a `ResilientSummarizationEngine` wrapper that provides:

### 1. Up to 7 Total Attempts
Hard limit prevents infinite retry loops. Configurable per-request.

### 2. Model Escalation Chain
When quality issues occur, escalate to more capable models:

```
anthropic/claude-3-haiku        # Tier 1: Fast/cheap (brief summaries)
anthropic/claude-3.5-haiku
anthropic/claude-3.5-sonnet     # Tier 2: Balanced (detailed summaries)
anthropic/claude-3.7-sonnet
anthropic/claude-sonnet-4       # Tier 3: Advanced (comprehensive)
anthropic/claude-sonnet-4.5     # Tier 4: Best available (final fallback)
```

Starting model depends on summary type:
- `brief`: Start at index 0 (haiku)
- `detailed`: Start at index 2 (sonnet)
- `comprehensive`: Start at index 4 (sonnet-4)

### 3. Retry Strategies by Failure Type

| Failure | First Action | Second Action |
|---------|--------------|---------------|
| Token truncation | Double max_tokens (cap 16K) | Escalate model |
| JSON parse error | Add JSON reminder prompt | Escalate model |
| Malformed content | Escalate model immediately | Continue chain |
| Network/timeout | Retry same model (backoff) | - |
| Rate limit | Wait retry_after, same model | - |
| Model unavailable | Escalate model immediately | - |

### 4. Attempt Tracking in Metadata
Every generation stores attempt history:

```json
{
  "generation_attempts": {
    "total_attempts": 3,
    "total_cost_usd": 0.0234,
    "total_tokens": 4521,
    "total_latency_ms": 8450,
    "final_model": "anthropic/claude-3.5-sonnet",
    "attempts": [
      {
        "attempt": 1,
        "model": "anthropic/claude-3-haiku",
        "success": false,
        "retry_reason": "malformed_content",
        "retry_action": "escalate_model",
        "tokens": 1234,
        "cost_usd": 0.0012,
        "latency_ms": 2340
      }
    ]
  }
}
```

### 5. Cost Cap
Default $0.50 maximum cost per generation. Prevents runaway costs from retry loops.

## Implementation

### New File: `src/summarization/retry_strategy.py`
- `RetryReason` enum: TRUNCATION, JSON_PARSE_ERROR, MALFORMED_CONTENT, etc.
- `RetryAction` enum: SAME_MODEL, ESCALATE_MODEL, INCREASE_TOKENS, ADD_PROMPT_HINT
- `GenerationAttempt` dataclass: Records single attempt details
- `GenerationAttemptTracker`: Manages attempts, enforces limits
- `determine_retry_strategy()`: Logic for choosing retry action
- `is_malformed_content()`: Detects fallback markers in output
- `detect_quality_issue()`: Comprehensive quality check

### Modified: `src/config/constants.py`
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

### Modified: `src/summarization/engine.py`
Integration in `summarize_messages()`:
1. Create `GenerationAttemptTracker`
2. Loop: generate → check quality → retry if needed
3. Store `tracker.to_metadata()` in result

### Modified: `src/summarization/response_parser.py`
Added helper: `is_malformed_content()` for detecting fallback markers.

## Consequences

### Positive
- **Higher success rate**: Multiple attempts with better models catch edge cases
- **Observability**: Full attempt history for debugging and optimization
- **Cost control**: Hard cap prevents runaway spending
- **Flexibility**: Per-request configuration of limits

### Negative
- **Increased latency**: Retries add time (mitigated by parallel processing)
- **Higher cost**: Multiple attempts cost more (mitigated by cost cap)
- **Complexity**: More code paths to test and maintain

### Neutral
- Existing single-attempt behavior preserved when no retries needed
- Backward compatible metadata structure

## Verification

1. **Unit tests**: `tests/unit/test_summarization/test_retry_strategy.py`
2. **Integration test**: Regenerate known-bad summary (sum_57a526b3539d)
3. **Metrics**: Monitor `generation_attempts.total_attempts` distribution

## Related
- ADR-023: JSON Parse Error Recovery (predecessor)
- ADR-014: Reference Jump Links (affected by retry)
