"""
Command logging system for Summary Bot NG.

Provides comprehensive logging of all commands executed through:
- Discord slash commands
- Scheduled tasks
- Webhook API requests

Features:
- Automatic sensitive data sanitization
- Async batch writing for performance
- Query interface for analytics
- Automatic retention policy enforcement
"""

from .models import (
    CommandLog,
    CommandType,
    CommandStatus,
    LoggingConfig
)
from .logger import CommandLogger
from .repository import CommandLogRepository
from .sanitizer import LogSanitizer
from .decorators import log_command
from .query import CommandLogQuery
from .analytics import CommandAnalytics
from .cleanup import LogCleanupService
from .error_tracker import (
    ErrorTracker,
    get_error_tracker,
    initialize_error_tracker,
    track_errors,
)
from .audit_service import (
    AuditService,
    get_audit_service,
    audit_log,
    audit_action,
)

__all__ = [
    # Models
    "CommandLog",
    "CommandType",
    "CommandStatus",
    "LoggingConfig",
    # Core Services
    "CommandLogger",
    "CommandLogRepository",
    "LogSanitizer",
    # Utilities
    "log_command",
    "CommandLogQuery",
    "CommandAnalytics",
    "LogCleanupService",
    # Error tracking
    "ErrorTracker",
    "get_error_tracker",
    "initialize_error_tracker",
    "track_errors",
    # Audit logging (ADR-045)
    "AuditService",
    "get_audit_service",
    "audit_log",
    "audit_action",
]

__version__ = "1.0.0"
