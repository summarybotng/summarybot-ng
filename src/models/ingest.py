"""
Normalized ingest models for multi-source message ingestion (ADR-002).

These models define the contract between external data sources (WhatsApp, Slack, etc.)
and SummaryBot-NG's internal processing pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field

from .message import SourceType


class ParticipantRole(str, Enum):
    """Participant roles in a conversation."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class IngestParticipant(BaseModel):
    """A participant in an ingested conversation."""
    id: str  # Source-native ID (JID for WhatsApp, Discord ID, etc.)
    display_name: str
    role: ParticipantRole = ParticipantRole.MEMBER
    phone_number: Optional[str] = None  # WhatsApp-specific


class IngestAttachment(BaseModel):
    """An attachment in an ingested message."""
    filename: str
    mime_type: str
    size_bytes: int
    url: Optional[str] = None  # CDN URL (Discord) or None (WhatsApp)
    local_path: Optional[str] = None  # Local file path (WhatsApp media)
    caption: Optional[str] = None


class IngestReaction(BaseModel):
    """A reaction on an ingested message."""
    emoji: str
    sender_id: str


class IngestMessage(BaseModel):
    """A single normalized message from any data source."""
    id: str  # Source-native message ID
    source_type: SourceType
    channel_id: str  # Chat JID (WhatsApp) or Channel ID (Discord)
    sender: IngestParticipant
    timestamp: datetime
    content: str  # Plain text content
    attachments: List[IngestAttachment] = Field(default_factory=list)
    reply_to_id: Optional[str] = None  # Quoted message ID
    is_from_bot_owner: bool = False  # Message sent by the account owner
    is_forwarded: bool = False
    is_edited: bool = False
    is_deleted: bool = False
    reactions: List[IngestReaction] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Source-specific extra data


class ChannelType(str, Enum):
    """Types of channels/conversations."""
    INDIVIDUAL = "individual"  # 1:1 chat
    GROUP = "group"  # Group chat
    THREAD = "thread"  # Thread within a channel
    CHANNEL = "channel"  # Public channel (Discord/Slack style)
    BROADCAST = "broadcast"  # Broadcast list


class IngestDocument(BaseModel):
    """A batch of messages from a single conversation, ready for processing.

    This is the payload format for the POST /api/v1/ingest endpoint.
    """
    source_type: SourceType
    channel_id: str
    channel_name: str
    channel_type: ChannelType
    participants: List[IngestParticipant] = Field(default_factory=list)
    messages: List[IngestMessage]
    time_range_start: datetime
    time_range_end: datetime
    total_message_count: int
    metadata: Dict[str, Any] = Field(default_factory=dict)  # E.g., group description, topic

    class Config:
        """Pydantic config."""
        use_enum_values = True


class IngestResponse(BaseModel):
    """Response from the ingest endpoint."""
    status: str = "accepted"
    batch_id: str
    message_count: int
    source: str
    channel: str
    processed: bool = False


class IngestBatch(BaseModel):
    """Stored ingest batch record."""
    id: str
    source_type: SourceType
    channel_id: str
    channel_name: Optional[str] = None
    channel_type: ChannelType
    message_count: int
    time_range_start: datetime
    time_range_end: datetime
    raw_payload: str  # JSON string of IngestDocument
    processed: bool = False
    document_id: Optional[str] = None  # Link to generated document
    created_at: datetime = Field(default_factory=datetime.utcnow)
