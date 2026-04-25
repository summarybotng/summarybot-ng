# ADR-053: WhatsApp Live Fetch Feasibility Assessment

## Status
Rejected (Not Feasible with Current Architecture)

## Context

summarybot-ng supports live message fetching from Discord and Slack via their respective APIs. This assessment evaluates whether the same approach can work for WhatsApp.

### Current Architecture (Discord/Slack)

```
Schedule Trigger
    ↓
Platform Fetcher (DiscordFetcher / SlackFetcher)
    ↓
API Call: "Get messages from channel X, time range Y to Z"
    ↓
Messages returned
    ↓
Summarization
```

**Key capability**: Both Discord and Slack APIs support **historical message retrieval** - fetching past messages on demand.

## WhatsApp API Analysis

### Official WhatsApp Business Platform

Based on [Meta's WhatsApp Business Platform](https://business.whatsapp.com/products/business-platform) and [webhook documentation](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages):

| Capability | Discord/Slack | WhatsApp Cloud API |
|------------|---------------|-------------------|
| Fetch historical messages | ✅ Yes | ❌ **No** |
| Real-time incoming via webhook | ✅ Yes | ✅ Yes |
| Message history storage | API provides | **Your responsibility** |
| On-demand time-range queries | ✅ Yes | ❌ **No** |

### Critical Limitation

> "The API is not designed to act as a message storage system or archive. Any long-term storage, analytics, or message history should be implemented on your own infrastructure."

— [WhatsApp Webhook Guide](https://hookdeck.com/webhooks/platforms/guide-to-whatsapp-webhooks-features-and-best-practices)

WhatsApp Cloud API is **push-only**:
- You receive webhooks when messages arrive
- You **cannot** query "give me messages from the last 24 hours"
- No equivalent to `GET /channels/{id}/messages?after=timestamp`

### Pricing Considerations (2025)

Per [WhatsApp Business API Pricing 2025](https://latenode.com/blog/integration-api-management/whatsapp-business-api/whatsapp-business-api-pricing-for-2025-understanding-costs-and-how-to-save):
- Template-based pricing since April 2025
- Per-message costs for business-initiated conversations
- Not relevant for fetch (read-only) but affects any replies

## Alternative Approaches

### Approach A: Webhook-to-Storage Pipeline (Current)

```
WhatsApp Webhook → Ingest Handler → SQLite Storage
                                         ↓
                          Archive Summarization (on stored data)
```

**Status**: ✅ Already implemented (`/api/v1/whatsapp/` routes)

**Limitations**:
- Only messages received AFTER webhook setup
- No historical backfill possible
- Requires persistent webhook endpoint

### Approach B: WhatsApp Export File Import

```
User exports WhatsApp chat (.txt/.zip)
    ↓
Upload to summarybot
    ↓
Parse and store
    ↓
Summarize stored archive
```

**Status**: ✅ Already implemented (archive ingest)

**Limitations**:
- Manual user action required
- Not real-time
- Different UX from Discord/Slack

### Approach C: Third-Party APIs (e.g., whapi.cloud)

Unofficial APIs like [Whapi](https://whapi.cloud/docs) offer:
- Message history retrieval
- Group management
- Similar to Discord/Slack APIs

**Risks**:
- Terms of Service violations
- Account bans
- Reliability concerns
- Legal/compliance issues

**Status**: ❌ Not recommended

## Feasibility Verdict

### Can we build a `WhatsAppFetcher` like `DiscordFetcher`?

**No.** The fundamental API design differs:

| Feature | Required for Fetcher | WhatsApp Support |
|---------|---------------------|------------------|
| Query past messages | ✅ | ❌ |
| Time-range filtering | ✅ | ❌ |
| On-demand retrieval | ✅ | ❌ |
| Stateless operation | ✅ | ❌ (needs webhook state) |

### What We CAN Do

1. **Archive Import** (existing): Users upload exported chats
2. **Webhook Streaming** (existing): Real-time ingest from connected accounts
3. **Scheduled Summaries on Stored Data**: Summarize webhook-collected messages

### What We CANNOT Do

- "Fetch last 24 hours from WhatsApp group X" on-demand
- Scheduled summaries without prior webhook collection
- Backfill historical conversations

## Decision

**Do not** add WhatsApp to the `Platform` enum for scheduled fetching.

**Keep** WhatsApp support for:
- Archive imports (`SourceType.WHATSAPP`)
- Webhook-based real-time ingest
- Summarization of stored webhook data

## Implications

1. Remove `WHATSAPP` from `Platform` enum (schedule fetchers)
2. Keep `WHATSAPP` in `SourceType` enum (archive imports)
3. Document the difference clearly in user-facing docs
4. Consider UX improvements for webhook-based WhatsApp workflows

## References

- [WhatsApp Business Platform](https://business.whatsapp.com/products/business-platform)
- [WhatsApp Webhooks Reference](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages)
- [Guide to WhatsApp Webhooks](https://hookdeck.com/webhooks/platforms/guide-to-whatsapp-webhooks-features-and-best-practices)
- [WhatsApp Business API Pricing 2025](https://latenode.com/blog/integration-api-management/whatsapp-business-api/whatsapp-business-api-pricing-for-2025-understanding-costs-and-how-to-save)
- [Twilio WhatsApp Overview](https://www.twilio.com/docs/whatsapp/api)
