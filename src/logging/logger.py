"""
Core command logging functionality.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from collections import deque

from .models import CommandLog, CommandType, CommandStatus, LoggingConfig
from .sanitizer import LogSanitizer
from .repository import CommandLogRepository
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class CommandLogger:
    """
    Core command logging service.

    Features:
    - Async, non-blocking logging
    - Batch writes for performance
    - Automatic sanitization
    - Graceful degradation on errors
    """

    def __init__(
        self,
        repository: CommandLogRepository,
        config: LoggingConfig,
        sanitizer: Optional[LogSanitizer] = None
    ):
        """
        Initialize command logger.

        Args:
            repository: Database repository for persistence
            config: Logging configuration
            sanitizer: Optional sanitizer (creates default if None)
        """
        self.repository = repository
        self.config = config
        self.sanitizer = sanitizer or LogSanitizer(config)

        # Async queue for batch processing
        self._log_queue: deque = deque(maxlen=config.batch_size * 10)
        self._flush_task: Optional[asyncio.Task] = None
        self._shutdown = False

    async def start(self) -> None:
        """Start the logging service."""
        if self.config.async_writes:
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info("Command logger started with async writes")
        else:
            logger.info("Command logger started with sync writes")

    async def stop(self) -> None:
        """Stop the logging service and flush remaining logs."""
        self._shutdown = True

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining logs
        await self._flush_queue()
        logger.info("Command logger stopped")

    async def _flush_loop(self) -> None:
        """Background task to flush logs periodically."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.flush_interval_seconds)
                await self._flush_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in flush loop: {e}")

    async def _flush_queue(self) -> None:
        """Flush queued logs to database."""
        if not self._log_queue:
            return

        # Batch write for performance
        batch = []
        while self._log_queue and len(batch) < self.config.batch_size:
            batch.append(self._log_queue.popleft())

        if batch:
            try:
                await self.repository.save_batch(batch)
                logger.debug(f"Flushed {len(batch)} log entries")
            except Exception as e:
                logger.error(f"Failed to flush logs: {e}")
                # Put logs back in queue for retry
                self._log_queue.extendleft(reversed(batch))

    async def log_command(
        self,
        command_type: CommandType,
        command_name: str,
        user_id: Optional[str],
        guild_id: str,
        channel_id: str,
        parameters: Dict[str, Any],
        execution_context: Dict[str, Any] = None
    ) -> CommandLog:
        """
        Create and queue a command log entry.

        Args:
            command_type: Type of command (Discord, scheduled, webhook)
            command_name: Name of the command
            user_id: User ID (None for scheduled tasks)
            guild_id: Guild ID
            channel_id: Channel ID
            parameters: Command parameters
            execution_context: Additional execution context

        Returns:
            CommandLog instance that can be updated with results
        """
        if not self.config.enabled:
            # Return dummy log that won't be persisted
            return CommandLog()

        # Sanitize sensitive data
        sanitized_params = self.sanitizer.sanitize_parameters(parameters)
        sanitized_context = self.sanitizer.sanitize_execution_context(
            execution_context or {}
        )

        # Create log entry
        log_entry = CommandLog(
            command_type=command_type,
            command_name=command_name,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            parameters=sanitized_params,
            execution_context=sanitized_context,
            started_at=utc_now_naive()
        )

        # Queue for async write or write immediately
        if self.config.async_writes:
            self._log_queue.append(log_entry)
        else:
            try:
                await self.repository.save(log_entry)
            except Exception as e:
                logger.error(f"Failed to save log entry: {e}")

        return log_entry

    async def complete_log(
        self,
        log_entry: CommandLog,
        result_summary: Dict[str, Any] = None
    ) -> None:
        """
        Update log entry with completion status.

        Args:
            log_entry: Log entry to update
            result_summary: Optional summary of results
        """
        if not self.config.enabled:
            return

        log_entry.mark_completed(result_summary)

        # Sanitize result summary
        if log_entry.result_summary:
            log_entry.result_summary = self.sanitizer.sanitize_parameters(
                log_entry.result_summary
            )

        # Update in database
        try:
            await self.repository.update(log_entry)
        except Exception as e:
            logger.error(f"Failed to update log entry: {e}")

    async def fail_log(
        self,
        log_entry: CommandLog,
        error_code: str,
        error_message: str
    ) -> None:
        """
        Update log entry with failure status.

        Args:
            log_entry: Log entry to update
            error_code: Error code
            error_message: Error message
        """
        if not self.config.enabled:
            return

        # Sanitize error message
        sanitized_error = self.sanitizer.sanitize_error_message(error_message)
        log_entry.mark_failed(error_code, sanitized_error)

        # Update in database
        try:
            await self.repository.update(log_entry)
        except Exception as e:
            logger.error(f"Failed to update log entry: {e}")
