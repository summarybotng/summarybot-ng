"""
WhatsApp Import models (ADR-081, ADR-112).

Provides data classes for import tracking, identity resolution,
participant management, and coverage gap awareness.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


class ImportStatus(str, Enum):
    """Status of a WhatsApp import."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportFormat(str, Enum):
    """Format of WhatsApp export file."""
    WHATSAPP_TXT = "whatsapp_txt"
    WHATSAPP_TXT_ANDROID = "whatsapp_txt_android"
    READER_BOT_JSON = "reader_bot_json"


@dataclass
class WhatsAppImport:
    """A WhatsApp chat import record."""
    id: str
    guild_id: str
    chat_id: str
    chat_name: str

    # Attribution
    imported_by: str
    imported_at: datetime

    # File metadata
    original_filename: str
    file_hash: str
    file_size_bytes: int
    format: str

    # Content summary
    date_range_start: datetime
    date_range_end: datetime
    message_count: int
    participant_count: int

    # Processing status
    status: ImportStatus = ImportStatus.PENDING
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None

    # Anonymization
    anonymization_version: int = 1
    participants_json: Optional[str] = None

    # ADR-112: Detected events from system messages
    detected_join_date: Optional[date] = None
    detected_events_json: Optional[str] = None

    # Soft delete
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None

    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "imported_by": self.imported_by,
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
            "original_filename": self.original_filename,
            "file_hash": self.file_hash,
            "file_size_bytes": self.file_size_bytes,
            "format": self.format,
            "date_range": {
                "start": self.date_range_start.isoformat() if self.date_range_start else None,
                "end": self.date_range_end.isoformat() if self.date_range_end else None,
            },
            "message_count": self.message_count,
            "participant_count": self.participant_count,
            "status": self.status.value if isinstance(self.status, ImportStatus) else self.status,
            "error_message": self.error_message,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }


@dataclass
class WhatsAppParticipant:
    """A WhatsApp participant identity."""
    id: str
    guild_id: str
    chat_id: str

    # Identity
    phone_hash: Optional[str]
    pseudonym: str

    # Aliases
    aliases: List[str] = field(default_factory=list)
    preferred_name: Optional[str] = None

    # Statistics
    first_seen_import_id: Optional[str] = None
    message_count: int = 0

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "pseudonym": self.pseudonym,
            "preferred_name": self.preferred_name,
            "message_count": self.message_count,
            "alias_count": len(self.aliases),
            # Note: aliases not exposed in public API
        }

    def to_admin_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for admin API responses (includes aliases)."""
        result = self.to_dict()
        result["aliases"] = self.aliases
        result["phone_hash"] = self.phone_hash[:4] + "****" if self.phone_hash else None
        return result


@dataclass
class WhatsAppIdentityMerge:
    """Record of an identity merge operation."""
    id: str
    guild_id: str
    chat_id: str

    source_participant_id: str
    target_participant_id: str

    merged_by: str
    merged_at: datetime
    reason: str  # 'manual', 'phone_match', 'fuzzy_alias'

    reversed_at: Optional[datetime] = None
    reversed_by: Optional[str] = None

    source_data_json: Optional[str] = None


@dataclass
class WhatsAppMessageFingerprint:
    """Fingerprint for message deduplication."""
    fingerprint: str
    import_id: str
    participant_id: str
    message_timestamp: datetime
    created_at: Optional[datetime] = None


class GapType(str, Enum):
    """Type of coverage gap (ADR-112)."""
    BEFORE_JOIN = "before_join"  # Gap before user joined the chat (missing messages)
    BETWEEN_IMPORTS = "between_imports"  # Gap between two imports
    AFTER_LAST = "after_last"  # Gap after last import to present
    PRE_JOIN_CONTEXT = "pre_join_context"  # Period before join with context messages (not a gap)


class DetectedEventType(str, Enum):
    """Type of detected event from system messages (ADR-112)."""
    GROUP_CREATED = "group_created"
    USER_JOINED = "user_joined"
    USER_ADDED = "user_added"
    USER_LEFT = "user_left"


@dataclass
class DetectedEvent:
    """An event detected from system messages (ADR-112)."""
    event_type: DetectedEventType
    timestamp: datetime
    details: Optional[str] = None  # e.g., "joined using invite link"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


@dataclass
class CoverageGap:
    """A gap in coverage for a WhatsApp chat (ADR-112)."""
    start: date
    end: date
    gap_type: GapType
    days: int
    can_fill: bool = True  # True if another user might have this data

    def to_dict(self) -> Dict[str, Any]:
        fill_hints = {
            GapType.BEFORE_JOIN: "Ask group members who joined earlier to export",
            GapType.BETWEEN_IMPORTS: "Import another export covering this period",
            GapType.AFTER_LAST: "Export recent messages from WhatsApp",
            GapType.PRE_JOIN_CONTEXT: "Context period before you joined (read-only history)",
        }
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "type": self.gap_type.value,
            "days": self.days,
            "can_fill": self.can_fill,
            "fill_hint": fill_hints.get(self.gap_type, ""),
        }


@dataclass
class ChatCoverage:
    """Coverage information for a WhatsApp chat (ADR-081, ADR-112)."""
    chat_id: str
    chat_name: str
    earliest: Optional[datetime]
    latest: Optional[datetime]
    total_messages: int
    import_count: int
    gaps: List[CoverageGap] = field(default_factory=list)
    # ADR-112: Additional coverage metadata
    detected_join_date: Optional[date] = None
    detected_events: List[DetectedEvent] = field(default_factory=list)
    coverage_percent: Optional[float] = None  # Estimated coverage if join date known

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "earliest": self.earliest.isoformat() if self.earliest else None,
            "latest": self.latest.isoformat() if self.latest else None,
            "total_messages": self.total_messages,
            "import_count": self.import_count,
            "gaps": [g.to_dict() for g in self.gaps],
            "detected_join_date": self.detected_join_date.isoformat() if self.detected_join_date else None,
            "detected_events": [e.to_dict() for e in self.detected_events],
            "coverage_percent": round(self.coverage_percent, 1) if self.coverage_percent else None,
        }


@dataclass
class ImportUploadResult:
    """Result of uploading a WhatsApp import."""
    import_id: str
    status: str
    message_count: int
    participant_count: int
    date_range_start: datetime
    date_range_end: datetime
    duplicate_of: Optional[str] = None
    new_messages: Optional[int] = None
    skipped_messages: Optional[int] = None
    message: Optional[str] = None
