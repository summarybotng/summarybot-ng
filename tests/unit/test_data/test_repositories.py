"""
Unit tests for repository implementations.

Tests cover:
- SummaryRepository CRUD operations
- GuildConfigRepository operations
- ScheduledTaskRepository operations
- Query methods with filters
- Pagination
- Error handling
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from typing import List

from src.data.sqlite import SQLiteSummaryRepository, SQLiteConfigRepository, SQLiteTaskRepository
from src.data.base import SearchCriteria
from src.models.summary import (
    SummaryResult, SummaryOptions, ActionItem, TechnicalTerm,
    Participant, SummarizationContext, Priority, SummaryLength
)
from src.models.task import (
    ScheduledTask, TaskResult, Destination, TaskStatus,
    ScheduleType, DestinationType, TaskType
)
from src.config.settings import GuildConfig, PermissionSettings


class TestSummaryRepository:
    """Test SummaryRepository operations."""

    @pytest.mark.asyncio
    async def test_save_summary(
        self,
        summary_repository: SQLiteSummaryRepository,
        sample_summary_result: SummaryResult
    ):
        """Test saving a summary to the database."""
        summary_id = await summary_repository.save_summary(sample_summary_result)

        assert summary_id == sample_summary_result.id

    @pytest.mark.asyncio
    async def test_get_summary(
        self,
        summary_repository: SQLiteSummaryRepository,
        sample_summary_result: SummaryResult
    ):
        """Test retrieving a summary by ID."""
        await summary_repository.save_summary(sample_summary_result)

        retrieved = await summary_repository.get_summary(sample_summary_result.id)

        assert retrieved is not None
        assert retrieved.id == sample_summary_result.id
        assert retrieved.channel_id == sample_summary_result.channel_id
        assert retrieved.guild_id == sample_summary_result.guild_id
        assert retrieved.message_count == sample_summary_result.message_count
        assert retrieved.summary_text == sample_summary_result.summary_text
        assert len(retrieved.key_points) == len(sample_summary_result.key_points)
        assert len(retrieved.action_items) == len(sample_summary_result.action_items)

    @pytest.mark.asyncio
    async def test_get_nonexistent_summary(
        self,
        summary_repository: SQLiteSummaryRepository
    ):
        """Test retrieving a summary that doesn't exist."""
        result = await summary_repository.get_summary("nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_summary(
        self,
        summary_repository: SQLiteSummaryRepository,
        sample_summary_result: SummaryResult
    ):
        """Test updating an existing summary."""
        await summary_repository.save_summary(sample_summary_result)

        # Modify the summary
        sample_summary_result.summary_text = "Updated summary text"
        sample_summary_result.key_points.append("New key point")

        # Save again (should update)
        await summary_repository.save_summary(sample_summary_result)

        # Retrieve and verify
        retrieved = await summary_repository.get_summary(sample_summary_result.id)

        assert retrieved.summary_text == "Updated summary text"
        assert "New key point" in retrieved.key_points

    @pytest.mark.asyncio
    async def test_delete_summary(
        self,
        summary_repository: SQLiteSummaryRepository,
        sample_summary_result: SummaryResult
    ):
        """Test deleting a summary."""
        await summary_repository.save_summary(sample_summary_result)

        deleted = await summary_repository.delete_summary(sample_summary_result.id)

        assert deleted is True

        # Verify it's gone
        retrieved = await summary_repository.get_summary(sample_summary_result.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_summary(
        self,
        summary_repository: SQLiteSummaryRepository
    ):
        """Test deleting a summary that doesn't exist."""
        deleted = await summary_repository.delete_summary("nonexistent-id")

        assert deleted is False

    @pytest.mark.asyncio
    async def test_find_summaries_by_guild(
        self,
        summary_repository: SQLiteSummaryRepository,
        sample_summary_result: SummaryResult
    ):
        """Test finding summaries by guild ID."""
        # Create multiple summaries
        for i in range(3):
            summary = SummaryResult(
                id=f"summary-{i}",
                channel_id=sample_summary_result.channel_id,
                guild_id=sample_summary_result.guild_id,
                start_time=datetime.utcnow() - timedelta(hours=i+1),
                end_time=datetime.utcnow(),
                message_count=10,
                summary_text=f"Summary {i}",
                key_points=[],
                action_items=[],
                technical_terms=[],
                participants=[],
                metadata={},
                created_at=datetime.utcnow()
            )
            await summary_repository.save_summary(summary)

        criteria = SearchCriteria(guild_id=sample_summary_result.guild_id)
        results = await summary_repository.find_summaries(criteria)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_find_summaries_by_channel(
        self,
        summary_repository: SQLiteSummaryRepository,
        sample_summary_result: SummaryResult
    ):
        """Test finding summaries by channel ID."""
        await summary_repository.save_summary(sample_summary_result)

        # Create summary for different channel
        other_summary = SummaryResult(
            id="other-summary",
            channel_id="other-channel",
            guild_id=sample_summary_result.guild_id,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            message_count=5,
            summary_text="Other summary",
            key_points=[],
            action_items=[],
            technical_terms=[],
            participants=[],
            metadata={},
            created_at=datetime.utcnow()
        )
        await summary_repository.save_summary(other_summary)

        criteria = SearchCriteria(channel_id=sample_summary_result.channel_id)
        results = await summary_repository.find_summaries(criteria)

        assert len(results) == 1
        assert results[0].channel_id == sample_summary_result.channel_id

    @pytest.mark.asyncio
    async def test_find_summaries_with_time_range(
        self,
        summary_repository: SQLiteSummaryRepository
    ):
        """Test finding summaries within a time range."""
        now = datetime.utcnow()

        # Create summaries at different times
        for days_ago in [1, 3, 7, 14]:
            summary = SummaryResult(
                id=f"summary-{days_ago}",
                channel_id="channel-123",
                guild_id="guild-456",
                start_time=now - timedelta(days=days_ago, hours=1),
                end_time=now - timedelta(days=days_ago),
                message_count=10,
                summary_text=f"Summary from {days_ago} days ago",
                key_points=[],
                action_items=[],
                technical_terms=[],
                participants=[],
                metadata={},
                created_at=now - timedelta(days=days_ago)
            )
            await summary_repository.save_summary(summary)

        # Search for last 5 days
        criteria = SearchCriteria(
            start_time=now - timedelta(days=5),
            end_time=now
        )
        results = await summary_repository.find_summaries(criteria)

        assert len(results) == 2  # Should find summaries from 1 and 3 days ago

    @pytest.mark.asyncio
    async def test_find_summaries_with_pagination(
        self,
        summary_repository: SQLiteSummaryRepository
    ):
        """Test pagination in summary search."""
        # Create 15 summaries
        for i in range(15):
            summary = SummaryResult(
                id=f"summary-{i:02d}",
                channel_id="channel-123",
                guild_id="guild-456",
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
                message_count=10,
                summary_text=f"Summary {i}",
                key_points=[],
                action_items=[],
                technical_terms=[],
                participants=[],
                metadata={},
                created_at=datetime.utcnow() - timedelta(minutes=i)
            )
            await summary_repository.save_summary(summary)

        # Get first page
        criteria = SearchCriteria(limit=5, offset=0)
        page1 = await summary_repository.find_summaries(criteria)

        assert len(page1) == 5

        # Get second page
        criteria = SearchCriteria(limit=5, offset=5)
        page2 = await summary_repository.find_summaries(criteria)

        assert len(page2) == 5

        # Verify different results
        assert page1[0].id != page2[0].id

    @pytest.mark.asyncio
    async def test_count_summaries(
        self,
        summary_repository: SQLiteSummaryRepository,
        sample_summary_result: SummaryResult
    ):
        """Test counting summaries."""
        # Create multiple summaries
        for i in range(5):
            summary = SummaryResult(
                id=f"summary-{i}",
                channel_id=sample_summary_result.channel_id,
                guild_id=sample_summary_result.guild_id,
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
                message_count=10,
                summary_text=f"Summary {i}",
                key_points=[],
                action_items=[],
                technical_terms=[],
                participants=[],
                metadata={},
                created_at=datetime.utcnow()
            )
            await summary_repository.save_summary(summary)

        criteria = SearchCriteria(guild_id=sample_summary_result.guild_id)
        count = await summary_repository.count_summaries(criteria)

        assert count == 5

    @pytest.mark.asyncio
    async def test_get_summaries_by_channel(
        self,
        summary_repository: SQLiteSummaryRepository,
        sample_summary_result: SummaryResult
    ):
        """Test getting recent summaries for a channel."""
        # Create multiple summaries
        for i in range(15):
            summary = SummaryResult(
                id=f"summary-{i}",
                channel_id=sample_summary_result.channel_id,
                guild_id=sample_summary_result.guild_id,
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
                message_count=10,
                summary_text=f"Summary {i}",
                key_points=[],
                action_items=[],
                technical_terms=[],
                participants=[],
                metadata={},
                created_at=datetime.utcnow() - timedelta(minutes=i)
            )
            await summary_repository.save_summary(summary)

        # Get recent summaries (default limit 10)
        results = await summary_repository.get_summaries_by_channel(
            sample_summary_result.channel_id
        )

        assert len(results) == 10
        # Should be ordered by most recent first
        assert results[0].created_at >= results[-1].created_at

    @pytest.mark.asyncio
    async def test_save_summary_with_complex_data(
        self,
        summary_repository: SQLiteSummaryRepository,
        sample_summary_result: SummaryResult
    ):
        """Test saving and retrieving summary with all complex fields."""
        await summary_repository.save_summary(sample_summary_result)

        retrieved = await summary_repository.get_summary(sample_summary_result.id)

        # Verify action items
        assert len(retrieved.action_items) == len(sample_summary_result.action_items)
        assert retrieved.action_items[0].description == sample_summary_result.action_items[0].description
        assert retrieved.action_items[0].priority == sample_summary_result.action_items[0].priority

        # Verify technical terms
        assert len(retrieved.technical_terms) == len(sample_summary_result.technical_terms)
        assert retrieved.technical_terms[0].term == sample_summary_result.technical_terms[0].term

        # Verify participants
        assert len(retrieved.participants) == len(sample_summary_result.participants)
        assert retrieved.participants[0].user_id == sample_summary_result.participants[0].user_id

        # Verify context
        assert retrieved.context is not None
        assert retrieved.context.channel_name == sample_summary_result.context.channel_name


class TestConfigRepository:
    """Test ConfigRepository operations."""

    @pytest.mark.asyncio
    async def test_save_guild_config(
        self,
        config_repository: SQLiteConfigRepository,
        sample_guild_config: GuildConfig
    ):
        """Test saving a guild configuration."""
        await config_repository.save_guild_config(sample_guild_config)

        # Verify it was saved
        retrieved = await config_repository.get_guild_config(sample_guild_config.guild_id)
        assert retrieved is not None

    @pytest.mark.asyncio
    async def test_get_guild_config(
        self,
        config_repository: SQLiteConfigRepository,
        sample_guild_config: GuildConfig
    ):
        """Test retrieving a guild configuration."""
        await config_repository.save_guild_config(sample_guild_config)

        retrieved = await config_repository.get_guild_config(sample_guild_config.guild_id)

        assert retrieved.guild_id == sample_guild_config.guild_id
        assert retrieved.enabled_channels == sample_guild_config.enabled_channels
        assert retrieved.excluded_channels == sample_guild_config.excluded_channels
        assert retrieved.webhook_enabled == sample_guild_config.webhook_enabled

    @pytest.mark.asyncio
    async def test_get_nonexistent_guild_config(
        self,
        config_repository: SQLiteConfigRepository
    ):
        """Test retrieving a configuration that doesn't exist."""
        result = await config_repository.get_guild_config("nonexistent-guild")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_guild_config(
        self,
        config_repository: SQLiteConfigRepository,
        sample_guild_config: GuildConfig
    ):
        """Test updating an existing guild configuration."""
        await config_repository.save_guild_config(sample_guild_config)

        # Update config
        sample_guild_config.enabled_channels.append("new-channel")
        sample_guild_config.webhook_enabled = False

        await config_repository.save_guild_config(sample_guild_config)

        # Retrieve and verify
        retrieved = await config_repository.get_guild_config(sample_guild_config.guild_id)

        assert "new-channel" in retrieved.enabled_channels
        assert retrieved.webhook_enabled is False

    @pytest.mark.asyncio
    async def test_delete_guild_config(
        self,
        config_repository: SQLiteConfigRepository,
        sample_guild_config: GuildConfig
    ):
        """Test deleting a guild configuration."""
        await config_repository.save_guild_config(sample_guild_config)

        deleted = await config_repository.delete_guild_config(sample_guild_config.guild_id)

        assert deleted is True

        # Verify it's gone
        retrieved = await config_repository.get_guild_config(sample_guild_config.guild_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_guild_config(
        self,
        config_repository: SQLiteConfigRepository
    ):
        """Test deleting a configuration that doesn't exist."""
        deleted = await config_repository.delete_guild_config("nonexistent-guild")

        assert deleted is False

    @pytest.mark.asyncio
    async def test_get_all_guild_configs(
        self,
        config_repository: SQLiteConfigRepository,
        sample_guild_config: GuildConfig
    ):
        """Test retrieving all guild configurations."""
        # Create multiple configs
        configs = []
        for i in range(3):
            config = GuildConfig(
                guild_id=f"guild-{i}",
                enabled_channels=[f"channel-{i}"],
                excluded_channels=[],
                default_summary_options=SummaryOptions(),
                permission_settings=PermissionSettings()
            )
            await config_repository.save_guild_config(config)
            configs.append(config)

        # Retrieve all
        all_configs = await config_repository.get_all_guild_configs()

        assert len(all_configs) == 3
        guild_ids = [c.guild_id for c in all_configs]
        assert "guild-0" in guild_ids
        assert "guild-2" in guild_ids

    @pytest.mark.asyncio
    async def test_save_config_with_summary_options(
        self,
        config_repository: SQLiteConfigRepository,
        sample_guild_config: GuildConfig
    ):
        """Test saving configuration with detailed summary options."""
        await config_repository.save_guild_config(sample_guild_config)

        retrieved = await config_repository.get_guild_config(sample_guild_config.guild_id)

        assert retrieved.default_summary_options.summary_length.value == SummaryLength.DETAILED.value
        assert retrieved.default_summary_options.include_bots is False
        assert retrieved.default_summary_options.extract_action_items is True


class TestTaskRepository:
    """Test TaskRepository operations."""

    @pytest.mark.asyncio
    async def test_save_task(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask
    ):
        """Test saving a scheduled task."""
        task_id = await task_repository.save_task(sample_scheduled_task)

        assert task_id == sample_scheduled_task.id

    @pytest.mark.asyncio
    async def test_get_task(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask
    ):
        """Test retrieving a task by ID."""
        await task_repository.save_task(sample_scheduled_task)

        retrieved = await task_repository.get_task(sample_scheduled_task.id)

        assert retrieved is not None
        assert retrieved.id == sample_scheduled_task.id
        assert retrieved.name == sample_scheduled_task.name
        assert retrieved.schedule_type == sample_scheduled_task.schedule_type
        assert len(retrieved.destinations) == len(sample_scheduled_task.destinations)

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(
        self,
        task_repository: SQLiteTaskRepository
    ):
        """Test retrieving a task that doesn't exist."""
        result = await task_repository.get_task("nonexistent-task")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_task(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask
    ):
        """Test updating an existing task."""
        await task_repository.save_task(sample_scheduled_task)

        # Update task
        sample_scheduled_task.name = "Updated Task Name"
        sample_scheduled_task.is_active = False
        sample_scheduled_task.run_count += 1

        await task_repository.save_task(sample_scheduled_task)

        # Retrieve and verify
        retrieved = await task_repository.get_task(sample_scheduled_task.id)

        assert retrieved.name == "Updated Task Name"
        assert retrieved.is_active is False
        assert retrieved.run_count == sample_scheduled_task.run_count

    @pytest.mark.asyncio
    async def test_delete_task(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask
    ):
        """Test deleting a task."""
        await task_repository.save_task(sample_scheduled_task)

        deleted = await task_repository.delete_task(sample_scheduled_task.id)

        assert deleted is True

        # Verify it's gone
        retrieved = await task_repository.get_task(sample_scheduled_task.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_tasks_by_guild(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask
    ):
        """Test retrieving all tasks for a guild."""
        # Create multiple tasks
        for i in range(3):
            task = ScheduledTask(
                id=f"task-{i}",
                name=f"Task {i}",
                channel_id=sample_scheduled_task.channel_id,
                guild_id=sample_scheduled_task.guild_id,
                schedule_type=ScheduleType.DAILY,
                summary_options=SummaryOptions(),
                created_by="admin"
            )
            await task_repository.save_task(task)

        # Create task for different guild
        other_task = ScheduledTask(
            id="other-task",
            name="Other Task",
            channel_id="other-channel",
            guild_id="other-guild",
            schedule_type=ScheduleType.DAILY,
            summary_options=SummaryOptions(),
            created_by="admin"
        )
        await task_repository.save_task(other_task)

        # Retrieve tasks for specific guild
        tasks = await task_repository.get_tasks_by_guild(sample_scheduled_task.guild_id)

        assert len(tasks) == 3
        assert all(t.guild_id == sample_scheduled_task.guild_id for t in tasks)

    @pytest.mark.asyncio
    async def test_get_active_tasks(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask
    ):
        """Test retrieving all active tasks."""
        # Create active tasks
        for i in range(2):
            task = ScheduledTask(
                id=f"active-task-{i}",
                name=f"Active Task {i}",
                channel_id="channel",
                guild_id="guild",
                schedule_type=ScheduleType.DAILY,
                is_active=True,
                summary_options=SummaryOptions(),
                created_by="admin"
            )
            await task_repository.save_task(task)

        # Create inactive task
        inactive_task = ScheduledTask(
            id="inactive-task",
            name="Inactive Task",
            channel_id="channel",
            guild_id="guild",
            schedule_type=ScheduleType.DAILY,
            is_active=False,
            summary_options=SummaryOptions(),
            created_by="admin"
        )
        await task_repository.save_task(inactive_task)

        # Retrieve active tasks
        active_tasks = await task_repository.get_active_tasks()

        assert len(active_tasks) == 2
        assert all(t.is_active for t in active_tasks)

    @pytest.mark.asyncio
    async def test_save_task_result(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask,
        sample_task_result: TaskResult
    ):
        """Test saving a task execution result."""
        await task_repository.save_task(sample_scheduled_task)
        execution_id = await task_repository.save_task_result(sample_task_result)

        assert execution_id == sample_task_result.execution_id

    @pytest.mark.asyncio
    async def test_get_task_results(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask
    ):
        """Test retrieving task execution results."""
        await task_repository.save_task(sample_scheduled_task)

        # Create multiple results
        for i in range(5):
            result = TaskResult(
                task_id=sample_scheduled_task.id,
                execution_id=f"exec-{i}",
                status=TaskStatus.COMPLETED,
                started_at=datetime.utcnow() - timedelta(minutes=i),
                summary_id=f"summary-{i}"
            )
            await task_repository.save_task_result(result)

        # Retrieve results
        results = await task_repository.get_task_results(sample_scheduled_task.id, limit=3)

        assert len(results) == 3
        # Should be ordered by most recent first
        assert results[0].started_at >= results[-1].started_at

    @pytest.mark.asyncio
    async def test_save_task_with_destinations(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask
    ):
        """Test saving task with multiple destinations."""
        await task_repository.save_task(sample_scheduled_task)

        retrieved = await task_repository.get_task(sample_scheduled_task.id)

        assert len(retrieved.destinations) == 2
        assert retrieved.destinations[0].type == DestinationType.DISCORD_CHANNEL
        assert retrieved.destinations[1].type == DestinationType.WEBHOOK

    @pytest.mark.asyncio
    async def test_task_result_with_delivery_results(
        self,
        task_repository: SQLiteTaskRepository,
        sample_scheduled_task: ScheduledTask,
        sample_task_result: TaskResult
    ):
        """Test saving task result with delivery results."""
        await task_repository.save_task(sample_scheduled_task)
        await task_repository.save_task_result(sample_task_result)

        results = await task_repository.get_task_results(sample_task_result.task_id)

        assert len(results) == 1
        assert len(results[0].delivery_results) == 2
        assert results[0].delivery_results[0]["success"] is True
