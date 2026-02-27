# ADR-022: Auto-Retry Truncated LLM Responses

## Status
Accepted

## Date
2026-02-27

## Context

When generating summaries, Claude API responses can be truncated if the output exceeds the `max_tokens` limit. This results in incomplete JSON that fails to parse, causing "[Unable to parse summary format]" errors displayed to users.

### Token Limits by Summary Length

| Summary Length | Initial max_tokens | Model |
|---------------|-------------------|-------|
| BRIEF | 1,000 | claude-3-haiku |
| DETAILED | 4,000 | claude-3.5-sonnet |
| COMPREHENSIVE | 8,000 | claude-3.5-sonnet |

### Problem

1. Complex conversations with many participants/topics can exceed token limits
2. Truncated JSON responses fail to parse
3. Users see unhelpful error messages instead of summaries
4. No automatic recovery mechanism existed

### Detection

Claude API returns `stop_reason` in responses:
- `"end_turn"` - Response completed naturally
- `"max_tokens"` - Response was truncated (hit limit)

The `ClaudeResponse.is_complete()` method returns `False` when `stop_reason == "max_tokens"`.

## Decision

Implement automatic retry with escalated `max_tokens` when truncation is detected.

### Escalation Strategy

```
Initial max_tokens → Retry max_tokens (2x, capped at 16,000)

BRIEF:         1,000 → 2,000
DETAILED:      4,000 → 8,000
COMPREHENSIVE: 8,000 → 16,000
```

### Algorithm

```python
MAX_RETRY_TOKENS = 16000

# After initial API call
if not response.is_complete() and current_max_tokens < MAX_RETRY_TOKENS:
    retry_max_tokens = min(current_max_tokens * 2, MAX_RETRY_TOKENS)

    # Retry with higher limit
    response = await claude_client.create_summary_with_fallback(
        prompt=prompt,
        system_prompt=system_prompt,
        options=ClaudeOptions(max_tokens=retry_max_tokens, ...)
    )

    # If still truncated after retry, warn but continue
    if not response.is_complete():
        logger.warning("Response still truncated after retry")
```

### Behavior

1. **Detection**: Check `response.is_complete()` after API call
2. **Escalation**: If truncated AND below cap, retry with 2x tokens
3. **Single Retry**: Only one retry attempt to avoid excessive API costs
4. **Graceful Degradation**: If still truncated after retry, continue with partial response
5. **Logging**: Log all truncation events for monitoring

## Consequences

### Positive

- Reduces "[Unable to parse summary format]" errors significantly
- Automatic recovery without user intervention
- Transparent to users (they just get working summaries)
- Logged for monitoring and debugging

### Negative

- Additional API cost when retry occurs (~2x tokens for that request)
- Additional latency (~3-5 seconds) when retry is triggered
- Still possible to fail if content truly exceeds 16,000 tokens

### Neutral

- Only triggers when needed (no overhead for normal responses)
- Cap at 16,000 prevents runaway costs

## Implementation

### Files Changed

- `src/summarization/engine.py` - Added retry logic in `summarize_messages()`
- `src/summarization/claude_client.py` - `ClaudeResponse.is_complete()` method

### Monitoring

Log messages to watch for:
```
WARNING - Response truncated (stop_reason=max_tokens, used X/Y tokens). Auto-retrying with max_tokens=Z...
INFO - Retry response: input_tokens=X, output_tokens=Y, stop_reason=end_turn
WARNING - Response still truncated after retry with Z tokens.
```

## Alternatives Considered

### 1. Increase Default Limits
- **Rejected**: Higher baseline costs for all summaries, even simple ones

### 2. Multiple Retries
- **Rejected**: Diminishing returns, exponential cost increase

### 3. Truncate Input Instead
- **Rejected**: Loses important context, may miss key information

### 4. Return Partial Response
- **Current Fallback**: If retry still truncates, we parse what we can

## Future Improvements

1. **Adaptive Limits**: Learn from historical token usage per guild/channel
2. **Pre-flight Estimation**: Estimate output tokens before API call
3. **Streaming**: Use streaming responses to detect truncation earlier
4. **Cost Tracking**: Track retry costs separately for billing visibility
