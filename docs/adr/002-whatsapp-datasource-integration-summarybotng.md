# ADR-002: WhatsApp Data Source Integration with SummaryBot-NG

**Status:** Proposed
**Date:** 2026-02-11
**Supersedes:** None
**Depends on:** ADR-001 (WhatsApp Conversation Reader Bot)
**Context Domain:** Data Source Integration / Conversation Intelligence

---

## 1. Executive Summary

This specification defines how to integrate WhatsApp as a **first-class data source** into [SummaryBot-NG](https://github.com/summarybotng/summarybot-ng) — an AI-powered conversation summarization platform currently built around Discord. The integration feeds WhatsApp conversations captured via Baileys (ADR-001) into SummaryBot-NG's existing document processing, AI summarization, and export pipelines.

### Goal

**WhatsApp conversations should be summarizable with the same power and flexibility as Discord channels** — including time-range filtering, per-chat summaries, cross-chat synthesis, media-aware context, and delivery via webhook/API/dashboard.

---

## 2. Problem Statement

SummaryBot-NG currently supports one conversation data source: **Discord**. Its architecture (`/discord/channels/{channel_id}/summarize`) is tightly coupled to Discord's data model (channels, threads, guild permissions). WhatsApp conversations have fundamentally different characteristics:

| Dimension | Discord | WhatsApp |
|-----------|---------|----------|
| Identity | User IDs + Guild roles | Phone numbers (JIDs) |
| Channels | Named channels in guilds | Individual chats + groups |
| Threads | Explicit thread model | Reply-to chains (implicit) |
| Media | Attachments with CDN URLs | E2E encrypted, must download via Baileys |
| History access | Bot API with message fetch | Real-time capture only (no backfill API) |
| Authentication | Bot token + OAuth2 | QR code scan (linked device) |
| Message format | Markdown with embeds | Plain text + formatting codes |
| Presence model | Online/DND/Idle/Offline | Online/Typing/Recording |

These differences require a **source-agnostic abstraction layer** in SummaryBot-NG rather than another hardcoded integration.

---

## 3. Decision

### 3.1 Integration Strategy: **Ingest Adapter Pattern**

We will NOT fork SummaryBot-NG's Discord pipeline. Instead, we introduce a **pluggable Ingest Adapter** abstraction that normalizes all data sources into SummaryBot-NG's existing `Document` model. WhatsApp becomes the second adapter alongside the existing Discord adapter.

```
┌─────────────────────────────────────────────────────────────────┐
│                        SummaryBot-NG                            │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Discord     │  │  WhatsApp    │  │  Future Sources      │  │
│  │   Ingest      │  │  Ingest      │  │  (Slack, Teams,      │  │
│  │   Adapter     │  │  Adapter     │  │   Telegram, Email)   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                  │                      │              │
│         v                  v                      v              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            Unified Document Ingest Pipeline               │   │
│  │                                                           │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │   │
│  │  │ Normalizer  │─>│ Enricher     │─>│ Document Store │  │   │
│  │  │ (→Document) │  │ (lang, topic)│  │ (PostgreSQL)   │  │   │
│  │  └─────────────┘  └──────────────┘  └────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │                                                       │
│         v                                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         AI Summarization Engine (Claude API)              │   │
│  │         (unchanged — works on Documents regardless        │   │
│  │          of source)                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │                                                       │
│         v                                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Export / Delivery                                 │   │
│  │         (Webhook, API, Dashboard, Markdown, HTML)         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Deployment Topology

The WhatsApp Reader (ADR-001) runs as a **separate process** that pushes data into SummaryBot-NG via its REST API. They are loosely coupled:

```
┌─────────────────────┐          ┌─────────────────────────┐
│  WhatsApp Reader    │          │     SummaryBot-NG       │
│  (Node.js/Baileys)  │  HTTP    │     (Python/FastAPI)    │
│                     │ ──────>  │                         │
│  - Captures msgs    │  POST    │  - Ingests documents    │
│  - Stores in SQLite │ /ingest  │  - Summarizes with AI   │
│  - Pushes batches   │          │  - Serves via API/UI    │
│  - Downloads media  │          │                         │
└─────────────────────┘          └─────────────────────────┘
     Runs on any host              Runs on any host
     (even same machine)           (Docker/Fly.io/etc.)
```

**Why separate processes?**
1. **Language boundary** — WhatsApp Reader is TypeScript (Baileys requires it); SummaryBot-NG is Python
2. **Lifecycle independence** — WhatsApp session can reconnect/restart without affecting summarization
3. **Scaling** — Reader is I/O-bound (WebSocket); Summarizer is CPU/API-bound (LLM calls)
4. **Failure isolation** — A Baileys crash doesn't take down the summarization service

---

## 4. Unified Ingest Interface

### 4.1 Ingest Adapter Contract

All data sources implement this interface to feed documents into SummaryBot-NG:

```python
# src/feeds/ingest_adapter.py

from abc import ABC, abstractmethod
from typing import AsyncIterator
from src.models.document import IngestDocument

class IngestAdapter(ABC):
    """Base class for all data source adapters."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Unique identifier: 'discord', 'whatsapp', 'slack', etc."""
        ...

    @abstractmethod
    async def fetch_messages(
        self,
        channel_id: str,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        limit: int = 1000,
    ) -> AsyncIterator[IngestDocument]:
        """Yield normalized documents from the source."""
        ...

    @abstractmethod
    async def list_channels(self) -> list[ChannelInfo]:
        """List available conversations/channels from this source."""
        ...

    @abstractmethod
    async def get_channel_info(self, channel_id: str) -> ChannelInfo:
        """Get metadata about a specific conversation."""
        ...
```

### 4.2 Normalized Document Model

The `IngestDocument` extends SummaryBot-NG's existing `Document` model with source-agnostic fields:

```python
# src/models/ingest_document.py

from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class SourceType(str, Enum):
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    TELEGRAM = "telegram"

class ParticipantRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

class Participant(BaseModel):
    id: str                          # Source-native ID (JID, Discord ID, etc.)
    display_name: str
    role: ParticipantRole = ParticipantRole.MEMBER
    phone_number: str | None = None  # WhatsApp-specific, optional

class MessageAttachment(BaseModel):
    filename: str
    mime_type: str
    size_bytes: int
    url: str | None = None           # CDN URL (Discord) or None (WhatsApp)
    local_path: str | None = None    # Local file path (WhatsApp media)
    caption: str | None = None

class NormalizedMessage(BaseModel):
    id: str                          # Source-native message ID
    source_type: SourceType
    channel_id: str                  # Chat JID (WhatsApp) or Channel ID (Discord)
    sender: Participant
    timestamp: datetime
    content: str                     # Plain text content
    attachments: list[MessageAttachment] = []
    reply_to_id: str | None = None   # Quoted message ID
    is_from_bot_owner: bool = False  # Message sent by the account owner
    is_forwarded: bool = False
    is_edited: bool = False
    is_deleted: bool = False
    reactions: list[dict] = []       # [{emoji: str, sender_id: str}]
    metadata: dict = {}              # Source-specific extra data

class IngestDocument(BaseModel):
    """A batch of messages from a single conversation, ready for summarization."""
    source_type: SourceType
    channel_id: str
    channel_name: str
    channel_type: str                # 'individual', 'group', 'thread', 'channel'
    participants: list[Participant]
    messages: list[NormalizedMessage]
    time_range_start: datetime
    time_range_end: datetime
    total_message_count: int
    metadata: dict = {}              # Source-specific (e.g. group description, topic)
```

---

## 5. WhatsApp Ingest Adapter — Detailed Design

### 5.1 Architecture

The WhatsApp Ingest Adapter has two components:

1. **Push Agent** (TypeScript, runs in WhatsApp Reader process) — Batches captured messages and POSTs them to SummaryBot-NG's ingest endpoint
2. **Receive Handler** (Python, runs in SummaryBot-NG) — Accepts WhatsApp document payloads and feeds them into the summarization pipeline

```
WhatsApp Reader (TypeScript)              SummaryBot-NG (Python)
┌──────────────────────────┐              ┌───────────────────────────┐
│                          │              │                           │
│  Baileys ──> EventBus    │              │   POST /api/v1/ingest     │
│                │         │              │         │                 │
│                v         │    HTTP       │         v                 │
│  ┌──────────────────┐   │  ──────────>  │  ┌──────────────────┐    │
│  │  WhatsApp Push   │   │  JSON batch   │  │  WhatsApp Ingest │    │
│  │  Agent           │───┼──────────────>│  │  Handler         │    │
│  │                  │   │               │  └────────┬─────────┘    │
│  │  - Batch msgs    │   │               │           │              │
│  │  - Map to norm   │   │               │           v              │
│  │  - Upload media  │   │               │  ┌──────────────────┐    │
│  │  - Retry logic   │   │               │  │  Document Store  │    │
│  └──────────────────┘   │               │  │  (PostgreSQL)    │    │
│                          │              │  └──────────────────┘    │
└──────────────────────────┘              └───────────────────────────┘
```

### 5.2 Push Agent (TypeScript Side)

The Push Agent runs inside the WhatsApp Reader process (ADR-001) as an additional event subscriber:

```typescript
// src/feeds/whatsapp-push-agent.ts (in WhatsApp Reader repo)

interface PushAgentConfig {
  summarybotUrl: string;       // e.g. "https://summarybot.example.com"
  apiKey: string;              // SummaryBot-NG API key
  batchSize: number;           // Messages per batch (default: 50)
  batchIntervalMs: number;     // Max wait before flushing (default: 30000)
  enableMediaUpload: boolean;  // Upload media files to SummaryBot
  chatFilter?: {
    include?: string[];        // Only push these chat JIDs
    exclude?: string[];        // Never push these chat JIDs
  };
}

class WhatsAppPushAgent {
  private buffer: Map<string, NormalizedMessage[]> = new Map();
  private flushTimer: NodeJS.Timer | null = null;

  constructor(
    private config: PushAgentConfig,
    private eventBus: EventBus,
    private mediaStore: MediaStore,
  ) {
    // Subscribe to message events from ADR-001's event bus
    this.eventBus.on(MessageReceived, (msg) => this.onMessage(msg));
    this.eventBus.on(MessageSent, (msg) => this.onMessage(msg));
    this.startFlushTimer();
  }

  private onMessage(msg: DomainMessage): void {
    // Apply chat filter
    if (!this.shouldCapture(msg.chatId)) return;

    // Normalize to IngestDocument format
    const normalized = this.normalize(msg);

    // Buffer by chat
    const chatBuffer = this.buffer.get(msg.chatId) ?? [];
    chatBuffer.push(normalized);
    this.buffer.set(msg.chatId, chatBuffer);

    // Flush if batch size reached for this chat
    if (chatBuffer.length >= this.config.batchSize) {
      this.flushChat(msg.chatId);
    }
  }

  private normalize(msg: DomainMessage): NormalizedMessage {
    return {
      id: msg.id,
      source_type: 'whatsapp',
      channel_id: msg.chatId,
      sender: {
        id: msg.sender.jid,
        display_name: msg.sender.pushName || msg.sender.name || msg.sender.jid,
        phone_number: msg.sender.phoneNumber,
      },
      timestamp: msg.timestamp.toISOString(),
      content: msg.content.text ?? msg.content.caption ?? '',
      attachments: msg.content.media ? [{
        filename: msg.content.media.filename,
        mime_type: msg.content.media.mimetype,
        size_bytes: msg.content.media.size,
        local_path: msg.content.media.localPath,
        caption: msg.content.caption,
      }] : [],
      reply_to_id: msg.quotedMessage ?? undefined,
      is_from_bot_owner: msg.isFromMe,
      is_forwarded: msg.isForwarded,
      is_edited: msg.isEdited,
      is_deleted: msg.isDeleted,
      reactions: msg.reactions.map(r => ({
        emoji: r.emoji,
        sender_id: r.senderJid,
      })),
    };
  }

  private async flushChat(chatId: string): Promise<void> {
    const messages = this.buffer.get(chatId);
    if (!messages?.length) return;
    this.buffer.delete(chatId);

    const payload: IngestPayload = {
      source_type: 'whatsapp',
      channel_id: chatId,
      channel_name: await this.getChatName(chatId),
      channel_type: chatId.endsWith('@g.us') ? 'group' : 'individual',
      messages,
      time_range_start: messages[0].timestamp,
      time_range_end: messages[messages.length - 1].timestamp,
      total_message_count: messages.length,
    };

    await this.pushWithRetry(payload);
  }

  private async pushWithRetry(payload: IngestPayload, retries = 3): Promise<void> {
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const res = await fetch(`${this.config.summarybotUrl}/api/v1/ingest`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': this.config.apiKey,
          },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
        return;
      } catch (err) {
        if (attempt === retries) throw err;
        await new Promise(r => setTimeout(r, 2 ** attempt * 1000));
      }
    }
  }
}
```

### 5.3 Ingest API Endpoint (Python Side)

New endpoint in SummaryBot-NG's FastAPI app:

```python
# src/feeds/whatsapp_ingest_handler.py

from fastapi import APIRouter, Depends, HTTPException, Header
from src.models.ingest_document import IngestDocument, SourceType
from src.data.document_repository import DocumentRepository
from src.config.settings import Settings

router = APIRouter(prefix="/api/v1", tags=["ingest"])

@router.post("/ingest")
async def ingest_messages(
    payload: IngestDocument,
    x_api_key: str = Header(...),
    repo: DocumentRepository = Depends(get_document_repo),
    settings: Settings = Depends(get_settings),
):
    """
    Receive a batch of normalized messages from any data source.
    Validates, persists, and optionally triggers summarization.
    """
    if x_api_key != settings.ingest_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if payload.source_type not in [s.value for s in SourceType]:
        raise HTTPException(status_code=400, detail=f"Unknown source: {payload.source_type}")

    if not payload.messages:
        raise HTTPException(status_code=400, detail="Empty message batch")

    # Persist the document batch
    doc_id = await repo.store_ingest_batch(payload)

    # Optionally trigger auto-summarization if configured
    if settings.auto_summarize_on_ingest:
        from src.scheduling.summarize_scheduler import schedule_summarization
        await schedule_summarization(
            document_ids=[doc_id],
            summary_type=settings.default_summary_type,
            priority="normal",
        )

    return {
        "status": "accepted",
        "document_id": doc_id,
        "message_count": len(payload.messages),
        "source": payload.source_type,
        "channel": payload.channel_name,
    }
```

### 5.4 WhatsApp Summarize Endpoint

Mirrors the existing Discord endpoint pattern:

```python
# src/feeds/whatsapp_routes.py

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])

@router.post("/chats/{chat_id}/summarize")
async def summarize_whatsapp_chat(
    chat_id: str,
    request: WhatsAppSummarizeRequest,
    repo: DocumentRepository = Depends(get_document_repo),
    summarizer: SummarizationService = Depends(get_summarizer),
):
    """
    Summarize a WhatsApp chat by its JID.

    Equivalent to: POST /discord/channels/{channel_id}/summarize
    """
    messages = await repo.get_messages(
        source_type="whatsapp",
        channel_id=chat_id,
        time_from=request.time_from,
        time_to=request.time_to,
        limit=request.max_messages,
    )

    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for this chat in the given range")

    summary = await summarizer.summarize(
        documents=messages,
        summary_type=request.summary_type,
        output_format=request.output_format,
        custom_prompt=request.custom_prompt,
    )

    return summary

class WhatsAppSummarizeRequest(BaseModel):
    time_from: datetime | None = None
    time_to: datetime | None = None
    max_messages: int = Field(default=1000, le=5000)
    summary_type: str = "comprehensive"  # brief | detailed | comprehensive | technical | executive
    output_format: str = "markdown"      # markdown | html | json | plain
    custom_prompt: str | None = None
    include_media_context: bool = True   # Include media captions/descriptions in summary
    filter_participants: list[str] | None = None  # Only include messages from these JIDs
    webhook_url: str | None = None       # Deliver result via webhook
```

---

## 6. WhatsApp-Specific Enrichment

WhatsApp conversations carry context that Discord doesn't. The enrichment pipeline adds WhatsApp-aware processing:

### 6.1 Conversation Thread Reconstruction

WhatsApp doesn't have explicit threads. Reconstruct them from reply-to chains:

```python
# src/message_processing/thread_reconstructor.py

class ThreadReconstructor:
    """Reconstruct conversation threads from WhatsApp reply-to chains."""

    def reconstruct(self, messages: list[NormalizedMessage]) -> list[Thread]:
        threads: dict[str, Thread] = {}
        orphans: list[NormalizedMessage] = []

        for msg in messages:
            if msg.reply_to_id:
                thread_root = self._find_root(msg.reply_to_id, messages)
                thread = threads.setdefault(thread_root, Thread(root_id=thread_root))
                thread.messages.append(msg)
            else:
                orphans.append(msg)

        # Group consecutive orphans by time proximity (< 5 min gap) as implicit threads
        return self._merge_implicit_threads(threads, orphans)
```

### 6.2 Media Context Extraction

For richer summaries, extract textual context from media:

| Media Type | Context Extraction |
|------------|-------------------|
| Images | Caption text; OCR via Tesseract (optional) |
| Videos | Caption text; duration metadata |
| Audio/Voice notes | Transcription via Whisper API (optional) |
| Documents (PDF, DOCX) | Feed into SummaryBot-NG's existing document processor |
| Stickers | Emoji equivalent or "[sticker]" placeholder |
| Location | Reverse geocode to address string |
| Contacts | Name + phone number as text |
| Polls | Question + options + vote counts as structured text |

```python
# src/message_processing/whatsapp_media_enricher.py

class WhatsAppMediaEnricher:
    """Extract textual context from WhatsApp media for summarization."""

    async def enrich(self, msg: NormalizedMessage) -> NormalizedMessage:
        for attachment in msg.attachments:
            if attachment.mime_type.startswith('audio/'):
                transcript = await self.transcribe_audio(attachment)
                msg.content += f"\n[Voice note transcript: {transcript}]"

            elif attachment.mime_type.startswith('image/'):
                if attachment.caption:
                    msg.content += f"\n[Image: {attachment.caption}]"
                # Optional: OCR
                # text = await self.ocr_image(attachment)
                # msg.content += f"\n[Image text: {text}]"

            elif attachment.mime_type == 'application/pdf':
                msg.metadata['has_document'] = True
                # Delegate to SummaryBot-NG's document processor

        return msg
```

### 6.3 WhatsApp Formatting Normalization

Convert WhatsApp formatting to SummaryBot-NG's expected Markdown:

| WhatsApp | Normalized (Markdown) |
|----------|-----------------------|
| `*bold*` | `**bold**` |
| `_italic_` | `*italic*` |
| `~strikethrough~` | `~~strikethrough~~` |
| ` ```code``` ` | ` ```code``` ` (same) |
| `> quote` | `> quote` (same) |

---

## 7. Prompt Engineering for WhatsApp Summaries

WhatsApp conversations differ from Discord in tone and structure. The summarization prompts need adaptation:

### 7.1 WhatsApp-Specific Prompt Template

```python
# src/prompts/whatsapp_summary_prompt.py

WHATSAPP_SUMMARY_SYSTEM_PROMPT = """
You are summarizing a WhatsApp conversation. WhatsApp conversations differ from
formal channels in these ways:
- Messages are often short, informal, and use abbreviations/slang
- Conversations may rapidly switch topics
- Voice note transcripts may contain filler words and be less structured
- Group chats may have multiple simultaneous sub-conversations
- Reply-to chains indicate threaded discussions within the flat message list
- Messages marked [forwarded] are shared content, not original thoughts
- Reactions (emoji) indicate agreement/acknowledgment without adding text

When summarizing:
1. Group messages by topic/thread, not chronologically
2. Identify and separate distinct conversation threads
3. Distinguish between decisions, action items, shared information, and social chatter
4. Note who said what for accountability (use display names, not phone numbers)
5. Preserve links and references shared in the conversation
6. Flag forwarded content separately from original discussion
7. Treat voice note transcripts as first-class content (not metadata)
8. Omit greetings, goodbyes, and acknowledgment-only messages unless they carry decisions
"""

WHATSAPP_SUMMARY_USER_PROMPT = """
Summarize the following WhatsApp {chat_type} conversation between {participant_count} participants.
Time range: {time_from} to {time_to}
Total messages: {message_count}

Participants: {participant_list}

{format_instructions}

--- CONVERSATION START ---
{messages}
--- CONVERSATION END ---
"""
```

### 7.2 Summary Types Mapping

| SummaryBot-NG Type | WhatsApp Adaptation |
|---------------------|---------------------|
| **brief** | Key decisions + action items only (< 200 words) |
| **detailed** | Topic-grouped summary with participant attribution |
| **comprehensive** | Full thread reconstruction, media context, sentiment |
| **technical** | Code snippets, links, document references extracted |
| **executive** | Decisions, blockers, next steps (strip all social chatter) |

---

## 8. Data Flow — End to End

```
                         WhatsApp Reader (ADR-001)
                         ┌────────────────────────┐
  WhatsApp Server ──WS──>│ Baileys                │
                         │   │                    │
                         │   v                    │
                         │ EventBus               │
                         │   │         │          │
                         │   v         v          │
                         │ SQLite   Push Agent    │
                         │ (local    (batch +     │
                         │  store)    normalize)  │
                         └───────────┬────────────┘
                                     │
                           HTTP POST /api/v1/ingest
                           (JSON, batches of 50 msgs)
                                     │
                         ┌───────────v────────────┐
                         │    SummaryBot-NG       │
                         │                        │
                         │  Ingest Handler        │
                         │    │                   │
                         │    v                   │
                         │  Enrichment Pipeline   │
                         │  ├─ Thread Reconstruct │
                         │  ├─ Media Enrichment   │
                         │  ├─ Format Normalize   │
                         │  └─ Language Detection  │
                         │    │                   │
                         │    v                   │
                         │  Document Store (PG)   │
                         │    │                   │
                         │    v (on-demand or     │
                         │       scheduled)       │
                         │  AI Summarization      │
                         │  (Claude API)          │
                         │    │                   │
                         │    v                   │
                         │  Summary Store         │
                         │    │                   │
                         │    v                   │
                         │  Delivery              │
                         │  ├─ REST API response  │
                         │  ├─ Webhook POST       │
                         │  ├─ Dashboard UI       │
                         │  └─ Export (MD/HTML/PDF)│
                         └────────────────────────┘
```

### 8.1 Trigger Models

| Trigger | Description | Use Case |
|---------|-------------|----------|
| **Real-time push** | Push Agent sends batches as messages arrive | Live monitoring dashboard |
| **Scheduled batch** | Cron job queries WhatsApp Reader SQLite and pushes | Daily/weekly digests |
| **On-demand API** | User hits `POST /whatsapp/chats/{id}/summarize` | Ad-hoc catch-up |
| **CLI command** | `summarybot summarize --source whatsapp --chat "Family Group"` | Developer tooling |

---

## 9. Database Schema Extensions

New tables/columns in SummaryBot-NG's PostgreSQL:

```sql
-- Extend existing documents table with source tracking
ALTER TABLE documents ADD COLUMN source_type VARCHAR(20) DEFAULT 'discord';
ALTER TABLE documents ADD COLUMN source_channel_id VARCHAR(255);
ALTER TABLE documents ADD COLUMN source_metadata JSONB DEFAULT '{}';

-- WhatsApp-specific: store raw ingested message batches
CREATE TABLE whatsapp_ingest_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_jid VARCHAR(255) NOT NULL,
    chat_name VARCHAR(255),
    chat_type VARCHAR(20) NOT NULL,          -- 'individual', 'group'
    message_count INTEGER NOT NULL,
    time_range_start TIMESTAMPTZ NOT NULL,
    time_range_end TIMESTAMPTZ NOT NULL,
    raw_payload JSONB NOT NULL,              -- Full normalized message batch
    processed BOOLEAN DEFAULT FALSE,
    document_id UUID REFERENCES documents(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    INDEX idx_wa_batch_chat (chat_jid),
    INDEX idx_wa_batch_time (time_range_start, time_range_end)
);

-- WhatsApp contacts (for display name resolution)
CREATE TABLE whatsapp_contacts (
    jid VARCHAR(255) PRIMARY KEY,
    display_name VARCHAR(255),
    phone_number VARCHAR(20),
    is_group BOOLEAN DEFAULT FALSE,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW()
);

-- Mapping: which WhatsApp chats are being tracked
CREATE TABLE whatsapp_tracked_chats (
    chat_jid VARCHAR(255) PRIMARY KEY,
    chat_name VARCHAR(255),
    chat_type VARCHAR(20) NOT NULL,
    auto_summarize BOOLEAN DEFAULT FALSE,
    summary_schedule VARCHAR(50),            -- cron expression, e.g. '0 9 * * 1' (Monday 9am)
    summary_type VARCHAR(20) DEFAULT 'comprehensive',
    webhook_url VARCHAR(500),                -- Deliver summaries here
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 10. Configuration

### 10.1 WhatsApp Reader Side (`.env`)

```bash
# SummaryBot-NG Integration
SUMMARYBOT_URL=https://summarybot.example.com
SUMMARYBOT_API_KEY=sk-ingest-xxxxxxxxxxxx
PUSH_BATCH_SIZE=50
PUSH_BATCH_INTERVAL_MS=30000
PUSH_ENABLED=true

# Chat Filter (comma-separated JIDs, empty = all chats)
PUSH_INCLUDE_CHATS=
PUSH_EXCLUDE_CHATS=status@broadcast

# Media
PUSH_INCLUDE_MEDIA=true
MEDIA_UPLOAD_MAX_SIZE_MB=25
```

### 10.2 SummaryBot-NG Side (`.env`)

```bash
# WhatsApp Ingest
WHATSAPP_INGEST_ENABLED=true
WHATSAPP_INGEST_API_KEY=sk-ingest-xxxxxxxxxxxx
WHATSAPP_AUTO_SUMMARIZE=false
WHATSAPP_DEFAULT_SUMMARY_TYPE=comprehensive

# Voice Note Transcription (optional)
WHISPER_API_URL=https://api.openai.com/v1/audio/transcriptions
WHISPER_API_KEY=sk-xxxx
WHISPER_ENABLED=false

# Media Processing
WHATSAPP_MEDIA_STORAGE_PATH=/data/whatsapp-media
WHATSAPP_MEDIA_MAX_SIZE_MB=50
```

---

## 11. API Surface — Complete Endpoints

### 11.1 New Endpoints in SummaryBot-NG

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/ingest` | Universal ingest endpoint (any source) |
| `GET` | `/api/v1/whatsapp/chats` | List all tracked WhatsApp chats |
| `GET` | `/api/v1/whatsapp/chats/{jid}` | Get chat details + message count |
| `POST` | `/api/v1/whatsapp/chats/{jid}/summarize` | Summarize a specific chat |
| `GET` | `/api/v1/whatsapp/chats/{jid}/messages` | Paginated message history |
| `POST` | `/api/v1/whatsapp/summarize-cross-chat` | Summarize across multiple chats |
| `PUT` | `/api/v1/whatsapp/chats/{jid}/tracking` | Configure auto-summarize for chat |
| `GET` | `/api/v1/whatsapp/status` | WhatsApp Reader connection status |
| `GET` | `/api/v1/sources` | List all configured data sources |

### 11.2 Cross-Chat Summarization

Unique to WhatsApp — summarize a topic across multiple chats:

```python
class CrossChatSummarizeRequest(BaseModel):
    chat_ids: list[str]               # Multiple chat JIDs
    time_from: datetime | None = None
    time_to: datetime | None = None
    topic_filter: str | None = None   # Only include messages related to this topic
    summary_type: str = "executive"
    output_format: str = "markdown"
```

Use case: "Summarize everything discussed about the product launch across all my WhatsApp groups this week."

---

## 12. Implementation Phases

### Phase 1 — Ingest Pipeline (Week 1-2)
- [ ] Create `IngestAdapter` base class in SummaryBot-NG
- [ ] Refactor Discord integration to use `IngestAdapter`
- [ ] Add `POST /api/v1/ingest` endpoint
- [ ] Add `source_type` column to existing `documents` table
- [ ] Build WhatsApp Push Agent in WhatsApp Reader
- [ ] End-to-end test: WhatsApp message → SummaryBot-NG document store

### Phase 2 — Summarization (Week 3-4)
- [ ] WhatsApp-specific prompt templates
- [ ] Thread reconstruction from reply chains
- [ ] Format normalization (WhatsApp → Markdown)
- [ ] `POST /whatsapp/chats/{jid}/summarize` endpoint
- [ ] Support all 5 summary types for WhatsApp
- [ ] End-to-end test: WhatsApp message → AI summary → API response

### Phase 3 — Enrichment (Week 5-6)
- [ ] Media caption extraction
- [ ] Voice note transcription (Whisper integration)
- [ ] Language detection for multilingual chats
- [ ] Forwarded message handling
- [ ] Participant display name resolution

### Phase 4 — Operations (Week 7-8)
- [ ] Auto-summarize scheduling per chat (cron-based)
- [ ] Webhook delivery for scheduled summaries
- [ ] Cross-chat summarization endpoint
- [ ] Dashboard UI for WhatsApp chats (alongside Discord)
- [ ] Monitoring: ingest rates, latency, error tracking

### Phase 5 — Polish (Week 9-10)
- [ ] Chat filtering UI (include/exclude chats)
- [ ] Export formats (PDF, DOCX) for WhatsApp summaries
- [ ] Retention policies for ingested WhatsApp data
- [ ] Documentation and API reference updates
- [ ] Performance optimization (batch processing, caching)

---

## 13. Testing Strategy

| Layer | Test Type | Tools | Coverage Target |
|-------|-----------|-------|-----------------|
| Push Agent | Unit tests | vitest + mocks | Message normalization, batching, retry |
| Ingest API | Integration tests | pytest + httpx | Endpoint validation, auth, error handling |
| Thread Reconstruction | Unit tests | pytest | Reply chain parsing, implicit thread detection |
| Media Enrichment | Unit + integration | pytest + mocks | Caption extraction, transcription stubs |
| Summarization | Integration tests | pytest + Claude mock | Prompt rendering, response parsing |
| End-to-End | E2E | Docker Compose + test fixtures | Full flow: ingest → summarize → deliver |

### Test Fixtures

```python
# tests/fixtures/whatsapp_messages.py

SAMPLE_WHATSAPP_BATCH = IngestDocument(
    source_type="whatsapp",
    channel_id="120363043587256789@g.us",
    channel_name="Project Alpha Team",
    channel_type="group",
    participants=[
        Participant(id="1234567890@s.whatsapp.net", display_name="Alice", role="admin"),
        Participant(id="0987654321@s.whatsapp.net", display_name="Bob", role="member"),
    ],
    messages=[
        NormalizedMessage(
            id="3EB0A8B2F7C6",
            source_type="whatsapp",
            channel_id="120363043587256789@g.us",
            sender=Participant(id="1234567890@s.whatsapp.net", display_name="Alice"),
            timestamp=datetime(2026, 2, 10, 14, 30),
            content="Has everyone reviewed the Q1 budget proposal?",
            reply_to_id=None,
            is_from_bot_owner=False,
        ),
        NormalizedMessage(
            id="3EB0A8B2F7C7",
            source_type="whatsapp",
            channel_id="120363043587256789@g.us",
            sender=Participant(id="0987654321@s.whatsapp.net", display_name="Bob"),
            timestamp=datetime(2026, 2, 10, 14, 32),
            content="Yes, I think we need to increase the marketing allocation by 15%",
            reply_to_id="3EB0A8B2F7C6",
            is_from_bot_owner=False,
        ),
    ],
    time_range_start=datetime(2026, 2, 10, 14, 30),
    time_range_end=datetime(2026, 2, 10, 14, 32),
    total_message_count=2,
)
```

---

## 14. Security Considerations

| Concern | Mitigation |
|---------|------------|
| API key for ingest endpoint | Rotate keys via env config; rate-limit per key |
| Message content in transit | TLS 1.3 between WhatsApp Reader and SummaryBot-NG |
| Message content at rest | Encrypt `raw_payload` column if required by policy |
| PII in summaries | Option to anonymize participant names in output |
| Media files | Scan uploads for malware; enforce size limits; sandboxed storage |
| Claude API prompt injection | Sanitize message content before embedding in prompts |
| Access control | Per-chat permission model (who can request summaries for which chats) |

---

## 15. Consequences

### Positive
- **WhatsApp conversations become first-class citizens** in SummaryBot-NG's summarization pipeline
- **Ingest Adapter pattern** makes it trivial to add Slack, Telegram, Teams, or Email as future sources
- **No changes to SummaryBot-NG's core AI engine** — it just sees Documents, regardless of source
- **Push-based architecture** means SummaryBot-NG doesn't need WhatsApp credentials or Baileys dependency
- **Cross-chat summarization** is a novel capability not available in any off-the-shelf tool

### Negative
- **Two services to operate** — WhatsApp Reader + SummaryBot-NG
- **Language boundary** — TypeScript push agent must stay in sync with Python ingest schema
- **Latency** — HTTP batch push adds ~100-500ms vs in-process event handling
- **Media handling complexity** — files must be transferred from WhatsApp Reader to SummaryBot-NG

### Trade-offs
- Batch size tuning: larger batches = fewer HTTP calls but higher latency for real-time summaries
- Voice transcription: powerful but adds cost (Whisper API) and latency per message
- Thread reconstruction is heuristic — may not perfectly match user intent

---

## 16. References

- [ADR-001: WhatsApp Conversation Reader Bot](./001-whatsapp-conversation-reader-bot.md) — WhatsApp data capture architecture
- [SummaryBot-NG Repository](https://github.com/summarybotng/summarybot-ng) — Target summarization platform
- [SummaryBot-NG API Specification](https://github.com/summarybotng/summarybot-ng/blob/main/architecture/api-specifications.md) — Existing API contract
- [SummaryBot-NG System Overview](https://github.com/summarybotng/summarybot-ng/blob/main/architecture/enhanced-system-overview.md) — Current architecture
- [WhiskeySockets/Baileys](https://github.com/WhiskeySockets/Baileys) — WhatsApp Web API library
- [Catch-up Companion](https://github.com/antoinekllee/catch-up-companion) — Reference: WhatsApp summary bot using Twilio + GPT
- [WhatsApp Message Summaries (Meta AI)](https://blog.whatsapp.com/catch-up-on-conversations-with-private-message-summaries) — Native WhatsApp summary feature reference
