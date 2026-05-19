# ADR-096: Adaptive Summary Granularity

## Status
Proposed

## Context

Weekly summaries need to balance comprehensiveness against practical limits:
- **Token limits**: LLMs have context windows; verbose summaries truncate
- **Compression ratios**: Guild-wide weeklies show ~1:1 compression (input ≈ output)
- **API costs**: Truncation retries waste money
- **Continuity**: Weekly summaries feed into the next week's context

### Observed Problem

A guild with 47 channels and 185 messages/week produced a 33k char input that needed 8k+ output tokens. This is because the LLM creates per-channel breakdowns within a single summary, essentially doing per-channel work anyway.

### Granularity Options

| Level | Scope | When Appropriate |
|-------|-------|------------------|
| **Server-wide** | All channels → 1 summary | Low activity (<100 msgs/week) |
| **Per-category** | Each Discord category → 1 summary | Medium activity (100-500 msgs/week) |
| **Per-channel** | Each channel → 1 summary | High activity (>500 msgs/week) |
| **Adaptive** | System chooses based on activity | Variable activity |

### Trade-offs

**Server-wide (current)**
```
+ Single unified view of guild activity
+ Simple to implement
- Poor compression (1:1) because LLM itemizes per-channel
- Large summaries truncate
- Expensive API calls with retries
```

**Per-channel**
```
+ Better compression (channel context is focused)
+ Natural unit for continuity (channel history)
+ Smaller, faster API calls
- Many summaries for large guilds (47 channels = 47 summaries)
- Some channels may be empty/low-activity
```

**Per-category**
```
+ Logical grouping (e.g., "Development", "General", "Off-topic")
+ Fewer summaries than per-channel
+ Respects Discord's organization structure
- Categories can still be very active
- Not all servers use categories meaningfully
```

**Adaptive (proposed)**
```
+ Right-sizes based on actual activity
+ Efficient resource usage
- More complex logic
- Activity patterns change over time
```

## Decision

Implement **adaptive granularity** with these thresholds:

### Algorithm

```python
def choose_granularity(guild_id: str, period: DateRange) -> Granularity:
    """Choose summary granularity based on message activity."""

    # Get message counts per channel for the period
    channel_counts = get_message_counts_by_channel(guild_id, period)
    total_messages = sum(channel_counts.values())
    active_channels = len([c for c in channel_counts.values() if c > 0])

    # Estimate output tokens (chars ≈ messages × 150 avg, tokens ≈ chars/4)
    estimated_tokens = total_messages * 150 / 4

    if estimated_tokens < 2000:
        # Small enough for single summary
        return Granularity.SERVER_WIDE

    if estimated_tokens < 8000 and active_channels <= 10:
        # Moderate activity, few channels
        return Granularity.SERVER_WIDE

    # Check category activity
    category_counts = aggregate_by_category(channel_counts)
    max_category_tokens = max(category_counts.values()) * 150 / 4

    if max_category_tokens < 4000:
        # Each category is manageable
        return Granularity.PER_CATEGORY

    # Fall back to per-channel
    return Granularity.PER_CHANNEL
```

### Thresholds (Configurable)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `server_wide_max_tokens` | 4,000 | Max estimated tokens for server-wide |
| `category_max_tokens` | 4,000 | Max estimated tokens per category |
| `min_channel_messages` | 5 | Skip channels with fewer messages |

### Continuity Implications

Granularity affects continuity chains:

```
Week 1: Server-wide (low activity) → stores as server_summary_w1
Week 2: Server-wide (low activity) → context from server_summary_w1
Week 3: Per-category (activity increased) → NEW chains per category
Week 4: Per-category → context from category_summary_w3
```

**Key insight**: When granularity changes, start fresh continuity chains at the new level. Don't try to merge/split previous summaries.

### Empty Channel Handling

Skip channels with zero messages rather than creating empty summaries:

```python
for channel in channels:
    messages = fetch_messages(channel, period)
    if len(messages) < min_channel_messages:
        continue  # Skip low-activity channels
    generate_summary(channel, messages)
```

## Implementation

### Phase 1: Per-Channel Weekly (MVP)

1. Add `granularity_mode` to scheduled tasks: `"server"`, `"category"`, `"channel"`, `"adaptive"`
2. For retrospective jobs, default to `"channel"` for weeklies
3. Skip empty channels automatically
4. Store channel_id in summary metadata for continuity lookup

### Phase 2: Category Support

1. Fetch Discord category structure via API
2. Group channels by category
3. Generate one summary per category
4. Handle uncategorized channels

### Phase 3: Adaptive Selection

1. Pre-scan message counts before summarization
2. Apply thresholds to choose granularity
3. Log chosen granularity for debugging
4. Allow override via job config

### Database Schema

```sql
-- Track granularity choice for continuity
ALTER TABLE stored_summaries ADD COLUMN granularity_level TEXT;
-- "server", "category", "channel"

ALTER TABLE stored_summaries ADD COLUMN category_id TEXT;
-- For category-level summaries
```

## Consequences

### Positive

- **Efficient API usage**: Right-sized summaries avoid truncation
- **Better compression**: Focused context compresses better
- **Scalable**: Works for both small and large guilds
- **Continuity-aware**: Tracks context chains at appropriate level

### Negative

- **Complexity**: More logic than simple server-wide
- **Variable output**: Users see different summary counts based on activity
- **Migration**: Existing server-wide summaries won't chain to new per-channel ones

### Cost Analysis

| Scenario | Server-wide | Per-channel |
|----------|-------------|-------------|
| 47 channels, 185 msgs | 1 × ~$0.08 (with retries) | 10 × ~$0.01 = $0.10 |
| 47 channels, 500 msgs | 1 × ~$0.15 (multiple retries) | 20 × ~$0.01 = $0.20 |

Per-channel is slightly more expensive but more reliable (no truncation retries).

## Alternatives Considered

### Fixed Per-Channel Always
- Simple but creates many empty/tiny summaries
- Rejected: wasteful for low-activity channels

### User-Configurable Only
- Let users choose granularity
- Rejected: most users won't know optimal settings

### Time-Based Adaptive (Shorter Periods)
- High activity → daily summaries instead of weekly
- Rejected: changes temporal granularity, not spatial; may implement separately

## References

- ADR-087: Wiki Ingestion Granularity (continuity model)
- ADR-095: Adaptive Token Allocation (compression ratio data)
