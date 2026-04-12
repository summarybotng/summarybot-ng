# ADR-043: Slack Workspace Integration — Feasibility Study

**Status:** Proposed (Deep Dive Analysis)
**Date:** 2026-04-11
**Depends on:** ADR-002 (WhatsApp Data Source Integration), ADR-026 (Multi-Platform Source Architecture)
**Context Domain:** Data Source Integration / Multi-Platform Support

---

## 1. Executive Summary

This ADR analyzes the feasibility, challenges, and architectural implications of extending SummaryBot-NG to ingest and summarize **Slack workspaces**. While the existing Ingest Adapter pattern (ADR-002) provides a foundation, Slack introduces significant paradigm differences from Discord that require careful consideration.

### Key Finding

**Feasibility: HIGH** with caveats. Slack integration is technically achievable but introduces:
- **Higher operational complexity** (OAuth flows, workspace-by-workspace installation)
- **Stricter rate limits** requiring careful throttling
- **Significant tier restrictions** (free plan: 90-day history limit, no message export)
- **Enterprise compliance requirements** (Grid, DLP, eDiscovery)
- **Monetization friction** (Slack Marketplace review if distributing publicly)

### Recommendation

Implement Slack as the third ingest adapter, prioritizing:
1. **Private/internal deployment first** (avoid Marketplace complexity)
2. **Paid workspace focus** (free tier limitations too restrictive)
3. **Events API over polling** (real-time capture, better rate limit profile)

---

## 2. Platform Comparison: Discord vs Slack

### 2.1 Conceptual Mapping

| Concept | Discord | Slack | Mapping Complexity |
|---------|---------|-------|--------------------|
| **Top-level container** | Guild (Server) | Workspace | 🟢 Direct 1:1 |
| **Primary conversation** | Channel (text) | Channel (public/private) | 🟢 Direct 1:1 |
| **Sub-conversations** | Thread (forum posts) | Thread (message replies) | 🟡 Similar but different UX |
| **Categories** | Category (channel groups) | ❌ None | 🔴 Discord-only concept |
| **DMs** | DM Channel | DM / Multi-party DM | 🟡 Similar |
| **Permissions** | Roles + Channel overrides | Workspace + Channel membership | 🟡 Different model |
| **Identity** | User ID + discriminator | User ID + email domain | 🟡 Email-centric in Slack |
| **Bot access** | Bot token + intents | Bot token + scopes | 🟡 OAuth flow required |
| **Attachments** | CDN URLs | S3-backed URLs (expire!) | 🔴 Critical difference |
| **Reactions** | Custom emoji + Unicode | Custom emoji + Unicode | 🟢 Same |
| **Mentions** | `<@user_id>` | `<@user_id>` | 🟢 Same format |
| **Formatting** | Markdown | mrkdwn (Slack-specific) | 🟡 Similar but not identical |

### 2.2 Critical Paradigm Differences

#### 2.2.1 Threading Model

**Discord**: Threads are explicit forum-style posts or message-started threads. They appear as separate channel-like entities.

**Slack**: Every message can become a thread parent. Replies are nested under the parent message. Threads are first-class but inline with channel flow.

```
Discord Thread Structure:
├── #general (channel)
│   ├── Message 1
│   └── [Thread: "Bug Discussion"] (separate entity)
│       ├── Reply 1
│       └── Reply 2

Slack Thread Structure:
├── #general (channel)
│   ├── Message 1
│   │   └── [3 replies]  ← Thread inline
│   │       ├── Reply 1
│   │       └── Reply 2
│   └── Message 2
```

**Implication**: Slack threads require fetching `conversations.replies` separately for each thread parent. This multiplies API calls significantly.

#### 2.2.2 History Access Differences

| Aspect | Discord | Slack (Free) | Slack (Pro/Business+) | Slack (Enterprise Grid) |
|--------|---------|--------------|----------------------|-------------------------|
| **History depth** | Unlimited | 90 days | Unlimited | Unlimited |
| **Message export** | ✅ Bot can read all | ❌ Limited | ✅ Full access | ✅ Full + compliance |
| **Bulk export** | Paginated API | Rate-limited | Rate-limited | Bulk export APIs |
| **Deleted messages** | Cannot retrieve | Cannot retrieve | Cannot retrieve | eDiscovery can |
| **Private channels** | Needs invite | Needs invite | Needs invite | Admin override possible |

**Implication**: Free Slack workspaces cannot be effectively summarized beyond 90 days. Retrospective summaries (ADR-006) would fail.

#### 2.2.3 Rate Limiting Architecture

**Discord**: Generous limits, bucket-based per route, global limit ~50 req/s for bots.

**Slack**: Tiered method limits (Tier 1-4), workspace-wide budget, much stricter.

| Slack Tier | Requests/min | Example Methods |
|------------|--------------|-----------------|
| Tier 1 | 1 | `admin.*`, `files.delete` |
| Tier 2 | 20 | `conversations.history`, `users.info` |
| Tier 3 | 50 | `conversations.replies`, `reactions.get` |
| Tier 4 | 100 | `chat.postMessage`, `reactions.add` |
| Special | Variable | `search.messages` (20/min), `files.upload` (20/min) |

**Implication**: Summarizing a busy Slack channel requires careful throttling. Fetching 1000 messages + their threads could take 2-5 minutes due to rate limits.

#### 2.2.4 File/Attachment Handling

**Discord**: Attachments have permanent CDN URLs (unless message deleted).

**Slack**: File URLs **expire after a few hours** unless you use `files.sharedPublicURL` (which makes files public) or download them immediately.

```python
# Discord attachment - always accessible
{
    "url": "https://cdn.discordapp.com/attachments/123/456/image.png",
    "proxy_url": "https://media.discordapp.net/attachments/123/456/image.png"
}

# Slack file - URL expires!
{
    "url_private": "https://files.slack.com/files-pri/T123-F456/image.png",
    "url_private_download": "https://files.slack.com/files-pri/T123-F456/download/image.png",
    "permalink": "https://workspace.slack.com/files/U123/F456/image.png"
    # ⚠️ url_private* require Bearer token and expire
}
```

**Implication**: For summaries that reference media, we must either:
1. Download files immediately during ingestion
2. Use permalinks (require Slack auth to view)
3. Accept that file references may break

#### 2.2.5 Slack Connect (External Collaboration)

Slack Connect allows channels shared between different organizations. This creates unique scenarios:

- Messages from external users (different workspace)
- Mixed permission models
- Data sovereignty concerns (which org "owns" the data?)
- Compliance: which org's DLP policies apply?

**Implication**: Slack Connect channels require careful handling. Initial implementation should either:
1. Skip Slack Connect channels entirely
2. Only summarize messages from the "home" workspace

---

## 3. Authentication & Authorization

### 3.1 Slack App Installation Flow

Unlike Discord (add bot via URL), Slack requires a full OAuth 2.0 flow:

```
1. Admin clicks "Add to Slack" → redirects to Slack
2. Slack shows permission consent screen
3. User approves → Slack redirects to callback URL
4. Callback exchanges code for access token
5. Token stored per-workspace in SummaryBot-NG
```

```
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│  SummaryBot-NG   │         │      Slack       │         │   Workspace      │
│  Dashboard       │         │   OAuth Server   │         │   Admin          │
└────────┬─────────┘         └────────┬─────────┘         └────────┬─────────┘
         │                            │                            │
         │  1. "Add to Slack" click   │                            │
         │ ──────────────────────────>│                            │
         │                            │  2. Show consent screen    │
         │                            │ ──────────────────────────>│
         │                            │                            │
         │                            │  3. Approve permissions    │
         │                            │ <──────────────────────────│
         │                            │                            │
         │  4. Redirect with code     │                            │
         │ <──────────────────────────│                            │
         │                            │                            │
         │  5. Exchange code for      │                            │
         │     access_token           │                            │
         │ ──────────────────────────>│                            │
         │                            │                            │
         │  6. Return tokens          │                            │
         │ <──────────────────────────│                            │
         │                            │                            │
         │  7. Store tokens, poll     │                            │
         │     or subscribe Events    │                            │
```

### 3.2 Required OAuth Scopes

| Scope | Purpose | Risk Level |
|-------|---------|------------|
| `channels:history` | Read public channel messages | Medium |
| `channels:read` | List public channels | Low |
| `groups:history` | Read private channel messages | High |
| `groups:read` | List private channels (user is member of) | Medium |
| `im:history` | Read DMs | High |
| `im:read` | List DMs | Medium |
| `mpim:history` | Read group DMs | High |
| `mpim:read` | List group DMs | Medium |
| `users:read` | Get user info (names, avatars) | Low |
| `team:read` | Get workspace info | Low |
| `files:read` | Access file content | Medium |
| `reactions:read` | Read reactions on messages | Low |

**Minimum viable scope set**:
```
channels:history channels:read users:read team:read reactions:read
```

**Full access scope set** (needed for comprehensive summaries):
```
channels:history channels:read groups:history groups:read
im:history im:read mpim:history mpim:read
users:read team:read files:read reactions:read
```

### 3.3 Token Management

Slack tokens don't expire like OAuth refresh tokens. However:
- Tokens can be **revoked** by workspace admins
- Tokens can be **rotated** (Enterprise Grid feature)
- Bot must handle `token_revoked` events gracefully

```python
# src/slack/token_store.py

@dataclass
class SlackWorkspaceToken:
    workspace_id: str          # T0XXXXXXX
    workspace_name: str
    bot_token: str             # xoxb-...
    bot_user_id: str           # U0XXXXXXX (the bot's user ID)
    installed_by: str          # User ID who installed
    installed_at: datetime
    scopes: list[str]
    is_enterprise: bool
    enterprise_id: str | None  # E0XXXXXXX for Grid

    def is_valid(self) -> bool:
        """Check if token is still valid (ping Slack API)."""
        ...
```

---

## 4. Data Ingestion Architecture

### 4.1 Option A: Polling (conversations.history)

Periodically poll channels for new messages.

**Pros**:
- Simple to implement
- Works without incoming webhook infrastructure
- Can backfill history easily

**Cons**:
- High rate limit consumption
- Latency (messages not captured in real-time)
- Must track "last seen" timestamp per channel
- Threads require separate API calls

```python
# Polling approach
async def poll_slack_channel(workspace_id: str, channel_id: str, since: datetime):
    client = get_slack_client(workspace_id)
    cursor = None

    while True:
        # Rate limit: Tier 2 (20/min)
        response = await client.conversations_history(
            channel=channel_id,
            oldest=since.timestamp(),
            cursor=cursor,
            limit=100,
        )

        for message in response["messages"]:
            yield normalize_slack_message(message)

            # Fetch thread replies if message has them
            if message.get("reply_count", 0) > 0:
                # Additional API call per thread! Rate limit: Tier 3
                replies = await client.conversations_replies(
                    channel=channel_id,
                    ts=message["ts"],
                )
                for reply in replies["messages"][1:]:  # Skip parent
                    yield normalize_slack_message(reply, parent_ts=message["ts"])

        if not response.get("has_more"):
            break
        cursor = response["response_metadata"]["next_cursor"]
```

### 4.2 Option B: Events API (Recommended)

Subscribe to real-time events via webhooks.

**Pros**:
- Real-time message capture
- Lower rate limit impact (events pushed to us)
- No polling infrastructure needed
- Captures edits and deletions immediately

**Cons**:
- Requires public HTTPS endpoint
- Must handle event deduplication
- Initial backfill still needs polling
- More complex setup (SSL, retries)

```python
# Event subscription approach

# Subscribe to these event types:
SLACK_EVENT_SUBSCRIPTIONS = [
    "message",              # New messages
    "message.channels",     # Public channel messages
    "message.groups",       # Private channel messages
    "message.im",           # DMs
    "message.mpim",         # Group DMs
    "reaction_added",       # Reactions
    "reaction_removed",
    "member_joined_channel",
    "member_left_channel",
    "channel_created",
    "channel_deleted",
    "channel_archive",
    "channel_unarchive",
]

@router.post("/slack/events")
async def slack_events_webhook(request: Request):
    body = await request.json()

    # Slack URL verification challenge
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    # Event handling
    if body.get("type") == "event_callback":
        event = body["event"]
        workspace_id = body["team_id"]

        if event["type"] == "message":
            # Skip bot messages, message_changed, etc.
            if event.get("subtype") in ("bot_message", "message_changed", "message_deleted"):
                return {"ok": True}

            message = normalize_slack_message(event)
            await ingest_message(workspace_id, message)

    return {"ok": True}
```

### 4.3 Recommended: Hybrid Approach

1. **Events API** for real-time capture (new messages as they arrive)
2. **Polling** for initial backfill (history before bot was installed)
3. **Polling** for retrospective summaries (user requests specific date range)

```
┌────────────────────────────────────────────────────────────────────┐
│                         SLACK INGEST                                │
│                                                                     │
│  ┌─────────────────┐       ┌─────────────────┐                     │
│  │  Events API     │       │  Polling Engine │                     │
│  │  (real-time)    │       │  (backfill +    │                     │
│  │                 │       │   on-demand)    │                     │
│  └────────┬────────┘       └────────┬────────┘                     │
│           │                         │                               │
│           └────────────┬────────────┘                               │
│                        │                                            │
│                        v                                            │
│           ┌────────────────────────┐                                │
│           │  Message Normalizer    │                                │
│           │  (Slack → ProcessedMsg)│                                │
│           └────────────┬───────────┘                                │
│                        │                                            │
│                        v                                            │
│           ┌────────────────────────┐                                │
│           │  Ingest Pipeline       │                                │
│           │  (existing ADR-002)    │                                │
│           └────────────────────────┘                                │
└────────────────────────────────────────────────────────────────────┘
```

---

## 5. Message Normalization

### 5.1 Slack Message Structure

Slack messages are more complex than Discord:

```json
{
    "type": "message",
    "subtype": null,  // or "bot_message", "file_share", "thread_broadcast", etc.
    "user": "U0XXXXXXX",
    "text": "Hello <@U0YYYYYYY>, check out <https://example.com|this link>!",
    "ts": "1712345678.123456",  // Unique message ID + timestamp
    "thread_ts": "1712345000.000000",  // Parent message if in thread
    "reply_count": 5,
    "reply_users_count": 3,
    "latest_reply": "1712345999.999999",
    "reactions": [
        {"name": "thumbsup", "users": ["U0XXXXXXX"], "count": 1}
    ],
    "files": [
        {
            "id": "F0XXXXXXX",
            "name": "report.pdf",
            "mimetype": "application/pdf",
            "filetype": "pdf",
            "size": 123456,
            "url_private": "https://files.slack.com/...",
            "permalink": "https://workspace.slack.com/files/..."
        }
    ],
    "attachments": [  // Link unfurls, not file attachments
        {
            "title": "Example Website",
            "title_link": "https://example.com",
            "text": "Description of the link...",
            "image_url": "https://example.com/preview.png"
        }
    ],
    "blocks": [  // Block Kit structured content
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "Hello world"}
        }
    ]
}
```

### 5.2 Normalization Mapping

```python
# src/slack/normalizer.py

def normalize_slack_message(msg: dict, channel_id: str, workspace: SlackWorkspace) -> ProcessedMessage:
    """Convert Slack message to SummaryBot-NG ProcessedMessage."""

    # Resolve user info (may need API call if not cached)
    user = workspace.get_user(msg.get("user"))

    # Convert Slack timestamp to datetime
    ts = float(msg["ts"])
    timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)

    # Determine message type
    subtype = msg.get("subtype")
    if subtype == "thread_broadcast":
        msg_type = MessageType.REPLY  # Thread reply broadcast to channel
    elif msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
        msg_type = MessageType.REPLY  # Thread reply
    else:
        msg_type = MessageType.DEFAULT

    # Extract attachments (files, not link unfurls)
    attachments = []
    for f in msg.get("files", []):
        attachments.append(AttachmentInfo(
            id=f["id"],
            filename=f.get("name", "unknown"),
            size=f.get("size", 0),
            url=f.get("permalink", ""),  # Use permalink (requires auth)
            proxy_url=f.get("url_private_download", ""),
            type=_map_slack_filetype(f.get("filetype")),
            content_type=f.get("mimetype"),
        ))

    # Convert mrkdwn to clean text
    content = _slack_mrkdwn_to_text(msg.get("text", ""))

    return ProcessedMessage(
        id=msg["ts"],  # Slack uses timestamp as message ID
        author_name=user.display_name if user else "Unknown",
        author_id=msg.get("user", ""),
        content=content,
        timestamp=timestamp,
        message_type=msg_type,
        attachments=attachments,
        reactions_count=sum(r["count"] for r in msg.get("reactions", [])),
        channel_id=channel_id,
        channel_name=workspace.get_channel_name(channel_id),
        source_type=SourceType.SLACK,
        reply_to_id=msg.get("thread_ts") if msg.get("thread_ts") != msg["ts"] else None,
    )


def _slack_mrkdwn_to_text(text: str) -> str:
    """Convert Slack mrkdwn to plain text."""
    # Replace user mentions: <@U123> → @username
    text = re.sub(r'<@([UW][A-Z0-9]+)>', r'@user', text)
    # Replace channel mentions: <#C123|general> → #general
    text = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'#\1', text)
    # Replace links: <https://...|text> → text (or URL if no text)
    text = re.sub(r'<(https?://[^|>]+)\|([^>]+)>', r'\2', text)
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)
    # Bold: *text* → text (Slack uses single asterisk)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Italic: _text_ → text
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Strikethrough: ~text~ → text
    text = re.sub(r'~([^~]+)~', r'\1', text)
    # Code: `code` → code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Code block: ```code``` → code
    text = re.sub(r'```([^`]+)```', r'\1', text)

    return text.strip()
```

---

## 6. Thread Handling Strategy

### 6.1 The Thread Challenge

Slack threads are deeply nested but the API returns them separately:
1. `conversations.history` returns top-level messages only (with `reply_count`)
2. `conversations.replies` must be called per thread to get replies

For a channel with 100 messages where 20 have threads:
- Discord: 1 API call
- Slack: 1 + 20 = 21 API calls minimum

### 6.2 Optimization Strategies

#### Strategy A: Lazy Thread Loading
Only fetch thread replies when summarizing, not during ingestion.

```python
async def fetch_for_summary(channel_id: str, start: datetime, end: datetime):
    messages = await fetch_channel_history(channel_id, start, end)

    # Identify threads worth expanding (3+ replies, recent activity)
    threads_to_expand = [
        m for m in messages
        if m.get("reply_count", 0) >= 3
        and float(m.get("latest_reply", "0")) > start.timestamp()
    ]

    # Batch fetch threads with rate limiting
    for thread_parent in threads_to_expand:
        replies = await fetch_thread_replies(channel_id, thread_parent["ts"])
        messages.extend(replies)

    return messages
```

#### Strategy B: Thread Summary in Metadata
Don't fetch thread replies; instead, include thread metadata in summary prompt.

```python
# Include in prompt context
"Message from @alice: 'What should we do about the bug?'
  └─ [Thread: 8 replies from 3 participants, latest 2h ago]"
```

#### Strategy C: Selective Thread Expansion
Use heuristics to decide which threads matter:
- Threads with 5+ replies
- Threads with reactions on replies
- Threads mentioned by name/topic
- Threads with attachments

### 6.3 Recommendation

For v1: **Strategy B** (metadata only) with fallback to **Strategy A** for "detailed" summary requests. This minimizes API calls while preserving context.

---

## 7. Enterprise Grid Considerations

### 7.1 What is Enterprise Grid?

Slack Enterprise Grid is a multi-workspace deployment for large organizations:
- One "Enterprise" with multiple "Workspaces"
- Central admin console
- Shared channels across workspaces
- Organization-wide apps (install once, works everywhere)

### 7.2 Grid-Specific Challenges

| Feature | Standard Slack | Enterprise Grid |
|---------|---------------|-----------------|
| App installation | Per-workspace | Org-wide or per-workspace |
| Token scope | Single workspace | Org-wide token option |
| Channel discovery | Simple | Cross-workspace channels |
| Admin override | Workspace admin | Enterprise admin |
| Compliance | Workspace-level | Org-wide DLP, eDiscovery |
| Audit logs | Limited | Full audit trail |

### 7.3 Recommendation for Grid

1. **Start with per-workspace installation** (simpler)
2. Add org-wide installation support later
3. Clearly document compliance implications
4. Add Enterprise admin approval workflow if needed

---

## 8. Privacy & Compliance

### 8.1 Data Handling Requirements

| Concern | Slack Specifics | Mitigation |
|---------|-----------------|------------|
| **Message retention** | Must respect workspace retention policies | Honor `retention_policy` in workspace settings |
| **DLP (Data Loss Prevention)** | Enterprise Grid has DLP rules | Filter messages flagged by DLP before summarizing |
| **eDiscovery hold** | Legal holds freeze message deletion | Do not delete messages under legal hold |
| **GDPR/Right to be forgotten** | User deletion requests | Support `user_data_deleted` event, purge user data |
| **External sharing** | Slack Connect channels | Configurable: skip or include external messages |
| **PII in summaries** | Emails, phone numbers in messages | Anonymization option before sending to Claude |

### 8.2 Required Event Subscriptions for Compliance

```python
COMPLIANCE_EVENTS = [
    "user_change",           # User profile updates (for name changes)
    "team_domain_change",    # Workspace URL changes
    "app_uninstalled",       # Our app was removed - delete tokens
    "tokens_revoked",        # Token invalidated
    "message_deleted",       # Remove from our storage
    "file_deleted",          # Remove file references
]
```

---

## 9. Implementation Phases

### Phase 1: Foundation (4-6 weeks)
- [ ] Slack OAuth flow in dashboard
- [ ] Token storage per-workspace
- [ ] Basic `conversations.history` polling
- [ ] Message normalization (no threads)
- [ ] Slack adapter implementing `IngestAdapter` interface

### Phase 2: Real-Time (3-4 weeks)
- [ ] Events API endpoint
- [ ] Real-time message ingestion
- [ ] Event deduplication
- [ ] Backfill capability on install

### Phase 3: Threads & Files (3-4 weeks)
- [ ] Thread reply fetching
- [ ] Thread metadata in summaries
- [ ] File download and storage
- [ ] File expiration handling

### Phase 4: Advanced (4-6 weeks)
- [ ] Private channel support
- [ ] DM support (opt-in)
- [ ] Slack Connect handling
- [ ] Enterprise Grid org-wide install
- [ ] Compliance event handling

### Phase 5: Polish (2-3 weeks)
- [ ] Rate limit optimization
- [ ] Caching layer
- [ ] Dashboard UI for Slack workspaces
- [ ] Documentation

**Total Estimated Effort: 16-23 weeks**

---

## 10. Technical Architecture

### 10.1 New Components

```
src/
├── slack/
│   ├── __init__.py
│   ├── client.py              # Slack API client wrapper
│   ├── oauth.py               # OAuth flow handlers
│   ├── events.py              # Events API webhook handler
│   ├── normalizer.py          # Message → ProcessedMessage
│   ├── thread_handler.py      # Thread fetching logic
│   ├── file_handler.py        # File download/storage
│   └── rate_limiter.py        # Slack-specific rate limiting
├── data/
│   └── slack_token_repository.py  # Workspace token storage
└── dashboard/
    └── routes/
        └── slack.py           # Slack-specific API endpoints
```

### 10.2 Database Schema

```sql
-- Slack workspace installations
CREATE TABLE slack_workspaces (
    workspace_id TEXT PRIMARY KEY,      -- T0XXXXXXX
    workspace_name TEXT NOT NULL,
    workspace_domain TEXT,              -- foo.slack.com
    bot_token TEXT NOT NULL,            -- Encrypted
    bot_user_id TEXT NOT NULL,
    installed_by TEXT NOT NULL,
    installed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scopes TEXT NOT NULL,               -- JSON array
    is_enterprise BOOLEAN DEFAULT FALSE,
    enterprise_id TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMP,
    metadata TEXT                       -- JSON
);

-- Slack channels being tracked
CREATE TABLE slack_channels (
    channel_id TEXT PRIMARY KEY,        -- C0XXXXXXX
    workspace_id TEXT NOT NULL REFERENCES slack_workspaces(workspace_id),
    channel_name TEXT NOT NULL,
    channel_type TEXT NOT NULL,         -- 'public', 'private', 'im', 'mpim'
    is_shared BOOLEAN DEFAULT FALSE,    -- Slack Connect
    is_archived BOOLEAN DEFAULT FALSE,
    auto_summarize BOOLEAN DEFAULT FALSE,
    summary_schedule TEXT,              -- Cron expression
    last_message_ts TEXT,               -- For polling cursor
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Map Slack users to display names
CREATE TABLE slack_users (
    user_id TEXT PRIMARY KEY,           -- U0XXXXXXX
    workspace_id TEXT NOT NULL REFERENCES slack_workspaces(workspace_id),
    display_name TEXT NOT NULL,
    real_name TEXT,
    email TEXT,
    is_bot BOOLEAN DEFAULT FALSE,
    avatar_url TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_slack_channels_workspace ON slack_channels(workspace_id);
CREATE INDEX idx_slack_users_workspace ON slack_users(workspace_id);
```

---

## 11. API Endpoints

### 11.1 New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/slack/install` | Redirect to Slack OAuth |
| `GET` | `/slack/oauth/callback` | OAuth callback handler |
| `POST` | `/slack/events` | Events API webhook |
| `GET` | `/slack/workspaces` | List connected workspaces |
| `GET` | `/slack/workspaces/{id}` | Workspace details |
| `DELETE` | `/slack/workspaces/{id}` | Disconnect workspace |
| `GET` | `/slack/workspaces/{id}/channels` | List channels |
| `POST` | `/slack/workspaces/{id}/channels/{ch}/summarize` | Summarize channel |
| `PUT` | `/slack/workspaces/{id}/channels/{ch}/tracking` | Configure auto-summarize |

---

## 12. Risk Assessment

### 12.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Rate limit exhaustion | High | Medium | Aggressive caching, smart polling |
| Thread fetch explosion | High | High | Lazy loading, metadata-only mode |
| Token revocation | Medium | High | Graceful degradation, re-auth flow |
| File URL expiration | High | Medium | Immediate download or permalink-only |
| Event deduplication failure | Medium | Low | Idempotent processing, dedup table |

### 12.2 Business Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Slack Marketplace rejection | Medium | High | Start with private distribution |
| Enterprise compliance concerns | Medium | High | Clear data handling documentation |
| Free tier limitations | High | High | Document, recommend paid plans |
| Slack pricing changes | Low | Medium | Abstract away Slack-specific logic |

---

## 13. Cost Estimation

### 13.1 Development Effort

| Phase | Weeks | Engineers |
|-------|-------|-----------|
| Foundation | 5 | 1-2 |
| Real-Time | 4 | 1 |
| Threads & Files | 4 | 1 |
| Advanced | 5 | 1-2 |
| Polish | 2 | 1 |
| **Total** | **20** | **1-2** |

### 13.2 Infrastructure

- Events API endpoint: Existing FastAPI server (no additional cost)
- File storage: ~10GB per active workspace per year (~$0.25/month/workspace)
- API calls: Free (we're the customer, not calling OpenAI for Slack API)

---

## 14. Decision Matrix

### 14.1 Build vs Buy

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **Build in-house** | Full control, integrates with existing architecture | Development effort | ✅ Recommended |
| **Slack native summaries** | Zero effort | No customization, no integration | ❌ Not suitable |
| **Third-party (e.g., Summarize.tech)** | Quick | No Discord integration, data leaves system | ❌ Not suitable |

### 14.2 Go/No-Go Criteria

| Criterion | Requirement | Status |
|-----------|-------------|--------|
| Ingest Adapter pattern exists | Yes | ✅ ADR-002 established |
| OAuth infrastructure available | Yes | ✅ Dashboard has auth system |
| Rate limiting solution | Yes | ✅ Can extend existing |
| Thread handling strategy | Yes | ✅ Defined in this ADR |
| Compliance story | Yes | ✅ Outlined above |
| Resource availability | 1-2 engineers for 20 weeks | ⏳ To be confirmed |

---

## 15. Conclusion

### 15.1 Feasibility Assessment

**Overall: FEASIBLE with caveats**

| Dimension | Assessment |
|-----------|------------|
| **Technical** | ✅ Achievable using existing patterns |
| **API Access** | ✅ Slack APIs are well-documented |
| **Rate Limits** | ⚠️ Challenging but manageable |
| **Threading** | ⚠️ Requires careful design |
| **Compliance** | ⚠️ Enterprise Grid adds complexity |
| **Effort** | ⚠️ 16-23 weeks significant investment |

### 15.2 Recommended Approach

1. **Start with private/internal deployment** (no Marketplace)
2. **Target paid Slack workspaces** (free tier too limited)
3. **Use Events API + polling hybrid**
4. **Implement thread metadata first**, expand later
5. **Skip Slack Connect initially**
6. **Build on ADR-002 Ingest Adapter pattern**

### 15.3 Next Steps

1. [ ] Get stakeholder approval for 20-week investment
2. [ ] Set up Slack app in test workspace
3. [ ] Implement OAuth flow (Phase 1)
4. [ ] Validate rate limit assumptions with real data
5. [ ] Finalize thread handling strategy based on testing

---

## 16. User Interface Paradigm Differences

### 16.1 Discord-Centric Current UI

The current SummaryBot-NG UI is heavily Discord-oriented:

```typescript
// Current type assumptions (src/frontend/src/types/index.ts)
export interface Guild {
  id: string;
  name: string;
  icon: string | null;
  channels: Channel[];
  categories: Category[];  // ← Discord-only concept
}
```

**Current UI Flow:**
1. User logs in via Discord OAuth
2. Dashboard shows "Your Servers" (Discord guilds)
3. User selects a server → sees channels grouped by categories
4. Summaries are scoped to guild → channel hierarchy

### 16.2 Slack-Specific UI Requirements

Slack users expect different interaction patterns:

| Pattern | Discord UI | Slack UI Expectation |
|---------|------------|---------------------|
| **Navigation** | Server list → Channels | Workspace → Channels (flat) |
| **Categories** | Visual groupings | ❌ Not applicable |
| **Threads** | Separate tab/view | Inline with messages |
| **DMs** | Separate DM section | Integrated in channel list |
| **Search** | Per-channel | Workspace-wide prominent |
| **Reactions** | Emoji picker | Similar but fewer custom emoji |
| **Mentions** | @user or @role | @user, @channel, @here |
| **Workspace branding** | Server icon | Workspace icon + name |

### 16.3 Proposed Unified Navigation

To support multiple platforms, the UI needs platform-agnostic terminology:

```
Current (Discord-only):
├── Your Servers ← Discord terminology
│   ├── Gaming Server
│   └── Work Server

Proposed (Multi-platform):
├── Your Sources ← Platform-agnostic
│   ├── 🎮 Gaming Server (Discord)
│   ├── 💼 Acme Corp (Slack)
│   └── 📱 Team Chat (WhatsApp)
```

**Implementation:**
```typescript
// Proposed unified type (aligns with ADR-026)
export interface Source {
  id: string;
  name: string;
  icon: string | null;
  type: SourceType;  // 'discord' | 'slack' | 'whatsapp'
  channels: UnifiedChannel[];
  // categories only for Discord
  categories?: Category[];
}

export interface UnifiedChannel {
  id: string;
  name: string;
  type: ChannelType;
  source_type: SourceType;
  // Thread count for Slack channels
  active_threads?: number;
}
```

### 16.4 Platform-Specific UI Adaptations

#### Slack-Specific UI Elements

1. **Thread Indicators**: Show inline thread reply counts
   ```
   ├── #engineering
   │   ├── "Deploy v2.0 to prod" [15 replies] ← Slack thread indicator
   │   └── "Outage post-mortem"  [42 replies]
   ```

2. **Workspace Selector**: Slack users may have multiple workspaces
   ```
   Acme Corp (Slack) ▼
   ├── #general
   ├── #engineering
   └── #random
   ```

3. **Channel Privacy Icons**: Slack distinguishes public/private more prominently
   ```
   # public-channel     ← Hash = public
   🔒 private-channel   ← Lock = private
   ```

4. **Slack Connect Badge**: Mark external channels
   ```
   #shared-with-partner 🔗  ← External collaboration
   ```

#### Discord-Specific UI Elements (Retain)

1. **Categories**: Continue showing category groupings
2. **Roles**: Show role-based permissions
3. **Forum Channels**: Dedicated forum post views

---

## 17. Multi-Organization Model

### 17.1 Reference: ADR-026 Linked Sources Architecture

ADR-026 establishes the definitive architecture for organizations with multiple communication platforms. Key concepts:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORGANIZATION: Acme Inc                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│   │   Discord    │     │    Slack     │     │   WhatsApp   │   │
│   │  Server A    │     │  Workspace   │     │   Group      │   │
│   └──────┬───────┘     └──────┬───────┘     └──────┬───────┘   │
│          │                    │                    │            │
│          └────────────────────┼────────────────────┘            │
│                               │                                  │
│                    ┌──────────▼──────────┐                       │
│                    │  Primary Guild ID   │                       │
│                    │  (Unified Identity) │                       │
│                    └─────────────────────┘                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 17.2 Linked Sources Pattern

From ADR-026, non-Discord sources link to a Discord guild for:

1. **Permission inheritance**: Discord guild membership controls access
2. **Unified billing**: One subscription per organization
3. **Cross-platform summaries**: Combine Discord + Slack + WhatsApp in single digest

```sql
-- ADR-026 schema (existing)
CREATE TABLE guild_linked_sources (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL REFERENCES guilds(id),
    source_type TEXT NOT NULL,          -- 'slack' | 'whatsapp'
    source_id TEXT NOT NULL,            -- Slack workspace_id or WhatsApp group_id
    source_name TEXT,
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    linked_by TEXT,                      -- User who connected
    permissions TEXT,                    -- JSON: what this link allows
    UNIQUE(guild_id, source_type, source_id)
);
```

### 17.3 Multi-Guild Organizations

For organizations with **multiple Discord servers** (e.g., separate servers per team/region):

```
Acme Inc Organization
├── Discord: Acme Engineering (Guild A)
│   ├── Linked: Slack Engineering Workspace
│   └── Linked: WhatsApp Eng On-Call
├── Discord: Acme Sales (Guild B)
│   ├── Linked: Slack Sales Workspace
│   └── Linked: WhatsApp Sales Team
└── Discord: Acme Global (Guild C) ← Company-wide
    └── Linked: (none, Discord-only)
```

**Summaries can span:**
- Single source: Just #engineering channel in Discord
- Cross-platform: Discord #eng + Slack #incidents + WhatsApp alerts
- Organization-wide: All sources across all guilds (requires org-level access)

### 17.4 Slack Integration Points

For Slack specifically, the linked sources model means:

```python
# When installing Slack app
async def link_slack_workspace(guild_id: str, workspace_id: str, installer: str):
    """Link a Slack workspace to a Discord guild."""

    # Verify installer has permission on Discord guild
    if not await has_guild_permission(installer, guild_id, "manage_integrations"):
        raise PermissionError("Must have Manage Integrations on Discord server")

    # Create link
    await db.execute("""
        INSERT INTO guild_linked_sources
        (id, guild_id, source_type, source_id, source_name, linked_by)
        VALUES (?, ?, 'slack', ?, ?, ?)
    """, [generate_id(), guild_id, workspace_id, workspace_name, installer])

    # Store Slack tokens
    await slack_token_store.save(workspace_id, tokens)
```

### 17.5 Dashboard Access Control

Access follows Discord guild membership (ADR-026):

```
User has access to Discord Guild A
  ↓
Can view all sources linked to Guild A
  ↓
Including Slack Workspace X (linked to Guild A)
  ↓
Even if user is NOT in Slack Workspace X directly
```

This simplifies access control:
- No need for separate Slack user management
- Discord roles control dashboard access
- Slack bot token handles API access

### 17.6 UI Implementation for Multi-Source

```typescript
// Dashboard navigation with linked sources
function SourceNavigation({ guild }: { guild: Guild }) {
  const linkedSources = useLinkedSources(guild.id);

  return (
    <nav>
      {/* Primary Discord Guild */}
      <SourceItem
        type="discord"
        name={guild.name}
        icon={guild.icon}
        channels={guild.channels}
      />

      {/* Linked Sources */}
      {linkedSources.map(source => (
        <SourceItem
          key={source.id}
          type={source.source_type}
          name={source.source_name}
          icon={source.icon}
          channels={source.channels}
        />
      ))}
    </nav>
  );
}
```

### 17.7 Summary Scope Options

With multi-source support, summaries can target:

| Scope | Description | Use Case |
|-------|-------------|----------|
| `single_channel` | One channel from one source | Daily #general summary |
| `cross_channel` | Multiple channels, one source | Weekly engineering digest |
| `cross_source` | Channels from multiple sources | Incident retrospective |
| `organization` | All sources in org | Executive monthly summary |

```python
# Example: Cross-source summary request
{
    "scope": "cross_source",
    "sources": [
        {"type": "discord", "id": "guild_123", "channels": ["ch_1", "ch_2"]},
        {"type": "slack", "id": "T0ABC", "channels": ["C0DEF"]},
        {"type": "whatsapp", "id": "grp_456", "channels": ["all"]}
    ],
    "time_range": {"start": "2026-04-01", "end": "2026-04-07"},
    "summary_type": "comprehensive"
}
```

---

## 18. References

- [Slack API Documentation](https://api.slack.com/)
- [Slack Web API Methods](https://api.slack.com/methods)
- [Slack Events API](https://api.slack.com/apis/connections/events-api)
- [Slack OAuth 2.0](https://api.slack.com/authentication/oauth-v2)
- [Slack Rate Limits](https://api.slack.com/docs/rate-limits)
- [Slack Enterprise Grid](https://api.slack.com/enterprise/grid)
- [ADR-002: WhatsApp Data Source Integration](./002-whatsapp-datasource-integration-summarybotng.md)
- [ADR-026: Multi-Platform Source Architecture](./026-multi-platform-source-architecture.md)
- [Slack mrkdwn Format](https://api.slack.com/reference/surfaces/formatting)
