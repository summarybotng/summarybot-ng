# ADR-083: WhatsApp Manual Summarization

## Status
Accepted

## Context

ADR-081 introduced WhatsApp import management, allowing users to upload WhatsApp chat exports. However, the manual summarization feature (Generate Summary dialog) only supported Discord and Slack platforms. Users needed the ability to generate summaries from their imported WhatsApp chats on-demand.

## Decision

Extend the PlatformFetcher abstraction (ADR-051) to support WhatsApp manual summarization:

### Backend Changes

1. **WhatsAppFetcher** (`src/dashboard/platforms/whatsapp_fetcher.py`):
   - Implements `PlatformFetcher` interface
   - Reads messages from `ingest_messages` table via `batch_id` → `whatsapp_imports`
   - `fetch_messages()`: Queries messages within time range from selected chats
   - `resolve_channels()`: Returns all imported chats when none specified
   - `get_channels()`: Returns available chats with message counts
   - `get_context()`: Builds summarization context with chat names

2. **Platform Factory** (`src/dashboard/platforms/__init__.py`):
   - Added `Platform.WHATSAPP` enum value
   - `get_platform_fetcher()` returns `WhatsAppFetcher` when platform is WhatsApp
   - Checks for imported chats before returning fetcher

### Frontend Changes

1. **useWhatsApp Hook** (`src/frontend/src/hooks/useWhatsApp.ts`):
   - `useWhatsAppChats(guildId)`: Fetches imported chats from `/whatsapp/guilds/{id}/imports`
   - Returns chat_id, chat_name, total_messages, coverage

2. **Summaries Page** (`src/frontend/src/pages/Summaries.tsx`):
   - Added WhatsApp button to platform selector (3-column grid)
   - WhatsApp chat selector UI with search and checkboxes
   - Shows message counts per chat
   - Fallback message with link to WhatsApp Imports when no chats exist
   - Clears selections when switching platforms
   - Properly handles default channels for each platform

## Message Flow

```
User selects WhatsApp → Selects chats → Sets time range → Generate
    ↓
Backend: get_platform_fetcher("whatsapp", guild_id)
    ↓
WhatsAppFetcher.fetch_messages(chat_ids, start, end)
    ↓
Query: ingest_messages JOIN whatsapp_imports WHERE guild_id AND chat_id
    ↓
Returns ProcessedMessage[] with SourceType.WHATSAPP
    ↓
Standard summarization pipeline processes messages
```

## Consequences

### Positive
- Unified summarization interface for all platforms
- WhatsApp imports can be summarized on-demand with custom time ranges
- Chat selection allows focused summaries on specific conversations
- Consistent UX with Discord/Slack summarization

### Negative
- WhatsApp summaries limited to imported date ranges (no live fetching)
- Category scope not applicable to WhatsApp (disabled in UI)

## Related ADRs
- ADR-051: Platform Message Fetcher Abstraction
- ADR-081: WhatsApp Import Management
- ADR-043: Slack Integration
