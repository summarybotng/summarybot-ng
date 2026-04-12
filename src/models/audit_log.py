"""
Audit log model for tracking user actions and system events.

ADR-045: Audit Logging System
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import json

from .base import generate_id
from src.utils.time import utc_now_naive


class AuditEventCategory(Enum):
    """Category of audit event."""
    AUTH = "auth"           # Authentication events
    ACCESS = "access"       # Resource access
    ACTION = "action"       # User actions/mutations
    SOURCE = "source"       # Source management
    ADMIN = "admin"         # Administrative actions
    SYSTEM = "system"       # System events


class AuditSeverity(Enum):
    """Severity/importance of audit event."""
    DEBUG = "debug"         # Verbose logging (disabled by default)
    INFO = "info"           # Normal operations
    NOTICE = "notice"       # Notable events (first login, etc.)
    WARNING = "warning"     # Potentially suspicious
    ALERT = "alert"         # Security-relevant (failed auth, access denied)


@dataclass
class AuditLog:
    """
    Immutable audit log entry.

    Captures who did what, when, where, and how for security
    monitoring and compliance.
    """
    id: str = field(default_factory=lambda: f"audit_{generate_id()}")
    event_type: str = ""                     # Full event type (e.g., "auth.login.success")
    category: AuditEventCategory = AuditEventCategory.SYSTEM
    severity: AuditSeverity = AuditSeverity.INFO

    # Actor (who)
    user_id: Optional[str] = None            # Discord user ID
    user_name: Optional[str] = None          # Username for display (denormalized)
    session_id: Optional[str] = None         # JWT session identifier

    # Context (where)
    guild_id: Optional[str] = None           # Guild context
    guild_name: Optional[str] = None         # Guild name (denormalized)
    ip_address: Optional[str] = None         # Client IP (anonymized after 30 days)
    user_agent: Optional[str] = None         # Browser/client info

    # Target (what)
    resource_type: Optional[str] = None      # "summary", "schedule", "template", etc.
    resource_id: Optional[str] = None        # ID of affected resource
    resource_name: Optional[str] = None      # Name for display

    # Details (how)
    action: Optional[str] = None             # Specific action taken
    details: Dict[str, Any] = field(default_factory=dict)  # Additional context
    changes: Optional[Dict[str, Any]] = None  # Before/after for mutations

    # Result
    success: bool = True                     # Whether action succeeded
    error_message: Optional[str] = None      # Error if failed

    # Metadata
    timestamp: datetime = field(default_factory=utc_now_naive)
    request_id: Optional[str] = None         # Correlation ID for request tracing
    duration_ms: Optional[int] = None        # Operation duration

    def __post_init__(self):
        """Convert string enums if needed."""
        if isinstance(self.category, str):
            self.category = AuditEventCategory(self.category)
        if isinstance(self.severity, str):
            self.severity = AuditSeverity(self.severity)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "category": self.category.value if isinstance(self.category, AuditEventCategory) else self.category,
            "severity": self.severity.value if isinstance(self.severity, AuditSeverity) else self.severity,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "session_id": self.session_id,
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "action": self.action,
            "details": self.details,
            "changes": self.changes,
            "success": self.success,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "request_id": self.request_id,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLog":
        """Create instance from dictionary."""
        # Handle datetime conversion
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

        # Handle enum conversion
        if isinstance(data.get("category"), str):
            data["category"] = AuditEventCategory(data["category"])
        if isinstance(data.get("severity"), str):
            data["severity"] = AuditSeverity(data["severity"])

        # Handle JSON fields
        if isinstance(data.get("details"), str):
            data["details"] = json.loads(data["details"]) if data["details"] else {}
        if isinstance(data.get("changes"), str):
            data["changes"] = json.loads(data["changes"]) if data["changes"] else None

        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def create(
        cls,
        event_type: str,
        *,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        guild_id: Optional[str] = None,
        guild_name: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        changes: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> "AuditLog":
        """
        Factory method to create an audit log entry.

        Automatically determines category and severity from event_type.
        """
        # Parse category from event type
        parts = event_type.split(".")
        try:
            category = AuditEventCategory(parts[0])
        except ValueError:
            category = AuditEventCategory.SYSTEM

        # Determine severity
        severity = cls._determine_severity(event_type, success)

        return cls(
            event_type=event_type,
            category=category,
            severity=severity,
            user_id=user_id,
            user_name=user_name,
            session_id=session_id,
            guild_id=guild_id,
            guild_name=guild_name,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            action=action,
            details=details or {},
            changes=changes,
            success=success,
            error_message=error_message,
            request_id=request_id,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _determine_severity(event_type: str, success: bool) -> AuditSeverity:
        """Determine severity based on event type and success."""
        if not success:
            if "auth" in event_type or "access.denied" in event_type:
                return AuditSeverity.ALERT
            return AuditSeverity.WARNING

        if "admin" in event_type:
            return AuditSeverity.NOTICE
        if "delete" in event_type or "purge" in event_type:
            return AuditSeverity.NOTICE

        return AuditSeverity.INFO


@dataclass
class AuditSummary:
    """Summary of audit events for a time period."""
    total_count: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_event_type: Dict[str, int] = field(default_factory=dict)
    by_user: Dict[str, int] = field(default_factory=dict)
    by_guild: Dict[str, int] = field(default_factory=dict)
    failed_count: int = 0
    alert_count: int = 0
