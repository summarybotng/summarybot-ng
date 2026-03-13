"""
Decorators for automatic command logging.
"""

import functools
import logging
from typing import Callable, Any, Dict, Optional

from .models import CommandType
from .logger import CommandLogger

logger = logging.getLogger(__name__)


def log_command(
    command_type: CommandType,
    command_name: str = None
):
    """
    Decorator to automatically log command execution.

    Usage:
        @log_command(CommandType.SLASH_COMMAND)
        async def handle_summarize(interaction, **kwargs):
            # Command implementation
            pass

    Args:
        command_type: Type of command being logged
        command_name: Optional command name (uses function name if not provided)

    Returns:
        Decorated function with automatic logging
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs) -> Any:
            # Get command logger from handler instance
            if not hasattr(self, 'command_logger') or self.command_logger is None:
                # No logger configured, execute without logging
                return await func(self, *args, **kwargs)

            command_logger: CommandLogger = self.command_logger

            # Extract context from function arguments
            context = _extract_context(args, kwargs, command_type)

            # Determine command name
            cmd_name = command_name or func.__name__

            # Create log entry
            log_entry = await command_logger.log_command(
                command_type=command_type,
                command_name=cmd_name,
                user_id=context.get("user_id"),
                guild_id=context.get("guild_id", ""),
                channel_id=context.get("channel_id", ""),
                parameters=context.get("parameters", {}),
                execution_context=context.get("execution_context", {})
            )

            # Execute command
            try:
                result = await func(self, *args, **kwargs)

                # Extract result summary
                result_summary = _extract_result_summary(result, command_type)

                # Mark log as completed
                await command_logger.complete_log(log_entry, result_summary)

                return result

            except Exception as e:
                # Mark log as failed
                error_code = getattr(e, 'error_code', 'UNKNOWN_ERROR')
                error_message = str(e)

                await command_logger.fail_log(
                    log_entry,
                    error_code=error_code,
                    error_message=error_message
                )

                # Re-raise exception
                raise

        return wrapper

    return decorator


def _extract_context(args, kwargs, command_type: CommandType) -> Dict[str, Any]:
    """
    Extract logging context from function arguments.

    Different command types have different argument structures:
    - Discord commands: interaction object
    - Scheduled tasks: task object
    - Webhooks: request object

    Args:
        args: Positional arguments
        kwargs: Keyword arguments
        command_type: Type of command

    Returns:
        Context dictionary with user_id, guild_id, channel_id, parameters, etc.
    """
    context = {
        "user_id": None,
        "guild_id": "",
        "channel_id": "",
        "parameters": {},
        "execution_context": {}
    }

    if command_type == CommandType.SLASH_COMMAND:
        # First arg should be interaction
        if args and hasattr(args[0], 'user'):
            interaction = args[0]
            context["user_id"] = str(interaction.user.id)
            context["guild_id"] = str(interaction.guild_id) if interaction.guild else ""
            context["channel_id"] = str(interaction.channel_id)
            context["parameters"] = dict(kwargs)
            context["execution_context"] = {
                "interaction_id": str(interaction.id),
                "command_name": interaction.command.name if interaction.command else ""
            }

    elif command_type == CommandType.SCHEDULED_TASK:
        # First arg should be task
        if args:
            task = args[0]
            context["user_id"] = None  # Scheduled tasks have no user
            context["guild_id"] = getattr(task, 'guild_id', '')
            context["channel_id"] = getattr(task, 'channel_id', '')
            context["parameters"] = {
                "task_id": getattr(task, 'id', ''),
                "schedule_type": str(getattr(task, 'schedule_type', ''))
            }
            context["execution_context"] = {
                "scheduled_time": str(getattr(task, 'next_run', '')),
                "task_name": getattr(task, 'name', '')
            }

    elif command_type == CommandType.WEBHOOK_REQUEST:
        # Extract from request object or kwargs
        if "request" in kwargs:
            request = kwargs["request"]
            context["guild_id"] = request.get("guild_id", "")
            context["channel_id"] = request.get("channel_id", "")
            context["parameters"] = request.get("parameters", {})

            # Get execution context from headers/metadata
            if "headers" in kwargs:
                headers = kwargs["headers"]
                context["execution_context"] = {
                    "source_ip": headers.get("x-forwarded-for", ""),
                    "user_agent": headers.get("user-agent", ""),
                    "signature": headers.get("x-signature", "")
                }

    return context


def _extract_result_summary(result: Any, command_type: CommandType) -> Dict[str, Any]:
    """
    Extract summary from command result.

    Different commands return different result types.
    Extract relevant metrics for logging.

    Args:
        result: Command execution result
        command_type: Type of command

    Returns:
        Summary dictionary with relevant metrics
    """
    summary = {}

    if result is None:
        return summary

    if command_type == CommandType.SLASH_COMMAND:
        # For summarize commands
        if hasattr(result, 'message_count'):
            summary["messages_processed"] = result.message_count
        if hasattr(result, 'summary_text'):
            summary["summary_length"] = len(result.summary_text)
        if hasattr(result, 'key_points'):
            summary["key_points_count"] = len(result.key_points)

    elif command_type == CommandType.SCHEDULED_TASK:
        if isinstance(result, dict):
            summary["messages_processed"] = result.get("message_count", 0)
            summary["destinations_delivered"] = result.get("deliveries", 0)

    return summary
