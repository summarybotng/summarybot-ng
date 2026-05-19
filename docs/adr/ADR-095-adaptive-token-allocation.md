# ADR-095: Adaptive Token Allocation for Summarization

## Status
Accepted

## Context

The summarization engine used fixed `max_tokens` values based solely on summary length (brief/detailed/comprehensive). This caused two problems:

1. **Wasted retries**: Small inputs got excessive token allocations, while large inputs (multi-channel weekly summaries) started too low and required multiple truncation retries (4k → 8k → 16k), wasting API calls.

2. **Arbitrary limits**: The original values (1000/4000/8000) were set when LLM costs were higher and weren't based on empirical data.

### Observed Data

**Initial observation** (v1): A 21,903 character input with `max_tokens=2000` was truncated at exactly 2000/2000 tokens, requiring a retry at 4000. This revealed the actual compression ratio was ~3:1, not the assumed 10:1.

**Production data** (v2): A 30,107 character weekly guild summary with `max_tokens=3000` was truncated, then again at 6000, finally succeeding at 12000. This revealed weekly multi-channel summaries have nearly 1:1 compression due to per-channel breakdowns.

```
Input: 30,107 chars → ~7,500 tokens
Output needed: 8,000+ tokens (truncated at 3k and 6k)
Actual ratio: 7,500 / 8,000 ≈ 0.94:1 (nearly 1:1!)
```

Weekly summaries spanning many channels produce verbose output with channel-by-channel analysis, requiring much more output tokens than single-channel summaries.

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

### Parameters (v3 - Updated 2026-05-18)

| Length | Compression Ratio | Min Tokens | Max Tokens |
|--------|-------------------|------------|------------|
| Brief | 4:1 | 2,000 | 6,000 |
| Detailed | **1:1** | 4,000 | 16,000 |
| Comprehensive | 1:1 | 8,000 | 24,000 |

**Note**: Detailed uses 1:1 ratio because weekly guild-wide summaries produce verbose per-channel breakdowns that don't compress at all. Real data: 33k chars (8.3k tokens) was truncated at 6.9k output tokens.

### Examples

| Input Size | Length | Calculation | Result |
|------------|--------|-------------|--------|
| 33k chars | Detailed | 8.3k tokens / 1 = 8,300 | 8,300 |
| 100k chars | Detailed | 25k tokens / 1 = 25,000 → max 16,000 | 16,000 |
| 20k chars | Brief | 5k tokens / 4 = 1,250 → min 2,000 | 2,000 |
| 50k chars | Comprehensive | 12.5k tokens / 1 = 12,500 | 12,500 |

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
- Commit: `fix: Further reduce compression ratios based on production data (v2)`
