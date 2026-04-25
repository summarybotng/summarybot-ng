# ADR-051: Platform Message Fetcher Abstraction

## Status
Accepted (2026-04-25)

## Context

The summary generation code in `src/dashboard/routes/summaries.py` has grown to 3,300+ lines with significant platform-specific branching for Discord, Slack, and potentially future platforms (WhatsApp, Telegram). Current issues:

### Code Duplication
- **Message fetching logic duplicated**: Generation (~125 LOC) and regeneration (~95 LOC) have nearly identical Slack fetching code
- **Channel resolution**: 5 separate code paths for Discord/Slack scope handling
- **User name resolution**: Slack-specific batch lookup duplicated in 2 places
- **Context building**: Different name/guild lookups per platform

### Branching Complexity
```python
# Current pattern (repeated 8+ times in file)
if is_slack:
    # 50-120 lines of Slack-specific code
else:
    # 20-50 lines of Discord-specific code
```

### Maintenance Risk
- Adding new platform requires modifying 5+ functions
- Bug fixes must be applied in multiple places (e.g., user name resolution)
- No clear contract for what a "platform" must provide

## Decision

Introduce a **Platform Message Fetcher** abstraction using the Strategy pattern to encapsulate platform-specific message retrieval, user resolution, and channel operations.

### Architecture

```
src/dashboard/
├── platforms/
│   ├── __init__.py           # Factory function
│   ├── base.py               # Protocol/ABC definitions
│   ├── discord_fetcher.py    # Discord implementation
│   ├── slack_fetcher.py      # Slack implementation
│   └── types.py              # Shared types
└── routes/
    └── summaries.py          # Uses PlatformFetcher interface
```

### Core Interface

```python
# src/dashboard/platforms/base.py
from typing import Protocol, List, Optional
from datetime import datetime
from dataclasses import dataclass

from src.models.message import ProcessedMessage

@dataclass
class FetchResult:
    """Result of message fetching operation."""
    messages: List[ProcessedMessage]
    channel_names: dict[str, str]  # channel_id -> display name
    user_names: dict[str, str]     # user_id -> display name
    errors: List[tuple[str, str]]  # (channel_id, error_message)


@dataclass
class PlatformContext:
    """Context for summarization."""
    platform_name: str       # "Discord", "Slack"
    server_name: str         # Guild name or workspace name
    server_id: str
    primary_channel_name: str


class PlatformFetcher(Protocol):
    """Protocol for platform-specific message fetching."""

    @property
    def platform_name(self) -> str:
        """Return platform identifier: 'discord', 'slack', etc."""
        ...

    async def fetch_messages(
        self,
        channel_ids: List[str],
        start_time: datetime,
        end_time: datetime,
        job_id: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> FetchResult:
        """
        Fetch messages from specified channels within time range.

        Returns ProcessedMessage objects with resolved author names.
        """
        ...

    async def resolve_channels(
        self,
        scope: str,  # "channel", "category", "guild"
        channel_ids: Optional[List[str]] = None,
        category_id: Optional[str] = None,
    ) -> List[str]:
        """
        Resolve channel IDs based on scope.

        - CHANNEL: Validate provided channel_ids exist
        - CATEGORY: Get all channels in category (Discord-only)
        - GUILD: Get all summarizable channels
        """
        ...

    async def get_context(
        self,
        channel_ids: List[str],
    ) -> PlatformContext:
        """Build summarization context with display names."""
        ...

    def get_archive_source_key(self, server_id: str) -> str:
        """Return archive key like 'discord:123' or 'slack:456'."""
        ...

    async def close(self) -> None:
        """Cleanup resources (HTTP clients, etc.)."""
        ...
```

### Factory Function

```python
# src/dashboard/platforms/__init__.py
from typing import Optional
from .base import PlatformFetcher
from .discord_fetcher import DiscordFetcher
from .slack_fetcher import SlackFetcher


async def get_platform_fetcher(
    platform: str,
    guild_id: str,
) -> Optional[PlatformFetcher]:
    """
    Factory to create appropriate platform fetcher.

    Args:
        platform: "discord" or "slack"
        guild_id: Discord guild ID (also used for Slack workspace linking)

    Returns:
        PlatformFetcher instance or None if platform unavailable
    """
    if platform == "slack":
        from src.data.repositories import get_slack_repository
        slack_repo = await get_slack_repository()
        workspace = await slack_repo.get_workspace_by_guild(guild_id)
        if workspace and workspace.enabled:
            return SlackFetcher(workspace)
        return None

    elif platform == "discord":
        from src.discord_bot import get_discord_bot
        from src.dashboard.routes.summaries import _get_guild_or_404
        try:
            guild = _get_guild_or_404(guild_id)
            bot = get_discord_bot()
            return DiscordFetcher(guild, bot)
        except Exception:
            return None

    return None


def detect_platform(archive_source_key: Optional[str]) -> str:
    """Detect platform from archive source key."""
    if archive_source_key and archive_source_key.startswith("slack:"):
        return "slack"
    return "discord"
```

### Implementation Examples

#### SlackFetcher

```python
# src/dashboard/platforms/slack_fetcher.py
class SlackFetcher:
    def __init__(self, workspace: SlackWorkspace):
        self.workspace = workspace
        self._client: Optional[SlackClient] = None

    @property
    def platform_name(self) -> str:
        return "slack"

    async def _get_client(self) -> SlackClient:
        if not self._client:
            self._client = SlackClient(self.workspace)
        return self._client

    async def fetch_messages(
        self,
        channel_ids: List[str],
        start_time: datetime,
        end_time: datetime,
        job_id: str,
        progress_callback: Optional[Callable] = None,
    ) -> FetchResult:
        client = await self._get_client()
        messages = []
        channel_names = {}
        errors = []

        oldest_ts = str(start_time.timestamp())
        latest_ts = str(end_time.timestamp())

        for idx, channel_id in enumerate(channel_ids):
            try:
                # Get channel name
                try:
                    info = await client.get_channel_info(channel_id)
                    channel_names[channel_id] = info.channel_name
                except Exception:
                    channel_names[channel_id] = channel_id

                # Fetch with auto-join
                cursor = None
                while True:
                    try:
                        data = await client.get_channel_history(
                            channel_id=channel_id,
                            oldest=oldest_ts,
                            latest=latest_ts,
                            limit=200,
                            cursor=cursor,
                        )
                    except SlackAPIError as e:
                        if "not_in_channel" in str(e):
                            await client.join_channel(channel_id)
                            data = await client.get_channel_history(...)
                        else:
                            raise

                    for msg in data.get("messages", []):
                        if msg.get("subtype") in ("bot_message", "channel_join"):
                            continue
                        messages.append(self._convert_message(msg, channel_id, channel_names))

                    cursor = data.get("response_metadata", {}).get("next_cursor")
                    if not cursor:
                        break

                if progress_callback:
                    progress_callback(idx + 1, f"Fetched #{channel_names[channel_id]}")

            except Exception as e:
                errors.append((channel_id, str(e)))

        # Batch resolve user names
        user_names = await self._resolve_users(messages)
        for msg in messages:
            if msg.author_id in user_names:
                msg.author_name = user_names[msg.author_id]

        return FetchResult(
            messages=messages,
            channel_names=channel_names,
            user_names=user_names,
            errors=errors,
        )

    async def _resolve_users(self, messages: List[ProcessedMessage]) -> dict[str, str]:
        client = await self._get_client()
        user_ids = set(m.author_id for m in messages if m.author_id != "unknown")
        user_names = {}

        for user_id in user_ids:
            try:
                info = await client.get_user_info(user_id)
                user_names[user_id] = info.display_name or info.real_name or user_id
            except Exception:
                user_names[user_id] = user_id

        return user_names

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
```

#### DiscordFetcher

```python
# src/dashboard/platforms/discord_fetcher.py
class DiscordFetcher:
    def __init__(self, guild: discord.Guild, bot):
        self.guild = guild
        self.bot = bot

    @property
    def platform_name(self) -> str:
        return "discord"

    async def fetch_messages(
        self,
        channel_ids: List[str],
        start_time: datetime,
        end_time: datetime,
        job_id: str,
        progress_callback: Optional[Callable] = None,
    ) -> FetchResult:
        from src.message_processing import MessageProcessor

        raw_messages = []
        channel_names = {}
        errors = []

        for idx, channel_id in enumerate(channel_ids):
            channel = self.guild.get_channel(int(channel_id))
            if not channel:
                errors.append((channel_id, "Channel not found"))
                continue

            channel_names[channel_id] = channel.name

            try:
                async for message in channel.history(
                    after=start_time,
                    before=end_time,
                    limit=1000,
                ):
                    raw_messages.append(message)

                if progress_callback:
                    progress_callback(idx + 1, f"Fetched #{channel.name}")
            except Exception as e:
                errors.append((channel_id, str(e)))

        # Process through MessageProcessor
        processor = MessageProcessor(self.bot.client)
        processed = await processor.process_messages(
            raw_messages,
            SummaryOptions(min_messages=1)
        )

        # Extract user names from Discord messages
        user_names = {str(m.author.id): m.author.display_name for m in raw_messages}

        return FetchResult(
            messages=processed,
            channel_names=channel_names,
            user_names=user_names,
            errors=errors,
        )

    async def close(self) -> None:
        pass  # Discord client managed globally
```

### Usage in summaries.py

```python
# Before (120+ lines of branching)
if is_slack:
    slack_client = SlackClient(slack_workspace)
    try:
        oldest_ts = str(start_time.timestamp())
        # ... 100 lines of Slack-specific code ...
    finally:
        await slack_client.close()
else:
    for channel_id in channel_ids:
        channel = guild.get_channel(int(channel_id))
        # ... 30 lines of Discord-specific code ...

# After (10 lines)
from ..platforms import get_platform_fetcher, detect_platform

platform = body.platform if body else detect_platform(stored.archive_source_key)
fetcher = await get_platform_fetcher(platform, guild_id)

if not fetcher:
    raise HTTPException(status_code=400, detail="Platform unavailable")

try:
    result = await fetcher.fetch_messages(
        channel_ids=channel_ids,
        start_time=start_time,
        end_time=end_time,
        job_id=job_id,
        progress_callback=lambda idx, msg: job.update_progress(idx, None, msg),
    )
    all_messages = result.messages
finally:
    await fetcher.close()
```

## Implementation Plan

### Phase 1: Extract Base Classes (Low Risk)
1. Create `src/dashboard/platforms/` directory
2. Define `PlatformFetcher` protocol and `FetchResult` dataclass
3. Create factory function with existing logic

### Phase 2: Implement SlackFetcher (Medium Risk)
1. Extract Slack fetching from `generate_summary()` into `SlackFetcher`
2. Extract Slack fetching from `regenerate_stored_summary()` (identical code)
3. Add unit tests for `SlackFetcher`

### Phase 3: Implement DiscordFetcher (Medium Risk)
1. Extract Discord fetching into `DiscordFetcher`
2. Integrate with existing `MessageProcessor`
3. Add unit tests

### Phase 4: Refactor Routes (High Risk - Staged)
1. Update `generate_summary()` to use fetcher
2. Update `regenerate_stored_summary()` to use fetcher
3. Remove duplicated code
4. Integration testing

### Phase 5: Additional Abstractions (Optional)
1. `ChannelResolver` - scope-based channel resolution
2. `ContextBuilder` - summarization context creation
3. `TitleGenerator` - platform-aware title generation

### Phase 6: Scheduled Tasks Platform Support
Extend the scheduler to support multi-platform message sources.

#### 6.1 UI Changes (ScheduleForm)

Add platform selector before scope selection:

```typescript
// src/frontend/src/components/schedules/ScheduleForm.tsx
export interface ScheduleFormData {
  name: string;
  platform: "discord" | "slack";  // NEW: Platform selection
  scope: ScopeType;
  channel_ids: string[];
  // ... existing fields
}

// Platform selector component
<Select
  value={formData.platform}
  onValueChange={(value) => onChange({ ...formData, platform: value, channel_ids: [] })}
>
  <SelectTrigger>
    <SelectValue placeholder="Select platform" />
  </SelectTrigger>
  <SelectContent>
    <SelectItem value="discord">
      <span className="flex items-center gap-2">🎮 Discord</span>
    </SelectItem>
    <SelectItem value="slack" disabled={!hasLinkedSlackWorkspace}>
      <span className="flex items-center gap-2">💬 Slack</span>
    </SelectItem>
  </SelectContent>
</Select>
```

#### 6.2 Slack Channel Selector

When Slack is selected, show workspace channels instead of Discord channels:

```typescript
// Fetch Slack channels when platform is "slack"
const { data: slackChannels } = useSlackChannels(guildId, {
  enabled: formData.platform === "slack"
});

// Scope selector shows Slack channels
{formData.platform === "slack" ? (
  <SlackChannelSelector
    channels={slackChannels || []}
    selected={formData.channel_ids}
    onChange={(ids) => onChange({ ...formData, channel_ids: ids })}
  />
) : (
  <ScopeSelector ... />
)}
```

#### 6.3 Backend Schedule Model

Extend the schedule model to store platform:

```sql
-- Migration: Add platform column to scheduled_tasks
ALTER TABLE scheduled_tasks ADD COLUMN platform TEXT DEFAULT 'discord';
```

```python
# src/models/schedule.py
@dataclass
class ScheduledTask:
    id: str
    name: str
    guild_id: str
    platform: str = "discord"  # NEW: "discord" or "slack"
    scope: str = "channel"
    channel_ids: List[str] = field(default_factory=list)
    # ... existing fields
```

#### 6.4 Scheduler Execution

Update scheduler to use PlatformFetcher:

```python
# src/scheduling/executor.py
async def execute_scheduled_summary(task: ScheduledTask):
    from src.dashboard.platforms import get_platform_fetcher

    # Get appropriate fetcher based on task platform
    fetcher = await get_platform_fetcher(task.platform, task.guild_id)
    if not fetcher:
        raise ScheduleExecutionError(f"Platform {task.platform} unavailable")

    try:
        # Resolve channels based on scope
        if task.scope == "guild":
            channel_ids = await fetcher.resolve_channels("guild")
        elif task.scope == "category":
            channel_ids = await fetcher.resolve_channels("category", category_id=task.category_id)
        else:
            channel_ids = task.channel_ids

        # Fetch messages using platform-agnostic interface
        result = await fetcher.fetch_messages(
            channel_ids=channel_ids,
            start_time=task.get_time_range_start(),
            end_time=datetime.utcnow(),
            job_id=job.id,
        )

        # Generate summary (same for all platforms)
        summary = await summarizer.generate(
            messages=result.messages,
            context=await fetcher.get_context(channel_ids),
            options=task.summary_options,
        )

        # Store with platform-specific archive key
        stored = await store_summary(
            summary=summary,
            source="scheduled",
            archive_source_key=fetcher.get_archive_source_key(task.guild_id),
            schedule_id=task.id,
        )

    finally:
        await fetcher.close()
```

#### 6.5 ScheduleCard Platform Badge

Display platform on schedule cards:

```typescript
// src/frontend/src/components/schedules/ScheduleCard.tsx
function getPlatformBadge(platform: string) {
  switch (platform) {
    case "slack":
      return { label: "Slack", icon: "💬", className: "bg-purple-500/10 text-purple-600" };
    case "discord":
    default:
      return { label: "Discord", icon: "🎮", className: "bg-indigo-500/10 text-indigo-600" };
  }
}

// In the card header
<Badge variant="outline" className={getPlatformBadge(schedule.platform).className}>
  {getPlatformBadge(schedule.platform).icon} {getPlatformBadge(schedule.platform).label}
</Badge>
```

#### 6.6 API Endpoints

Update schedule endpoints to accept platform:

```python
# src/dashboard/routes/schedules.py
class CreateScheduleRequest(BaseModel):
    name: str
    platform: Literal["discord", "slack"] = "discord"  # NEW
    scope: Literal["channel", "category", "guild"]
    channel_ids: List[str] = []
    # ... existing fields

@router.post("/guilds/{guild_id}/schedules")
async def create_schedule(guild_id: str, body: CreateScheduleRequest):
    # Validate platform availability
    if body.platform == "slack":
        slack_repo = await get_slack_repository()
        workspace = await slack_repo.get_workspace_by_guild(guild_id)
        if not workspace or not workspace.enabled:
            raise HTTPException(400, "No linked Slack workspace")

    # Create schedule with platform
    schedule = ScheduledTask(
        id=generate_id("sched"),
        guild_id=guild_id,
        platform=body.platform,
        # ... rest of fields
    )
```

## Consequences

### Positive
- **Single source of truth**: Message fetching logic in one place per platform
- **Easy platform addition**: New platforms implement `PlatformFetcher`
- **Testability**: Platform implementations can be unit tested in isolation
- **Reduced file size**: summaries.py reduced by ~300 lines
- **Bug fixes apply everywhere**: Fix user resolution once, works for all operations
- **Unified scheduling**: Same scheduler code works for Discord and Slack
- **Platform flexibility**: Users can schedule summaries from any connected platform

### Negative
- **Initial refactoring effort**: ~2-3 days of work + ~1 day for schedule integration
- **New directory/files**: 5 new files in `platforms/`
- **Learning curve**: Developers must understand abstraction
- **Migration**: Existing schedules default to "discord" platform

### Risks
- **Regression**: Must maintain identical behavior during refactor
- **Discord.py integration**: DiscordFetcher needs to handle discord.py quirks

## Verification

1. **Unit Tests**: Each fetcher has tests for:
   - Message fetching with pagination
   - User name resolution
   - Error handling (channel not found, rate limits)
   - Auto-join for Slack

2. **Integration Tests**:
   - Generate summary for Discord channel
   - Generate summary for Slack channel
   - Regenerate both platform types
   - Schedule creation with platform selection
   - Schedule execution for both platforms

3. **Manual Testing**:
   - Generate summary via UI for both platforms
   - Verify user names display correctly in References
   - Verify channel names in title/context
   - Create schedule for Slack workspace channels
   - Verify schedule card shows platform badge
   - Run scheduled task and verify correct platform messages fetched

## References

- ADR-002: WhatsApp DataSource Integration (ProcessedMessage model)
- ADR-043: Slack Workspace Integration (Slack client architecture)
- ADR-016: Summary Regeneration (regeneration requirements)
- ADR-011: Schedule Scopes (channel/category/guild scope patterns)
- ADR-005: Delivery Destinations (multi-destination delivery patterns)
