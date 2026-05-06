"""
Tests for command logger.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from src.logging.logger import CommandLogger
from src.logging.models import CommandLog, CommandType, CommandStatus, LoggingConfig
from src.logging.repository import CommandLogRepository
from src.logging.sanitizer import LogSanitizer


@pytest_asyncio.fixture
async def mock_repository():
    """Create mock repository."""
    repo = Mock(spec=CommandLogRepository)
    repo.save = AsyncMock(return_value="log-123")
    repo.save_batch = AsyncMock(return_value=["log-1", "log-2"])
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def config():
    """Create test configuration."""
    return LoggingConfig(
        enabled=True,
        async_writes=False,  # Disable async for testing
        batch_size=10,
        flush_interval_seconds=1
    )


@pytest_asyncio.fixture
async def logger_instance(mock_repository, config):
    """Create command logger instance."""
    return CommandLogger(
        repository=mock_repository,
        config=config
    )


@pytest.mark.asyncio
class TestCommandLogger:
    """Test CommandLogger class."""

    async def test_log_command_basic(self, logger_instance, mock_repository):
        """Test logging a basic command."""
        log_entry = await logger_instance.log_command(
            command_type=CommandType.SLASH_COMMAND,
            command_name="test_command",
            user_id="user-123",
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={"count": 100}
        )

        assert log_entry.command_type == CommandType.SLASH_COMMAND
        assert log_entry.command_name == "test_command"
        assert log_entry.user_id == "user-123"
        assert log_entry.guild_id == "guild-456"
        assert log_entry.channel_id == "channel-789"
        assert log_entry.parameters == {"count": 100}
        assert log_entry.status == CommandStatus.SUCCESS
        assert log_entry.completed_at is None

        # Should have saved to repository
        mock_repository.save.assert_called_once()

    async def test_log_command_with_sanitization(self, logger_instance, mock_repository):
        """Test that sensitive data is sanitized."""
        log_entry = await logger_instance.log_command(
            command_type=CommandType.SLASH_COMMAND,
            command_name="test",
            user_id="user-123",
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={
                "api_key": "sk-secret",
                "count": 100
            }
        )

        # API key should be redacted
        assert log_entry.parameters["api_key"] == "[REDACTED]"
        assert log_entry.parameters["count"] == 100

    async def test_complete_log(self, logger_instance, mock_repository):
        """Test completing a log entry."""
        # Create initial log
        log_entry = await logger_instance.log_command(
            command_type=CommandType.SLASH_COMMAND,
            command_name="test",
            user_id="user-123",
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={}
        )

        # Complete the log
        result_summary = {"messages_processed": 50}
        await logger_instance.complete_log(log_entry, result_summary)

        assert log_entry.status == CommandStatus.SUCCESS
        assert log_entry.completed_at is not None
        assert log_entry.duration_ms is not None
        assert log_entry.duration_ms >= 0
        assert log_entry.result_summary == result_summary

        # Should have updated repository
        mock_repository.update.assert_called_once()

    async def test_fail_log(self, logger_instance, mock_repository):
        """Test marking a log as failed."""
        # Create initial log
        log_entry = await logger_instance.log_command(
            command_type=CommandType.SLASH_COMMAND,
            command_name="test",
            user_id="user-123",
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={}
        )

        # Mark as failed
        await logger_instance.fail_log(
            log_entry,
            error_code="API_ERROR",
            error_message="API request failed with status 500"
        )

        assert log_entry.status == CommandStatus.FAILED
        assert log_entry.error_code == "API_ERROR"
        assert log_entry.error_message == "API request failed with status 500"
        assert log_entry.completed_at is not None
        assert log_entry.duration_ms is not None

        # Should have updated repository
        mock_repository.update.assert_called()

    async def test_timeout_log(self, logger_instance, mock_repository):
        """Test marking a log as timed out."""
        log_entry = await logger_instance.log_command(
            command_type=CommandType.SLASH_COMMAND,
            command_name="test",
            user_id="user-123",
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={}
        )

        await logger_instance.timeout_log(
            log_entry,
            timeout_seconds=30
        )

        assert log_entry.status == CommandStatus.TIMEOUT
        assert log_entry.error_message is not None
        assert "30" in log_entry.error_message

    async def test_cancel_log(self, logger_instance, mock_repository):
        """Test marking a log as cancelled."""
        log_entry = await logger_instance.log_command(
            command_type=CommandType.SLASH_COMMAND,
            command_name="test",
            user_id="user-123",
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={}
        )

        await logger_instance.cancel_log(
            log_entry,
            reason="User cancelled operation"
        )

        assert log_entry.status == CommandStatus.CANCELLED
        assert log_entry.error_message == "User cancelled operation"

    async def test_scheduled_task_log(self, logger_instance, mock_repository):
        """Test logging a scheduled task (no user_id)."""
        log_entry = await logger_instance.log_command(
            command_type=CommandType.SCHEDULED_TASK,
            command_name="daily_summary",
            user_id=None,
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={"task_id": "task-123"}
        )

        assert log_entry.command_type == CommandType.SCHEDULED_TASK
        assert log_entry.user_id is None
        assert log_entry.parameters["task_id"] == "task-123"

    async def test_webhook_request_log(self, logger_instance, mock_repository):
        """Test logging a webhook request."""
        log_entry = await logger_instance.log_command(
            command_type=CommandType.WEBHOOK_REQUEST,
            command_name="POST /summaries",
            user_id=None,
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={"endpoint": "/summaries"},
            execution_context={
                "source_ip": "192.168.1.100",
                "user_agent": "Mozilla/5.0"
            }
        )

        assert log_entry.command_type == CommandType.WEBHOOK_REQUEST
        assert log_entry.execution_context["source_ip"] == "192.168.*.*"  # IP should be masked

    async def test_disabled_logging(self, mock_repository):
        """Test that logging is skipped when disabled."""
        config = LoggingConfig(enabled=False)
        logger = CommandLogger(repository=mock_repository, config=config)

        log_entry = await logger.log_command(
            command_type=CommandType.SLASH_COMMAND,
            command_name="test",
            user_id="user-123",
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={}
        )

        # Should return None when disabled
        assert log_entry is None
        mock_repository.save.assert_not_called()

    async def test_async_batch_writing(self, mock_repository):
        """Test async batch writing."""
        config = LoggingConfig(
            enabled=True,
            async_writes=True,
            batch_size=3,
            flush_interval_seconds=0.1
        )
        logger = CommandLogger(repository=mock_repository, config=config)

        await logger.start()

        try:
            # Log multiple commands
            for i in range(5):
                await logger.log_command(
                    command_type=CommandType.SLASH_COMMAND,
                    command_name=f"test_{i}",
                    user_id=f"user-{i}",
                    guild_id="guild-456",
                    channel_id="channel-789",
                    parameters={}
                )

            # Wait for flush
            await asyncio.sleep(0.2)

            # Should have batched writes
            assert mock_repository.save_batch.called or mock_repository.save.called

        finally:
            await logger.stop()

    async def test_metadata_capture(self, logger_instance, mock_repository):
        """Test that metadata is captured."""
        log_entry = await logger_instance.log_command(
            command_type=CommandType.SLASH_COMMAND,
            command_name="test",
            user_id="user-123",
            guild_id="guild-456",
            channel_id="channel-789",
            parameters={},
            metadata={"version": "1.0.0", "environment": "test"}
        )

        assert log_entry.metadata["version"] == "1.0.0"
        assert log_entry.metadata["environment"] == "test"
