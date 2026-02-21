# ADR-011: Unified Scope Selection for All Summary Types

## Status
Proposed

## Date
2026-02-21

## Context

Currently, the three summary generation features have inconsistent scope selection capabilities:

| Feature | Channel | Category | Server/Guild |
|---------|---------|----------|--------------|
| **Real-Time Summaries** | ✅ | ✅ | ✅ |
| **Scheduled Summaries** | ✅ | ❌ | ❌ |
| **Retrospective/Archive** | ✅ | ❌ | ❌ |

Real-time summaries use a `SummaryScope` enum with three options:
- `CHANNEL` - Specific channel(s)
- `CATEGORY` - All text channels in a category
- `GUILD` - All enabled/accessible text channels in the server

Scheduled summaries and retrospective generation only accept explicit `channel_ids` lists, requiring users to manually select each channel even when they want all channels in a category or the entire server.

This creates friction for users who want to:
- Schedule daily summaries for an entire category (e.g., "Engineering" channels)
- Generate retrospective summaries for all server activity
- Maintain consistency as channels are added/removed from categories

## Decision

Extend the `SummaryScope` model to scheduled summaries and retrospective generation, providing a unified scope selection experience across all summary types.

### 1. Shared Scope Model

Reuse the existing `SummaryScope` enum from `src/dashboard/models.py`:

```python
class SummaryScope(str, Enum):
    CHANNEL = "channel"      # Specific channel(s)
    CATEGORY = "category"    # All channels in a category
    GUILD = "guild"          # All enabled channels in the guild
```

### 2. Updated Data Models

#### Scheduled Summaries

**Current:**
```python
class ScheduleCreateRequest(BaseModel):
    channel_ids: List[str]  # Required, explicit list
    # ...
```

**Proposed:**
```python
class ScheduleCreateRequest(BaseModel):
    scope: SummaryScope = SummaryScope.CHANNEL
    channel_ids: Optional[List[str]] = None   # Required for CHANNEL scope
    category_id: Optional[str] = None         # Required for CATEGORY scope
    # GUILD scope needs no additional fields
    # ...
```

#### Retrospective/Archive Generation

**Current:**
```python
class GenerateRequest(BaseModel):
    channel_ids: Optional[List[str]] = None  # Optional, defaults to all
    # ...
```

**Proposed:**
```python
class GenerateRequest(BaseModel):
    scope: SummaryScope = SummaryScope.GUILD  # Default to guild for retrospective
    channel_ids: Optional[List[str]] = None   # Required for CHANNEL scope
    category_id: Optional[str] = None         # Required for CATEGORY scope
    # ...
```

### 3. Scope Resolution Logic

Create a shared utility function for scope resolution:

```python
# src/dashboard/utils/scope_resolver.py

async def resolve_channels_for_scope(
    guild: discord.Guild,
    scope: SummaryScope,
    channel_ids: Optional[List[str]] = None,
    category_id: Optional[str] = None,
    config: Optional[GuildConfig] = None,
) -> List[discord.TextChannel]:
    """
    Resolve the list of channels based on scope.

    Args:
        guild: Discord guild object
        scope: The scope type (channel, category, guild)
        channel_ids: Explicit channel IDs (for CHANNEL scope)
        category_id: Category ID (for CATEGORY scope)
        config: Guild config for enabled channels (optional)

    Returns:
        List of text channels to summarize

    Raises:
        HTTPException: If required parameters are missing or invalid
    """
    if scope == SummaryScope.CHANNEL:
        if not channel_ids:
            raise HTTPException(400, "channel_ids required for CHANNEL scope")
        return [guild.get_channel(int(cid)) for cid in channel_ids
                if guild.get_channel(int(cid))]

    elif scope == SummaryScope.CATEGORY:
        if not category_id:
            raise HTTPException(400, "category_id required for CATEGORY scope")
        category = guild.get_channel(int(category_id))
        if not category or not isinstance(category, discord.CategoryChannel):
            raise HTTPException(404, f"Category not found: {category_id}")
        return [ch for ch in category.text_channels
                if ch.permissions_for(guild.me).read_message_history]

    elif scope == SummaryScope.GUILD:
        if config and config.enabled_channels:
            return [guild.get_channel(int(cid)) for cid in config.enabled_channels
                    if guild.get_channel(int(cid))]
        return [ch for ch in guild.text_channels
                if ch.permissions_for(guild.me).read_message_history]
```

### 4. Frontend Components

#### Shared ScopeSelector Component

Create a reusable component for scope selection:

```typescript
// src/frontend/src/components/common/ScopeSelector.tsx

interface ScopeSelectorProps {
  scope: "channel" | "category" | "guild";
  onScopeChange: (scope: "channel" | "category" | "guild") => void;
  selectedChannels: string[];
  onChannelsChange: (channels: string[]) => void;
  selectedCategory: string | null;
  onCategoryChange: (category: string | null) => void;
  channels: Channel[];
  categories: Category[];
}

export function ScopeSelector({
  scope,
  onScopeChange,
  selectedChannels,
  onChannelsChange,
  selectedCategory,
  onCategoryChange,
  channels,
  categories,
}: ScopeSelectorProps) {
  return (
    <div className="space-y-4">
      {/* Scope Type Selection */}
      <div className="space-y-2">
        <Label>Summarize</Label>
        <Select value={scope} onValueChange={onScopeChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="channel">Specific Channels</SelectItem>
            <SelectItem value="category">Entire Category</SelectItem>
            <SelectItem value="guild">Entire Server</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Channel Selection (for CHANNEL scope) */}
      {scope === "channel" && (
        <ChannelMultiSelect
          channels={channels}
          selected={selectedChannels}
          onChange={onChannelsChange}
        />
      )}

      {/* Category Selection (for CATEGORY scope) */}
      {scope === "category" && (
        <CategorySelect
          categories={categories}
          selected={selectedCategory}
          onChange={onCategoryChange}
        />
      )}

      {/* Guild scope shows info text */}
      {scope === "guild" && (
        <p className="text-sm text-muted-foreground">
          All accessible text channels will be summarized
        </p>
      )}
    </div>
  );
}
```

#### Integration Points

1. **ScheduleForm.tsx**: Replace channel multi-select with ScopeSelector
2. **Archive.tsx GenerateDialog**: Add ScopeSelector before date range
3. **SummariesPage.tsx**: Already has scope selection (reference implementation)

### 5. Database Schema Changes

#### Schedules Table

Add new columns:
```sql
ALTER TABLE scheduled_tasks ADD COLUMN scope VARCHAR(20) DEFAULT 'channel';
ALTER TABLE scheduled_tasks ADD COLUMN category_id VARCHAR(20);
```

#### Migration Strategy

- Existing schedules with `channel_ids` get `scope = 'channel'`
- No data migration needed for archive (request-time resolution)

### 6. Dynamic Resolution for Schedules

For category and guild scopes, channels are resolved **at execution time**, not at creation time. This means:

- New channels added to a category are automatically included
- Removed channels are automatically excluded
- Guild scope adapts to channel additions/removals

```python
# In schedule executor
async def execute_scheduled_summary(task: ScheduledTask):
    guild = bot.get_guild(int(task.guild_id))

    # Resolve channels dynamically based on scope
    channels = await resolve_channels_for_scope(
        guild=guild,
        scope=SummaryScope(task.scope),
        channel_ids=task.channel_ids,
        category_id=task.category_id,
        config=await get_guild_config(task.guild_id),
    )

    # Continue with summary generation...
```

### 7. API Changes

#### Schedule Endpoints

**POST /api/v1/guilds/{guild_id}/schedules**
```json
{
  "name": "Daily Engineering Summary",
  "scope": "category",
  "category_id": "123456789",
  "schedule_type": "daily",
  "schedule_time": "09:00",
  "timezone": "America/New_York",
  "destinations": [...]
}
```

**GET /api/v1/guilds/{guild_id}/schedules**
Response includes scope information:
```json
{
  "id": "sched_123",
  "name": "Daily Engineering Summary",
  "scope": "category",
  "category_id": "123456789",
  "category_name": "Engineering",  // Resolved for display
  "resolved_channels": ["ch1", "ch2", "ch3"],  // Current resolution
  ...
}
```

#### Archive Endpoints

**POST /api/v1/archive/generate**
```json
{
  "source_type": "discord",
  "server_id": "123456789",
  "scope": "category",
  "category_id": "987654321",
  "date_range": { "start": "2025-11-01", "end": "2025-11-08" },
  "granularity": "daily"
}
```

### 8. UI/UX Considerations

1. **Scope Badge**: Show scope type badge on schedule cards (e.g., "Category: Engineering")
2. **Channel Count**: Display resolved channel count for category/guild scopes
3. **Warning for Large Scopes**: Alert when selecting guild scope on servers with many channels
4. **Category Preview**: Show which channels are in a category before selection

### 9. Backward Compatibility

- Existing schedules continue to work (default scope = "channel")
- API accepts both old format (channel_ids only) and new format (scope + params)
- Frontend gracefully handles schedules without scope field

## Implementation Plan

### Phase 1: Backend Foundation
1. Create `scope_resolver.py` utility
2. Update `ScheduleCreateRequest` and `GenerateRequest` models
3. Add database migration for schedules table
4. Update schedule creation/update endpoints

### Phase 2: Schedule Integration
1. Update `ScheduleForm.tsx` with ScopeSelector
2. Update schedule executor for dynamic resolution
3. Add scope display to schedule cards
4. Update schedule API responses

### Phase 3: Retrospective Integration
1. Update `GenerateDialog` in Archive.tsx
2. Update archive message fetcher for scope resolution
3. Add scope to job status display

### Phase 4: Polish
1. Add channel count preview for category/guild scopes
2. Add warnings for large channel counts
3. Update documentation
4. Add comprehensive tests

## Files to Modify

| File | Changes |
|------|---------|
| `src/dashboard/models.py` | Update ScheduleCreateRequest, add to GenerateRequest |
| `src/dashboard/utils/scope_resolver.py` | New file - shared resolution logic |
| `src/dashboard/routes/schedules.py` | Use scope resolver, update responses |
| `src/dashboard/routes/archive.py` | Add scope to GenerateRequest, use resolver |
| `src/scheduler/executor.py` | Dynamic channel resolution |
| `src/frontend/src/components/common/ScopeSelector.tsx` | New shared component |
| `src/frontend/src/components/schedules/ScheduleForm.tsx` | Integrate ScopeSelector |
| `src/frontend/src/pages/Archive.tsx` | Add scope to GenerateDialog |
| `src/frontend/src/hooks/useSchedules.ts` | Update types |
| `src/frontend/src/hooks/useArchive.ts` | Update GenerateRequest type |
| `src/frontend/src/types/index.ts` | Add scope types |

## Consequences

### Positive
- Consistent UX across all summary types
- Dynamic resolution means schedules adapt to channel changes
- Reduced friction for whole-category or whole-server summaries
- Reusable components reduce code duplication

### Negative
- Migration complexity for existing schedules
- More complex validation logic
- Category/guild scopes may generate larger summaries (cost consideration)

### Risks
- Large guild scopes could hit rate limits or timeouts
- Category resolution depends on Discord API availability

## Related ADRs
- ADR-005: Scheduled Summary Delivery
- ADR-006: Archive System
- ADR-008: Unified Summary Experience
