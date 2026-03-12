"""
Base exception classes for Summary Bot NG.
"""

import traceback
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from src.utils.time import utc_now_naive


@dataclass
class ErrorContext:
    """Context information for errors."""
    user_id: Optional[str] = None
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    command: Optional[str] = None
    operation: Optional[str] = None
    request_id: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "command": self.command,
            "operation": self.operation,
            "request_id": self.request_id,
            "additional_data": self.additional_data
        }


class SummaryBotException(Exception):
    """Base exception class for all Summary Bot errors."""
    
    def __init__(self, 
                 message: str,
                 error_code: str,
                 context: Optional[ErrorContext] = None,
                 user_message: Optional[str] = None,
                 retryable: bool = False,
                 cause: Optional[Exception] = None):
        """Initialize the exception.
        
        Args:
            message: Technical error message for logging
            error_code: Unique error code for identification
            context: Error context information
            user_message: User-friendly error message
            retryable: Whether the operation can be retried
            cause: The underlying exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or ErrorContext()
        self.user_message = user_message or message
        self.retryable = retryable
        self.cause = cause
        self.timestamp = utc_now_naive()
        self.traceback_str = traceback.format_exc() if cause else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "user_message": self.user_message,
            "timestamp": self.timestamp.isoformat(),
            "retryable": self.retryable,
            "context": self.context.to_dict(),
            "cause": str(self.cause) if self.cause else None,
            "traceback": self.traceback_str
        }
    
    def to_log_string(self) -> str:
        """Generate a formatted log string."""
        parts = [
            f"[{self.error_code}] {self.__class__.__name__}: {self.message}"
        ]
        
        if self.context.operation:
            parts.append(f"Operation: {self.context.operation}")
        
        if self.context.user_id:
            parts.append(f"User: {self.context.user_id}")
        
        if self.context.guild_id:
            parts.append(f"Guild: {self.context.guild_id}")
        
        if self.context.channel_id:
            parts.append(f"Channel: {self.context.channel_id}")
        
        if self.cause:
            parts.append(f"Caused by: {self.cause}")
        
        return " | ".join(parts)
    
    def get_user_response(self) -> str:
        """Get user-friendly response message."""
        if self.retryable:
            return f"{self.user_message} Please try again in a few moments."
        return self.user_message
    
    def with_context(self, **context_updates) -> 'SummaryBotException':
        """Create a new exception with updated context."""
        new_context = ErrorContext(
            user_id=context_updates.get('user_id', self.context.user_id),
            guild_id=context_updates.get('guild_id', self.context.guild_id),
            channel_id=context_updates.get('channel_id', self.context.channel_id),
            command=context_updates.get('command', self.context.command),
            operation=context_updates.get('operation', self.context.operation),
            request_id=context_updates.get('request_id', self.context.request_id),
            additional_data={**self.context.additional_data, **context_updates.get('additional_data', {})}
        )
        
        return self.__class__(
            message=self.message,
            error_code=self.error_code,
            context=new_context,
            user_message=self.user_message,
            retryable=self.retryable,
            cause=self.cause
        )


class CriticalError(SummaryBotException):
    """Critical error that requires immediate attention."""
    
    def __init__(self, message: str, error_code: str, context: Optional[ErrorContext] = None):
        super().__init__(
            message=message,
            error_code=error_code,
            context=context,
            user_message="A critical error occurred. The development team has been notified.",
            retryable=False
        )


class RecoverableError(SummaryBotException):
    """Error that can potentially be recovered from."""
    
    def __init__(self, message: str, error_code: str, context: Optional[ErrorContext] = None,
                 user_message: Optional[str] = None):
        super().__init__(
            message=message,
            error_code=error_code,
            context=context,
            user_message=user_message,
            retryable=True
        )


class UserError(SummaryBotException):
    """Error caused by user input or actions."""
    
    def __init__(self, message: str, error_code: str, user_message: str, 
                 context: Optional[ErrorContext] = None):
        super().__init__(
            message=message,
            error_code=error_code,
            context=context,
            user_message=user_message,
            retryable=False
        )


def create_error_context(user_id: str = None, guild_id: str = None, 
                        channel_id: str = None, command: str = None,
                        operation: str = None, **additional) -> ErrorContext:
    """Helper function to create error context."""
    return ErrorContext(
        user_id=user_id,
        guild_id=guild_id,
        channel_id=channel_id,
        command=command,
        operation=operation,
        additional_data=additional
    )


def handle_unexpected_error(error: Exception, context: Optional[ErrorContext] = None) -> SummaryBotException:
    """Convert unexpected errors to SummaryBotException."""
    if isinstance(error, SummaryBotException):
        return error
    
    return CriticalError(
        message=f"Unexpected error: {str(error)}",
        error_code="UNEXPECTED_ERROR",
        context=context
    )