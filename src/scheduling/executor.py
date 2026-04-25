"""
Task execution logic for scheduled tasks.

CS-008: Uses delivery strategy pattern for extensible destination handling.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

import discord

from .tasks import SummaryTask, CleanupTask
from src.utils.time import utc_now_naive
from .delivery import (
    DeliveryStrategy,
    DeliveryResult,
    DiscordDeliveryStrategy,
    DiscordDMDeliveryStrategy,
    WebhookDeliveryStrategy,
    EmailDeliveryStrategy,
    DashboardDeliveryStrategy,
)
from ..models.task import TaskResult, DestinationType, ScheduledTask, Destination, SummaryScope
# ADR-051: Platform fetcher abstraction for multi-platform support
from ..dashboard.platforms import get_platform_fetcher
from ..models.summary import SummaryResult, SummarizationContext
from ..models.stored_summary import StoredSummary
from ..models.error_log import ErrorType, ErrorSeverity
from ..exceptions import (
    SummaryBotException, InsufficientContentError,
    MessageFetchError, ChannelAccessError, create_error_context
)
from ..logging import CommandLogger, log_command, CommandType
from ..logging.error_tracker import get_error_tracker
from ..dashboard.models import SummaryScope as DashboardScope

logger = logging.getLogger(__name__)


@dataclass
class TaskDeliveryContext:
    """Adapter that provides DeliveryContext interface for SummaryTask.

    CS-008: Bridges the gap between SummaryTask and the DeliveryStrategy protocol.
    """
    task: SummaryTask
    discord_client: Any

    @property
    def guild_id(self) -> str:
        return self.task.guild_id

    @property
    def scheduled_task(self) -> Any:
        return self.task.scheduled_task

    def get_all_channel_ids(self) -> List[str]:
        return self.task.get_all_channel_ids()


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
    """Executes scheduled tasks with proper error handling and delivery.

    CS-008: Uses delivery strategy pattern for extensible destination handling.
    """

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

        # CS-008: Initialize delivery strategy registry
        self._delivery_strategies: Dict[DestinationType, DeliveryStrategy] = {
            DestinationType.DISCORD_CHANNEL: DiscordDeliveryStrategy(),
            DestinationType.DISCORD_DM: DiscordDMDeliveryStrategy(),
            DestinationType.WEBHOOK: WebhookDeliveryStrategy(),
            DestinationType.EMAIL: EmailDeliveryStrategy(),
            DestinationType.DASHBOARD: DashboardDeliveryStrategy(),
        }

    async def _get_template_content(self, task: SummaryTask) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """ADR-034: Get custom system prompt from guild template if configured.

        Args:
            task: Summary task with scheduled task reference

        Returns:
            Tuple of (content, name, id) - all None if no template configured
        """
        template_id = getattr(task.scheduled_task, 'prompt_template_id', None)
        if not template_id:
            return (None, None, None)

        try:
            from ..data.repositories import get_prompt_template_repository
            repo = await get_prompt_template_repository()
            template = await repo.get_template(template_id)
            if template:
                logger.info(f"Using guild prompt template '{template.name}' for task {task.scheduled_task.id}")
                # ADR-035: Return tuple with content, name, and id
                return (template.content, template.name, template.id)
            else:
                logger.warning(f"Template {template_id} not found for task {task.scheduled_task.id}")
                return (None, None, None)
        except Exception as e:
            logger.warning(f"Failed to fetch template {template_id}: {e}")
            return (None, None, None)

    @log_command(CommandType.SCHEDULED_TASK, command_name="execute_summary_task")
    async def execute_summary_task(self, task: SummaryTask) -> TaskExecutionResult:
        """Execute a summary task.

        Args:
            task: Summary task to execute

        Returns:
            Task execution result
        """
        start_time = utc_now_naive()
        task.mark_started()

        # ADR-011: Check if this task needs runtime scope resolution
        if task.should_resolve_runtime() or self._needs_scope_resolution(task):
            await self._resolve_scope_channels_runtime(task)

        # Check if this is individual mode
        if task.is_category_summary() and task.scheduled_task.category_mode == "individual":
            return await self._execute_individual_mode(task, start_time)

        # Otherwise execute combined mode (default)
        return await self._execute_combined_mode(task, start_time)

    def _needs_scope_resolution(self, task: SummaryTask) -> bool:
        """Check if task needs scope-based channel resolution (ADR-011)."""
        scope = getattr(task.scheduled_task, 'scope', None)
        if scope is None:
            return False
        return scope in (SummaryScope.CATEGORY, SummaryScope.GUILD)

    async def _resolve_scope_channels_runtime(self, task: SummaryTask) -> None:
        """Resolve channels based on scope at runtime (ADR-011).

        Args:
            task: Summary task with scope to resolve
        """
        if not self.discord_client:
            raise MessageFetchError("Discord client not available for scope resolution")

        scope = getattr(task.scheduled_task, 'scope', SummaryScope.CHANNEL)
        guild = self.discord_client.get_guild(int(task.guild_id))

        if not guild:
            raise MessageFetchError(f"Guild {task.guild_id} not found")

        if scope == SummaryScope.CATEGORY:
            # Resolve category channels
            category_id = task.scheduled_task.category_id
            if not category_id:
                raise MessageFetchError("Category ID required for CATEGORY scope")

            category = guild.get_channel(int(category_id))
            if not isinstance(category, discord.CategoryChannel):
                raise MessageFetchError(f"Category {category_id} not found or not accessible")

            excluded = set(task.scheduled_task.excluded_channel_ids)
            channels = [
                ch for ch in category.text_channels
                if str(ch.id) not in excluded
                and ch.permissions_for(guild.me).read_message_history
            ]

            task.scheduled_task.channel_ids = [str(ch.id) for ch in channels]
            logger.info(f"Resolved category '{category.name}' to {len(channels)} channels at runtime")

        elif scope == SummaryScope.GUILD:
            # Resolve all accessible text channels in guild
            # Try fetching from API first to ensure we have all channels
            text_channels = list(guild.text_channels)
            if len(text_channels) <= 1:
                # Cache may be stale, fetch from Discord API
                try:
                    fetched = await guild.fetch_channels()
                    text_channels = [ch for ch in fetched if isinstance(ch, discord.TextChannel)]
                    logger.info(f"Fetched {len(text_channels)} text channels for guild scope")
                except Exception as e:
                    logger.warning(f"Failed to fetch channels, using cache: {e}")

            channels = [
                ch for ch in text_channels
                if ch.permissions_for(guild.me).read_message_history
            ]

            task.scheduled_task.channel_ids = [str(ch.id) for ch in channels]
            logger.info(f"Resolved guild scope to {len(channels)} channels at runtime")

        else:
            # CHANNEL scope - channels already set, just validate
            logger.debug(f"Channel scope - using {len(task.scheduled_task.channel_ids)} pre-set channels")

    async def _resolve_category_channels_runtime(self, task: SummaryTask) -> None:
        """Resolve category channels at runtime (legacy, delegates to scope resolver).

        Args:
            task: Summary task with category to resolve
        """
        # Delegate to scope-based resolution
        await self._resolve_scope_channels_runtime(task)

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

        # ADR-034: Get custom template content if configured
        # ADR-035: Returns tuple (content, name, id)
        template_content, template_name, template_id = await self._get_template_content(task)

        # ADR-051: Get platform from scheduled task (default to discord)
        platform = getattr(task.scheduled_task, 'platform', 'discord') or 'discord'

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

                # ADR-051: Fetch messages using platform-appropriate method
                channel_messages = []
                channel_name = f"Channel {channel_id}"

                if platform != 'discord':
                    # Use platform fetcher for non-Discord platforms
                    try:
                        fetcher = await get_platform_fetcher(platform, task.guild_id)
                        if fetcher:
                            result = await fetcher.fetch_messages(
                                channel_ids=[channel_id],
                                start_time=start_msg_time,
                                end_time=end_msg_time,
                            )
                            await fetcher.close()
                            channel_messages = result.messages
                            if channel_id in result.channel_names:
                                channel_name = f"#{result.channel_names[channel_id]}"
                        else:
                            logger.error(f"Platform '{platform}' not available for guild {task.guild_id}")
                            results.append({"channel_id": channel_id, "success": False, "error": f"Platform {platform} not available"})
                            continue
                    except Exception as e:
                        logger.error(f"ADR-051: Platform fetcher failed for channel {channel_id}: {e}")
                        results.append({"channel_id": channel_id, "success": False, "error": str(e)})
                        continue
                else:
                    # Discord: Use existing message processor
                    channel_messages = await self.message_processor.process_channel_messages(
                        channel_id=channel_id,
                        start_time=start_msg_time,
                        end_time=end_msg_time,
                        options=task.summary_options
                    )
                    # Get channel name from Discord client
                    if self.discord_client:
                        try:
                            channel = self.discord_client.get_channel(int(channel_id))
                            if channel:
                                channel_name = f"#{channel.name}"
                        except (ValueError, AttributeError) as e:
                            # SEC-005: Log channel resolution errors at debug level
                            logger.debug(f"Could not resolve channel {channel_id}: {e}")

                if len(channel_messages) < task.summary_options.min_messages:
                    logger.warning(f"Channel {channel_id}: insufficient messages ({len(channel_messages)} < {task.summary_options.min_messages})")
                    results.append({"channel_id": channel_id, "success": False, "error": "Insufficient messages"})
                    continue

                # Create summarization context
                context = SummarizationContext(
                    channel_name=channel_name,
                    guild_name=f"Guild {task.guild_id}",
                    total_participants=len(set(msg.author_id for msg in channel_messages)),
                    time_span_hours=task.time_range_hours,
                    message_types={"text": len(channel_messages)}
                )

                # Generate summary
                # ADR-034: Pass custom system prompt from guild template if configured
                summary_result = await self.summarization_engine.summarize_messages(
                    messages=channel_messages,
                    options=task.summary_options,
                    context=context,
                    channel_id=channel_id,
                    guild_id=task.guild_id,
                    custom_system_prompt=template_content
                )

                logger.info(f"Generated summary {summary_result.id} for channel {channel_id}")

                # ADR-035: Store custom template info in metadata when used
                if template_name:
                    summary_result.metadata["perspective"] = template_name
                    summary_result.metadata["prompt_template_id"] = template_id
                    summary_result.metadata["prompt_template_name"] = template_name

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

        execution_time = (utc_now_naive() - start_time).total_seconds()

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
        is_multi_channel = len(channel_ids) > 1
        logger.info(f"Executing combined mode for {len(channel_ids)} channel(s): {channel_ids[:5]}{'...' if len(channel_ids) > 5 else ''}")

        # ADR-034: Get custom template content if configured
        # ADR-035: Returns tuple (content, name, id)
        template_content, template_name, template_id = await self._get_template_content(task)

        try:
            # Get time range for messages
            start_msg_time, end_msg_time = task.get_time_range()

            # ADR-051: Get platform from scheduled task (default to discord)
            platform = getattr(task.scheduled_task, 'platform', 'discord') or 'discord'

            # Fetch and process messages from all channels
            # For multi-channel, skip per-channel min check and do aggregate check later
            # ADR-041: Track skipped channels for soft-fail handling
            all_messages = []
            channels_with_content = []  # Track channels that actually had messages
            channels_skipped = []  # ADR-041: Track channels skipped due to access issues
            channel_names_map = {}  # ADR-051: Map of channel_id -> channel_name

            # ADR-051: Use platform fetcher for non-Discord platforms
            if platform != 'discord':
                try:
                    fetcher = await get_platform_fetcher(platform, task.guild_id)
                    if not fetcher:
                        raise MessageFetchError(f"Platform '{platform}' not available for guild {task.guild_id}")

                    result = await fetcher.fetch_messages(
                        channel_ids=channel_ids,
                        start_time=start_msg_time,
                        end_time=end_msg_time,
                    )
                    await fetcher.close()

                    all_messages = result.messages
                    channel_names_map = result.channel_names
                    channels_with_content = list(result.channel_names.keys())

                    # Convert errors to skipped channels format
                    for channel_id, error_msg in result.errors:
                        channels_skipped.append({
                            "channel_id": channel_id,
                            "channel_name": result.channel_names.get(channel_id, f"Channel {channel_id}"),
                            "reason": "fetch_error",
                            "error_code": "PLATFORM_FETCH_ERROR",
                            "message": str(error_msg)[:100]
                        })

                    logger.info(f"ADR-051: Fetched {len(all_messages)} messages from {platform} platform")

                except Exception as e:
                    logger.error(f"ADR-051: Platform fetcher failed for {platform}: {e}")
                    raise MessageFetchError(f"Failed to fetch messages from {platform}: {e}")
            else:
                # Discord: Use existing message processor
                for channel_id in channel_ids:
                    try:
                        channel_messages = await self.message_processor.process_channel_messages(
                            channel_id=channel_id,
                            start_time=start_msg_time,
                            end_time=end_msg_time,
                            options=task.summary_options,
                            skip_min_check=is_multi_channel  # Skip per-channel check for multi-channel
                        )
                        if channel_messages:
                            all_messages.extend(channel_messages)
                            channels_with_content.append(channel_id)
                    except ChannelAccessError as e:
                        # ADR-041: Soft-fail - skip this channel but continue with others
                        channel_name = await self._get_channel_name(channel_id)
                        channels_skipped.append({
                            "channel_id": channel_id,
                            "channel_name": channel_name,
                            "reason": "missing_access",
                            "error_code": getattr(e, 'error_code', 'CHANNEL_ACCESS_DENIED'),
                            "message": str(e)[:100]
                        })
                        logger.warning(f"ADR-041: Skipping channel {channel_id} ({channel_name}) due to access error: {e}")
                    except InsufficientContentError:
                        # For single channel, re-raise; for multi-channel, continue to next channel
                        if not is_multi_channel:
                            raise
                        # Multi-channel: this channel had no messages, continue to others
                        logger.debug(f"Channel {channel_id} had no messages, continuing to next channel")

            # Build channel names list from channels WITH CONTENT (for title)
            channel_names = []
            for channel_id in channels_with_content:
                # ADR-051: Use channel_names_map if available (from platform fetcher)
                if channel_id in channel_names_map:
                    channel_names.append(f"#{channel_names_map[channel_id]}")
                elif self.discord_client:
                    try:
                        channel = self.discord_client.get_channel(int(channel_id))
                        if channel:
                            channel_names.append(f"#{channel.name}")
                        else:
                            channel_names.append(f"Channel {channel_id}")
                    except (ValueError, AttributeError) as e:
                        # SEC-005: Log channel resolution errors at debug level
                        logger.debug(f"Could not resolve channel {channel_id}: {e}")
                        channel_names.append(f"Channel {channel_id}")
                else:
                    channel_names.append(f"Channel {channel_id}")

            # Sort messages by timestamp
            all_messages.sort(key=lambda m: m.timestamp)

            # For multi-channel, do aggregate min_messages check here
            if is_multi_channel and len(all_messages) < task.summary_options.min_messages:
                raise InsufficientContentError(
                    message_count=len(all_messages),
                    min_required=task.summary_options.min_messages
                )

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
            # ADR-034: Pass custom system prompt from guild template if configured
            summary_result = await self.summarization_engine.summarize_messages(
                messages=all_messages,
                options=task.summary_options,
                context=context,
                channel_id=task.channel_id,  # Primary channel for storage
                guild_id=task.guild_id,
                custom_system_prompt=template_content
            )

            logger.info(f"Generated summary {summary_result.id}")

            # ADR-035: Store custom template info in metadata when used
            if template_name:
                summary_result.metadata["perspective"] = template_name
                summary_result.metadata["prompt_template_id"] = template_id
                summary_result.metadata["prompt_template_name"] = template_name

            # Store channels_with_content in metadata for title generation
            if summary_result.metadata is None:
                summary_result.metadata = {}
            summary_result.metadata["channels_with_content"] = channels_with_content
            # Store scope info for reference
            if task.scheduled_task and task.scheduled_task.scope:
                summary_result.metadata["scope_type"] = task.scheduled_task.scope.value
            summary_result.metadata["scope_channel_ids"] = channel_ids

            # ADR-041: Add soft-fail access tracking to metadata
            if channels_skipped:
                total_requested = len(channel_ids)
                total_accessible = len(channels_with_content)
                coverage_percent = (total_accessible / total_requested * 100) if total_requested > 0 else 100

                summary_result.metadata["has_access_issues"] = True
                summary_result.metadata["channels_requested"] = total_requested
                summary_result.metadata["channels_accessible"] = total_accessible
                summary_result.metadata["channels_skipped_count"] = len(channels_skipped)
                summary_result.metadata["skipped_channels"] = channels_skipped
                summary_result.metadata["access_coverage_percent"] = round(coverage_percent, 1)

                # Log consolidated warning instead of per-channel errors
                logger.warning(
                    f"ADR-041: Summary {summary_result.id} generated with partial access: "
                    f"{total_accessible}/{total_requested} channels ({coverage_percent:.1f}% coverage). "
                    f"Skipped {len(channels_skipped)} channel(s) due to permission issues."
                )

                # Track consolidated error for admin visibility
                await self._track_access_issues(
                    task=task.scheduled_task,
                    skipped_channels=channels_skipped,
                    summary_id=summary_result.id,
                    coverage_percent=coverage_percent
                )
            else:
                summary_result.metadata["has_access_issues"] = False

            # Deliver to destinations
            delivery_results = await self._deliver_summary(
                summary=summary_result,
                destinations=task.destinations,
                task=task
            )

            # Mark task as completed
            task.mark_completed()

            execution_time = (utc_now_naive() - start_time).total_seconds()

            return TaskExecutionResult(
                task_id=task.scheduled_task.id,
                success=True,
                summary_result=summary_result,
                delivery_results=delivery_results,
                execution_time_seconds=execution_time
            )

        except InsufficientContentError as e:
            # Not enough messages is NOT a failure - it's a skip
            # This should NOT increment failure_count or disable the task
            logger.info(f"Skipping task {task.scheduled_task.id}: insufficient content ({e.message_count} messages)")
            task.mark_skipped()

            execution_time = (utc_now_naive() - start_time).total_seconds()

            return TaskExecutionResult(
                task_id=task.scheduled_task.id,
                success=True,  # Not a failure - just nothing to summarize
                error_message=f"Skipped: {e.user_message}",
                error_details={"skipped": True, "reason": "insufficient_content", **e.to_dict()},
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

            execution_time = (utc_now_naive() - start_time).total_seconds()

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
        start_time = utc_now_naive()
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

            execution_time = (utc_now_naive() - start_time).total_seconds()

            return TaskExecutionResult(
                task_id=task.task_id,
                success=True,
                execution_time_seconds=execution_time
            )

        except Exception as e:
            logger.exception(f"Failed to execute cleanup task: {e}")
            task.mark_failed(str(e))

            execution_time = (utc_now_naive() - start_time).total_seconds()

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
            "timestamp": utc_now_naive().isoformat()
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

        CS-008: Uses strategy pattern for extensible delivery handling.

        Args:
            summary: Summary result to deliver
            destinations: List of delivery destinations
            task: Original summary task

        Returns:
            List of delivery results
        """
        delivery_results = []

        # CS-008: Create delivery context adapter
        context = TaskDeliveryContext(task=task, discord_client=self.discord_client)

        for destination in destinations:
            if not destination.enabled:
                continue

            # ADR-031: Log delivery attempt
            logger.info(
                f"Delivering summary {summary.id} to {destination.type.value}: "
                f"target={destination.target}, task_id={task.scheduled_task.id}"
            )

            try:
                # CS-008: Look up strategy from registry
                strategy = self._delivery_strategies.get(destination.type)

                if strategy:
                    result = await strategy.deliver(
                        summary=summary,
                        destination=destination,
                        context=context,
                    )
                    delivery_results.append(result.to_dict())
                else:
                    logger.warning(f"No delivery strategy for type: {destination.type.value}")
                    delivery_results.append({
                        "destination_type": destination.type.value,
                        "target": destination.target,
                        "success": False,
                        "error": f"Unsupported destination type: {destination.type.value}"
                    })

            except Exception as e:
                # ADR-031: Log delivery failure with full context
                logger.error(
                    f"Delivery failed: destination={destination.type.value}, "
                    f"target={destination.target}, task_id={task.scheduled_task.id}, "
                    f"summary_id={summary.id}, error={type(e).__name__}: {e}"
                )
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

    # CS-008: Old delivery methods removed - now using delivery strategy pattern
    # See src/scheduling/delivery/ for strategy implementations

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

    async def _get_channel_name(self, channel_id: str) -> str:
        """ADR-041: Get channel name for display in skipped channels list.

        Args:
            channel_id: Discord channel ID

        Returns:
            Channel name or fallback string
        """
        if not self.discord_client:
            return f"Channel {channel_id}"

        try:
            channel = self.discord_client.get_channel(int(channel_id))
            if channel and hasattr(channel, 'name'):
                return f"#{channel.name}"
        except (ValueError, AttributeError):
            pass

        return f"Channel {channel_id}"

    async def _track_access_issues(
        self,
        task: ScheduledTask,
        skipped_channels: List[Dict[str, Any]],
        summary_id: str,
        coverage_percent: float
    ) -> None:
        """ADR-041: Track consolidated access issue as a single warning.

        Instead of logging 12+ individual errors, log one consolidated warning
        that helps admins understand the scope of the permission issue.

        Args:
            task: The scheduled task that had access issues
            skipped_channels: List of channels that were skipped
            summary_id: ID of the generated summary
            coverage_percent: Percentage of channels that were accessible
        """
        try:
            tracker = get_error_tracker()

            # Only track once per unique set of skipped channels (7-day cache)
            channel_ids_hash = hash(tuple(sorted(c['channel_id'] for c in skipped_channels)))

            await tracker.capture_error(
                error=Exception(f"Schedule has partial channel access: {len(skipped_channels)} channels inaccessible"),
                error_type=ErrorType.DISCORD_PERMISSION,
                severity=ErrorSeverity.WARNING,  # Warning, not error - schedule still succeeded
                guild_id=task.guild_id,
                channel_id=task.channel_id,
                operation=f"scheduled_task:{task.name or task.id}",
                details={
                    "task_id": task.id,
                    "task_name": task.name,
                    "summary_id": summary_id,
                    "skipped_count": len(skipped_channels),
                    "coverage_percent": coverage_percent,
                    "skipped_channels": [
                        {"id": c["channel_id"], "name": c["channel_name"]}
                        for c in skipped_channels[:10]  # Limit to 10 for storage
                    ],
                    "action_required": "Grant bot 'Read Message History' permission or exclude channels from schedule",
                    "is_consolidated": True,  # Flag to indicate this is a consolidated report
                },
            )
            logger.debug(f"Tracked consolidated access warning for task {task.id}")
        except Exception as e:
            logger.warning(f"Failed to track access issues: {e}")
