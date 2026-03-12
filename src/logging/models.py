"""
Data models for command logging system.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from ..models.base import BaseModel, generate_id
from src.utils.time import utc_now_naive


class CommandType(Enum):
    """Types of commands that can be logged."""
    SLASH_COMMAND = "slash_command"
    SCHEDULED_TASK = "scheduled_task"
    WEBHOOK_REQUEST = "webhook_request"


class CommandStatus(Enum):
    """Execution status of a command."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class CommandLog(BaseModel):
    """
    Represents a logged command execution.

    This model captures all relevant information about a command execution
    including context, parameters, timing, and results.
    """

    # Identity and classification
    id: str = field(default_factory=generate_id)
    command_type: CommandType = CommandType.SLASH_COMMAND
    command_name: str = ""

    # Context
    user_id: Optional[str] = None  # Null for scheduled tasks
    guild_id: str = ""
    channel_id: str = ""

    # Execution data
    parameters: Dict[str, Any] = field(default_factory=dict)
    execution_context: Dict[str, Any] = field(default_factory=dict)

    # Results
    status: CommandStatus = CommandStatus.SUCCESS
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    # Output
    result_summary: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_completed(self, result_summary: Dict[str, Any] = None) -> None:
        """Mark command execution as completed successfully."""
        self.completed_at = utc_now_naive()
        self.duration_ms = int(
            (self.completed_at - self.started_at).total_seconds() * 1000
        )
        self.status = CommandStatus.SUCCESS
        if result_summary:
            self.result_summary = result_summary

    def mark_failed(self, error_code: str, error_message: str) -> None:
        """Mark command execution as failed."""
        self.completed_at = utc_now_naive()
        self.duration_ms = int(
            (self.completed_at - self.started_at).total_seconds() * 1000
        )
        self.status = CommandStatus.FAILED
        self.error_code = error_code
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "command_type": self.command_type.value,
            "command_name": self.command_name,
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "parameters": json.dumps(self.parameters),
            "execution_context": json.dumps(self.execution_context),
            "status": self.status.value,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "result_summary": json.dumps(self.result_summary) if self.result_summary else None,
            "metadata": json.dumps(self.metadata)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommandLog':
        """Create instance from database row."""
        return cls(
            id=data["id"],
            command_type=CommandType(data["command_type"]),
            command_name=data["command_name"],
            user_id=data.get("user_id"),
            guild_id=data["guild_id"],
            channel_id=data["channel_id"],
            parameters=json.loads(data["parameters"]) if data["parameters"] else {},
            execution_context=json.loads(data["execution_context"]) if data["execution_context"] else {},
            status=CommandStatus(data["status"]),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            duration_ms=data.get("duration_ms"),
            result_summary=json.loads(data["result_summary"]) if data.get("result_summary") else {},
            metadata=json.loads(data["metadata"]) if data["metadata"] else {}
        )


@dataclass
class LoggingConfig:
    """Configuration for command logging."""

    enabled: bool = True
    retention_days: int = 90
    async_writes: bool = True
    batch_size: int = 100
    flush_interval_seconds: int = 5
    sanitize_enabled: bool = True
    max_message_length: int = 200
    redact_patterns: List[str] = field(default_factory=lambda: [
        "token", "secret", "key", "password", "api_key", "bearer", "authorization"
    ])

    @classmethod
    def from_env(cls) -> 'LoggingConfig':
        """Load configuration from environment variables."""
        return cls(
            enabled=os.getenv("COMMAND_LOG_ENABLED", "true").lower() == "true",
            retention_days=int(os.getenv("COMMAND_LOG_RETENTION_DAYS", "90")),
            async_writes=os.getenv("COMMAND_LOG_ASYNC_WRITES", "true").lower() == "true",
            batch_size=int(os.getenv("COMMAND_LOG_BATCH_SIZE", "100")),
            flush_interval_seconds=int(os.getenv("COMMAND_LOG_FLUSH_INTERVAL_SECONDS", "5")),
            sanitize_enabled=os.getenv("COMMAND_LOG_SANITIZE_ENABLED", "true").lower() == "true",
            max_message_length=int(os.getenv("COMMAND_LOG_MAX_MESSAGE_LENGTH", "200")),
            redact_patterns=os.getenv("COMMAND_LOG_REDACT_PATTERNS", "token,secret,key,password,api_key").split(",")
        )
