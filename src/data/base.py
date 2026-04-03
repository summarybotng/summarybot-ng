"""
Abstract repository interfaces for data access layer.

This module defines the repository pattern interfaces for all data operations.
Concrete implementations should inherit from these abstract base classes.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..models.summary import SummaryResult
from ..models.task import ScheduledTask, TaskResult
from ..models.feed import FeedConfig
from ..models.error_log import ErrorLog, ErrorType, ErrorSeverity
from ..models.stored_summary import StoredSummary
from ..models.ingest import IngestDocument, IngestBatch
from ..models.message import ProcessedMessage
from ..models.summary_job import SummaryJob
from ..models.prompt_template import GuildPromptTemplate
from ..config.settings import GuildConfig


class SearchCriteria:
    """Search criteria for querying summaries."""

    def __init__(
        self,
        guild_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        order_direction: str = "DESC",
        # ADR-002: Multi-source support
        source_type: Optional[str] = None,  # 'discord', 'whatsapp', etc.
        # Perspective filter
        perspective: Optional[str] = None,  # 'general', 'developer', 'executive', etc.
    ):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.start_time = start_time
        self.end_time = end_time
        self.limit = limit
        self.offset = offset
        self.order_by = order_by
        self.order_direction = order_direction
        self.source_type = source_type
        self.perspective = perspective


class SummaryRepository(ABC):
    """Abstract repository for summary data operations."""

    @abstractmethod
    async def save_summary(self, summary: SummaryResult) -> str:
        """
        Save a summary to the database.

        Args:
            summary: The summary result to save

        Returns:
            The ID of the saved summary
        """
        pass

    @abstractmethod
    async def get_summary(self, summary_id: str) -> Optional[SummaryResult]:
        """
        Retrieve a summary by its ID.

        Args:
            summary_id: The unique identifier of the summary

        Returns:
            The summary result if found, None otherwise
        """
        pass

    @abstractmethod
    async def find_summaries(self, criteria: SearchCriteria) -> List[SummaryResult]:
        """
        Find summaries matching the given criteria.

        Args:
            criteria: Search criteria for filtering summaries

        Returns:
            List of matching summary results
        """
        pass

    @abstractmethod
    async def delete_summary(self, summary_id: str) -> bool:
        """
        Delete a summary from the database.

        Args:
            summary_id: The unique identifier of the summary to delete

        Returns:
            True if the summary was deleted, False otherwise
        """
        pass

    @abstractmethod
    async def count_summaries(self, criteria: SearchCriteria) -> int:
        """
        Count summaries matching the given criteria.

        Args:
            criteria: Search criteria for filtering summaries

        Returns:
            Number of matching summaries
        """
        pass

    @abstractmethod
    async def get_summaries_by_channel(
        self,
        channel_id: str,
        limit: int = 10
    ) -> List[SummaryResult]:
        """
        Get recent summaries for a specific channel.

        Args:
            channel_id: The channel ID to search for
            limit: Maximum number of summaries to return

        Returns:
            List of recent summary results for the channel
        """
        pass


class ConfigRepository(ABC):
    """Abstract repository for configuration data operations."""

    @abstractmethod
    async def save_guild_config(self, config: GuildConfig) -> None:
        """
        Save or update a guild configuration.

        Args:
            config: The guild configuration to save
        """
        pass

    @abstractmethod
    async def get_guild_config(self, guild_id: str) -> Optional[GuildConfig]:
        """
        Retrieve configuration for a specific guild.

        Args:
            guild_id: The unique identifier of the guild

        Returns:
            The guild configuration if found, None otherwise
        """
        pass

    @abstractmethod
    async def delete_guild_config(self, guild_id: str) -> bool:
        """
        Delete a guild configuration.

        Args:
            guild_id: The unique identifier of the guild

        Returns:
            True if the configuration was deleted, False otherwise
        """
        pass

    @abstractmethod
    async def get_all_guild_configs(self) -> List[GuildConfig]:
        """
        Retrieve all guild configurations.

        Returns:
            List of all guild configurations
        """
        pass


class TaskRepository(ABC):
    """Abstract repository for scheduled task data operations."""

    @abstractmethod
    async def save_task(self, task: ScheduledTask) -> str:
        """
        Save or update a scheduled task.

        Args:
            task: The scheduled task to save

        Returns:
            The ID of the saved task
        """
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """
        Retrieve a task by its ID.

        Args:
            task_id: The unique identifier of the task

        Returns:
            The scheduled task if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_tasks_by_guild(self, guild_id: str) -> List[ScheduledTask]:
        """
        Get all tasks for a specific guild.

        Args:
            guild_id: The unique identifier of the guild

        Returns:
            List of scheduled tasks for the guild
        """
        pass

    @abstractmethod
    async def get_active_tasks(self) -> List[ScheduledTask]:
        """
        Get all active tasks across all guilds.

        Returns:
            List of all active scheduled tasks
        """
        pass

    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        """
        Delete a scheduled task.

        Args:
            task_id: The unique identifier of the task

        Returns:
            True if the task was deleted, False otherwise
        """
        pass

    @abstractmethod
    async def save_task_result(self, result: TaskResult) -> str:
        """
        Save a task execution result.

        Args:
            result: The task execution result to save

        Returns:
            The ID of the saved result
        """
        pass

    @abstractmethod
    async def get_task_results(
        self,
        task_id: str,
        limit: int = 10
    ) -> List[TaskResult]:
        """
        Get execution results for a specific task.

        Args:
            task_id: The unique identifier of the task
            limit: Maximum number of results to return

        Returns:
            List of task execution results
        """
        pass


class FeedRepository(ABC):
    """Abstract repository for RSS/Atom feed configuration operations."""

    @abstractmethod
    async def save_feed(self, feed: FeedConfig) -> str:
        """
        Save or update a feed configuration.

        Args:
            feed: The feed configuration to save

        Returns:
            The ID of the saved feed
        """
        pass

    @abstractmethod
    async def get_feed(self, feed_id: str) -> Optional[FeedConfig]:
        """
        Retrieve a feed by its ID.

        Args:
            feed_id: The unique identifier of the feed

        Returns:
            The feed configuration if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_feed_by_token(self, token: str) -> Optional[FeedConfig]:
        """
        Retrieve a feed by its authentication token.

        Args:
            token: The feed authentication token

        Returns:
            The feed configuration if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_feeds_by_guild(self, guild_id: str) -> List[FeedConfig]:
        """
        Get all feeds for a specific guild.

        Args:
            guild_id: The unique identifier of the guild

        Returns:
            List of feed configurations for the guild
        """
        pass

    @abstractmethod
    async def delete_feed(self, feed_id: str) -> bool:
        """
        Delete a feed configuration.

        Args:
            feed_id: The unique identifier of the feed

        Returns:
            True if the feed was deleted, False otherwise
        """
        pass

    @abstractmethod
    async def update_access_stats(self, feed_id: str) -> None:
        """
        Update access statistics for a feed.

        Args:
            feed_id: The unique identifier of the feed
        """
        pass


class WebhookRepository(ABC):
    """Abstract repository for webhook data operations."""

    @abstractmethod
    async def save_webhook(self, webhook: Dict[str, Any]) -> str:
        """
        Save or update a webhook.

        Args:
            webhook: Webhook data dictionary

        Returns:
            The ID of the saved webhook
        """
        pass

    @abstractmethod
    async def get_webhook(self, webhook_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a webhook by its ID.

        Args:
            webhook_id: The unique identifier of the webhook

        Returns:
            The webhook data if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_webhooks_by_guild(self, guild_id: str) -> List[Dict[str, Any]]:
        """
        Get all webhooks for a specific guild.

        Args:
            guild_id: The unique identifier of the guild

        Returns:
            List of webhook data dictionaries
        """
        pass

    @abstractmethod
    async def delete_webhook(self, webhook_id: str) -> bool:
        """
        Delete a webhook.

        Args:
            webhook_id: The unique identifier of the webhook

        Returns:
            True if the webhook was deleted, False otherwise
        """
        pass

    @abstractmethod
    async def update_delivery_status(
        self,
        webhook_id: str,
        status: str,
        delivery_time: Optional[datetime] = None
    ) -> None:
        """
        Update delivery status for a webhook.

        Args:
            webhook_id: The unique identifier of the webhook
            status: The delivery status ('success' or 'failed')
            delivery_time: When the delivery occurred
        """
        pass


class ErrorRepository(ABC):
    """Abstract repository for error log operations."""

    @abstractmethod
    async def save_error(self, error: ErrorLog) -> str:
        """
        Save an error log entry.

        Args:
            error: The error log to save

        Returns:
            The ID of the saved error
        """
        pass

    @abstractmethod
    async def get_error(self, error_id: str) -> Optional[ErrorLog]:
        """
        Retrieve an error by its ID.

        Args:
            error_id: The unique identifier of the error

        Returns:
            The error log if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_errors_by_guild(
        self,
        guild_id: str,
        limit: int = 50,
        error_type: Optional[ErrorType] = None,
        severity: Optional[ErrorSeverity] = None,
        include_resolved: bool = False,
    ) -> List[ErrorLog]:
        """
        Get errors for a specific guild.

        Args:
            guild_id: The unique identifier of the guild
            limit: Maximum number of errors to return
            error_type: Filter by error type
            severity: Filter by severity
            include_resolved: Include resolved errors

        Returns:
            List of error logs
        """
        pass

    @abstractmethod
    async def get_recent_errors(
        self,
        limit: int = 100,
        error_type: Optional[ErrorType] = None,
        severity: Optional[ErrorSeverity] = None,
    ) -> List[ErrorLog]:
        """
        Get recent errors across all guilds.

        Args:
            limit: Maximum number of errors to return
            error_type: Filter by error type
            severity: Filter by severity

        Returns:
            List of recent error logs
        """
        pass

    @abstractmethod
    async def resolve_error(
        self,
        error_id: str,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Mark an error as resolved.

        Args:
            error_id: The unique identifier of the error
            notes: Resolution notes

        Returns:
            True if the error was resolved, False if not found
        """
        pass

    @abstractmethod
    async def delete_old_errors(self, days: int = 7) -> int:
        """
        Delete errors older than specified days.

        Args:
            days: Delete errors older than this many days

        Returns:
            Number of errors deleted
        """
        pass

    @abstractmethod
    async def get_error_counts(
        self,
        guild_id: Optional[str] = None,
        hours: int = 24,
    ) -> Dict[str, int]:
        """
        Get error counts grouped by type.

        Args:
            guild_id: Filter by guild (None = all guilds)
            hours: Time window in hours

        Returns:
            Dictionary mapping error types to counts
        """
        pass

    @abstractmethod
    async def bulk_resolve_by_type(
        self,
        guild_id: str,
        error_type: ErrorType,
        notes: Optional[str] = None,
    ) -> int:
        """
        Resolve all unresolved errors of a specific type for a guild.

        Args:
            guild_id: The guild to resolve errors for
            error_type: The type of errors to resolve
            notes: Optional resolution notes

        Returns:
            Number of errors resolved
        """
        pass


class IngestRepository(ABC):
    """Abstract repository for ingested message batch operations (ADR-002)."""

    @abstractmethod
    async def store_batch(
        self,
        batch_id: str,
        document: IngestDocument,
        processed_messages: List[ProcessedMessage],
    ) -> str:
        """
        Store an ingest batch with its processed messages.

        Args:
            batch_id: Unique identifier for the batch
            document: Original ingest document
            processed_messages: Converted ProcessedMessage objects

        Returns:
            The batch ID
        """
        pass

    @abstractmethod
    async def get_batch(self, batch_id: str) -> Optional[IngestBatch]:
        """
        Retrieve an ingest batch by ID.

        Args:
            batch_id: The batch identifier

        Returns:
            The batch if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_messages(
        self,
        source_type: str,
        channel_id: str,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[ProcessedMessage]:
        """
        Get processed messages for a channel.

        Args:
            source_type: Source type ('whatsapp', 'discord', etc.)
            channel_id: Channel/chat identifier
            time_from: Optional start time filter
            time_to: Optional end time filter
            limit: Maximum messages to return
            offset: Number of messages to skip

        Returns:
            List of ProcessedMessage objects
        """
        pass

    @abstractmethod
    async def list_channels(
        self,
        source_type: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List channels with ingested messages.

        Args:
            source_type: Source type to filter by
            limit: Maximum channels to return
            offset: Number of channels to skip

        Returns:
            List of channel info dictionaries
        """
        pass

    @abstractmethod
    async def count_channels(self, source_type: str) -> int:
        """
        Count channels with ingested messages.

        Args:
            source_type: Source type to filter by

        Returns:
            Number of channels
        """
        pass

    @abstractmethod
    async def get_channel_stats(
        self,
        source_type: str,
        channel_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific channel.

        Args:
            source_type: Source type
            channel_id: Channel identifier

        Returns:
            Channel statistics dictionary or None
        """
        pass

    @abstractmethod
    async def delete_batch(self, batch_id: str) -> bool:
        """
        Delete an ingest batch and its messages.

        Args:
            batch_id: The batch identifier

        Returns:
            True if deleted, False if not found
        """
        pass


class StoredSummaryRepository(ABC):
    """Abstract repository for stored summary operations (ADR-005)."""

    @abstractmethod
    async def save(self, summary: StoredSummary) -> str:
        """
        Save a stored summary to the database.

        Args:
            summary: The stored summary to save

        Returns:
            The ID of the saved summary
        """
        pass

    @abstractmethod
    async def get(self, summary_id: str) -> Optional[StoredSummary]:
        """
        Retrieve a stored summary by its ID.

        Args:
            summary_id: The unique identifier of the summary

        Returns:
            The stored summary if found, None otherwise
        """
        pass

    @abstractmethod
    async def find_by_guild(
        self,
        guild_id: str,
        limit: int = 20,
        offset: int = 0,
        pinned_only: bool = False,
        include_archived: bool = False,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,
    ) -> List[StoredSummary]:
        """
        Find stored summaries for a guild.

        Args:
            guild_id: The guild ID to search for
            limit: Maximum number of summaries to return
            offset: Number of summaries to skip
            pinned_only: Only return pinned summaries
            include_archived: Include archived summaries
            tags: Filter by tags (any match)
            source: ADR-008 - Filter by source type (realtime, archive, etc.)
                    Use "all" or None for no filtering

        Returns:
            List of matching stored summaries
        """
        pass

    @abstractmethod
    async def count_by_guild(
        self,
        guild_id: str,
        include_archived: bool = False,
    ) -> int:
        """
        Count stored summaries for a guild.

        Args:
            guild_id: The guild ID to count for
            include_archived: Include archived summaries

        Returns:
            Number of matching summaries
        """
        pass

    @abstractmethod
    async def update(self, summary: StoredSummary) -> bool:
        """
        Update a stored summary.

        Args:
            summary: The stored summary with updated fields

        Returns:
            True if updated, False if not found
        """
        pass

    @abstractmethod
    async def delete(self, summary_id: str) -> bool:
        """
        Delete a stored summary.

        Args:
            summary_id: The unique identifier of the summary

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def find_by_schedule(
        self,
        schedule_id: str,
        limit: int = 10,
    ) -> List[StoredSummary]:
        """
        Find stored summaries created by a specific schedule.

        Args:
            schedule_id: The schedule task ID
            limit: Maximum number of summaries to return

        Returns:
            List of stored summaries from the schedule
        """
        pass

    # ADR-020: Navigation and Search

    @abstractmethod
    async def get_navigation(
        self,
        summary_id: str,
        guild_id: str,
        source: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """
        Get previous/next summary IDs for navigation.

        Args:
            summary_id: Current summary ID
            guild_id: Guild to scope navigation within
            source: Optional source filter (archive, realtime, etc.)

        Returns:
            Dict with keys: previous_id, previous_date, next_id, next_date
        """
        pass

    @abstractmethod
    async def search(
        self,
        guild_id: str,
        query: str,
        fields: Optional[List[str]] = None,
        source: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Full-text search across summary content.

        Args:
            guild_id: Guild to search within
            query: Search query (supports FTS5 syntax)
            fields: Fields to search (summary_text, key_points, action_items, participants, technical_terms)
            source: Filter by source type
            date_from: Start date filter
            date_to: End date filter
            limit: Max results
            offset: Pagination offset

        Returns:
            Dict with keys: query, total, items (list of search results with highlights)
        """
        pass

    @abstractmethod
    async def search_by_participant(
        self,
        guild_id: str,
        user_id: Optional[str] = None,
        display_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Find summaries by participant.

        Args:
            guild_id: Guild to search within
            user_id: Discord user ID
            display_name: Partial name match
            date_from: Start date filter
            date_to: End date filter
            limit: Max results
            offset: Pagination offset

        Returns:
            Dict with participant info and matching summaries
        """
        pass


class SummaryJobRepository(ABC):
    """Abstract repository for summary job tracking (ADR-013)."""

    @abstractmethod
    async def save(self, job: "SummaryJob") -> str:
        """Save a job to the database."""
        pass

    @abstractmethod
    async def get(self, job_id: str) -> Optional["SummaryJob"]:
        """Get a job by ID."""
        pass

    @abstractmethod
    async def update(self, job: "SummaryJob") -> bool:
        """Update an existing job."""
        pass

    @abstractmethod
    async def find_by_guild(
        self,
        guild_id: str,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List["SummaryJob"]:
        """Find jobs for a guild with optional filters."""
        pass

    @abstractmethod
    async def find_active(self, guild_id: Optional[str] = None) -> List["SummaryJob"]:
        """Find all active (pending/running) jobs."""
        pass

    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        """Delete a job by ID."""
        pass

    @abstractmethod
    async def cleanup_old(self, days: int = 7) -> int:
        """Delete jobs older than specified days. Returns count deleted."""
        pass

    @abstractmethod
    async def mark_interrupted_jobs(self, reason: str = "server_restart") -> int:
        """
        Mark all RUNNING jobs as PAUSED due to server restart.

        ADR-013: Startup recovery - when the server restarts, any jobs that were
        RUNNING are marked as PAUSED so users can see they were interrupted.

        Args:
            reason: The pause reason to set

        Returns:
            Number of jobs that were marked as paused
        """
        pass


class PromptTemplateRepository(ABC):
    """Abstract repository for guild prompt templates (ADR-034)."""

    @abstractmethod
    async def save_template(self, template: GuildPromptTemplate) -> GuildPromptTemplate:
        """Save or update a prompt template."""
        pass

    @abstractmethod
    async def get_template(self, template_id: str) -> Optional[GuildPromptTemplate]:
        """Retrieve a template by its ID."""
        pass

    @abstractmethod
    async def get_templates_by_guild(self, guild_id: str) -> List[GuildPromptTemplate]:
        """Retrieve all templates for a guild."""
        pass

    @abstractmethod
    async def delete_template(self, template_id: str) -> bool:
        """Delete a template by its ID."""
        pass

    @abstractmethod
    async def get_template_usage(self, template_id: str) -> List[Dict[str, str]]:
        """Get schedules using this template.

        Returns:
            List of dicts with schedule_id and schedule_name
        """
        pass

    @abstractmethod
    async def get_usage_count(self, template_id: str) -> int:
        """Get count of schedules using this template."""
        pass

    @abstractmethod
    async def duplicate_template(
        self, template_id: str, new_name: str, user_id: str
    ) -> Optional[GuildPromptTemplate]:
        """Duplicate a template with a new name."""
        pass

    @abstractmethod
    async def template_name_exists(
        self, guild_id: str, name: str, exclude_id: Optional[str] = None
    ) -> bool:
        """Check if a template name already exists in a guild."""
        pass


class DatabaseConnection(ABC):
    """Abstract database connection interface."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish database connection."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close database connection."""
        pass

    @abstractmethod
    async def execute(self, query: str, params: Optional[tuple] = None) -> Any:
        """
        Execute a database query.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            Query result
        """
        pass

    @abstractmethod
    async def fetch_one(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch a single row from the database.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            Single row as a dictionary, or None if no results
        """
        pass

    @abstractmethod
    async def fetch_all(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Fetch all rows from the database.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            List of rows as dictionaries
        """
        pass

    @abstractmethod
    async def begin_transaction(self) -> 'Transaction':
        """
        Begin a new database transaction.

        Returns:
            Transaction context manager
        """
        pass


class Transaction(ABC):
    """Abstract database transaction interface."""

    @abstractmethod
    async def commit(self) -> None:
        """Commit the transaction."""
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback the transaction."""
        pass

    @abstractmethod
    async def __aenter__(self) -> 'Transaction':
        """Enter transaction context."""
        pass

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit transaction context."""
        pass
