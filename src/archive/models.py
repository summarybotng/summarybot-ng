"""
Archive data models for retrospective summary storage.

Implements ADR-006: Retrospective Summary Archive with platform-agnostic
source abstraction, cost tracking, and versioned prompt support.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
import json
import re


class SourceType(Enum):
    """Supported chat platforms."""
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    TELEGRAM = "telegram"


class SummaryStatus(Enum):
    """Status of a summary generation."""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    DELETED = "deleted"


class IncompleteReason(Enum):
    """Reasons why a summary could not be generated."""
    NO_MESSAGES = "NO_MESSAGES"
    INSUFFICIENT_MESSAGES = "INSUFFICIENT_MESSAGES"
    API_ERROR = "API_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    BOT_OFFLINE = "BOT_OFFLINE"
    SOURCE_INACCESSIBLE = "SOURCE_INACCESSIBLE"
    PROMPT_ERROR = "PROMPT_ERROR"
    EXPORT_UNAVAILABLE = "EXPORT_UNAVAILABLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class DSTTransition(Enum):
    """DST transition type for a day."""
    NONE = None
    SPRING_FORWARD = "spring_forward"
    FALL_BACK = "fall_back"


@dataclass
class ArchiveSource:
    """Platform-agnostic source identifier."""
    source_type: SourceType
    server_id: str
    server_name: str
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None

    @property
    def source_key(self) -> str:
        """Unique key for this source (used in cost tracking, etc.)."""
        return f"{self.source_type.value}:{self.server_id}"

    @property
    def folder_name(self) -> str:
        """Generate safe folder name for this source."""
        safe_name = re.sub(r'[^\w\-]', '-', self.server_name.lower())
        return f"{safe_name}_{self.server_id}"

    @property
    def channel_folder_name(self) -> Optional[str]:
        """Generate safe folder name for channel (if applicable)."""
        if not self.channel_id or not self.channel_name:
            return None
        safe_name = re.sub(r'[^\w\-]', '-', self.channel_name.lower())
        return f"{safe_name}_{self.channel_id}"

    def get_archive_path(self, archive_root: Path) -> Path:
        """Generate full archive path for this source."""
        base = archive_root / "sources" / self.source_type.value / self.folder_name
        if self.channel_id:
            return base / "channels" / self.channel_folder_name / "summaries"
        return base / "summaries"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source_type": self.source_type.value,
            "server_id": self.server_id,
            "server_name": self.server_name,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArchiveSource":
        """Deserialize from dictionary."""
        return cls(
            source_type=SourceType(data["source_type"]),
            server_id=data["server_id"],
            server_name=data["server_name"],
            channel_id=data.get("channel_id"),
            channel_name=data.get("channel_name"),
        )


@dataclass
class PeriodInfo:
    """Time period information with timezone and DST handling."""
    start: datetime
    end: datetime
    timezone: str
    duration_hours: int = 24
    dst_transition: Optional[str] = None  # "spring_forward", "fall_back", or None

    @property
    def start_utc(self) -> datetime:
        """Get start time in UTC."""
        import pytz
        tz = pytz.timezone(self.timezone)
        if self.start.tzinfo is None:
            local_dt = tz.localize(self.start)
        else:
            local_dt = self.start
        return local_dt.astimezone(pytz.UTC).replace(tzinfo=None)

    @property
    def end_utc(self) -> datetime:
        """Get end time in UTC."""
        import pytz
        tz = pytz.timezone(self.timezone)
        if self.end.tzinfo is None:
            local_dt = tz.localize(self.end)
        else:
            local_dt = self.end
        return local_dt.astimezone(pytz.UTC).replace(tzinfo=None)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "timezone": self.timezone,
            "duration_hours": self.duration_hours,
            "dst_transition": self.dst_transition,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PeriodInfo":
        """Deserialize from dictionary."""
        return cls(
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            timezone=data["timezone"],
            duration_hours=data.get("duration_hours", 24),
            dst_transition=data.get("dst_transition"),
        )


@dataclass
class GenerationInfo:
    """Information about how a summary was generated."""
    prompt_version: str
    prompt_checksum: str
    model: str
    options: Dict[str, Any]
    duration_seconds: float
    tokens_input: int
    tokens_output: int
    cost_usd: float
    pricing_version: str
    api_key_used: str  # "server:{source_key}" or "default"
    provider: str = "openrouter"

    @property
    def tokens_total(self) -> int:
        """Total tokens used."""
        return self.tokens_input + self.tokens_output

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "prompt_version": self.prompt_version,
            "prompt_checksum": self.prompt_checksum,
            "model": self.model,
            "options": self.options,
            "duration_seconds": self.duration_seconds,
            "tokens_used": {
                "input": self.tokens_input,
                "output": self.tokens_output,
            },
            "cost_usd": self.cost_usd,
            "pricing_version": self.pricing_version,
            "api_key_used": self.api_key_used,
            "provider": self.provider,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenerationInfo":
        """Deserialize from dictionary."""
        tokens = data.get("tokens_used", {})
        return cls(
            prompt_version=data["prompt_version"],
            prompt_checksum=data["prompt_checksum"],
            model=data["model"],
            options=data.get("options", {}),
            duration_seconds=data.get("duration_seconds", 0.0),
            tokens_input=tokens.get("input", 0),
            tokens_output=tokens.get("output", 0),
            cost_usd=data.get("cost_usd", 0.0),
            pricing_version=data.get("pricing_version", "unknown"),
            api_key_used=data.get("api_key_used", "default"),
            provider=data.get("provider", "openrouter"),
        )


@dataclass
class GenerationLock:
    """Lock information for in-progress generation."""
    job_id: str
    acquired_at: datetime
    acquired_by: str
    expires_at: datetime

    def is_expired(self) -> bool:
        """Check if lock has expired."""
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "job_id": self.job_id,
            "acquired_at": self.acquired_at.isoformat(),
            "acquired_by": self.acquired_by,
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenerationLock":
        """Deserialize from dictionary."""
        return cls(
            job_id=data["job_id"],
            acquired_at=datetime.fromisoformat(data["acquired_at"]),
            acquired_by=data["acquired_by"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )


@dataclass
class SummaryStatistics:
    """Statistics about a summary's source content."""
    message_count: int
    participant_count: int
    word_count: int = 0
    attachment_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "message_count": self.message_count,
            "participant_count": self.participant_count,
            "word_count": self.word_count,
            "attachment_count": self.attachment_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SummaryStatistics":
        """Deserialize from dictionary."""
        return cls(
            message_count=data.get("message_count", 0),
            participant_count=data.get("participant_count", 0),
            word_count=data.get("word_count", 0),
            attachment_count=data.get("attachment_count", 0),
        )


@dataclass
class BackfillInfo:
    """Information about backfill status."""
    is_backfill: bool
    original_generation_failed: bool = False
    backfilled_at: Optional[datetime] = None
    reason: Optional[str] = None  # "historical_archive", "prompt_update", "retry", etc.

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "is_backfill": self.is_backfill,
            "original_generation_failed": self.original_generation_failed,
            "backfilled_at": self.backfilled_at.isoformat() if self.backfilled_at else None,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackfillInfo":
        """Deserialize from dictionary."""
        backfilled_at = data.get("backfilled_at")
        return cls(
            is_backfill=data.get("is_backfill", False),
            original_generation_failed=data.get("original_generation_failed", False),
            backfilled_at=datetime.fromisoformat(backfilled_at) if backfilled_at else None,
            reason=data.get("reason"),
        )


@dataclass
class IncompleteInfo:
    """Information about why a summary is incomplete."""
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IncompleteInfo":
        """Deserialize from dictionary."""
        return cls(
            code=data["code"],
            message=data["message"],
            details=data.get("details", {}),
        )


@dataclass
class SummaryMetadata:
    """Metadata for a summary file (.meta.json companion)."""
    summary_id: Optional[str]
    generated_at: Optional[datetime]
    period: PeriodInfo
    source: ArchiveSource
    status: SummaryStatus
    statistics: Optional[SummaryStatistics] = None
    generation: Optional[GenerationInfo] = None
    backfill: Optional[BackfillInfo] = None
    incomplete_reason: Optional[IncompleteInfo] = None
    lock: Optional[GenerationLock] = None
    content_checksum: Optional[str] = None
    references_validated: bool = False
    backfill_eligible: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            "summary_id": self.summary_id,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "period": self.period.to_dict(),
            "source": self.source.to_dict(),
            "status": self.status.value,
            "backfill_eligible": self.backfill_eligible,
        }

        if self.statistics:
            result["statistics"] = self.statistics.to_dict()
        if self.generation:
            result["generation"] = self.generation.to_dict()
        if self.backfill:
            result["backfill"] = self.backfill.to_dict()
        if self.incomplete_reason:
            result["incomplete_reason"] = self.incomplete_reason.to_dict()
        if self.lock:
            result["lock"] = self.lock.to_dict()
        if self.content_checksum:
            result["integrity"] = {
                "content_checksum": self.content_checksum,
                "references_validated": self.references_validated,
            }

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SummaryMetadata":
        """Deserialize from dictionary."""
        generated_at = data.get("generated_at")
        integrity = data.get("integrity", {})

        return cls(
            summary_id=data.get("summary_id"),
            generated_at=datetime.fromisoformat(generated_at) if generated_at else None,
            period=PeriodInfo.from_dict(data["period"]),
            source=ArchiveSource.from_dict(data["source"]),
            status=SummaryStatus(data["status"]),
            statistics=SummaryStatistics.from_dict(data["statistics"]) if data.get("statistics") else None,
            generation=GenerationInfo.from_dict(data["generation"]) if data.get("generation") else None,
            backfill=BackfillInfo.from_dict(data["backfill"]) if data.get("backfill") else None,
            incomplete_reason=IncompleteInfo.from_dict(data["incomplete_reason"]) if data.get("incomplete_reason") else None,
            lock=GenerationLock.from_dict(data["lock"]) if data.get("lock") else None,
            content_checksum=integrity.get("content_checksum"),
            references_validated=integrity.get("references_validated", False),
            backfill_eligible=data.get("backfill_eligible", True),
        )

    def save(self, path: Path) -> None:
        """Save metadata to JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "SummaryMetadata":
        """Load metadata from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class CostEntry:
    """Single cost entry for a summary generation."""
    source_key: str
    summary_id: str
    timestamp: datetime
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    pricing_version: str
    api_key_source: str = "default"  # "server" or "default"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source_key": self.source_key,
            "summary_id": self.summary_id,
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost_usd": self.cost_usd,
            "pricing_version": self.pricing_version,
            "api_key_source": self.api_key_source,
        }


@dataclass
class SourceManifest:
    """Server/group manifest for a source."""
    source_type: SourceType
    server_id: str
    server_name: str
    default_timezone: str = "UTC"
    default_granularity: str = "daily"
    prompt_version_current: Optional[str] = None
    prompt_checksum_current: Optional[str] = None
    prompt_updated_at: Optional[datetime] = None
    cost_tracking_enabled: bool = True
    budget_monthly_usd: Optional[float] = None
    alert_threshold_percent: int = 80
    priority: int = 2
    openrouter_key_ref: Optional[str] = None
    use_server_key: bool = False
    fallback_to_default: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source_type": self.source_type.value,
            "server_id": self.server_id,
            "server_name": self.server_name,
            "default_timezone": self.default_timezone,
            "default_granularity": self.default_granularity,
            "prompt_versions": {
                "current": {
                    "version": self.prompt_version_current,
                    "checksum": self.prompt_checksum_current,
                    "updated_at": self.prompt_updated_at.isoformat() if self.prompt_updated_at else None,
                }
            } if self.prompt_version_current else None,
            "cost_tracking": {
                "enabled": self.cost_tracking_enabled,
                "budget_monthly_usd": self.budget_monthly_usd,
                "alert_threshold_percent": self.alert_threshold_percent,
                "priority": self.priority,
            },
            "api_keys": {
                "openrouter_key_ref": self.openrouter_key_ref,
                "use_server_key": self.use_server_key,
                "fallback_to_default": self.fallback_to_default,
            },
        }

    def save(self, path: Path) -> None:
        """Save manifest to JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass
class ArchiveManifest:
    """Global archive manifest."""
    schema_version: str = "1.0.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    generator_name: str = "SummaryBot-NG"
    generator_version: str = "2.1.0"
    sources: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "generator": {
                "name": self.generator_name,
                "version": self.generator_version,
            },
            "sources": self.sources,
        }

    def save(self, path: Path) -> None:
        """Save manifest to JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "ArchiveManifest":
        """Load manifest from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)

        return cls(
            schema_version=data.get("schema_version", "1.0.0"),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_updated=datetime.fromisoformat(data["last_updated"]),
            generator_name=data.get("generator", {}).get("name", "SummaryBot-NG"),
            generator_version=data.get("generator", {}).get("version", "unknown"),
            sources=data.get("sources", []),
        )
