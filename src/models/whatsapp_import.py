"""
WhatsApp Import models (ADR-081).

Provides data classes for import tracking, identity resolution,
and participant management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


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


@dataclass
class ChatCoverage:
    """Coverage information for a WhatsApp chat."""
    chat_id: str
    chat_name: str
    earliest: Optional[datetime]
    latest: Optional[datetime]
    total_messages: int
    import_count: int
    gaps: List[Dict[str, Any]] = field(default_factory=list)


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
