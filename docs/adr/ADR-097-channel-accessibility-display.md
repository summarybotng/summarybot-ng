# ADR-097: Channel Accessibility Display

## Status
Proposed

## Context

When users try to generate summaries for a category or guild-wide scope, they may encounter the error:
> "No accessible text channels in category 'X'"

This happens when the bot lacks `read_message_history` permission for channels in that category. Currently, users have no visibility into which channels the bot can actually access until they encounter this error.

The channels page (`/guilds/{id}/channels`) displays channel information including:
- Channel name and type
- Category grouping
- Enabled/disabled status for scheduled summaries
- `is_locked` status (whether @everyone can view - ADR-073)

However, it does **not** show whether the bot itself has permission to read message history, which is required for summarization.

### Current Behavior
1. User selects a category in the summary wizard
2. Backend checks `ch.permissions_for(guild.me).read_message_history`
3. If no channels pass this check, returns 400 error
4. User sees generic error with no prior warning

### Problem
- Users don't know which channels are accessible to the bot
- Error occurs at generation time, not during configuration
- No clear path to resolution (which channels need permission fixes)

## Decision

Add a `bot_can_read` field to the channel data and display accessibility status on the channels page.

### API Changes

**ChannelResponse Model** (`src/dashboard/models.py`):
```python
class ChannelResponse(BaseModel):
    """Channel information."""
    id: str
    name: str
    type: str
    category: Optional[str]
    enabled: bool
    is_locked: bool = False
    locked_override: bool = False
    bot_can_read: bool = True  # NEW: Can bot read message history?
```

**Guild Endpoint** (`src/dashboard/routes/guilds.py`):
```python
# Check bot permissions
can_read = channel.permissions_for(guild.me).read_message_history

channels.append(
    ChannelResponse(
        id=channel_id_str,
        name=channel.name,
        type="text",
        category=category_name,
        enabled=enabled,
        is_locked=is_locked,
        locked_override=locked_override,
        bot_can_read=can_read,  # NEW
    )
)
```

### Frontend Changes

**Channel Type** (`src/frontend/src/types/index.ts`):
```typescript
interface Channel {
  id: string;
  name: string;
  type: string;
  category?: string;
  enabled: boolean;
  is_locked?: boolean;
  locked_override?: boolean;
  bot_can_read?: boolean;  // NEW
}
```

**Channels Page** (`src/frontend/src/pages/Channels.tsx`):

Display accessibility indicator for each channel:
```tsx
{!channel.bot_can_read && (
  <Badge variant="destructive" className="ml-2">
    <ShieldOff className="h-3 w-3 mr-1" />
    No Access
  </Badge>
)}
```

Add summary stats at the top showing accessibility breakdown:
```tsx
<Alert variant="warning" className="mb-4">
  <AlertTriangle className="h-4 w-4" />
  <AlertDescription>
    {inaccessibleCount} of {totalChannels} channels are not accessible to the bot.
    These channels cannot be summarized until permissions are granted.
  </AlertDescription>
</Alert>
```

### Category Aggregation

For each category, show aggregate accessibility:
- "3 of 5 channels accessible"
- Warning badge if any channels are inaccessible
- Tooltip explaining the permission required

### Wizard Integration

In the summary wizard, when selecting a category:
1. Show count of accessible vs total channels
2. Warn if no channels are accessible
3. Prevent submission if zero accessible channels (fail fast)

## Visual Design

### Channel Row
```
#channel-name    [No Access]    [Locked]    [Enabled ✓]
```

### Category Header
```
▼ Media, Business & Marketing (2/5 accessible)  ⚠️
```

### Stats Banner
```
┌────────────────────────────────────────────────────────┐
│ ⚠️ 8 channels not accessible to the bot               │
│    Grant "Read Message History" permission to enable  │
└────────────────────────────────────────────────────────┘
```

## Consequences

### Positive
- Users can proactively identify and fix permission issues
- Clear visibility into what the bot can actually summarize
- Reduces confusion from unexpected 400 errors
- Self-service: users can fix permissions without support

### Negative
- Additional permission check on every guild fetch (minimal overhead)
- More UI complexity on channels page

### Neutral
- Existing `is_locked` field remains for @everyone visibility (different use case)

## Implementation

1. **Backend**: Add `bot_can_read` to ChannelResponse and compute it
2. **Frontend Types**: Update Channel interface
3. **Channels Page**: Add accessibility badges and warning banner
4. **Summary Wizard**: Add pre-validation warning for inaccessible categories

## Security Considerations

None - this only exposes whether the bot has permissions, which is observable behavior anyway.

## References

- ADR-073: Private Channel Handling (introduced `is_locked` field)
- Error: "No accessible text channels in category"
- Discord.py `Permissions.read_message_history`
