# ADR-003: Concrete SummaryBot-NG Modifications for WhatsApp Integration

**Status:** Proposed
**Date:** 2026-02-11
**Depends on:** ADR-002 (WhatsApp Data Source Integration)
**Repository:** [summarybotng/summarybot-ng](https://github.com/summarybotng/summarybot-ng)

---

## 1. Overview

This document maps every change needed inside the SummaryBot-NG codebase to support WhatsApp as a data source per ADR-002. It references actual files, classes, and patterns already in the repo.

**Estimated scope:** ~15 files modified, ~8 files created, 0 files deleted.

---

## 2. Change Map — File by File

### Legend

| Symbol | Meaning |
|--------|---------|
| **M** | Modify existing file |
| **N** | New file to create |

---

### 2.1 Data Models (`src/models/`)

#### **M** `src/models/message.py`

**Current state:** Defines `ProcessedMessage`, `AttachmentInfo`, `MessageReference`, etc. — all Discord-specific. The `MessageType` enum contains Discord values (`DEFAULT`, `REPLY`, `SLASH_COMMAND`). The `ProcessedMessage.clean_content()` method strips Discord-specific formatting (mentions like `<@123>`).

**Changes needed:**

1. **Add `source_type` field to `ProcessedMessage`:**
```python
# Add to imports
from enum import Enum

class SourceType(str, Enum):
    DISCORD = "discord"
    WHATSAPP = "whatsapp"

# Add field to ProcessedMessage dataclass
@dataclass
class ProcessedMessage(BaseModel):
    # ... existing fields ...
    source_type: SourceType = SourceType.DISCORD  # backward-compatible default
```

2. **Make `clean_content()` source-aware:**
```python
def clean_content(self) -> str:
    if self.source_type == SourceType.WHATSAPP:
        return self._clean_whatsapp_content()
    return self._clean_discord_content()  # existing logic, renamed

def _clean_whatsapp_content(self) -> str:
    """Convert WhatsApp formatting (*bold*, _italic_, ~strike~) to plain text."""
    text = self.content
    text = re.sub(r'\*(.*?)\*', r'\1', text)    # Remove bold markers
    text = re.sub(r'_(.*?)_', r'\1', text)       # Remove italic markers
    text = re.sub(r'~(.*?)~', r'\1', text)       # Remove strikethrough
    return text.strip()
```

3. **Extend `MessageType` enum** with WhatsApp values or make it source-generic:
```python
class MessageType(Enum):
    # Existing Discord types
    DEFAULT = "default"
    REPLY = "reply"
    # ...
    # New generic/WhatsApp types
    WHATSAPP_TEXT = "whatsapp_text"
    WHATSAPP_MEDIA = "whatsapp_media"
    WHATSAPP_VOICE = "whatsapp_voice"
    WHATSAPP_FORWARDED = "whatsapp_forwarded"
```

**Risk:** Medium — `ProcessedMessage` is used everywhere. The default value for `source_type` ensures zero breakage for existing Discord code paths.

---

#### **N** `src/models/ingest.py`

New model for the unified ingest payload (the `IngestDocument` and `NormalizedMessage` from ADR-002). This is the contract between the WhatsApp Push Agent and SummaryBot-NG.

```python
"""Normalized ingest models for multi-source message ingestion."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from .message import SourceType

class IngestParticipant(BaseModel):
    id: str
    display_name: str
    role: str = "member"
    phone_number: Optional[str] = None

class IngestAttachment(BaseModel):
    filename: str
    mime_type: str
    size_bytes: int
    url: Optional[str] = None
    caption: Optional[str] = None

class IngestMessage(BaseModel):
    id: str
    source_type: SourceType
    channel_id: str
    sender: IngestParticipant
    timestamp: datetime
    content: str
    attachments: list[IngestAttachment] = []
    reply_to_id: Optional[str] = None
    is_from_bot_owner: bool = False
    is_forwarded: bool = False
    is_edited: bool = False
    is_deleted: bool = False
    reactions: list[dict] = []
    metadata: dict = {}

class IngestDocument(BaseModel):
    source_type: SourceType
    channel_id: str
    channel_name: str
    channel_type: str  # 'individual', 'group', 'thread', 'channel'
    participants: list[IngestParticipant] = []
    messages: list[IngestMessage]
    time_range_start: datetime
    time_range_end: datetime
    total_message_count: int
    metadata: dict = {}
```

---

#### **M** `src/models/summary.py`

**Current state:** `SummarizationContext` has a `channel_name: str` field. `SummaryResult.to_embed_dict()` generates a Discord embed. `SummaryLength` has three values: `BRIEF`, `DETAILED`, `COMPREHENSIVE`.

**Changes needed:**

1. **Add `source_type` to `SummarizationContext`:**
```python
@dataclass
class SummarizationContext(BaseModel):
    # ... existing fields ...
    source_type: str = "discord"  # New field
    chat_type: str = "channel"    # New: 'channel', 'thread', 'group', 'individual'
```

2. **Make `SummaryResult` output format source-aware:**
```python
def to_markdown(self) -> str:
    """Generate markdown — works for both Discord and WhatsApp summaries."""
    # Existing logic works as-is (markdown is universal)
    # No changes needed here

def to_embed_dict(self) -> dict:
    """Generate Discord embed dict. Only valid for Discord source."""
    # Keep existing, but guard:
    if self.context and self.context.source_type != "discord":
        raise ValueError("Discord embeds only valid for Discord source")
    # ... existing logic ...
```

3. **Add `to_plain_dict()` for API responses** (WhatsApp summaries won't use Discord embeds):
```python
def to_plain_dict(self) -> dict:
    """Source-agnostic summary as a plain dictionary."""
    return {
        "summary": self.summary_text,
        "key_points": self.key_points,
        "action_items": [ai.to_markdown() for ai in self.action_items],
        "participants": [p.name for p in self.participants],
        "stats": self.get_summary_stats(),
        "source_type": self.context.source_type if self.context else "unknown",
    }
```

**Risk:** Low — additive changes only.

---

### 2.2 Message Processing (`src/message_processing/`)

#### **M** `src/message_processing/__init__.py`

Add the new WhatsApp processor to exports:

```python
from .whatsapp_processor import WhatsAppMessageProcessor  # New

__all__ = [
    # ... existing ...
    'WhatsAppMessageProcessor',
]
```

---

#### **M** `src/message_processing/processor.py`

**Current state:** `MessageProcessor` takes a `discord.Client` in its constructor and calls Discord-specific methods like `channel.history()` via `MessageFetcher`. It is the main orchestrator.

**Changes needed:** This class stays Discord-specific. It does NOT need to be modified to handle WhatsApp. Instead, WhatsApp messages arrive pre-fetched via the ingest API (they're pushed, not pulled). The processing pipeline (`_process_message_pipeline`) can be reused if we extract a shared base.

However, the internal `_process_message_pipeline` method is useful. Extract the core logic:

```python
# Add a class method that processes pre-fetched messages (no Discord client needed)
async def process_raw_messages(
    self,
    messages: list[ProcessedMessage],
    options: SummaryOptions,
) -> list[ProcessedMessage]:
    """Process pre-constructed ProcessedMessage objects through the pipeline.

    Used by WhatsApp ingest (messages arrive pre-fetched, no Discord client needed).
    """
    filtered = self.filter.filter_messages(messages, options)
    processed = []
    for msg in filtered:
        try:
            cleaned = self.cleaner.clean(msg)
            extracted = self.extractor.extract(cleaned)
            if self.validator.validate(extracted):
                processed.append(extracted)
        except Exception as e:
            logger.warning(f"Failed to process message {msg.id}: {e}")

    if len(processed) < options.min_messages:
        raise InsufficientContentError(len(processed), options.min_messages)

    return processed
```

**Risk:** Low — adding a new method, not changing existing ones.

---

#### **N** `src/message_processing/whatsapp_processor.py`

New file: converts `IngestMessage` objects from the API into `ProcessedMessage` objects that the existing summarization engine already understands.

```python
"""Convert WhatsApp ingest messages into ProcessedMessage format."""

from ..models.message import (
    ProcessedMessage, AttachmentInfo, MessageReference,
    SourceType, MessageType, AttachmentType,
)
from ..models.ingest import IngestMessage, IngestDocument

class WhatsAppMessageProcessor:
    """Transform WhatsApp ingest data into the internal ProcessedMessage format."""

    def convert_batch(self, doc: IngestDocument) -> list[ProcessedMessage]:
        """Convert an entire IngestDocument batch to ProcessedMessages."""
        messages = [self.convert_message(msg) for msg in doc.messages]
        # Build reply references by linking reply_to_ids
        msg_index = {m.id: m for m in messages}
        for orig, converted in zip(doc.messages, messages):
            if orig.reply_to_id and orig.reply_to_id in msg_index:
                ref_msg = msg_index[orig.reply_to_id]
                converted.reference = MessageReference(
                    message_id=ref_msg.id,
                    author_name=ref_msg.author_name,
                    content_preview=ref_msg.content[:100],
                )
        return messages

    def convert_message(self, msg: IngestMessage) -> ProcessedMessage:
        """Convert a single IngestMessage to ProcessedMessage."""
        return ProcessedMessage(
            id=msg.id,
            author_id=msg.sender.id,
            author_name=msg.sender.display_name,
            content=msg.content,
            timestamp=msg.timestamp,
            source_type=SourceType.WHATSAPP,
            message_type=self._map_message_type(msg),
            attachments=[self._convert_attachment(a) for a in msg.attachments],
            is_bot=False,
            is_webhook=False,
        )

    def _map_message_type(self, msg: IngestMessage) -> MessageType:
        if msg.is_forwarded:
            return MessageType.WHATSAPP_FORWARDED
        if msg.attachments:
            mime = msg.attachments[0].mime_type
            if mime.startswith('audio/'):
                return MessageType.WHATSAPP_VOICE
            return MessageType.WHATSAPP_MEDIA
        return MessageType.WHATSAPP_TEXT

    def _convert_attachment(self, att: IngestAttachment) -> AttachmentInfo:
        return AttachmentInfo(
            filename=att.filename,
            size=att.size_bytes,
            url=att.url or "",
            content_type=att.mime_type,
            attachment_type=self._detect_type(att.mime_type),
        )

    def _detect_type(self, mime: str) -> AttachmentType:
        if mime.startswith('image/'): return AttachmentType.IMAGE
        if mime.startswith('video/'): return AttachmentType.VIDEO
        if mime.startswith('audio/'): return AttachmentType.AUDIO
        return AttachmentType.DOCUMENT
```

---

#### **M** `src/message_processing/cleaner.py`

**Current state:** Strips Discord-specific noise (role mentions, channel references, custom emojis).

**Changes needed:** Make cleaning source-aware:

```python
def clean(self, message: ProcessedMessage) -> ProcessedMessage:
    if message.source_type == SourceType.WHATSAPP:
        return self._clean_whatsapp(message)
    return self._clean_discord(message)  # Existing logic renamed

def _clean_whatsapp(self, message: ProcessedMessage) -> ProcessedMessage:
    """Clean WhatsApp-specific formatting."""
    text = message.content
    # Normalize WhatsApp bold (*text*) to markdown bold (**text**)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'**\1**', text)
    # Remove zero-width characters common in WhatsApp
    text = text.replace('\u200e', '').replace('\u200f', '')
    message.content = text.strip()
    return message
```

**Risk:** Low — branching on the new `source_type` field.

---

#### **M** `src/message_processing/filter.py`

**Current state:** Filters out bot messages, system messages, empty messages. Uses Discord-specific heuristics.

**Changes needed:** Add WhatsApp-specific filters:

```python
def filter_messages(self, messages, options):
    return [m for m in messages if self._should_include(m, options)]

def _should_include(self, msg, options):
    if msg.source_type == SourceType.WHATSAPP:
        return self._should_include_whatsapp(msg, options)
    return self._should_include_discord(msg, options)  # Existing

def _should_include_whatsapp(self, msg, options):
    """WhatsApp-specific filtering."""
    # Skip deleted messages
    if msg.is_deleted:
        return False
    # Skip status broadcast messages
    if 'status@broadcast' in msg.channel_id:
        return False
    # Skip empty messages (media-only with no caption handled separately)
    if not msg.content and not msg.attachments:
        return False
    return True
```

---

### 2.3 Prompts (`src/prompts/`)

#### **M** `src/summarization/prompt_builder.py`

**Current state:** `PromptBuilder` has hardcoded Discord-specific system prompts (`_build_brief_system_prompt`, etc.) that say "expert at creating summaries of **Discord conversations**". The `build_user_prompt` method formats messages assuming Discord structure.

**This is the most critical change.** The prompts must become source-aware.

**Changes needed:**

1. **Add WhatsApp system prompts alongside Discord ones:**

```python
def __init__(self):
    self.system_prompts = {
        # Existing Discord prompts
        ("discord", SummaryLength.BRIEF): self._build_brief_system_prompt(),
        ("discord", SummaryLength.DETAILED): self._build_detailed_system_prompt(),
        ("discord", SummaryLength.COMPREHENSIVE): self._build_comprehensive_system_prompt(),
        # New WhatsApp prompts
        ("whatsapp", SummaryLength.BRIEF): self._build_whatsapp_brief_prompt(),
        ("whatsapp", SummaryLength.DETAILED): self._build_whatsapp_detailed_prompt(),
        ("whatsapp", SummaryLength.COMPREHENSIVE): self._build_whatsapp_comprehensive_prompt(),
    }

def build_system_prompt(self, options: SummaryOptions) -> str:
    source = getattr(options, 'source_type', 'discord')
    base_prompt = self.system_prompts[(source, options.summary_length)]
    # ... rest unchanged ...
```

2. **New prompt methods:**

```python
def _build_whatsapp_brief_prompt(self) -> str:
    return """You are summarizing a WhatsApp conversation. Create a concise summary.
Focus on: decisions made, action items, and key information shared.
Omit greetings, acknowledgments, and social filler.
Use participant display names, never phone numbers."""

def _build_whatsapp_detailed_prompt(self) -> str:
    return """You are summarizing a WhatsApp conversation. Create a detailed summary.
WhatsApp-specific guidance:
- Group messages by topic, not chronologically
- Reconstruct threads from reply-to chains
- Distinguish forwarded content from original discussion
- Treat voice note transcripts as primary content
- Note when media was shared even if you can't see the content
- Use participant display names, never phone numbers
- Handle informal language, abbreviations, and emoji naturally"""

def _build_whatsapp_comprehensive_prompt(self) -> str:
    return """You are creating an exhaustive summary of a WhatsApp conversation.
Include every substantive point, decision, reference, and action item.
WhatsApp-specific handling:
- Reconstruct conversation threads from reply chains
- Separate forwarded/shared content from original discussion
- Include media descriptions and voice note transcripts
- Track who committed to what (action items with owners)
- Note sentiment shifts and areas of disagreement
- Handle multilingual messages (some chats switch languages)
- Preserve links and document references
- Omit only pure greetings and single-emoji acknowledgments"""
```

3. **Make `_build_messages_section()` format WhatsApp messages differently:**

```python
def _build_messages_section(self, messages, options):
    source = getattr(options, 'source_type', 'discord')
    parts = ["## Messages to Summarize:"]
    for msg in messages:
        if source == "whatsapp":
            parts.append(self._format_whatsapp_message(msg))
        else:
            parts.append(self._format_discord_message(msg))  # existing
    return "\n".join(parts)

def _format_whatsapp_message(self, msg):
    """Format a WhatsApp message for the prompt context."""
    ts = msg.timestamp.strftime('%Y-%m-%d %H:%M')
    line = f"**{msg.author_name}** ({ts})"
    if msg.reference:
        line += f" [replying to {msg.reference.author_name}]"
    if msg.message_type == MessageType.WHATSAPP_FORWARDED:
        line += " [forwarded]"
    line += f": {msg.content}"
    for att in msg.attachments:
        att_desc = f"[{att.attachment_type.value}: {att.filename}]"
        if att.caption:
            att_desc += f" caption: {att.caption}"
        line += f"\n  {att_desc}"
    return line
```

**Risk:** Medium — changes the prompt builder's lookup structure. Thorough testing needed to ensure Discord prompts remain identical.

---

#### **M** `src/models/summary.py` → `SummaryOptions`

**Current state:** `SummaryOptions` controls summarization behavior. Has no concept of source.

**Change:** Add `source_type` field:

```python
@dataclass
class SummaryOptions(BaseModel):
    # ... existing fields ...
    source_type: str = "discord"  # New field
```

---

### 2.4 Summarization Engine (`src/summarization/`)

#### **M** `src/summarization/engine.py`

**Current state:** `SummarizationEngine.summarize_messages()` accepts `list[ProcessedMessage]` and `SummaryOptions`, builds a prompt, calls Claude, parses the response. It is already source-agnostic in its core logic — it doesn't call Discord APIs directly.

**Changes needed:** Minimal. The engine already works on `ProcessedMessage` objects. As long as the prompt builder returns correct prompts based on `source_type`, the engine doesn't need modification.

One small addition — pass source context through:

```python
async def summarize_messages(self, messages, options, context=None, ...):
    # Existing: builds context dict
    if context is None:
        context = {}
    # New: ensure source_type flows into context
    context.setdefault("source_type", options.source_type)
    # ... rest unchanged — prompt_builder.build_summarization_prompt()
    #     now picks the right prompt based on options.source_type
```

**Risk:** Very low — one line added.

---

### 2.5 Ingest API (`src/webhook_service/` or new `src/feeds/`)

#### **N** `src/feeds/ingest_handler.py`

The existing `src/feeds/` directory has `generator.py` (RSS feed output). The ingest handler is the inverse — data coming IN.

```python
"""HTTP endpoint for receiving messages from external sources (WhatsApp, etc.)."""

from fastapi import APIRouter, HTTPException, Header, Depends
from ..models.ingest import IngestDocument
from ..message_processing.whatsapp_processor import WhatsAppMessageProcessor
from ..data.base import SummaryRepository

router = APIRouter(prefix="/api/v1", tags=["ingest"])

@router.post("/ingest")
async def ingest_messages(
    payload: IngestDocument,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """Receive a batch of normalized messages from any external source."""
    # Validate API key
    expected_key = os.environ.get("INGEST_API_KEY")
    if not expected_key or x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not payload.messages:
        raise HTTPException(status_code=400, detail="Empty message batch")

    # Convert to ProcessedMessages
    if payload.source_type == "whatsapp":
        processor = WhatsAppMessageProcessor()
        processed = processor.convert_batch(payload)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported source: {payload.source_type}")

    # Store the batch (reuse existing repository pattern)
    batch_id = await store_ingest_batch(payload, processed)

    return {
        "status": "accepted",
        "batch_id": batch_id,
        "message_count": len(processed),
        "source": payload.source_type,
        "channel": payload.channel_name,
    }
```

---

#### **N** `src/feeds/whatsapp_routes.py`

WhatsApp-specific summarization endpoints:

```python
"""WhatsApp-specific API routes for summarization."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])

class WhatsAppSummarizeRequest(BaseModel):
    time_from: Optional[datetime] = None
    time_to: Optional[datetime] = None
    max_messages: int = Field(default=1000, le=5000)
    summary_type: str = "comprehensive"
    output_format: str = "markdown"
    custom_prompt: Optional[str] = None

@router.post("/chats/{chat_jid}/summarize")
async def summarize_whatsapp_chat(
    chat_jid: str,
    request: WhatsAppSummarizeRequest,
):
    """Summarize a WhatsApp chat. Mirrors /discord/channels/{id}/summarize."""
    # Fetch stored messages for this chat JID from the ingest store
    messages = await get_stored_messages(
        source_type="whatsapp",
        channel_id=chat_jid,
        time_from=request.time_from,
        time_to=request.time_to,
        limit=request.max_messages,
    )
    if not messages:
        raise HTTPException(status_code=404, detail="No messages found")

    options = SummaryOptions(
        summary_length=map_summary_type(request.summary_type),
        source_type="whatsapp",
    )
    result = await engine.summarize_messages(messages, options)
    return result.to_plain_dict()

@router.get("/chats")
async def list_whatsapp_chats():
    """List all WhatsApp chats with ingested messages."""
    ...

@router.get("/chats/{chat_jid}/messages")
async def get_whatsapp_messages(chat_jid: str, limit: int = 100, offset: int = 0):
    """Paginated message history for a WhatsApp chat."""
    ...
```

---

### 2.6 Data Layer (`src/data/`)

#### **M** `src/data/migrations/001_initial_schema.sql` (or new migration)

**Do NOT modify** the existing migration. Create a new one:

#### **N** `src/data/migrations/002_whatsapp_support.sql`

```sql
-- Migration: Add WhatsApp/multi-source support
-- Date: 2026-02-11

-- Add source tracking to existing summaries table
ALTER TABLE summaries ADD COLUMN source_type TEXT NOT NULL DEFAULT 'discord';
ALTER TABLE summaries ADD COLUMN source_channel_id TEXT;

-- WhatsApp ingested message batches
CREATE TABLE IF NOT EXISTS ingest_batches (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    channel_type TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    time_range_start TEXT NOT NULL,
    time_range_end TEXT NOT NULL,
    raw_payload TEXT NOT NULL,       -- JSON
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ingest_batch_channel ON ingest_batches(source_type, channel_id);
CREATE INDEX IF NOT EXISTS idx_ingest_batch_time ON ingest_batches(time_range_start, time_range_end);

-- Ingested messages (denormalized for fast query)
CREATE TABLE IF NOT EXISTS ingest_messages (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES ingest_batches(id),
    source_type TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    content TEXT,
    has_attachments INTEGER DEFAULT 0,
    reply_to_id TEXT,
    is_forwarded INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',      -- JSON
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ingest_msg_channel ON ingest_messages(source_type, channel_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ingest_msg_sender ON ingest_messages(sender_id);

-- Track which chats are configured for auto-summarization
CREATE TABLE IF NOT EXISTS tracked_chats (
    chat_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    chat_name TEXT,
    chat_type TEXT NOT NULL,
    auto_summarize INTEGER DEFAULT 0,
    summary_schedule TEXT,           -- cron expression
    summary_type TEXT DEFAULT 'comprehensive',
    webhook_url TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Record schema version
INSERT INTO schema_versions (version, description, applied_at)
VALUES (2, 'Add WhatsApp and multi-source support', datetime('now'));
```

---

#### **M** `src/data/base.py`

**Current state:** Defines `SummaryRepository`, `ConfigRepository`, `TaskRepository`, etc. as abstract base classes. `SearchCriteria` filters by `guild_id` and `channel_id`.

**Changes needed:**

1. **Add `source_type` to `SearchCriteria`:**
```python
@dataclass
class SearchCriteria:
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    source_type: Optional[str] = None  # New: 'discord', 'whatsapp'
    # ... rest unchanged ...
```

2. **Add new `IngestRepository` ABC:**
```python
class IngestRepository(ABC):
    """Repository for ingested message batches from external sources."""

    @abstractmethod
    async def store_batch(self, batch: IngestDocument) -> str: ...

    @abstractmethod
    async def get_messages(
        self, source_type: str, channel_id: str,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[ProcessedMessage]: ...

    @abstractmethod
    async def list_channels(self, source_type: str) -> list[dict]: ...

    @abstractmethod
    async def get_channel_stats(self, source_type: str, channel_id: str) -> dict: ...
```

---

#### **M** `src/data/sqlite.py`

**Current state:** Implements the repository ABCs with SQLite queries.

**Changes needed:** Add `IngestRepository` implementation:

```python
class SQLiteIngestRepository(IngestRepository):
    """SQLite implementation of IngestRepository."""

    async def store_batch(self, batch: IngestDocument) -> str:
        batch_id = str(uuid.uuid4())
        await self.db.execute(
            "INSERT INTO ingest_batches (id, source_type, channel_id, ...) VALUES (?, ?, ?, ...)",
            (batch_id, batch.source_type, batch.channel_id, ...)
        )
        for msg in batch.messages:
            await self.db.execute(
                "INSERT INTO ingest_messages (id, batch_id, ...) VALUES (?, ?, ...)",
                (msg.id, batch_id, ...)
            )
        return batch_id

    async def get_messages(self, source_type, channel_id, time_from=None, time_to=None, limit=1000):
        query = "SELECT * FROM ingest_messages WHERE source_type = ? AND channel_id = ?"
        params = [source_type, channel_id]
        if time_from:
            query += " AND timestamp >= ?"
            params.append(time_from.isoformat())
        if time_to:
            query += " AND timestamp <= ?"
            params.append(time_to.isoformat())
        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)
        rows = await self.db.fetch_all(query, params)
        return [self._row_to_processed_message(row) for row in rows]
```

---

### 2.7 App Wiring (`src/main.py`, `src/container.py`)

#### **M** `src/main.py`

**Current state:** `SummaryBotApp` initializes Discord bot, webhook server, scheduler. The FastAPI app is created inside the webhook service.

**Changes needed:** Register the new ingest and WhatsApp routers with the FastAPI app:

```python
# In the webhook/API server setup section:
from src.feeds.ingest_handler import router as ingest_router
from src.feeds.whatsapp_routes import router as whatsapp_router

# After existing router registration:
app.include_router(ingest_router)
app.include_router(whatsapp_router)
```

**Risk:** Very low — two lines.

---

#### **M** `src/container.py`

**Current state:** `ServiceContainer` lazy-initializes Claude client, cache, repos.

**Changes needed:** Add ingest repository:

```python
@property
def ingest_repository(self):
    if not hasattr(self, '_ingest_repo'):
        self._ingest_repo = SQLiteIngestRepository(self.db_connection)
    return self._ingest_repo
```

---

### 2.8 Configuration

#### **M** `.env.example`

Add WhatsApp-related environment variables:

```bash
# WhatsApp Ingest (ADR-002)
INGEST_API_KEY=              # API key for POST /api/v1/ingest
WHATSAPP_INGEST_ENABLED=true
WHATSAPP_AUTO_SUMMARIZE=false
WHATSAPP_DEFAULT_SUMMARY_TYPE=comprehensive
```

---

### 2.9 Tests (`tests/`)

#### **N** `tests/test_whatsapp_processor.py`

Unit tests for `WhatsAppMessageProcessor.convert_batch()` and `convert_message()`.

#### **N** `tests/test_ingest_handler.py`

Integration tests for `POST /api/v1/ingest` — auth, validation, happy path.

#### **N** `tests/test_whatsapp_routes.py`

Integration tests for `/api/v1/whatsapp/chats/{jid}/summarize`.

#### **N** `tests/test_whatsapp_prompts.py`

Tests that WhatsApp prompt templates are selected correctly and produce valid prompts.

---

## 3. Summary — Change Inventory

| # | File | Action | Risk | Description |
|---|------|--------|------|-------------|
| 1 | `src/models/message.py` | **M** | Medium | Add `SourceType` enum, `source_type` field, WhatsApp message types |
| 2 | `src/models/ingest.py` | **N** | Low | Ingest payload models (`IngestDocument`, `IngestMessage`) |
| 3 | `src/models/summary.py` | **M** | Low | Add `source_type` to `SummarizationContext` and `SummaryOptions` |
| 4 | `src/message_processing/__init__.py` | **M** | Low | Export `WhatsAppMessageProcessor` |
| 5 | `src/message_processing/processor.py` | **M** | Low | Add `process_raw_messages()` method |
| 6 | `src/message_processing/whatsapp_processor.py` | **N** | Low | Convert ingest messages to `ProcessedMessage` |
| 7 | `src/message_processing/cleaner.py` | **M** | Low | Source-aware cleaning branch |
| 8 | `src/message_processing/filter.py` | **M** | Low | Source-aware filtering branch |
| 9 | `src/summarization/prompt_builder.py` | **M** | Medium | WhatsApp prompt templates, source-keyed lookup |
| 10 | `src/summarization/engine.py` | **M** | Very Low | Pass `source_type` through context |
| 11 | `src/feeds/ingest_handler.py` | **N** | Low | `POST /api/v1/ingest` endpoint |
| 12 | `src/feeds/whatsapp_routes.py` | **N** | Low | WhatsApp summarization API routes |
| 13 | `src/data/migrations/002_whatsapp_support.sql` | **N** | Low | Schema for ingest batches + messages |
| 14 | `src/data/base.py` | **M** | Low | `IngestRepository` ABC, `source_type` in `SearchCriteria` |
| 15 | `src/data/sqlite.py` | **M** | Medium | `SQLiteIngestRepository` implementation |
| 16 | `src/main.py` | **M** | Very Low | Register two new routers |
| 17 | `src/container.py` | **M** | Very Low | Add `ingest_repository` property |
| 18 | `.env.example` | **M** | Very Low | Add WhatsApp env vars |
| 19 | `tests/test_whatsapp_processor.py` | **N** | — | Unit tests |
| 20 | `tests/test_ingest_handler.py` | **N** | — | Integration tests |
| 21 | `tests/test_whatsapp_routes.py` | **N** | — | API tests |
| 22 | `tests/test_whatsapp_prompts.py` | **N** | — | Prompt tests |

**Totals:** 13 files modified, 9 files created, 0 files deleted.

---

## 4. What Does NOT Change

These components work as-is with no modifications:

| Component | Why |
|-----------|-----|
| `src/summarization/claude_client.py` | Talks to Claude API — source-agnostic |
| `src/summarization/response_parser.py` | Parses Claude responses — source-agnostic |
| `src/summarization/cache.py` | Caches by summary hash — source-agnostic |
| `src/summarization/optimization.py` | Token optimization — source-agnostic |
| `src/feeds/generator.py` | RSS/Atom output — could generate feeds from WhatsApp summaries too, no changes needed |
| `src/webhook_service/` | Webhook delivery — already generic |
| `src/discord_bot/` | Discord slash commands — stays Discord-only, untouched |
| `src/permissions/` | Permission system — new WhatsApp permissions would be API-key based, not Discord roles |
| `src/scheduling/` | Task scheduler — can schedule WhatsApp summaries via existing `scheduled_tasks` table |
| `src/prompts/resolver.py` | Prompt resolution chain — works with any prompt, source-agnostic |
| `src/config/` | Guild config — WhatsApp config uses env vars + `tracked_chats` table instead |

---

## 5. Migration Path

### Step 1: Non-breaking model changes
Add `source_type` fields with default `"discord"` to `ProcessedMessage`, `SummaryOptions`, `SummarizationContext`, `SearchCriteria`. **Zero existing behavior changes.** All existing code continues to work because defaults match current behavior.

### Step 2: New files (no impact on existing code)
Create `src/models/ingest.py`, `src/message_processing/whatsapp_processor.py`, `src/feeds/ingest_handler.py`, `src/feeds/whatsapp_routes.py`, migration SQL. These are pure additions.

### Step 3: Wire up
Register routers in `main.py`, add repo to `container.py`. Two-line changes.

### Step 4: Source-aware branching
Update `cleaner.py`, `filter.py`, `prompt_builder.py` to branch on `source_type`. Existing Discord paths remain the default — WhatsApp paths are additive branches that only activate when `source_type == "whatsapp"`.

### Step 5: Test
All existing Discord tests must pass unchanged. New WhatsApp tests validate the new code paths.

---

## 6. Backward Compatibility Guarantee

Every change uses **default values matching current behavior**:
- `source_type: SourceType = SourceType.DISCORD`
- `source_type: str = "discord"`
- System prompt lookup falls back to Discord prompts

**No existing Discord functionality is altered.** The changes are purely additive. Running SummaryBot-NG without any WhatsApp configuration behaves identically to today.
