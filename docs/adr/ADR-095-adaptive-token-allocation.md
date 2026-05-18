# ADR-095: Adaptive Token Allocation for Summarization

## Status
Accepted

## Context

The summarization engine used fixed `max_tokens` values based solely on summary length (brief/detailed/comprehensive). This caused two problems:

1. **Wasted retries**: Small inputs got excessive token allocations, while large inputs (multi-channel weekly summaries) started too low and required multiple truncation retries (4k → 8k → 16k), wasting API calls.

2. **Arbitrary limits**: The original values (1000/4000/8000) were set when LLM costs were higher and weren't based on empirical data.

### Observed Data

A 21,903 character input with `max_tokens=2000` was truncated at exactly 2000/2000 tokens, requiring a retry at 4000. This revealed the actual compression ratio was ~3:1, not the assumed 10:1.

```
Input: 21,903 chars → ~5,500 tokens
Output needed: 2,000+ tokens (truncated)
Actual ratio: 21,903 / (2,000 × 4) ≈ 2.7:1
```

## Decision

Scale `max_tokens` proportionally with input size using empirically-derived compression ratios.

### Algorithm

```python
def get_max_tokens_for_length(self, input_char_count: int = 0) -> int:
    # 1. Estimate input tokens (~4 chars per token)
    input_tokens = input_char_count / 4

    # 2. Apply compression ratio based on summary length
    estimated_output = input_tokens / compression_ratio

    # 3. Clamp to min/max bounds
    return clamp(estimated_output, min_tokens, max_tokens)
```

### Parameters

| Length | Compression Ratio | Min Tokens | Max Tokens |
|--------|-------------------|------------|------------|
| Brief | 8:1 | 1,500 | 4,000 |
| Detailed | 4:1 | 3,000 | 12,000 |
| Comprehensive | 2:1 | 6,000 | 20,000 |

### Examples

| Input Size | Length | Calculation | Result |
|------------|--------|-------------|--------|
| 20k chars | Detailed | 5k tokens / 4 = 1,250 → min 3,000 | 3,000 |
| 100k chars | Detailed | 25k tokens / 4 = 6,250 | 6,250 |
| 500k chars | Detailed | 125k tokens / 4 = 31,250 → max 12,000 | 12,000 |
| 20k chars | Brief | 5k tokens / 8 = 625 → min 1,500 | 1,500 |

### Fallback

When `input_char_count` is not provided (0), use conservative defaults:
- Brief: 2,000
- Detailed: 4,000
- Comprehensive: 8,000

## Implementation

### Files Modified

1. **`src/models/summary.py`**
   - `SummaryOptions.get_max_tokens_for_length(input_char_count: int = 0)`
   - Added compression ratios, min/max bounds, scaling logic

2. **`src/summarization/engine.py`**
   - Pass `len(prompt_data.user_prompt)` to `get_max_tokens_for_length()`
   - Log format: `max_tokens=X (input=Y chars)`

### Logging

The engine now logs input size for observability:
```
Summarization engine: summary_length=detailed, model=claude-sonnet-4.5, max_tokens=3000 (input=21903 chars)
```

## Consequences

### Positive

- **Fewer retries**: Appropriate initial allocation reduces truncation retries from ~2-3 per summary to near zero
- **Lower costs**: Avoid wasting API calls on retry cascade
- **Data-driven**: Parameters based on observed real-world compression ratios
- **Adaptive**: Small summaries don't over-allocate; large summaries get sufficient space

### Negative

- **Slightly higher base allocation**: Minimums increased (2k → 3k for detailed) means some small summaries use more tokens than strictly necessary
- **Complexity**: Token estimation adds logic vs. simple lookup table

### Trade-off Analysis

The cost of one truncation retry (wasted API call) far exceeds the cost of slightly over-allocating output tokens. A single retry at 4k tokens costs more than the marginal difference between allocating 2k vs 3k tokens upfront.

## Future Improvements

1. **Feedback loop**: Track actual token usage vs. estimates to refine compression ratios over time
2. **Content-aware scaling**: Factor in message density (images, code blocks) which compress differently
3. **Model-specific ratios**: Different models may have different output verbosity

## References

- Commit: `feat: Scale max_tokens proportionally with input size`
- Commit: `fix: Adjust token scaling based on real data`
