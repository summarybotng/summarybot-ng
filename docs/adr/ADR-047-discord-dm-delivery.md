# ADR-047: Discord Direct Message Delivery Destination

**Status:** Implemented
**Date:** 2026-04-22
**Related:** ADR-005 (Dashboard Delivery), CS-008 (Delivery Strategy Pattern)

---

## 1. Context

### The Request

Users want to receive scheduled summary notifications directly via Discord DM (Direct Message) rather than only to channels. This is useful for:

1. **Personal notifications** - Admins want private summaries without creating a dedicated channel
2. **Mobile alerts** - DMs trigger push notifications on Discord mobile apps
3. **Privacy** - Some users prefer not to clutter channels with summary notifications
4. **Individual assignments** - Different team members get different channel summaries

### Current State

Before this ADR, SummaryBot supported these delivery destinations:
- `DISCORD_CHANNEL` - Post to a Discord text channel
- `WEBHOOK` - Send to any webhook URL
- `EMAIL` - Send via email (requires SMTP config)
- `FILE` - Write to local file system
- `DASHBOARD` - Store in dashboard for manual viewing

---

## 2. Decision

Add a new `DISCORD_DM` destination type that delivers summaries directly to a Discord user via Direct Message.

### 2.1 Destination Type

```python
class DestinationType(Enum):
    DISCORD_CHANNEL = "discord_channel"
    DISCORD_DM = "discord_dm"  # NEW: Direct message to user
    WEBHOOK = "webhook"
    EMAIL = "email"
    FILE = "file"
    DASHBOARD = "dashboard"
```

### 2.2 Target Configuration

For `DISCORD_DM` destinations:
- `target` field contains the **Discord User ID** (snowflake)
- Format options: `embed` (default), `markdown`

```python
Destination(
    type=DestinationType.DISCORD_DM,
    target="123456789012345678",  # Discord user ID
    format="embed",
    enabled=True
)
```

### 2.3 Delivery Strategy

A new `DiscordDMDeliveryStrategy` class implements delivery:

```python
class DiscordDMDeliveryStrategy(DeliveryStrategy):
    @property
    def destination_type(self) -> str:xxxx
        return "discord_dm"

    async def deliver(self, summary, destination, context) -> DeliveryResult:
        user = await context.discord_client.fetch_user(int(destination.target))
        dm_channel = await user.create_dm()

        if destination.format == "embed":
            embed = discord.Embed.from_dict(summary.to_embed_dict())
            await dm_channel.send(embed=embed)
        else:
            await dm_channel.send(summary.to_markdown())
```

---

## 3. Implementation Details

### 3.1 Error Handling

DM delivery can fail for several reasons:
- **User has DMs disabled** - Returns `discord.Forbidden`
- **User has blocked the bot** - Returns `discord.Forbidden`
- **User not found** - Returns `discord.NotFound`
- **Bot not in shared server** - May fail to fetch user

These are handled gracefully with appropriate error messages in `DeliveryResult`.

### 3.2 Rate Limiting

Discord DM rate limits are more restrictive than channel messages:
- No burst sending to many users simultaneously
- Consider adding delay between multiple DM deliveries

### 3.3 Display String

The `Destination.to_display_string()` method now handles DMs:

```python
type_names = {
    DestinationType.DISCORD_DM: "Discord DM",
    # ...
}
```

---

## 4. Usage Examples

### 4.1 Creating a Schedule with DM Delivery

```python
from src.models.task import ScheduledTask, Destination, DestinationType

task = ScheduledTask(
    name="Daily Summary for Admin",
    channel_ids=["channel1", "channel2"],
    guild_id="123456789",
    destinations=[
        Destination(
            type=DestinationType.DISCORD_DM,
            target="987654321098765432",  # Admin's user ID
            format="embed"
        )
    ],
    # ... other config
)
```

### 4.2 Dashboard UI

The frontend schedule editor should:
1. Allow selecting "Discord DM" as destination type
2. Provide user ID input (or user search/selection)
3. Show warning if user has DMs disabled (requires testing)

---

## 5. Files Changed

| File | Change |
|------|--------|
| `src/models/task.py` | Added `DISCORD_DM` to `DestinationType` enum |
| `src/models/task.py` | Added "Discord DM" to `Destination.to_display_string()` |
| `src/scheduling/delivery/discord_dm.py` | NEW: `DiscordDMDeliveryStrategy` class |
| `src/scheduling/delivery/__init__.py` | Export `DiscordDMDeliveryStrategy` |
| `src/scheduling/executor.py` | Register DM strategy in `_delivery_strategies` |

---

## 6. Consequences

### Positive
- Users can receive personal summary notifications
- Better mobile notification experience
- More flexible delivery options

### Negative
- DMs may be perceived as spam if overused
- User must have DMs enabled from server members
- Bot needs `create_dm` permission (typically implicit)

### Risks
- If bot is removed from guild, DMs to that guild's members may fail
- High volume DMs could hit rate limits

---

## 7. Future Considerations

1. **User preference opt-out** - Allow users to opt out of bot DMs
2. **DM verification** - Send test DM before enabling schedule
3. **Role-based delivery** - Send DMs to all users with a specific role
4. **Threaded DM conversations** - Group related summaries in DM threads
