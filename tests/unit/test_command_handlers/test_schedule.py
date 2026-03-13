"""
Unit tests for ScheduleCommandHandler.

Tests cover:
- Schedule creation
- Schedule listing
- Schedule cancellation
- Cron expression parsing
- Schedule validation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, time
import discord

from src.command_handlers.schedule import ScheduleCommandHandler
from src.models.task import ScheduledTask, TaskType, TaskStatus, ScheduleType
from src.models.summary import SummaryLength, SummaryOptions
from src.exceptions import UserError


@pytest.fixture
def mock_interaction():
    """Create mock Discord interaction."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = 123456789
    interaction.guild = MagicMock()
    interaction.guild.id = 987654321
    interaction.guild.name = "Test Guild"
    interaction.guild_id = 987654321
    interaction.command = MagicMock()
    interaction.command.name = "schedule"
    interaction.response = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup = AsyncMock()
    return interaction


@pytest.fixture
def mock_text_channel():
    """Create mock text channel."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 111222333
    channel.name = "test-channel"
    channel.mention = "<#111222333>"
    return channel


@pytest.fixture
def mock_admin_member():
    """Create mock admin member."""
    member = MagicMock()
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = True
    member.guild_permissions.manage_guild = False
    return member


@pytest.fixture
def mock_regular_member():
    """Create mock regular member."""
    member = MagicMock()
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = False
    member.guild_permissions.manage_guild = False
    return member


@pytest.fixture
def mock_task_scheduler():
    """Create mock task scheduler."""
    scheduler = AsyncMock()
    scheduler.schedule_task.return_value = "task_12345"
    scheduler.cancel_task.return_value = True
    scheduler.get_scheduled_tasks.return_value = []
    scheduler.update_task_status.return_value = None
    return scheduler


@pytest.fixture
def schedule_handler(mock_summarization_engine, mock_task_scheduler):
    """Create schedule command handler."""
    return ScheduleCommandHandler(
        summarization_engine=mock_summarization_engine,
        permission_manager=None,
        task_scheduler=mock_task_scheduler
    )


class TestScheduleCommandHandler:
    """Test ScheduleCommandHandler functionality."""

    @pytest.mark.asyncio
    async def test_handle_schedule_create_daily(self, schedule_handler, mock_interaction,
                                               mock_text_channel, mock_admin_member, mock_task_scheduler):
        """Test creating daily scheduled summary."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="daily",
            time_of_day="09:00",
            length="detailed"
        )

        # Should schedule task
        mock_task_scheduler.schedule_task.assert_called_once()

        # Verify task configuration
        scheduled_task = mock_task_scheduler.schedule_task.call_args[0][0]
        assert scheduled_task.schedule_type == ScheduleType.DAILY
        assert scheduled_task.schedule_time == "09:00"
        assert scheduled_task.task_type == TaskType.SUMMARY
        assert scheduled_task.is_active is True

        # Should send success message
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_schedule_create_weekly(self, schedule_handler, mock_interaction,
                                                mock_text_channel, mock_admin_member, mock_task_scheduler):
        """Test creating weekly scheduled summary."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="weekly",
            time_of_day="14:30"
        )

        mock_task_scheduler.schedule_task.assert_called_once()
        scheduled_task = mock_task_scheduler.schedule_task.call_args[0][0]
        assert scheduled_task.schedule_type == ScheduleType.WEEKLY
        assert scheduled_task.schedule_time == "14:30"

    @pytest.mark.asyncio
    async def test_handle_schedule_create_hourly(self, schedule_handler, mock_interaction,
                                                 mock_text_channel, mock_admin_member, mock_task_scheduler):
        """Test creating hourly scheduled summary."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="hourly"
        )

        mock_task_scheduler.schedule_task.assert_called_once()
        scheduled_task = mock_task_scheduler.schedule_task.call_args[0][0]
        assert scheduled_task.schedule_type == ScheduleType.CUSTOM

    @pytest.mark.asyncio
    async def test_handle_schedule_create_invalid_frequency(self, schedule_handler, mock_interaction,
                                                           mock_text_channel, mock_admin_member):
        """Test creating schedule with invalid frequency."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="invalid_frequency"
        )

        # Should send error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_schedule_create_invalid_time_format(self, schedule_handler, mock_interaction,
                                                             mock_text_channel, mock_admin_member):
        """Test creating schedule with invalid time format."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="daily",
            time_of_day="25:99"  # Invalid time
        )

        # Should send error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_schedule_create_different_lengths(self, schedule_handler, mock_interaction,
                                                           mock_text_channel, mock_admin_member, mock_task_scheduler):
        """Test creating schedules with different summary lengths."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        for length in ["brief", "detailed", "comprehensive"]:
            mock_task_scheduler.schedule_task.reset_mock()
            mock_interaction.response.send_message.reset_mock()

            await schedule_handler.handle_schedule_create(
                interaction=mock_interaction,
                channel=mock_text_channel,
                frequency="daily",
                length=length
            )

            mock_task_scheduler.schedule_task.assert_called_once()
            scheduled_task = mock_task_scheduler.schedule_task.call_args[0][0]
            assert scheduled_task.summary_options.summary_length == SummaryLength(length)

    @pytest.mark.asyncio
    async def test_handle_schedule_create_invalid_length(self, schedule_handler, mock_interaction,
                                                        mock_text_channel, mock_admin_member):
        """Test creating schedule with invalid length."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="daily",
            length="invalid_length"
        )

        # Should send error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_schedule_create_no_permission(self, schedule_handler, mock_interaction,
                                                       mock_text_channel, mock_regular_member):
        """Test creating schedule without permission."""
        mock_interaction.guild.get_member.return_value = mock_regular_member

        await schedule_handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="daily"
        )

        # Should send permission error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_schedule_create_no_scheduler(self, mock_summarization_engine,
                                                       mock_interaction, mock_text_channel, mock_admin_member):
        """Test creating schedule without task scheduler."""
        handler = ScheduleCommandHandler(
            summarization_engine=mock_summarization_engine,
            task_scheduler=None
        )

        mock_interaction.guild.get_member.return_value = mock_admin_member

        await handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="daily"
        )

        # Should send error about unavailable feature
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_schedule_list_empty(self, schedule_handler, mock_interaction,
                                              mock_task_scheduler):
        """Test listing schedules when none exist."""
        mock_task_scheduler.get_scheduled_tasks.return_value = []

        await schedule_handler.handle_schedule_list(mock_interaction)

        # Should send message about no schedules
        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        assert call_kwargs['ephemeral'] is True

    @pytest.mark.asyncio
    async def test_handle_schedule_list_with_tasks(self, schedule_handler, mock_interaction,
                                                   mock_task_scheduler):
        """Test listing existing scheduled tasks."""
        # Create sample tasks
        tasks = [
            ScheduledTask(
                id="task1",
                guild_id="987654321",
                channel_id="111222333",
                task_type=TaskType.SUMMARY,
                schedule_type=ScheduleType.DAILY,
                schedule_time="09:00",
                is_active=True,
                summary_options=SummaryOptions(summary_length=SummaryLength.DETAILED),
            ),
            ScheduledTask(
                id="task2",
                guild_id="987654321",
                channel_id="444555666",
                task_type=TaskType.SUMMARY,
                schedule_type=ScheduleType.WEEKLY,
                schedule_time="14:30",
                is_active=False,
                summary_options=SummaryOptions(summary_length=SummaryLength.BRIEF),
            )
        ]

        mock_task_scheduler.get_scheduled_tasks.return_value = tasks

        # Mock channel lookup
        channel1 = MagicMock()
        channel1.mention = "<#111222333>"
        channel2 = MagicMock()
        channel2.mention = "<#444555666>"

        def get_channel(channel_id):
            if channel_id == 111222333:
                return channel1
            elif channel_id == 444555666:
                return channel2
            return None

        mock_interaction.guild.get_channel = get_channel

        await schedule_handler.handle_schedule_list(mock_interaction)

        # Should send list of tasks
        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        assert 'embed' in call_kwargs
        assert call_kwargs['ephemeral'] is True

    @pytest.mark.asyncio
    async def test_handle_schedule_list_many_tasks(self, schedule_handler, mock_interaction, mock_task_scheduler):
        """Test listing more than 10 scheduled tasks."""
        # Create 15 tasks
        tasks = [
            ScheduledTask(
                id=f"task{i}",
                guild_id="987654321",
                channel_id="111222333",
                task_type=TaskType.SUMMARY,
                schedule_type=ScheduleType.DAILY,
                is_active=True,
                summary_options=SummaryOptions(summary_length=SummaryLength.DETAILED),
            )
            for i in range(15)
        ]

        mock_task_scheduler.get_scheduled_tasks.return_value = tasks
        mock_interaction.guild.get_channel.return_value = MagicMock(mention="<#111222333>")

        await schedule_handler.handle_schedule_list(mock_interaction)

        # Should indicate truncation
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_schedule_delete_success(self, schedule_handler, mock_interaction,
                                                  mock_admin_member, mock_task_scheduler):
        """Test deleting a scheduled summary."""
        mock_interaction.guild.get_member.return_value = mock_admin_member
        mock_task_scheduler.cancel_task.return_value = True

        await schedule_handler.handle_schedule_delete(
            interaction=mock_interaction,
            task_id="task_12345"
        )

        # Should cancel task
        mock_task_scheduler.cancel_task.assert_called_once_with("task_12345")

        # Should send success message
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_schedule_delete_not_found(self, schedule_handler, mock_interaction,
                                                    mock_admin_member, mock_task_scheduler):
        """Test deleting non-existent task."""
        mock_interaction.guild.get_member.return_value = mock_admin_member
        mock_task_scheduler.cancel_task.return_value = False

        await schedule_handler.handle_schedule_delete(
            interaction=mock_interaction,
            task_id="nonexistent_task"
        )

        # Should send error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_schedule_delete_no_permission(self, schedule_handler, mock_interaction, mock_regular_member):
        """Test deleting schedule without permission."""
        mock_interaction.guild.get_member.return_value = mock_regular_member

        await schedule_handler.handle_schedule_delete(
            interaction=mock_interaction,
            task_id="task_12345"
        )

        # Should send permission error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_schedule_pause(self, schedule_handler, mock_interaction,
                                        mock_admin_member, mock_task_scheduler):
        """Test pausing a scheduled summary."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_pause(
            interaction=mock_interaction,
            task_id="task_12345"
        )

        # Should update task status
        mock_task_scheduler.update_task_status.assert_called_once_with("task_12345", enabled=False)

        # Should send success message
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_schedule_pause_no_permission(self, schedule_handler, mock_interaction, mock_regular_member):
        """Test pausing schedule without permission."""
        mock_interaction.guild.get_member.return_value = mock_regular_member

        await schedule_handler.handle_schedule_pause(
            interaction=mock_interaction,
            task_id="task_12345"
        )

        # Should send permission error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_handle_schedule_resume(self, schedule_handler, mock_interaction,
                                         mock_admin_member, mock_task_scheduler):
        """Test resuming a paused scheduled summary."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_resume(
            interaction=mock_interaction,
            task_id="task_12345"
        )

        # Should update task status
        mock_task_scheduler.update_task_status.assert_called_once_with("task_12345", enabled=True)

        # Should send success message
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_schedule_resume_no_permission(self, schedule_handler, mock_interaction, mock_regular_member):
        """Test resuming schedule without permission."""
        mock_interaction.guild.get_member.return_value = mock_regular_member

        await schedule_handler.handle_schedule_resume(
            interaction=mock_interaction,
            task_id="task_12345"
        )

        # Should send permission error
        mock_interaction.response.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_schedule_metadata_includes_creator(self, schedule_handler, mock_interaction,
                                                      mock_text_channel, mock_admin_member, mock_task_scheduler):
        """Test that scheduled task includes creator info."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="daily"
        )

        scheduled_task = mock_task_scheduler.schedule_task.call_args[0][0]
        assert scheduled_task.created_by == str(mock_interaction.user.id)

    @pytest.mark.asyncio
    async def test_schedule_without_time_of_day(self, schedule_handler, mock_interaction,
                                                mock_text_channel, mock_admin_member, mock_task_scheduler):
        """Test creating schedule without specific time."""
        mock_interaction.guild.get_member.return_value = mock_admin_member

        await schedule_handler.handle_schedule_create(
            interaction=mock_interaction,
            channel=mock_text_channel,
            frequency="hourly"
        )

        scheduled_task = mock_task_scheduler.schedule_task.call_args[0][0]
        assert scheduled_task.schedule_time is None
