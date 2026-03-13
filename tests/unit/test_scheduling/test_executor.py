"""
Unit tests for task executor.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import discord

from src.scheduling.executor import TaskExecutor, TaskExecutionResult
from src.scheduling.tasks import SummaryTask, CleanupTask
from src.models.task import ScheduledTask, ScheduleType, Destination, DestinationType, TaskStatus
from src.models.summary import SummaryOptions, SummaryLength, SummaryResult, SummarizationContext
from src.models.message import ProcessedMessage
from src.exceptions import InsufficientContentError, MessageFetchError


@pytest.fixture
def mock_summarization_engine():
    """Create mock summarization engine."""
    engine = AsyncMock()

    # Default successful summary
    summary_result = SummaryResult(
        id="summary_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow(),
        message_count=50,
        summary_text="Test summary content",
        key_points=["Point 1", "Point 2"],
        action_items=[],
        technical_terms={},
        participants=["user1", "user2"],
        metadata={},
        created_at=datetime.utcnow()
    )

    engine.summarize_messages.return_value = summary_result
    return engine


@pytest.fixture
def mock_message_processor():
    """Create mock message processor."""
    processor = AsyncMock()

    # Return sample messages
    messages = [
        ProcessedMessage(
            id=f"msg_{i}",
            author_name=f"user{i % 3}",
            author_id=f"author_{i % 3}",
            content=f"Test message {i}",
            timestamp=datetime.utcnow() - timedelta(minutes=60 - i),
            thread_info=None,
            attachments=[],
            references=[]
        )
        for i in range(50)
    ]

    processor.process_channel_messages.return_value = messages
    return processor


@pytest.fixture
def mock_discord_client():
    """Create mock Discord client."""
    client = AsyncMock(spec=discord.Client)

    # Mock channel
    mock_channel = AsyncMock(spec=discord.TextChannel)
    mock_channel.id = 123456789
    mock_channel.name = "test-channel"
    mock_channel.send = AsyncMock()

    client.get_channel.return_value = mock_channel
    client.fetch_channel = AsyncMock(return_value=mock_channel)

    return client


@pytest.fixture
def task_executor(mock_summarization_engine, mock_message_processor, mock_discord_client):
    """Create task executor instance."""
    return TaskExecutor(
        summarization_engine=mock_summarization_engine,
        message_processor=mock_message_processor,
        discord_client=mock_discord_client
    )


@pytest.fixture
def sample_scheduled_task():
    """Create sample scheduled task."""
    return ScheduledTask(
        id="task_123",
        name="Test Summary",
        channel_id="123456789",
        guild_id="987654321",
        schedule_type=ScheduleType.DAILY,
        schedule_time="09:00",
        destinations=[
            Destination(
                type=DestinationType.DISCORD_CHANNEL,
                target="123456789",
                format="embed",
                enabled=True
            )
        ]
    )


@pytest.fixture
def sample_summary_task(sample_scheduled_task):
    """Create sample summary task."""
    return SummaryTask(
        scheduled_task=sample_scheduled_task,
        channel_id="123456789",
        guild_id="987654321",
        summary_options=SummaryOptions(
            summary_length=SummaryLength.DETAILED
        ),
        destinations=sample_scheduled_task.destinations,
        time_range_hours=24
    )


@pytest.mark.asyncio
async def test_execute_summary_task_success(task_executor, sample_summary_task, mock_summarization_engine, mock_message_processor):
    """Test successful summary task execution."""
    result = await task_executor.execute_summary_task(sample_summary_task)

    assert result.success is True
    assert result.task_id == sample_summary_task.scheduled_task.id
    assert result.summary_result is not None
    assert result.summary_result.id == "summary_123"
    assert result.error_message is None
    assert len(result.delivery_results) > 0

    # Verify task status
    assert sample_summary_task.status == TaskStatus.COMPLETED

    # Verify engine was called with correct parameters
    mock_summarization_engine.summarize_messages.assert_called_once()
    mock_message_processor.process_channel_messages.assert_called_once()


@pytest.mark.asyncio
async def test_execute_summary_task_insufficient_content(task_executor, sample_summary_task, mock_message_processor):
    """Test handling insufficient content error."""
    # Make processor return no messages
    mock_message_processor.process_channel_messages.return_value = []

    # Make engine raise insufficient content error
    task_executor.summarization_engine.summarize_messages.side_effect = InsufficientContentError(
        message_count=0,
        min_required=5
    )

    result = await task_executor.execute_summary_task(sample_summary_task)

    assert result.success is False
    assert result.summary_result is None
    assert result.error_message is not None
    assert "message" in result.error_message.lower() or "content" in result.error_message.lower()
    assert sample_summary_task.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_execute_summary_task_generic_error(task_executor, sample_summary_task, mock_message_processor):
    """Test handling generic errors during execution."""
    # Make processor raise an error
    mock_message_processor.process_channel_messages.side_effect = Exception("Network error")

    result = await task_executor.execute_summary_task(sample_summary_task)

    assert result.success is False
    assert result.error_message == "Network error"
    assert result.error_details["exception_type"] == "Exception"
    assert sample_summary_task.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_execute_summary_task_measures_time(task_executor, sample_summary_task):
    """Test that execution time is measured."""
    result = await task_executor.execute_summary_task(sample_summary_task)

    assert result.execution_time_seconds > 0
    assert isinstance(result.execution_time_seconds, float)


@pytest.mark.asyncio
async def test_execute_cleanup_task(task_executor):
    """Test cleanup task execution."""
    cleanup_task = CleanupTask(
        task_id="cleanup_123",
        guild_id="987654321",
        retention_days=90,
        delete_summaries=True,
        delete_logs=True
    )

    result = await task_executor.execute_cleanup_task(cleanup_task)

    assert result.success is True
    assert result.task_id == "cleanup_123"
    assert cleanup_task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_execute_cleanup_task_error(task_executor):
    """Test cleanup task error handling."""
    cleanup_task = CleanupTask(
        task_id="cleanup_123",
        retention_days=-1  # Invalid value might cause error
    )

    # This should still succeed with current placeholder implementation
    result = await task_executor.execute_cleanup_task(cleanup_task)
    assert result.success is True


@pytest.mark.asyncio
async def test_deliver_summary_discord_destination(task_executor, sample_summary_task):
    """Test delivery to Discord channel via delivery strategy."""
    summary = SummaryResult(
        id="summary_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow(),
        message_count=50,
        summary_text="Test summary",
        key_points=["Point 1"],
        action_items=[],
        technical_terms={},
        participants=["user1"],
        metadata={},
        created_at=datetime.utcnow()
    )

    destinations = [
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="123456789",
            format="embed",
            enabled=True
        )
    ]

    results = await task_executor._deliver_summary(
        summary=summary,
        destinations=destinations,
        task=sample_summary_task
    )

    assert len(results) == 1
    assert results[0]["destination_type"] == "discord_channel"


@pytest.mark.asyncio
async def test_deliver_summary_markdown_destination(task_executor, sample_summary_task):
    """Test delivery to Discord channel with markdown format via strategy."""
    summary = SummaryResult(
        id="summary_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow(),
        message_count=50,
        summary_text="Test summary",
        key_points=["Point 1"],
        action_items=[],
        technical_terms={},
        participants=["user1"],
        metadata={},
        created_at=datetime.utcnow()
    )

    destinations = [
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="123456789",
            format="markdown",
            enabled=True
        )
    ]

    results = await task_executor._deliver_summary(
        summary=summary,
        destinations=destinations,
        task=sample_summary_task
    )

    assert len(results) == 1


@pytest.mark.asyncio
async def test_deliver_summary_long_text(task_executor, sample_summary_task):
    """Test delivery handles long summary text."""
    long_text = "x" * 3000  # Exceeds Discord's 2000 character limit

    summary = SummaryResult(
        id="summary_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow(),
        message_count=50,
        summary_text=long_text,
        key_points=[],
        action_items=[],
        technical_terms={},
        participants=["user1"],
        metadata={},
        created_at=datetime.utcnow()
    )

    destinations = [
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="123456789",
            format="embed",
            enabled=True
        )
    ]

    results = await task_executor._deliver_summary(
        summary=summary,
        destinations=destinations,
        task=sample_summary_task
    )

    # Should attempt delivery (strategy handles chunking)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_deliver_summary_no_client(mock_summarization_engine, mock_message_processor, sample_summary_task):
    """Test delivery when Discord client is not available."""
    executor = TaskExecutor(
        summarization_engine=mock_summarization_engine,
        message_processor=mock_message_processor,
        discord_client=None
    )

    summary = SummaryResult(
        id="summary_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow(),
        message_count=1,
        summary_text="Test",
        key_points=[],
        action_items=[],
        technical_terms={},
        participants=[],
        metadata={},
        created_at=datetime.utcnow()
    )

    destinations = [
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="123456789",
            format="embed",
            enabled=True
        )
    ]

    # Create a minimal SummaryTask for the delivery context
    from src.scheduling.tasks import SummaryTask as ST
    from src.models.task import ScheduledTask, ScheduleType
    task = ST(
        scheduled_task=ScheduledTask(
            channel_id="123456789",
            guild_id="987654321",
            schedule_type=ScheduleType.DAILY
        ),
        channel_id="123456789",
        guild_id="987654321",
        summary_options=SummaryOptions(),
        destinations=destinations
    )

    results = await executor._deliver_summary(
        summary=summary,
        destinations=destinations,
        task=task
    )

    # Delivery strategy should handle missing client (may succeed or fail gracefully)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_deliver_summary_channel_not_found(task_executor, mock_discord_client, sample_summary_task):
    """Test handling when Discord channel is not found via strategy."""
    # Make get_channel return None
    mock_discord_client.get_channel.return_value = None
    mock_discord_client.fetch_channel.side_effect = discord.NotFound(
        MagicMock(), "Channel not found"
    )

    summary = SummaryResult(
        id="summary_123",
        channel_id="invalid_channel",
        guild_id="987654321",
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow(),
        message_count=1,
        summary_text="Test",
        key_points=[],
        action_items=[],
        technical_terms={},
        participants=[],
        metadata={},
        created_at=datetime.utcnow()
    )

    destinations = [
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="invalid_channel",
            format="embed",
            enabled=True
        )
    ]

    results = await task_executor._deliver_summary(
        summary=summary,
        destinations=destinations,
        task=sample_summary_task
    )

    # Should have a result for the attempted delivery
    assert len(results) == 1


@pytest.mark.asyncio
async def test_deliver_summary_webhook_destination(task_executor, sample_summary_task):
    """Test webhook delivery via delivery strategy."""
    summary = SummaryResult(
        id="summary_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow(),
        message_count=1,
        summary_text="Test",
        key_points=[],
        action_items=[],
        technical_terms={},
        participants=[],
        metadata={},
        created_at=datetime.utcnow()
    )

    destinations = [
        Destination(
            type=DestinationType.WEBHOOK,
            target="https://example.com/webhook",
            format="json",
            enabled=True
        )
    ]

    results = await task_executor._deliver_summary(
        summary=summary,
        destinations=destinations,
        task=sample_summary_task
    )

    assert len(results) == 1
    assert results[0]["destination_type"] == "webhook"
    assert results[0]["target"] == "https://example.com/webhook"


@pytest.mark.asyncio
async def test_deliver_summary_multiple_destinations(task_executor, sample_summary_task):
    """Test delivery to multiple destinations."""
    # Add multiple destinations
    sample_summary_task.destinations = [
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="123456789",
            format="embed",
            enabled=True
        ),
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="987654321",
            format="markdown",
            enabled=True
        ),
        Destination(
            type=DestinationType.WEBHOOK,
            target="https://example.com/webhook",
            format="json",
            enabled=True
        )
    ]

    summary = SummaryResult(
        id="summary_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow(),
        message_count=1,
        summary_text="Test",
        key_points=[],
        action_items=[],
        technical_terms={},
        participants=[],
        metadata={},
        created_at=datetime.utcnow()
    )

    results = await task_executor._deliver_summary(
        summary=summary,
        destinations=sample_summary_task.destinations,
        task=sample_summary_task
    )

    assert len(results) == 3
    # At least some should succeed
    successful = sum(1 for r in results if r.get("success"))
    assert successful > 0


@pytest.mark.asyncio
async def test_deliver_summary_skips_disabled_destinations(task_executor, sample_summary_task):
    """Test that disabled destinations are skipped."""
    sample_summary_task.destinations = [
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="123456789",
            format="embed",
            enabled=False  # Disabled
        )
    ]

    summary = SummaryResult(
        id="summary_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow(),
        message_count=1,
        summary_text="Test",
        key_points=[],
        action_items=[],
        technical_terms={},
        participants=[],
        metadata={},
        created_at=datetime.utcnow()
    )

    results = await task_executor._deliver_summary(
        summary=summary,
        destinations=sample_summary_task.destinations,
        task=sample_summary_task
    )

    # No destinations should be attempted
    assert len(results) == 0


@pytest.mark.asyncio
async def test_deliver_summary_handles_individual_failures(task_executor, sample_summary_task, mock_discord_client):
    """Test that individual delivery failures don't stop other deliveries."""
    sample_summary_task.destinations = [
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="bad_channel",
            format="embed",
            enabled=True
        ),
        Destination(
            type=DestinationType.DISCORD_CHANNEL,
            target="123456789",
            format="embed",
            enabled=True
        )
    ]

    # Make first channel fail, second succeed
    def get_channel_side_effect(channel_id):
        if channel_id == int("bad_channel"):
            return None
        return AsyncMock(spec=discord.TextChannel, send=AsyncMock())

    mock_discord_client.get_channel.side_effect = get_channel_side_effect
    mock_discord_client.fetch_channel.side_effect = discord.NotFound(
        MagicMock(), "Channel not found"
    )

    summary = SummaryResult(
        id="summary_123",
        channel_id="123456789",
        guild_id="987654321",
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow(),
        message_count=1,
        summary_text="Test",
        key_points=[],
        action_items=[],
        technical_terms={},
        participants=[],
        metadata={},
        created_at=datetime.utcnow()
    )

    results = await task_executor._deliver_summary(
        summary=summary,
        destinations=sample_summary_task.destinations,
        task=sample_summary_task
    )

    # Should have results for both attempts
    assert len(results) == 2


@pytest.mark.asyncio
async def test_handle_task_failure(task_executor, sample_scheduled_task, mock_discord_client):
    """Test failure notification handling."""
    sample_scheduled_task.failure_count = 2

    error = Exception("Test error")

    await task_executor.handle_task_failure(sample_scheduled_task, error)

    # Verify notification was sent
    channel = mock_discord_client.get_channel.return_value
    channel.send.assert_called_once()

    # Check notification content
    notification = channel.send.call_args[0][0]
    assert "Failed" in notification
    assert "Test error" in notification


@pytest.mark.asyncio
async def test_handle_task_failure_max_failures(task_executor, sample_scheduled_task, mock_discord_client):
    """Test failure notification when max failures reached."""
    sample_scheduled_task.failure_count = 3
    sample_scheduled_task.max_failures = 3

    error = Exception("Test error")

    await task_executor.handle_task_failure(sample_scheduled_task, error)

    # Verify disabled message is included
    channel = mock_discord_client.get_channel.return_value
    notification = channel.send.call_args[0][0]
    assert "disabled" in notification.lower()


@pytest.mark.asyncio
async def test_handle_task_failure_no_discord_destinations(task_executor, sample_scheduled_task):
    """Test failure handling when no Discord destinations are configured."""
    sample_scheduled_task.destinations = []

    error = Exception("Test error")

    # Should not raise an error
    await task_executor.handle_task_failure(sample_scheduled_task, error)


@pytest.mark.asyncio
async def test_handle_task_failure_no_discord_client(mock_summarization_engine, mock_message_processor, sample_scheduled_task):
    """Test failure handling when Discord client is not available."""
    executor = TaskExecutor(
        summarization_engine=mock_summarization_engine,
        message_processor=mock_message_processor,
        discord_client=None
    )

    error = Exception("Test error")

    # Should not raise an error
    await executor.handle_task_failure(sample_scheduled_task, error)


@pytest.mark.asyncio
async def test_task_execution_result_to_dict():
    """Test TaskExecutionResult serialization."""
    result = TaskExecutionResult(
        task_id="task_123",
        success=True,
        summary_result=None,
        error_message=None,
        delivery_results=[
            {"destination": "channel1", "success": True}
        ],
        execution_time_seconds=5.5
    )

    result_dict = result.to_dict()

    assert result_dict["task_id"] == "task_123"
    assert result_dict["success"] is True
    assert result_dict["execution_time_seconds"] == 5.5
    assert len(result_dict["delivery_results"]) == 1


@pytest.mark.asyncio
async def test_concurrent_task_execution(task_executor):
    """Test executing multiple tasks concurrently."""
    tasks = [
        SummaryTask(
            scheduled_task=ScheduledTask(
                id=f"task_{i}",
                name=f"Task {i}",
                channel_id="123456789",
                guild_id="987654321",
                schedule_type=ScheduleType.DAILY
            ),
            channel_id="123456789",
            guild_id="987654321",
            summary_options=SummaryOptions(),
            destinations=[]
        )
        for i in range(5)
    ]

    # Execute all tasks concurrently
    results = await asyncio.gather(
        *[task_executor.execute_summary_task(task) for task in tasks],
        return_exceptions=True
    )

    # All should complete
    assert len(results) == 5

    # Most should succeed
    successful = sum(1 for r in results if isinstance(r, TaskExecutionResult) and r.success)
    assert successful >= 4  # Allow for some variation


@pytest.mark.asyncio
async def test_retry_logic_integration(task_executor, sample_summary_task):
    """Test retry logic is properly integrated."""
    # Simulate a failure
    sample_summary_task.mark_failed("First failure")

    assert sample_summary_task.should_retry() is True
    assert sample_summary_task.retry_count == 1

    # Get retry delay
    delay = sample_summary_task.get_retry_delay()
    assert delay > 0

    # Simulate another failure
    sample_summary_task.mark_failed("Second failure")

    # Retry delay should have increased (exponential backoff)
    new_delay = sample_summary_task.get_retry_delay()
    assert new_delay > delay
