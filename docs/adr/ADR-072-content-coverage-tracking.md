# ADR-072: Content Coverage Tracking and Scheduled Backfill

## Status
Proposed

## Context

When a guild connects to SummaryBot, there's typically years of historical content in Discord/Slack that predates the connection. Users need to understand:

1. **How much content exists** - Total message volume, date range, channels
2. **How much is covered by summaries** - What percentage has been summarized
3. **What gaps exist** - Periods with no summary coverage
4. **Progress toward full coverage** - As backfill runs, show completion %

Currently there's no visibility into this. Users can't answer:
- "Have we summarized all of 2024?"
- "Which channels have no historical summaries?"
- "How long until backfill is complete?"

## Decision

Implement **Content Coverage Tracking** with:
1. Platform content inventory
2. Coverage gap detection
3. Scheduled backfill with progress tracking

### 1. Content Inventory

Query the source platform to understand what content exists:

```python
@dataclass
class ChannelInventory:
    channel_id: str
    channel_name: str
    earliest_message: datetime
    latest_message: datetime
    estimated_message_count: int
    accessible: bool  # Bot has permission

@dataclass
class GuildInventory:
    guild_id: str
    platform: str  # discord, slack
    channels: List[ChannelInventory]
    total_channels: int
    accessible_channels: int
    earliest_content: datetime
    latest_content: datetime
    estimated_total_messages: int
    inventory_date: datetime  # When this was computed
```

### 2. Coverage Tracking

Track what's been summarized:

```sql
-- Migration: 059_content_coverage.sql

CREATE TABLE content_coverage (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    platform TEXT NOT NULL,

    -- Time range covered by summaries
    covered_start TEXT,          -- Earliest summarized timestamp
    covered_end TEXT,            -- Latest summarized timestamp

    -- Summary counts
    summary_count INTEGER DEFAULT 0,

    -- Computed coverage
    coverage_percent REAL,       -- 0-100, based on time range
    gap_count INTEGER DEFAULT 0, -- Number of uncovered periods

    -- Timestamps
    last_summary_at TEXT,
    last_computed_at TEXT DEFAULT (datetime('now')),

    UNIQUE(guild_id, channel_id, platform)
);

CREATE TABLE coverage_gaps (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    platform TEXT NOT NULL,

    -- Gap boundaries
    gap_start TEXT NOT NULL,
    gap_end TEXT NOT NULL,

    -- Backfill status
    backfill_status TEXT DEFAULT 'pending',  -- pending, scheduled, running, complete, failed
    backfill_job_id TEXT,
    backfill_scheduled_for TEXT,

    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (guild_id, channel_id, platform)
        REFERENCES content_coverage(guild_id, channel_id, platform)
);

CREATE INDEX idx_coverage_gaps_status ON coverage_gaps(guild_id, backfill_status);
```

### 3. Coverage Computation

```python
async def compute_coverage(guild_id: str, platform: str) -> CoverageReport:
    """Compute content coverage for a guild."""

    # Get content inventory from platform
    inventory = await get_platform_inventory(guild_id, platform)

    # Get existing summaries
    summaries = await stored_repo.find_by_guild(guild_id)

    # Build coverage map per channel
    coverage_map = {}
    for channel in inventory.channels:
        channel_summaries = [s for s in summaries if channel.channel_id in s.source_channel_ids]

        if not channel_summaries:
            coverage_map[channel.channel_id] = ChannelCoverage(
                channel_id=channel.channel_id,
                channel_name=channel.channel_name,
                content_start=channel.earliest_message,
                content_end=channel.latest_message,
                covered_start=None,
                covered_end=None,
                coverage_percent=0,
                gaps=[Gap(channel.earliest_message, channel.latest_message)],
            )
        else:
            # Compute covered ranges and gaps
            covered_ranges = extract_covered_ranges(channel_summaries)
            gaps = find_gaps(
                content_start=channel.earliest_message,
                content_end=channel.latest_message,
                covered_ranges=covered_ranges,
            )
            coverage_pct = compute_coverage_percent(
                channel.earliest_message,
                channel.latest_message,
                covered_ranges,
            )
            coverage_map[channel.channel_id] = ChannelCoverage(
                channel_id=channel.channel_id,
                channel_name=channel.channel_name,
                content_start=channel.earliest_message,
                content_end=channel.latest_message,
                covered_start=min(r.start for r in covered_ranges),
                covered_end=max(r.end for r in covered_ranges),
                coverage_percent=coverage_pct,
                gaps=gaps,
            )

    return CoverageReport(
        guild_id=guild_id,
        platform=platform,
        channels=list(coverage_map.values()),
        total_coverage_percent=compute_overall_coverage(coverage_map),
        total_gaps=sum(len(c.gaps) for c in coverage_map.values()),
        computed_at=utc_now(),
    )
```

### 4. Coverage Dashboard UI

Add a "Coverage" tab or section showing:

```
┌─────────────────────────────────────────────────────────────┐
│  Content Coverage                                    Guild X │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Overall: ████████████░░░░░░░░ 62% covered                 │
│                                                             │
│  Platform: Discord                                          │
│  Content range: Jan 2022 - Apr 2026 (4.3 years)            │
│  Summaries: 847 covering 1,204 days                         │
│  Gaps: 23 periods totaling 412 days                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Channel           │ Coverage │ Gaps │ Action        │   │
│  ├───────────────────┼──────────┼──────┼───────────────┤   │
│  │ #general          │ 85%      │ 3    │ [Backfill]    │   │
│  │ #engineering      │ 72%      │ 8    │ [Backfill]    │   │
│  │ #random           │ 45%      │ 12   │ [Backfill]    │   │
│  │ #announcements    │ 100%     │ 0    │ ✓ Complete    │   │
│  │ #support          │ 0%       │ 1    │ [Backfill]    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [Schedule Full Backfill]  [Refresh Coverage]              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5. Scheduled Backfill

Allow scheduling backfill to run incrementally over time:

```python
@dataclass
class BackfillSchedule:
    guild_id: str
    channels: List[str]  # Empty = all channels
    priority: str  # oldest_first, newest_first, largest_gaps
    rate_limit: str  # e.g., "10 per hour", "50 per day"
    enabled: bool
    created_at: datetime

async def process_scheduled_backfill(schedule: BackfillSchedule):
    """Process one batch of scheduled backfill."""

    # Get next gaps to fill based on priority
    gaps = await get_pending_gaps(
        guild_id=schedule.guild_id,
        channels=schedule.channels,
        priority=schedule.priority,
        limit=get_batch_size(schedule.rate_limit),
    )

    for gap in gaps:
        # Check for existing summary (ADR-071 deduplication)
        existing = await find_summary_for_period(
            guild_id=schedule.guild_id,
            channel_id=gap.channel_id,
            start=gap.gap_start,
            end=gap.gap_end,
        )

        if existing:
            await mark_gap_covered(gap.id, existing.id)
            continue

        # Generate summary for this gap
        try:
            summary = await generate_summary_for_period(
                guild_id=schedule.guild_id,
                channel_id=gap.channel_id,
                start=gap.gap_start,
                end=gap.gap_end,
                source="backfill",
            )
            await mark_gap_covered(gap.id, summary.id)
        except Exception as e:
            await mark_gap_failed(gap.id, str(e))

    # Recompute coverage after batch
    await compute_coverage(schedule.guild_id, schedule.platform)
```

### 6. API Endpoints

```python
# GET /api/v1/guilds/{guild_id}/coverage
# Returns: CoverageReport

# POST /api/v1/guilds/{guild_id}/coverage/refresh
# Recomputes coverage from current data

# GET /api/v1/guilds/{guild_id}/coverage/gaps
# Returns: List[CoverageGap]

# POST /api/v1/guilds/{guild_id}/coverage/backfill
# Body: { channels?: [], priority: "oldest_first", rate: "10/hour" }
# Schedules backfill

# GET /api/v1/guilds/{guild_id}/coverage/backfill/status
# Returns: BackfillStatus with progress

# DELETE /api/v1/guilds/{guild_id}/coverage/backfill
# Cancels scheduled backfill
```

### 7. Backfill Job Integration

Integrate with existing job system (ADR-068):

```python
class JobType(str, Enum):
    SUMMARY = "SUMMARY"
    WIKI_BACKFILL = "WIKI_BACKFILL"
    CONTENT_BACKFILL = "CONTENT_BACKFILL"  # New
```

Backfill jobs appear in the Jobs list with progress:

```
┌──────────────────────────────────────────────────────────┐
│ Jobs                                                      │
├──────────────────────────────────────────────────────────┤
│ ● Content Backfill    Running   42/156 gaps   27%        │
│   Started 2h ago • ~4h remaining • Rate: 10/hour         │
│   [Pause] [Cancel]                                        │
└──────────────────────────────────────────────────────────┘
```

## Implementation Phases

| Phase | Feature | Effort |
|-------|---------|--------|
| 1 | Coverage computation & storage | Medium |
| 1 | Coverage API endpoints | Low |
| 2 | Coverage dashboard UI | Medium |
| 2 | Manual gap backfill (per-channel) | Low |
| 3 | Scheduled backfill with rate limiting | Medium |
| 3 | Backfill progress in Jobs UI | Low |

## Consequences

### Positive
- Users can see what content is/isn't summarized
- Automated backfill without manual intervention
- Rate limiting prevents API abuse and cost spikes
- Integrates with existing job system
- Progress visibility builds confidence

### Negative
- Platform inventory queries may be slow for large guilds
- Coverage computation adds database load
- Backfill at scale requires careful rate limiting

### Platform Considerations

| Platform | Inventory Method | Limitations |
|----------|------------------|-------------|
| Discord | `channel.history()` pagination | Rate limited, older messages slower |
| Slack | `conversations.history` | Requires appropriate scopes |

For very large guilds, inventory may be estimated rather than exact.

## References

- ADR-068: Background Jobs
- ADR-071: Summary Deduplication
- ADR-008: Summary Source Tracking
