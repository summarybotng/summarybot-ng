"""
Scheduling command handlers for automated summaries.
"""

import logging
from typing import Optional, List
from datetime import datetime, time
import discord

from .base import BaseCommandHandler
from .utils import format_error_response, format_success_response, format_info_response
from ..exceptions import UserError, create_error_context
from ..models.task import ScheduledTask, TaskType, TaskStatus, ScheduleType, Destination, DestinationType
from ..models.summary import SummaryLength, SummaryOptions
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


def parse_day_names(day_string: str) -> List[int]:
    """
    Parse day names from comma-separated string to weekday integers.

    Args:
        day_string: Comma-separated day names (e.g., "mon,wed,fri,sun")

    Returns:
        List of weekday integers (0=Monday, 6=Sunday)

    Raises:
        ValueError: If invalid day name provided
    """
    day_map = {
        'mon': 0, 'monday': 0,
        'tue': 1, 'tuesday': 1,
        'wed': 2, 'wednesday': 2,
        'thu': 3, 'thursday': 3,
        'fri': 4, 'friday': 4,
        'sat': 5, 'saturday': 5,
        'sun': 6, 'sunday': 6
    }

    days = []
    for day_name in day_string.lower().split(','):
        day_name = day_name.strip()
        if day_name not in day_map:
            raise ValueError(f"Invalid day name: {day_name}")
        days.append(day_map[day_name])

    return sorted(list(set(days)))  # Remove duplicates and sort


class ScheduleCommandHandler(BaseCommandHandler):
    """Handler for scheduling commands."""

    def __init__(self, summarization_engine, permission_manager=None,
                 task_scheduler=None):
        """
        Initialize schedule command handler.

        Args:
            summarization_engine: SummarizationEngine instance
            permission_manager: PermissionManager instance (optional)
            task_scheduler: TaskScheduler instance for managing scheduled tasks
        """
        super().__init__(summarization_engine, permission_manager)
        self.task_scheduler = task_scheduler

        # Scheduling commands require admin permissions
        self.requires_admin = True

    async def _execute_command(self, interaction: discord.Interaction, **kwargs) -> None:
        """Execute scheduling command."""
        pass

    async def _check_admin_permission(self, interaction: discord.Interaction) -> bool:
        """
        Check if user has admin permissions.

        Args:
            interaction: Discord interaction object

        Returns:
            True if user is admin
        """
        if not interaction.guild:
            return False

        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False

        return member.guild_permissions.administrator or member.guild_permissions.manage_guild

    async def handle_schedule_create(self,
                                    interaction: discord.Interaction,
                                    channel: discord.TextChannel,
                                    frequency: str,
                                    time_of_day: Optional[str] = None,
                                    length: str = "detailed",
                                    days: Optional[str] = None,
                                    additional_channels: Optional[str] = None) -> None:
        """
        Create a new scheduled summary.

        Args:
            interaction: Discord interaction object
            channel: Primary channel for summaries
            frequency: Schedule frequency (daily, weekly, half-weekly, monthly)
            time_of_day: Time to generate summary (HH:MM format)
            length: Summary length
            days: Specific days for half-weekly (e.g., "mon,wed,fri,sun")
            additional_channels: Additional channels for cross-channel summary (comma-separated)
        """
        try:
            # Check admin permission
            if not await self._check_admin_permission(interaction):
                await self.send_permission_error(interaction)
                return

            if not self.task_scheduler:
                raise UserError(
                    message="Task scheduler not available",
                    error_code="NO_SCHEDULER",
                    user_message="Scheduled summaries feature is not available."
                )

            # Validate frequency
            valid_frequencies = ["hourly", "daily", "weekly", "half-weekly", "monthly"]
            if frequency.lower() not in valid_frequencies:
                raise UserError(
                    message=f"Invalid frequency: {frequency}",
                    error_code="INVALID_FREQUENCY",
                    user_message=f"Frequency must be one of: {', '.join(valid_frequencies)}"
                )

            # Parse time if provided
            schedule_time = None
            if time_of_day:
                try:
                    hour, minute = map(int, time_of_day.split(':'))
                    schedule_time = time(hour=hour, minute=minute)
                except ValueError:
                    raise UserError(
                        message=f"Invalid time format: {time_of_day}",
                        error_code="INVALID_TIME",
                        user_message="Time must be in HH:MM format (e.g., 09:00, 14:30)"
                    )

            # Validate summary length
            try:
                summary_length = SummaryLength(length.lower())
            except ValueError:
                raise UserError(
                    message=f"Invalid length: {length}",
                    error_code="INVALID_LENGTH",
                    user_message="Length must be 'brief', 'detailed', or 'comprehensive'."
                )

            # Parse days for half-weekly scheduling
            schedule_days = []
            if frequency.lower() == "half-weekly":
                if not days:
                    raise UserError(
                        message="Days required for half-weekly schedule",
                        error_code="MISSING_DAYS",
                        user_message="Please specify days for half-weekly schedule (e.g., 'mon,wed,fri' or 'tue,thu')"
                    )
                try:
                    schedule_days = parse_day_names(days)
                except ValueError as e:
                    raise UserError(
                        message=str(e),
                        error_code="INVALID_DAYS",
                        user_message=f"Invalid day specification: {str(e)}. Use format like 'mon,wed,fri' or 'tue,thu,sat'"
                    )

            # Map frequency to ScheduleType
            frequency_map = {
                "daily": ScheduleType.DAILY,
                "weekly": ScheduleType.WEEKLY,
                "half-weekly": ScheduleType.HALF_WEEKLY,
                "monthly": ScheduleType.MONTHLY,
                "hourly": ScheduleType.CUSTOM  # hourly uses custom cron
            }
            schedule_type = frequency_map.get(frequency.lower(), ScheduleType.DAILY)

            # Create destination
            destination = Destination(
                type=DestinationType.DISCORD_CHANNEL,
                target=str(channel.id),
                format="embed",
                enabled=True
            )

            # Parse additional channels for cross-channel summaries
            all_channel_ids = [str(channel.id)]  # Start with primary channel
            if additional_channels:
                import re
                # Extract channel IDs from mentions (#channel) or raw IDs
                channel_pattern = r'<#(\d+)>|(\d{17,20})'
                matches = re.findall(channel_pattern, additional_channels)
                for mention_id, raw_id in matches:
                    channel_id = mention_id or raw_id
                    if channel_id and channel_id not in all_channel_ids:
                        all_channel_ids.append(channel_id)

            # Create summary options
            summary_opts = SummaryOptions(summary_length=summary_length)

            # Create task name based on number of channels
            if len(all_channel_ids) > 1:
                task_name = f"{frequency.capitalize()} cross-channel summary ({len(all_channel_ids)} channels)"
            else:
                task_name = f"{frequency.capitalize()} summary for #{channel.name}"

            # Create scheduled task
            task = ScheduledTask(
                name=task_name,
                guild_id=str(interaction.guild_id),
                channel_id=str(channel.id),  # Primary channel
                channel_ids=all_channel_ids,  # All channels including primary
                task_type=TaskType.SUMMARY,
                schedule_type=schedule_type,
                schedule_time=schedule_time.strftime('%H:%M') if schedule_time else None,
                schedule_days=schedule_days,
                destinations=[destination],
                summary_options=summary_opts,
                is_active=True,
                created_by=str(interaction.user.id)
            )

            # Schedule the task
            task_id = await self.task_scheduler.schedule_task(task)

            # Create success response
            schedule_desc = f"{frequency.capitalize()}"
            if schedule_days:
                day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                days_str = ", ".join([day_names[d] for d in schedule_days])
                schedule_desc = f"{days_str}"
            if schedule_time:
                schedule_desc += f" at {schedule_time.strftime('%H:%M')} UTC"

            # Create response with channel info
            if len(all_channel_ids) > 1:
                channel_list = ", ".join([f"<#{cid}>" for cid in all_channel_ids])
                description = f"Automatic cross-channel summaries will be posted to {channel.mention}\n**Channels:** {channel_list}"
            else:
                description = f"Automatic summaries will be posted to {channel.mention}"

            embed = format_success_response(
                title="Scheduled Summary Created",
                description=description,
                fields={
                    "Schedule": schedule_desc,
                    "Length": summary_length.value.capitalize(),
                    "Channels": f"{len(all_channel_ids)} channel(s)",
                    "Task ID": task_id,
                    "Status": "Active"
                }
            )

            embed.set_footer(text=f"Use /schedule list to view all scheduled summaries")

            await interaction.response.send_message(embed=embed)

            logger.info(
                f"Scheduled summary created - Guild: {interaction.guild_id}, "
                f"Channel: {channel.id}, Frequency: {frequency}, User: {interaction.user.id}"
            )

        except UserError as e:
            await self.send_error_response(interaction, e)
        except Exception as e:
            logger.exception(f"Failed to create scheduled summary: {e}")
            await self.send_error_response(interaction, e)

    async def handle_schedule_list(self, interaction: discord.Interaction) -> None:
        """
        List all scheduled summaries for the guild.

        Args:
            interaction: Discord interaction object
        """
        try:
            if not self.task_scheduler:
                raise UserError(
                    message="Task scheduler not available",
                    error_code="NO_SCHEDULER",
                    user_message="Scheduled summaries feature is not available."
                )

            guild_id = str(interaction.guild_id)
            tasks = await self.task_scheduler.get_scheduled_tasks(guild_id)

            # Filter for summary tasks only
            summary_tasks = [t for t in tasks if t.task_type == TaskType.SUMMARY]

            if not summary_tasks:
                embed = format_info_response(
                    title="Scheduled Summaries",
                    description="No scheduled summaries configured for this server.",
                    fields={
                        "Get Started": "Use `/schedule create` to set up automatic summaries."
                    }
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Create embed with task list
            embed = discord.Embed(
                title="📅 Scheduled Summaries",
                description=f"Active summaries for {interaction.guild.name}",
                color=0x4A90E2,
                timestamp=utc_now_naive()
            )

            for i, task in enumerate(summary_tasks[:10], 1):  # Limit to 10
                # Get channel info (support cross-channel)
                channel_ids = task.get_all_channel_ids()
                if len(channel_ids) > 1:
                    # Cross-channel summary
                    channel_mentions = []
                    for cid in channel_ids[:3]:  # Show first 3
                        try:
                            ch = interaction.guild.get_channel(int(cid))
                            channel_mentions.append(ch.mention if ch else f"`{cid}`")
                        except (ValueError, AttributeError):
                            # SEC-005: Specific exceptions for channel resolution
                            channel_mentions.append(f"`{cid}`")
                    channel_name = ", ".join(channel_mentions)
                    if len(channel_ids) > 3:
                        channel_name += f" +{len(channel_ids) - 3} more"
                    channel_name = f"🔀 {channel_name}"  # Icon for cross-channel
                else:
                    # Single channel
                    channel = interaction.guild.get_channel(int(task.channel_id))
                    channel_name = channel.mention if channel else f"Channel {task.channel_id}"

                # Use the built-in schedule description method
                schedule_desc = task.get_schedule_description()

                status_emoji = "✅" if task.is_active else "⏸️"

                # Get summary length from summary_options (with fallback)
                try:
                    if task.summary_options and task.summary_options.summary_length:
                        length = task.summary_options.summary_length.value
                    else:
                        length = "detailed"
                except (AttributeError, ValueError):
                    length = "detailed"

                field_value = (
                    f"{status_emoji} **Status:** {'Active' if task.is_active else 'Paused'}\n"
                    f"📝 **Channel:** {channel_name}\n"
                    f"🔄 **Schedule:** {schedule_desc}\n"
                    f"📏 **Length:** {length.capitalize()}\n"
                    f"🆔 **ID:** `{task.id}`"
                )

                embed.add_field(
                    name=f"#{i}",
                    value=field_value,
                    inline=False
                )

            if len(summary_tasks) > 10:
                embed.set_footer(text=f"Showing 10 of {len(summary_tasks)} scheduled summaries")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Failed to list scheduled summaries: {e}")
            await self.send_error_response(interaction, e)

    async def handle_schedule_delete(self,
                                    interaction: discord.Interaction,
                                    task_id: str) -> None:
        """
        Delete a scheduled summary.

        Args:
            interaction: Discord interaction object
            task_id: ID of task to delete
        """
        try:
            # Check admin permission
            if not await self._check_admin_permission(interaction):
                await self.send_permission_error(interaction)
                return

            if not self.task_scheduler:
                raise UserError(
                    message="Task scheduler not available",
                    error_code="NO_SCHEDULER",
                    user_message="Scheduled summaries feature is not available."
                )

            # Cancel the task
            success = await self.task_scheduler.cancel_task(task_id)

            if not success:
                raise UserError(
                    message=f"Task not found: {task_id}",
                    error_code="TASK_NOT_FOUND",
                    user_message=f"Could not find scheduled summary with ID `{task_id}`."
                )

            embed = format_success_response(
                title="Scheduled Summary Deleted",
                description=f"Successfully deleted scheduled summary.",
                fields={"Task ID": f"`{task_id}`"}
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

            logger.info(
                f"Scheduled summary deleted - Guild: {interaction.guild_id}, "
                f"Task: {task_id}, User: {interaction.user.id}"
            )

        except UserError as e:
            await self.send_error_response(interaction, e)
        except Exception as e:
            logger.exception(f"Failed to delete scheduled summary: {e}")
            await self.send_error_response(interaction, e)

    async def handle_schedule_pause(self,
                                   interaction: discord.Interaction,
                                   task_id: str) -> None:
        """
        Pause a scheduled summary.

        Args:
            interaction: Discord interaction object
            task_id: ID of task to pause
        """
        try:
            # Check admin permission
            if not await self._check_admin_permission(interaction):
                await self.send_permission_error(interaction)
                return

            if not self.task_scheduler:
                raise UserError(
                    message="Task scheduler not available",
                    error_code="NO_SCHEDULER",
                    user_message="Scheduled summaries feature is not available."
                )

            # Update task status
            await self.task_scheduler.update_task_status(task_id, enabled=False)

            embed = format_success_response(
                title="Scheduled Summary Paused",
                description="The scheduled summary has been paused.",
                fields={
                    "Task ID": f"`{task_id}`",
                    "Note": "Use `/schedule resume` to resume this summary."
                }
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Failed to pause scheduled summary: {e}")
            await self.send_error_response(interaction, e)

    async def handle_schedule_resume(self,
                                    interaction: discord.Interaction,
                                    task_id: str) -> None:
        """
        Resume a paused scheduled summary.

        Args:
            interaction: Discord interaction object
            task_id: ID of task to resume
        """
        try:
            # Check admin permission
            if not await self._check_admin_permission(interaction):
                await self.send_permission_error(interaction)
                return

            if not self.task_scheduler:
                raise UserError(
                    message="Task scheduler not available",
                    error_code="NO_SCHEDULER",
                    user_message="Scheduled summaries feature is not available."
                )

            # Update task status
            await self.task_scheduler.update_task_status(task_id, enabled=True)

            embed = format_success_response(
                title="Scheduled Summary Resumed",
                description="The scheduled summary has been resumed.",
                fields={"Task ID": f"`{task_id}`"}
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Failed to resume scheduled summary: {e}")
            await self.send_error_response(interaction, e)
