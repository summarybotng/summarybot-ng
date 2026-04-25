# Platform Support

summarybot-ng supports multiple messaging platforms with varying levels of integration.

## Support Matrix

| Platform | Live Fetch | Scheduled Summaries | Archive Import | Real-time Webhook |
|----------|------------|---------------------|----------------|-------------------|
| **Discord** | ✅ Full | ✅ Full | ✅ Full | ✅ Via bot |
| **Slack** | ✅ Full | ✅ Full | ✅ Full | ✅ Via app |
| **WhatsApp** | ❌ No | ❌ No | ✅ Import only | ✅ Ingest only |

## Discord

**Full Support** - Native integration via Discord bot.

### Capabilities
- Live message fetching from any accessible channel
- Scheduled summary generation (hourly, daily, weekly, etc.)
- Summary delivery to Discord channels or DMs
- Archive import from exported data
- Category and guild-wide summaries

### Requirements
- Discord bot token with `MESSAGE_CONTENT` intent
- Bot added to target server with appropriate permissions

### Configuration
Bot token set via `DISCORD_BOT_TOKEN` environment variable.

---

## Slack

**Full Support** - Integration via Slack app with OAuth.

### Capabilities
- Live message fetching from connected workspaces
- Scheduled summary generation
- Multi-workspace support per guild
- Archive import from exported data

### Requirements
- Slack app with `channels:history`, `groups:history` scopes
- OAuth flow to connect workspace to guild

### Configuration
- `SLACK_CLIENT_ID` and `SLACK_CLIENT_SECRET` for OAuth
- Workspace tokens stored encrypted in database

### ADR Reference
- [ADR-051: Platform Message Fetcher Abstraction](adr/ADR-051-platform-message-fetcher-abstraction.md)

---

## WhatsApp

**Archive Import Only** - No live message fetching supported.

### Why No Live Fetch?

WhatsApp Business API is **push-only**:
- Messages arrive via webhooks (real-time)
- **Cannot** query historical messages on demand
- No "get messages from last 24 hours" API

This is fundamentally different from Discord/Slack which support historical queries.

See [ADR-053: WhatsApp Live Fetch Feasibility](adr/ADR-053-whatsapp-live-fetch-feasibility.md) for details.

### What IS Supported

1. **Archive Import**: Upload exported WhatsApp chat files (`.txt` or `.zip`)
2. **Webhook Ingest**: Real-time message collection via WhatsApp Business API webhooks
3. **Summarization of Stored Data**: Generate summaries from previously collected messages

### Capabilities
- Import WhatsApp chat exports
- Ingest messages via webhook (requires WhatsApp Business API setup)
- Summarize imported/ingested conversations
- Voice transcript inclusion (if available)
- Thread reconstruction

### Limitations
- No on-demand "fetch last 24 hours"
- No scheduled summaries without prior data collection
- Requires manual export or webhook infrastructure

### Configuration
- Webhook endpoint: `POST /api/v1/whatsapp/ingest`
- WhatsApp Business API credentials for webhook integration

---

## Platform Comparison

### Fetch Architecture

```
Discord/Slack (Pull Model):
┌─────────────┐     "Get messages"      ┌─────────────┐
│ summarybot  │ ────────────────────────▶│   API       │
│             │ ◀────────────────────────│             │
└─────────────┘     Messages returned    └─────────────┘

WhatsApp (Push Model):
┌─────────────┐                          ┌─────────────┐
│ summarybot  │ ◀────────────────────────│  WhatsApp   │
│  (webhook)  │     Message pushed       │   Cloud     │
└─────────────┘                          └─────────────┘
```

### Use Case Fit

| Use Case | Best Platform |
|----------|---------------|
| Automated daily summaries | Discord, Slack |
| On-demand "summarize last week" | Discord, Slack |
| Archive old conversations | All (via import) |
| Real-time message collection | All (with setup) |
| Customer support summaries | Discord, Slack |

---

## Future Platforms

No additional platforms are currently planned. The architecture supports adding new platforms via:

1. Implement `PlatformFetcher` interface (for pull-based APIs)
2. Add to `Platform` enum
3. Create routes for OAuth/configuration

Platforms considered but not planned:
- **Microsoft Teams**: Possible, requires Graph API integration
- **Telegram**: Removed from roadmap (no current demand)
