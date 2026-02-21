"""
Task execution logic for scheduled tasks.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

import discord

from .tasks import SummaryTask, CleanupTask
from ..models.task import TaskResult, DestinationType, ScheduledTask, Destination
from ..models.summary import SummaryResult, SummarizationContext
from ..models.stored_summary import StoredSummary
from ..models.error_log import ErrorType, ErrorSeverity
from ..exceptions import (
    SummaryBotException, InsufficientContentError,
    MessageFetchError, create_error_context
)
from ..logging import CommandLogger, log_command, CommandType
from ..logging.error_tracker import get_error_tracker

logger = logging.getLogger(__name__)


@dataclass
class TaskExecutionResult:
    """Result of task execution."""

    task_id: str
    success: bool
    summary_result: Optional[SummaryResult] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    delivery_results: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "summary_id": self.summary_result.id if self.summary_result else None,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "delivery_results": self.delivery_results,
            "execution_time_seconds": self.execution_time_seconds
        }


class TaskExecutor:
    """Executes scheduled tasks with proper error handling and delivery."""

    def __init__(self,
                 summarization_engine,
                 message_processor,
                 discord_client: Optional[discord.Client] = None,
                 command_logger: Optional[CommandLogger] = None):
        """Initialize task executor.

        Args:
            summarization_engine: Summarization engine instance
            message_processor: Message processor instance
            discord_client: Optional Discord client for delivery
            command_logger: CommandLogger instance for audit logging (optional)
        """
        self.summarization_engine = summarization_engine
        self.message_processor = message_processor
        self.discord_client = discord_client
        self.command_logger = command_logger

    @log_command(CommandType.SCHEDULED_TASK, command_name="execute_summary_task")
    async def execute_summary_task(self, task: SummaryTask) -> TaskExecutionResult:
        """Execute a summary task.

        Args:
            task: Summary task to execute

        Returns:
            Task execution result
        """
        start_time = datetime.utcnow()
        task.mark_started()

        # Check if this is a category task that needs runtime resolution
        if task.should_resolve_runtime():
            await self._resolve_category_channels_runtime(task)

        # Check if this is individual mode
        if task.is_category_summary() and task.scheduled_task.category_mode == "individual":
            return await self._execute_individual_mode(task, start_time)

        # Otherwise execute combined mode (default)
        return await self._execute_combined_mode(task, start_time)

    async def _resolve_category_channels_runtime(self, task: SummaryTask) -> None:
        """Resolve category channels at runtime.

        Args:
            task: Summary task with category to resolve
        """
        if not self.discord_client:
            raise MessageFetchError("Discord client not available for category resolution")

        category_id = task.scheduled_task.category_id
        category = self.discord_client.get_channel(int(category_id))

        if not isinstance(category, discord.CategoryChannel):
            raise MessageFetchError(f"Category {category_id} not found or not accessible")

        # Get text channels from category, excluding specified channels
        excluded = set(task.scheduled_task.excluded_channel_ids)
        channels = [
            ch for ch in category.text_channels
            if str(ch.id) not in excluded
        ]

        # Update task's channel_ids for this execution
        task.scheduled_task.channel_ids = [str(ch.id) for ch in channels]

        logger.info(f"Resolved category {category.name} to {len(channels)} channels at runtime")

    async def _execute_individual_mode(self, task: SummaryTask, start_time: datetime) -> TaskExecutionResult:
        """Execute task in individual mode - separate summaries per channel.

        Args:
            task: Summary task
            start_time: Execution start time

        Returns:
            Task execution result
        """
        channel_ids = task.get_all_channel_ids()
        logger.info(f"Executing individual mode for {len(channel_ids)} channels")

        results = []
        summaries_created = []

        for channel_id in channel_ids:
            try:
                # Create single-channel task
                single_task_data = task.scheduled_task
                single_task_data.channel_id = channel_id
                single_task_data.channel_ids = [channel_id]

                # Get time range for messages
                start_msg_time, end_msg_time = task.get_time_range()

                # Fetch and process messages
                channel_messages = await self.message_processor.process_channel_messages(
                    channel_id=channel_id,
                    start_time=start_msg_time,
                    end_time=end_msg_time,
                    options=task.summary_options
                )

                if len(channel_messages) < task.summary_options.min_messages:
                    logger.warning(f"Channel {channel_id}: insufficient messages ({len(channel_messages)} < {task.summary_options.min_messages})")
                    results.append({"channel_id": channel_id, "success": False, "error": "Insufficient messages"})
                    continue

                # Get channel name
                channel_name = f"Channel {channel_id}"
                if self.discord_client:
                    try:
                        channel = self.discord_client.get_channel(int(channel_id))
                        if channel:
                            channel_name = f"#{channel.name}"
                    except:
                        pass

                # Create summarization context
                context = SummarizationContext(
                    channel_name=channel_name,
                    guild_name=f"Guild {task.guild_id}",
                    total_participants=len(set(msg.author_id for msg in channel_messages)),
                    time_span_hours=task.time_range_hours,
                    message_types={"text": len(channel_messages)}
                )

                # Generate summary
                summary_result = await self.summarization_engine.summarize_messages(
                    messages=channel_messages,
                    options=task.summary_options,
                    context=context,
                    channel_id=channel_id,
                    guild_id=task.guild_id
                )

                logger.info(f"Generated summary {summary_result.id} for channel {channel_id}")

                # Deliver to channel
                if self.discord_client:
                    try:
                        channel = self.discord_client.get_channel(int(channel_id))
                        if channel:
                            embed_dict = summary_result.to_embed_dict()
                            embed = discord.Embed.from_dict(embed_dict)
                            await channel.send(embed=embed)
                            results.append({"channel_id": channel_id, "success": True, "summary_id": summary_result.id})
                            summaries_created.append(summary_result)
                    except Exception as e:
                        logger.error(f"Failed to deliver summary to channel {channel_id}: {e}")
                        results.append({"channel_id": channel_id, "success": False, "error": str(e)})
                else:
                    results.append({"channel_id": channel_id, "success": True, "summary_id": summary_result.id})
                    summaries_created.append(summary_result)

            except InsufficientContentError as e:
                logger.warning(f"Insufficient content for channel {channel_id}: {e}")
                results.append({"channel_id": channel_id, "success": False, "error": str(e)})

            except Exception as e:
                logger.exception(f"Failed to summarize channel {channel_id}: {e}")
                results.append({"channel_id": channel_id, "success": False, "error": str(e)})

        # Mark task based on results
        success_count = sum(1 for r in results if r["success"])

        if success_count > 0:
            task.mark_completed()
        else:
            task.mark_failed(f"Failed to generate summaries for all {len(channel_ids)} channels")

        execution_time = (datetime.utcnow() - start_time).total_seconds()

        return TaskExecutionResult(
            task_id=task.scheduled_task.id,
            success=success_count > 0,
            summary_result=summaries_created[0] if summaries_created else None,
            delivery_results=results,
            execution_time_seconds=execution_time
        )

    async def _execute_combined_mode(self, task: SummaryTask, start_time: datetime) -> TaskExecutionResult:
        """Execute task in combined mode - single summary (existing logic).

        Args:
            task: Summary task
            start_time: Execution start time

        Returns:
            Task execution result
        """
        channel_ids = task.get_all_channel_ids()
        logger.info(f"Executing combined mode for {len(channel_ids)} channel(s): {channel_ids}")

        try:
            # Get time range for messages
            start_msg_time, end_msg_time = task.get_time_range()

            # Fetch and process messages from all channels
            all_messages = []
            channel_names = []

            for channel_id in channel_ids:
                channel_messages = await self.message_processor.process_channel_messages(
                    channel_id=channel_id,
                    start_time=start_msg_time,
                    end_time=end_msg_time,
                    options=task.summary_options
                )
                all_messages.extend(channel_messages)

                # Try to get channel name from Discord client
                if self.discord_client:
                    try:
                        channel = self.discord_client.get_channel(int(channel_id))
                        if channel:
                            channel_names.append(f"#{channel.name}")
                        else:
                            channel_names.append(f"Channel {channel_id}")
                    except:
                        channel_names.append(f"Channel {channel_id}")
                else:
                    channel_names.append(f"Channel {channel_id}")

            # Sort messages by timestamp
            all_messages.sort(key=lambda m: m.timestamp)

            logger.info(f"Fetched {len(all_messages)} total messages from {len(channel_ids)} channel(s)")

            # Create summarization context
            if not channel_names:
                channel_display = "Unknown Channel"
            elif task.is_cross_channel() or task.is_category_summary():
                channel_display = ", ".join(channel_names)
            else:
                channel_display = channel_names[0]
            context = SummarizationContext(
                channel_name=channel_display,
                guild_name=f"Guild {task.guild_id}",
                total_participants=len(set(msg.author_id for msg in all_messages)),
                time_span_hours=task.time_range_hours,
                message_types={"text": len(all_messages)}
            )

            # Generate summary
            summary_result = await self.summarization_engine.summarize_messages(
                messages=all_messages,
                options=task.summary_options,
                context=context,
                channel_id=task.channel_id,  # Primary channel for storage
                guild_id=task.guild_id
            )

            logger.info(f"Generated summary {summary_result.id}")

            # Deliver to destinations
            delivery_results = await self._deliver_summary(
                summary=summary_result,
                destinations=task.destinations,
                task=task
            )

            # Mark task as completed
            task.mark_completed()

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            return TaskExecutionResult(
                task_id=task.scheduled_task.id,
                success=True,
                summary_result=summary_result,
                delivery_results=delivery_results,
                execution_time_seconds=execution_time
            )

        except InsufficientContentError as e:
            logger.warning(f"Insufficient content for task {task.scheduled_task.id}: {e}")
            task.mark_failed(f"Not enough messages to summarize: {e.message}")

            # Track error in error log
            await self._track_schedule_error(
                task=task.scheduled_task,
                error=e,
                error_type=ErrorType.SCHEDULE_ERROR,
                error_message=e.user_message,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            return TaskExecutionResult(
                task_id=task.scheduled_task.id,
                success=False,
                error_message=e.user_message,
                error_details=e.to_dict(),
                execution_time_seconds=execution_time
            )

        except Exception as e:
            logger.exception(f"Failed to execute summary task: {e}")
            task.mark_failed(str(e))

            # Track error in error log
            await self._track_schedule_error(
                task=task.scheduled_task,
                error=e,
                error_type=ErrorType.SUMMARIZATION_ERROR,
                error_message=str(e),
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            return TaskExecutionResult(
                task_id=task.scheduled_task.id,
                success=False,
                error_message=str(e),
                error_details={"exception_type": type(e).__name__},
                execution_time_seconds=execution_time
            )

    @log_command(CommandType.SCHEDULED_TASK, command_name="execute_cleanup_task")
    async def execute_cleanup_task(self, task: CleanupTask) -> TaskExecutionResult:
        """Execute a cleanup task.

        Args:
            task: Cleanup task to execute

        Returns:
            Task execution result
        """
        start_time = datetime.utcnow()
        task.mark_started()

        logger.info(f"Executing cleanup task {task.task_id}")

        try:
            cutoff_date = task.get_cutoff_date()
            items_deleted = 0

            # TODO: Implement actual cleanup logic with database
            # This would involve:
            # - Deleting old summaries
            # - Cleaning up logs
            # - Clearing cached data

            logger.info(f"Cleanup would delete items older than {cutoff_date}")

            # Placeholder - would actually delete items
            items_deleted = 0

            # Mark task as completed
            task.mark_completed(items_deleted)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            return TaskExecutionResult(
                task_id=task.task_id,
                success=True,
                execution_time_seconds=execution_time
            )

        except Exception as e:
            logger.exception(f"Failed to execute cleanup task: {e}")
            task.mark_failed(str(e))

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                error_message=str(e),
                error_details={"exception_type": type(e).__name__},
                execution_time_seconds=execution_time
            )

    async def _track_schedule_error(
        self,
        task: ScheduledTask,
        error: Exception,
        error_type: ErrorType,
        error_message: str,
    ) -> None:
        """Track a schedule execution error in the error log.

        Args:
            task: The scheduled task that failed
            error: The exception that was raised
            error_type: Type of error for categorization
            error_message: Human-readable error message
        """
        try:
            tracker = get_error_tracker()
            await tracker.capture_error(
                error=error,
                error_type=error_type,
                severity=ErrorSeverity.ERROR,
                guild_id=task.guild_id,
                channel_id=task.channel_id,
                operation=f"scheduled_task:{task.name or task.id}",
                details={
                    "task_id": task.id,
                    "task_name": task.name,
                    "schedule_type": task.schedule_type.value if task.schedule_type else None,
                    "failure_count": task.failure_count,
                    "error_message": error_message,
                },
            )
            logger.debug(f"Tracked schedule error for task {task.id}")
        except Exception as e:
            logger.warning(f"Failed to track schedule error: {e}")

    async def handle_task_failure(self, task: ScheduledTask, error: Exception) -> None:
        """Handle task failure with notifications and recovery.

        Args:
            task: Failed task
            error: Exception that caused the failure
        """
        logger.error(f"Handling failure for task {task.id}: {error}")

        # Log failure details
        error_details = {
            "task_id": task.id,
            "task_name": task.name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "failure_count": task.failure_count,
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.error(f"Task failure details: {error_details}")

        # Track error in error log
        await self._track_schedule_error(
            task=task,
            error=error,
            error_type=ErrorType.SCHEDULE_ERROR,
            error_message=str(error),
        )

        # Send notification to Discord if available and task has destinations
        if self.discord_client and task.destinations:
            await self._send_failure_notification(task, error_details)

        # Check if task should be disabled
        if task.failure_count >= task.max_failures:
            logger.warning(
                f"Task {task.id} disabled after {task.failure_count} failures"
            )

    async def _deliver_summary(self,
                              summary: SummaryResult,
                              destinations: List,
                              task: SummaryTask) -> List[Dict[str, Any]]:
        """Deliver summary to configured destinations.

        Args:
            summary: Summary result to deliver
            destinations: List of delivery destinations
            task: Original summary task

        Returns:
            List of delivery results
        """
        delivery_results = []

        for destination in destinations:
            if not destination.enabled:
                continue

            try:
                if destination.type == DestinationType.DISCORD_CHANNEL:
                    result = await self._deliver_to_discord(
                        summary=summary,
                        channel_id=destination.target,
                        format_type=destination.format
                    )
                    delivery_results.append(result)

                elif destination.type == DestinationType.WEBHOOK:
                    result = await self._deliver_to_webhook(
                        summary=summary,
                        webhook_url=destination.target,
                        format_type=destination.format
                    )
                    delivery_results.append(result)

                elif destination.type == DestinationType.DASHBOARD:
                    # ADR-005: Store summary in dashboard for viewing
                    result = await self._deliver_to_dashboard(
                        summary=summary,
                        destination=destination,
                        task=task
                    )
                    delivery_results.append(result)

                # Other destination types would be implemented here

            except Exception as e:
                logger.error(f"Failed to deliver to {destination.type.value}: {e}")
                delivery_results.append({
                    "destination_type": destination.type.value,
                    "target": destination.target,
                    "success": False,
                    "error": str(e)
                })
                # Track delivery error
                try:
                    tracker = get_error_tracker()
                    await tracker.capture_error(
                        error=e,
                        error_type=ErrorType.SCHEDULE_ERROR,
                        severity=ErrorSeverity.WARNING,
                        guild_id=task.guild_id,
                        channel_id=destination.target if destination.type == DestinationType.DISCORD_CHANNEL else None,
                        operation=f"delivery:{destination.type.value}",
                        details={
                            "task_id": task.scheduled_task.id,
                            "destination_type": destination.type.value,
                            "target": destination.target,
                            "error_message": str(e),
                        },
                    )
                except Exception as track_err:
                    logger.warning(f"Failed to track delivery error: {track_err}")

        return delivery_results

    async def _deliver_to_discord(self,
                                 summary: SummaryResult,
                                 channel_id: str,
                                 format_type: str) -> Dict[str, Any]:
        """Deliver summary to Discord channel.

        Args:
            summary: Summary to deliver
            channel_id: Discord channel ID
            format_type: Format (embed, markdown, etc.)

        Returns:
            Delivery result
        """
        if not self.discord_client:
            return {
                "destination_type": "discord_channel",
                "target": channel_id,
                "success": False,
                "error": "Discord client not available"
            }

        try:
            channel = self.discord_client.get_channel(int(channel_id))
            if not channel:
                channel = await self.discord_client.fetch_channel(int(channel_id))

            if format_type == "embed":
                embed_dict = summary.to_embed_dict()
                embed = discord.Embed.from_dict(embed_dict)
                await channel.send(embed=embed)

            elif format_type == "markdown":
                markdown = summary.to_markdown()
                # Split if too long
                if len(markdown) > 2000:
                    chunks = [markdown[i:i+2000] for i in range(0, len(markdown), 2000)]
                    for chunk in chunks:
                        await channel.send(chunk)
                else:
                    await channel.send(markdown)

            else:
                await channel.send(f"Summary generated: {summary.summary_text[:500]}...")

            return {
                "destination_type": "discord_channel",
                "target": channel_id,
                "success": True,
                "message": "Delivered successfully"
            }

        except Exception as e:
            logger.exception(f"Failed to deliver to Discord channel {channel_id}: {e}")
            return {
                "destination_type": "discord_channel",
                "target": channel_id,
                "success": False,
                "error": str(e)
            }

    async def _deliver_to_webhook(self,
                                 summary: SummaryResult,
                                 webhook_url: str,
                                 format_type: str) -> Dict[str, Any]:
        """Deliver summary to webhook.

        Args:
            summary: Summary to deliver
            webhook_url: Webhook URL
            format_type: Format (json, markdown, etc.)

        Returns:
            Delivery result
        """
        # Placeholder - would use aiohttp or similar
        logger.info(f"Would deliver to webhook: {webhook_url}")

        return {
            "destination_type": "webhook",
            "target": webhook_url,
            "success": True,
            "message": "Webhook delivery not yet implemented"
        }

    async def _deliver_to_dashboard(self,
                                   summary: SummaryResult,
                                   destination: Destination,
                                   task: SummaryTask) -> Dict[str, Any]:
        """Deliver summary to dashboard for viewing (ADR-005).

        Stores the summary in the database for viewing in the dashboard UI.
        Users can later push this summary to Discord channels on demand.

        Args:
            summary: Summary result to store
            destination: Dashboard destination configuration
            task: Original summary task

        Returns:
            Delivery result with stored summary ID
        """
        try:
            from ..data.repositories import get_stored_summary_repository

            # Generate a descriptive title from channels
            channel_names = []
            channel_ids = task.get_all_channel_ids()

            if self.discord_client:
                for channel_id in channel_ids:
                    try:
                        channel = self.discord_client.get_channel(int(channel_id))
                        if channel:
                            channel_names.append(f"#{channel.name}")
                        else:
                            channel_names.append(f"Channel {channel_id}")
                    except Exception:
                        channel_names.append(f"Channel {channel_id}")
            else:
                channel_names = [f"Channel {cid}" for cid in channel_ids]

            title = f"{', '.join(channel_names)} — {datetime.utcnow().strftime('%b %d, %H:%M')}"

            # Create stored summary
            stored_summary = StoredSummary(
                guild_id=task.guild_id,
                source_channel_ids=channel_ids,
                schedule_id=task.scheduled_task.id,
                summary_result=summary,
                title=title,
            )

            # Persist to database
            stored_summary_repo = await get_stored_summary_repository()
            await stored_summary_repo.save(stored_summary)

            logger.info(f"Stored summary {stored_summary.id} in dashboard for guild {task.guild_id}")

            return {
                "destination_type": "dashboard",
                "target": "dashboard",
                "success": True,
                "message": "Stored in dashboard",
                "details": {
                    "summary_id": stored_summary.id,
                    "title": title
                }
            }

        except Exception as e:
            logger.exception(f"Failed to store summary in dashboard: {e}")
            return {
                "destination_type": "dashboard",
                "target": "dashboard",
                "success": False,
                "error": str(e)
            }

    async def _send_failure_notification(self,
                                        task: ScheduledTask,
                                        error_details: Dict[str, Any]) -> None:
        """Send failure notification to Discord.

        Args:
            task: Failed task
            error_details: Error details
        """
        if not self.discord_client:
            return

        # Find a Discord destination to send notification
        discord_destinations = [
            d for d in task.destinations
            if d.type == DestinationType.DISCORD_CHANNEL and d.enabled
        ]

        if not discord_destinations:
            return

        notification = (
            f"⚠️ **Scheduled Task Failed**\n\n"
            f"**Task:** {task.name}\n"
            f"**Error:** {error_details['error_message']}\n"
            f"**Failure Count:** {task.failure_count}/{task.max_failures}\n"
            f"**Time:** {error_details['timestamp']}\n"
        )

        if task.failure_count >= task.max_failures:
            notification += "\n❌ **Task has been disabled due to repeated failures.**"

        try:
            if discord_destinations:
                channel_id = discord_destinations[0].target
                channel = self.discord_client.get_channel(int(channel_id))
                if channel:
                    await channel.send(notification)
            else:
                logger.warning(f"No Discord destinations configured for failure notification")
        except Exception as e:
            logger.error(f"Failed to send failure notification: {e}")
