# ADR-001: WhatsApp Conversation Reader Bot

**Status:** Proposed
**Date:** 2026-02-11
**Decision Makers:** Project Team
**Context Domain:** Messaging Integration / Conversation Intelligence

---

## 1. Context & Problem Statement

We need to build a WhatsApp bot that can **read all conversations being exchanged** on a WhatsApp account. The system must capture incoming and outgoing messages in real-time, persist them, and expose them for downstream consumption (analytics, search, export, AI processing).

### Key Requirements

1. **Read all conversations** — incoming and outgoing messages across all chats (individual and group)
2. **Real-time capture** — messages must be captured as they arrive, not via polling
3. **Persistent storage** — full chat history must be stored durably
4. **Media handling** — support for images, videos, documents, audio, stickers, and contacts
5. **Metadata capture** — timestamps, sender info, read receipts, delivery status, reactions
6. **Searchable** — conversations must be queryable by contact, date range, content keywords
7. **Exportable** — ability to export conversations in structured formats (JSON, CSV)

---

## 2. Decision Drivers

| Driver | Weight | Notes |
|--------|--------|-------|
| Ability to read ALL conversations (not just bot-initiated) | Critical | Business API only receives messages sent TO the business number |
| No dependency on Meta business verification | High | Reduces onboarding friction |
| Real-time message capture | High | Webhook or socket-based, not polling |
| Multi-device support | High | WhatsApp multi-device is now standard |
| Cost | Medium | Avoid per-message pricing for read-only monitoring |
| Reliability & maintainability | Medium | Unofficial APIs can break on WhatsApp updates |
| Compliance & ToS risk | Medium | Must be acknowledged and mitigated |

---

## 3. Options Considered

### Option A: WhatsApp Cloud API (Official Business API)

**How it works:** Meta-hosted API. Register a WhatsApp Business Account, configure webhooks, receive messages sent to the business phone number.

| Pros | Cons |
|------|------|
| Official, stable, well-documented | Only receives messages sent TO the business number |
| Webhook-based real-time delivery | Cannot read conversations between other users |
| Media download support | Requires Meta Business verification |
| 500 msg/sec throughput | Per-message pricing (template messages) |
| Node.js SDK available | 24-hour customer service window limitation |

**Verdict:** **Not suitable.** The Cloud API is designed for business-customer communication. It cannot observe conversations on an existing personal/business WhatsApp account. It only sees messages explicitly sent to the registered business number.

### Option B: Baileys (Unofficial WhatsApp Web API)

**How it works:** TypeScript/JavaScript library that connects to WhatsApp Web via WebSocket, using the Linked Devices protocol. Authenticates by scanning a QR code, then maintains a persistent session.

| Pros | Cons |
|------|------|
| Reads ALL conversations (personal + group) | Unofficial — may break on WhatsApp protocol changes |
| Real-time via WebSocket events | Violates WhatsApp ToS if used for automation/surveillance |
| No per-message cost | No SLA or support guarantees |
| Multi-device compatible | Requires QR code scan for initial auth |
| Full media support | Must self-manage session persistence |
| TypeScript-native, active community | Risk of account ban if flagged |
| In-memory store or custom storage | Node 17+ required |

**Verdict:** **Best fit for the requirement.** Baileys is the only option that provides visibility into all conversations on an account, not just bot-directed messages.

### Option C: whatsapp-web.js (Puppeteer-based)

**How it works:** Uses Puppeteer to automate a headless Chromium browser running WhatsApp Web.

| Pros | Cons |
|------|------|
| Reads all conversations | Heavy resource usage (headless browser) |
| Mature library | Slower than WebSocket-based approach |
| Good community | Browser dependency adds fragility |

**Verdict:** **Viable but inferior to Baileys.** The browser overhead is unnecessary when a direct WebSocket connection is available.

### Option D: Third-Party Aggregator APIs (Twilio, Unipile, etc.)

**How it works:** SaaS platforms that wrap WhatsApp APIs with additional features.

| Pros | Cons |
|------|------|
| Managed infrastructure | Same Cloud API limitations (business-only) |
| Additional features (analytics, CRM) | Per-message costs add up |
| Support & SLA | Vendor lock-in |

**Verdict:** **Not suitable.** Same fundamental limitation as Option A — cannot read all account conversations.

---

## 4. Decision

**We will use Baileys (`@whiskeysockets/baileys`)** as the WhatsApp connectivity layer, wrapped in a Domain-Driven Design architecture that separates the WhatsApp protocol concerns from the business logic.

### Rationale

1. **Only option that meets the core requirement** of reading all conversations
2. **WebSocket-based** — efficient, real-time, no browser overhead
3. **TypeScript-native** — aligns with the project's Node.js/TypeScript stack
4. **Active maintenance** — WhiskeySockets fork is actively maintained with multi-device support
5. **Flexible storage** — no opinionated storage layer; we control persistence entirely

### Risk Acknowledgment

| Risk | Severity | Mitigation |
|------|----------|------------|
| WhatsApp protocol changes break Baileys | High | Pin dependency version, monitor releases, have fallback to whatsapp-web.js |
| Account ban for automation | Medium | Rate-limit operations, avoid sending messages, read-only mode, use dedicated number |
| ToS violation | Medium | Use only on accounts you own, for personal/internal use, not for surveillance of others |
| Session invalidation | Low | Implement automatic re-auth flow with QR code re-scan notification |

---

## 5. Domain-Driven Design (DDD) Architecture

### 5.1 Strategic Design — Bounded Contexts

```
+------------------------------------------------------------------+
|                      WhatsApp Reader System                       |
+------------------------------------------------------------------+
|                                                                    |
|  +-------------------+    +-------------------+    +-------------+ |
|  |    Connection      |    |   Conversation    |    |   Export    | |
|  |    Context         |--->|   Context         |--->|   Context   | |
|  |                    |    |                    |    |             | |
|  | - Auth/Session     |    | - Messages        |    | - Formats   | |
|  | - QR Code          |    | - Chats           |    | - Filters   | |
|  | - Socket Lifecycle |    | - Contacts        |    | - Schedules | |
|  | - Reconnection     |    | - Groups          |    |             | |
|  +-------------------+    | - Media           |    +-------------+ |
|           |                | - Search          |          ^        |
|           |                +-------------------+          |        |
|           |                        |                      |        |
|           v                        v                      |        |
|  +-------------------+    +-------------------+           |        |
|  |    Notification    |    |   Storage         |-----------+        |
|  |    Context         |    |   Context         |                   |
|  |                    |    |                    |                   |
|  | - Connection State |    | - Persistence     |                   |
|  | - Error Alerts     |    | - Indexing        |                   |
|  | - QR Re-scan       |    | - Media Files     |                   |
|  +-------------------+    | - Retention       |                   |
|                            +-------------------+                   |
+------------------------------------------------------------------+
```

### 5.2 Bounded Context Definitions

#### 5.2.1 Connection Context

**Responsibility:** Manages the lifecycle of the WhatsApp Web connection via Baileys.

**Aggregates:**
- `Session` — root aggregate; holds auth credentials, connection state, device info

**Domain Events:**
- `ConnectionEstablished`
- `ConnectionLost`
- `QRCodeGenerated`
- `SessionAuthenticated`
- `SessionInvalidated`

**Key Behaviors:**
- Initialize socket connection with Baileys
- Handle QR code generation and scanning flow
- Manage auth state persistence (creds.json)
- Auto-reconnect with exponential backoff
- Emit connection lifecycle events

```typescript
// src/connection/domain/entities/Session.ts
interface Session {
  id: string;
  phoneNumber: string;
  status: 'disconnected' | 'connecting' | 'qr_pending' | 'connected';
  lastConnected: Date | null;
  authState: AuthenticationState;
  deviceInfo: DeviceInfo | null;
}
```

#### 5.2.2 Conversation Context (Core Domain)

**Responsibility:** The heart of the system. Captures, normalizes, and manages all message and chat data flowing through the WhatsApp account.

**Aggregates:**

- `Chat` — root aggregate representing a conversation (individual or group)
- `Message` — entity within a Chat; represents a single message
- `Contact` — value object; participant identity
- `MediaAttachment` — value object; metadata for media files

**Domain Events:**
- `MessageReceived` — incoming message from another user
- `MessageSent` — outgoing message from the account owner
- `MessageUpdated` — edit, delete, or status change
- `MessageReactionAdded`
- `ChatCreated`
- `ChatArchived`
- `GroupParticipantChanged`
- `ReadReceiptUpdated`
- `PresenceUpdated` (typing indicators, online status)

**Key Behaviors:**
- Capture and normalize all incoming/outgoing messages
- Track message delivery status (sent, delivered, read)
- Handle message types: text, image, video, audio, document, sticker, location, contact, poll, reaction
- Track group metadata (participants, admins, subject, description)
- Full-text search across message content
- Filter by contact, chat, date range, message type

```typescript
// src/conversation/domain/entities/Chat.ts
interface Chat {
  id: ChatId;               // WhatsApp JID
  type: 'individual' | 'group' | 'broadcast';
  name: string;
  participants: Contact[];
  messages: Message[];
  unreadCount: number;
  lastMessageAt: Date;
  metadata: ChatMetadata;
}

// src/conversation/domain/entities/Message.ts
interface Message {
  id: MessageId;
  chatId: ChatId;
  sender: Contact;
  timestamp: Date;
  type: MessageType;
  content: TextContent | MediaContent | LocationContent | ContactContent;
  status: 'pending' | 'sent' | 'delivered' | 'read';
  isFromMe: boolean;
  quotedMessage: MessageId | null;
  reactions: Reaction[];
  isForwarded: boolean;
  isEdited: boolean;
  isDeleted: boolean;
}

type MessageType =
  | 'text'
  | 'image'
  | 'video'
  | 'audio'
  | 'document'
  | 'sticker'
  | 'location'
  | 'contact'
  | 'poll'
  | 'reaction';
```

#### 5.2.3 Storage Context

**Responsibility:** Persists all conversation data and media files. Provides query and indexing capabilities.

**Aggregates:**
- `MessageStore` — manages message persistence and retrieval
- `MediaStore` — manages binary media file storage

**Key Behaviors:**
- Persist messages with full metadata
- Store media files (images, videos, documents, audio)
- Index messages for full-text search
- Enforce retention policies (optional TTL)
- Provide paginated query interface
- Handle storage migrations

**Storage Strategy:**

| Data Type | Storage | Rationale |
|-----------|---------|-----------|
| Messages & metadata | SQLite (via better-sqlite3) | Embedded, zero-config, full SQL, FTS5 for search |
| Media files | Local filesystem (organized by chat/date) | Simple, no external deps, easy backup |
| Auth credentials | Encrypted JSON file | Baileys default, small payload |
| Session state | SQLite | Co-located with messages |

```typescript
// src/storage/domain/repositories/MessageRepository.ts
interface MessageRepository {
  save(message: Message): Promise<void>;
  saveBatch(messages: Message[]): Promise<void>;
  findById(id: MessageId): Promise<Message | null>;
  findByChat(chatId: ChatId, options: PaginationOptions): Promise<Message[]>;
  search(query: SearchQuery): Promise<SearchResult>;
  countByChat(chatId: ChatId): Promise<number>;
  deleteOlderThan(date: Date): Promise<number>;
}

interface SearchQuery {
  text?: string;                 // full-text search
  chatId?: ChatId;               // filter by chat
  senderId?: string;             // filter by sender
  messageType?: MessageType;     // filter by type
  dateFrom?: Date;               // date range start
  dateTo?: Date;                 // date range end
  limit: number;
  offset: number;
}
```

#### 5.2.4 Export Context

**Responsibility:** Transforms stored conversation data into various output formats.

**Supported Formats:**
- **JSON** — full structured export, suitable for programmatic consumption
- **CSV** — tabular export for spreadsheet analysis
- **HTML** — human-readable chat view (WhatsApp-style)
- **Plain Text** — simple text transcript

**Key Behaviors:**
- Export single chat or all chats
- Filter by date range, message type
- Include or exclude media references
- Stream large exports to avoid memory issues

```typescript
// src/export/domain/services/ExportService.ts
interface ExportService {
  exportChat(chatId: ChatId, format: ExportFormat, options: ExportOptions): Promise<ExportResult>;
  exportAll(format: ExportFormat, options: ExportOptions): Promise<ExportResult>;
  scheduleExport(schedule: CronExpression, config: ExportConfig): Promise<void>;
}

interface ExportOptions {
  dateFrom?: Date;
  dateTo?: Date;
  includeMedia: boolean;
  messageTypes?: MessageType[];
  outputPath: string;
}

type ExportFormat = 'json' | 'csv' | 'html' | 'txt';
```

#### 5.2.5 Notification Context

**Responsibility:** Alerts operators about system-level events that require attention.

**Key Events:**
- Connection lost / reconnected
- QR code needs re-scanning
- Storage approaching capacity
- Export completed
- Error thresholds exceeded

**Channels:**
- Console logging (default)
- Webhook (HTTP POST to configurable URL)
- Email (optional, via SMTP)

---

### 5.3 Context Map — Integration Patterns

```
Connection ──[Domain Events]──> Conversation
    │                               │
    │                               ├──[Domain Events]──> Storage
    │                               │                        │
    │                               │                        ├──[Query]──> Export
    │                               │                        │
    └──[Domain Events]──> Notification <────[Events]─────────┘
```

| Upstream | Downstream | Pattern |
|----------|------------|---------|
| Connection | Conversation | **Published Language** — Connection emits raw Baileys events; Conversation translates to domain messages |
| Conversation | Storage | **Repository Pattern** — Conversation entities persisted via Storage repositories |
| Storage | Export | **Query/Read Model** — Export reads from Storage using optimized queries |
| Connection, Storage | Notification | **Event Subscriber** — Notification subscribes to lifecycle and error events |

---

### 5.4 Tactical Design — Layer Architecture

```
src/
├── connection/
│   ├── domain/
│   │   ├── entities/          # Session
│   │   ├── events/            # ConnectionEstablished, QRCodeGenerated, etc.
│   │   └── services/          # ConnectionManager
│   ├── infrastructure/
│   │   ├── BaileysAdapter.ts  # Baileys socket wrapper (Anti-Corruption Layer)
│   │   └── AuthStateStore.ts  # creds.json persistence
│   └── application/
│       └── ConnectUseCase.ts  # Orchestrates connection lifecycle
│
├── conversation/
│   ├── domain/
│   │   ├── entities/          # Chat, Message, Contact, MediaAttachment
│   │   ├── value-objects/     # ChatId, MessageId, MessageType, Reaction
│   │   ├── events/            # MessageReceived, MessageSent, etc.
│   │   └── services/          # MessageNormalizer, ChatTracker
│   ├── infrastructure/
│   │   └── BaileysMessageMapper.ts  # Maps Baileys WAMessage to domain Message
│   └── application/
│       ├── CaptureMessageUseCase.ts
│       ├── SearchMessagesUseCase.ts
│       └── GetChatHistoryUseCase.ts
│
├── storage/
│   ├── domain/
│   │   ├── repositories/      # MessageRepository, ChatRepository, MediaRepository
│   │   └── services/          # RetentionPolicy, StorageMigrator
│   └── infrastructure/
│       ├── SQLiteMessageRepository.ts
│       ├── SQLiteChatRepository.ts
│       ├── FileSystemMediaStore.ts
│       └── migrations/
│
├── export/
│   ├── domain/
│   │   └── services/          # ExportService
│   └── infrastructure/
│       ├── JsonExporter.ts
│       ├── CsvExporter.ts
│       ├── HtmlExporter.ts
│       └── TextExporter.ts
│
├── notification/
│   ├── domain/
│   │   └── services/          # NotificationService
│   └── infrastructure/
│       ├── ConsoleNotifier.ts
│       └── WebhookNotifier.ts
│
├── shared/
│   ├── domain/
│   │   ├── EventBus.ts        # In-process event bus
│   │   └── DomainEvent.ts     # Base event type
│   └── infrastructure/
│       ├── Logger.ts
│       └── Config.ts
│
└── main.ts                    # Composition root / bootstrap
```

---

### 5.5 Key Anti-Corruption Layer: BaileysAdapter

The `BaileysAdapter` is the most critical infrastructure component. It wraps the Baileys library and translates its events and data structures into our domain language, isolating the rest of the system from Baileys' internals.

```typescript
// src/connection/infrastructure/BaileysAdapter.ts
class BaileysAdapter {
  private socket: ReturnType<typeof makeWASocket>;
  private eventBus: EventBus;

  async connect(): Promise<void> {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info');

    this.socket = makeWASocket({
      auth: state,
      printQRInTerminal: true,
      // Read-only mode: we minimize outgoing activity
    });

    // Connection events
    this.socket.ev.on('connection.update', (update) => {
      if (update.connection === 'open') {
        this.eventBus.publish(new ConnectionEstablished(/*...*/));
      }
      if (update.qr) {
        this.eventBus.publish(new QRCodeGenerated(update.qr));
      }
    });

    // Message events — the core of conversation reading
    this.socket.ev.on('messages.upsert', ({ messages, type }) => {
      for (const raw of messages) {
        const domainMessage = BaileysMessageMapper.toDomain(raw);
        this.eventBus.publish(new MessageReceived(domainMessage));
      }
    });

    // Message status updates (delivered, read)
    this.socket.ev.on('messages.update', (updates) => {
      for (const update of updates) {
        this.eventBus.publish(new MessageUpdated(update.key, update.update));
      }
    });

    // Chat updates
    this.socket.ev.on('chats.upsert', (chats) => { /*...*/ });
    this.socket.ev.on('chats.update', (chats) => { /*...*/ });

    // Group updates
    this.socket.ev.on('groups.upsert', (groups) => { /*...*/ });
    this.socket.ev.on('group-participants.update', (event) => { /*...*/ });

    // Presence (typing indicators)
    this.socket.ev.on('presence.update', (presence) => { /*...*/ });

    // Persist auth credentials on update
    this.socket.ev.on('creds.update', saveCreds);
  }

  async downloadMedia(message: WAMessage): Promise<Buffer> {
    return await downloadMediaMessage(message, 'buffer', {});
  }

  async disconnect(): Promise<void> {
    this.socket?.end(undefined);
  }
}
```

---

## 6. Data Model (SQLite Schema)

```sql
-- Chats table
CREATE TABLE chats (
    id TEXT PRIMARY KEY,                -- WhatsApp JID (e.g., 1234567890@s.whatsapp.net)
    type TEXT NOT NULL,                  -- 'individual', 'group', 'broadcast'
    name TEXT,
    participant_count INTEGER DEFAULT 0,
    last_message_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata TEXT                        -- JSON blob for extra fields
);

-- Messages table
CREATE TABLE messages (
    id TEXT PRIMARY KEY,                -- WhatsApp message ID
    chat_id TEXT NOT NULL,
    sender_jid TEXT NOT NULL,
    sender_name TEXT,
    timestamp TEXT NOT NULL,
    type TEXT NOT NULL,                  -- 'text', 'image', 'video', etc.
    content TEXT,                        -- text content or caption
    media_path TEXT,                     -- local file path for media
    media_mimetype TEXT,
    media_size INTEGER,
    status TEXT DEFAULT 'received',      -- 'pending', 'sent', 'delivered', 'read'
    is_from_me INTEGER DEFAULT 0,
    quoted_message_id TEXT,
    is_forwarded INTEGER DEFAULT 0,
    is_edited INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0,
    raw_data TEXT,                        -- original Baileys JSON for debugging
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (chat_id) REFERENCES chats(id)
);

-- Full-text search index
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    sender_name,
    content='messages',
    content_rowid='rowid'
);

-- Indexes
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
CREATE INDEX idx_messages_sender ON messages(sender_jid);
CREATE INDEX idx_messages_type ON messages(type);

-- Contacts table
CREATE TABLE contacts (
    jid TEXT PRIMARY KEY,
    name TEXT,
    push_name TEXT,                      -- WhatsApp display name
    phone_number TEXT,
    is_group INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Group participants
CREATE TABLE group_participants (
    group_jid TEXT NOT NULL,
    participant_jid TEXT NOT NULL,
    role TEXT DEFAULT 'member',          -- 'admin', 'superadmin', 'member'
    PRIMARY KEY (group_jid, participant_jid),
    FOREIGN KEY (group_jid) REFERENCES chats(id),
    FOREIGN KEY (participant_jid) REFERENCES contacts(jid)
);

-- Reactions
CREATE TABLE reactions (
    message_id TEXT NOT NULL,
    sender_jid TEXT NOT NULL,
    emoji TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    PRIMARY KEY (message_id, sender_jid),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
```

---

## 7. Technology Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Runtime | Node.js | 20 LTS | Stable, LTS, Baileys requires 17+ |
| Language | TypeScript | 5.x | Type safety, DDD-friendly |
| WhatsApp | @whiskeysockets/baileys | Latest | Only lib that reads all conversations |
| Database | better-sqlite3 | Latest | Embedded, synchronous, fast, FTS5 support |
| Event Bus | EventEmitter3 | Latest | Lightweight in-process pub/sub |
| CLI | Commander.js | Latest | For bot management commands |
| Logging | pino | Latest | Fast structured logging (Baileys uses it too) |
| Config | dotenv + zod | Latest | Type-safe environment configuration |
| Testing | vitest | Latest | Fast, TypeScript-native test runner |
| Media storage | Local filesystem | N/A | Organized as `media/{chatId}/{date}/{filename}` |

---

## 8. Deployment Architecture

```
┌────────────────────────────────────────────┐
│              Host Machine / VPS             │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │        WhatsApp Reader Bot           │  │
│  │                                      │  │
│  │  ┌──────────┐    ┌───────────────┐  │  │
│  │  │ Baileys   │───>│ Event Bus     │  │  │
│  │  │ Adapter   │    │ (in-process)  │  │  │
│  │  └──────────┘    └───────────────┘  │  │
│  │       │                │   │   │     │  │
│  │       │                v   v   v     │  │
│  │       │           ┌─────────────┐   │  │
│  │       │           │ Use Cases   │   │  │
│  │       │           └─────────────┘   │  │
│  │       │                │            │  │
│  │       v                v            │  │
│  │  ┌──────────┐    ┌───────────┐     │  │
│  │  │ Media    │    │ SQLite DB │     │  │
│  │  │ Files    │    │           │     │  │
│  │  └──────────┘    └───────────┘     │  │
│  └──────────────────────────────────────┘  │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │        Optional: REST API            │  │
│  │  (search, export, status endpoints)  │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

### Deployment Options

| Option | Description | Best For |
|--------|-------------|----------|
| Single process | Node.js process with PM2 | Personal use, single account |
| Docker container | Containerized with volume mounts for DB + media | Server deployment |
| VPS (DigitalOcean, etc.) | Dedicated small VM | Always-on monitoring |

---

## 9. Message Flow — Sequence Diagram

```
WhatsApp Server          Baileys           Adapter         EventBus        UseCase         SQLite
     │                     │                 │               │               │               │
     │──WebSocket msg──>   │                 │               │               │               │
     │                     │──messages.upsert│               │               │               │
     │                     │────────────────>│               │               │               │
     │                     │                 │──map to domain│               │               │
     │                     │                 │──MessageReceived──>           │               │
     │                     │                 │               │──────────────>│               │
     │                     │                 │               │               │──save()──────>│
     │                     │                 │               │               │               │──INSERT
     │                     │                 │               │               │               │
     │                     │                 │               │               │──saveMedia()  │
     │                     │                 │               │               │──>(filesystem)│
     │                     │                 │               │               │               │
```

---

## 10. Non-Functional Requirements

| Requirement | Target | Approach |
|-------------|--------|----------|
| Availability | 99%+ uptime | PM2 auto-restart, reconnect logic |
| Latency | < 100ms message capture | In-process event bus, sync SQLite writes |
| Storage | Unlimited growth | Configurable retention policy, media compression |
| Search | < 500ms for FTS queries | SQLite FTS5 index |
| Security | Auth state encrypted at rest | AES-256 encryption for creds.json |
| Observability | Structured logs, metrics | pino logger, optional Prometheus metrics |
| Backup | Daily | SQLite `.backup()` API, media rsync |

---

## 11. Implementation Phases

### Phase 1 — Core Connection & Message Capture
- Baileys adapter with connection lifecycle
- QR code authentication flow
- Message event capture (text only)
- SQLite storage with basic schema
- Console logging

### Phase 2 — Full Message Support
- All message types (media, location, contacts, polls)
- Media download and storage
- Group metadata tracking
- Read receipts and delivery status
- Message reactions

### Phase 3 — Search & Export
- Full-text search via FTS5
- JSON and CSV export
- Date range and contact filters
- CLI commands for search and export

### Phase 4 — Resilience & Operations
- Auto-reconnect with exponential backoff
- QR re-scan notifications
- Retention policies
- Database backup automation
- Monitoring and alerting

### Phase 5 — Optional REST API
- HTTP endpoints for search, export, status
- WebSocket endpoint for real-time message streaming
- API key authentication

---

## 12. Compliance & Ethical Considerations

| Concern | Mitigation |
|---------|------------|
| WhatsApp ToS | This tool should only be used on accounts you own, for personal data backup/archival purposes |
| Privacy (GDPR, etc.) | Store only your own conversations; implement data deletion on request |
| Account ban risk | Operate in read-only mode; avoid bulk messaging; use a dedicated number |
| End-to-end encryption | Baileys handles E2E decryption client-side via linked device protocol; messages are only readable on the authenticated device |
| Data at rest | Encrypt SQLite database and media files if handling sensitive data |

---

## 13. Consequences

### Positive
- Full visibility into all WhatsApp conversations on the account
- Real-time capture with minimal latency
- Clean DDD architecture enables easy extension (AI analysis, CRM integration, etc.)
- SQLite provides powerful querying with zero operational overhead
- No recurring API costs

### Negative
- Dependency on unofficial library — breakage risk on WhatsApp updates
- Requires re-authentication via QR code if session expires
- Cannot be deployed as a SaaS product due to ToS constraints
- Single-account architecture (one bot instance per WhatsApp number)

### Neutral
- Team must monitor Baileys releases for breaking changes
- Media storage will grow unbounded without retention policies

---

## 14. References

- [WhiskeySockets/Baileys GitHub](https://github.com/WhiskeySockets/Baileys) — Official Baileys repository
- [Baileys Documentation Wiki](https://baileys.wiki/docs/intro/) — Baileys usage guide
- [Baileys 2025 REST API](https://github.com/PointerSoftware/Baileys-2025-Rest-API) — REST API wrapper reference
- [WhatsApp Cloud API Developer Hub](https://business.whatsapp.com/developers/developer-hub) — Official Business API docs
- [WhatsApp Node.js SDK](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/receivingMessages/) — Official SDK for Cloud API
- [WhatsApp Cloud API Guide (Chatarmin)](https://chatarmin.com/en/blog/whatsapp-cloudapi) — Cloud API setup and pricing guide
- [Unipile WhatsApp API Guide](https://www.unipile.com/whatsapp-api-a-complete-guide-to-integration/) — Third-party integration reference
