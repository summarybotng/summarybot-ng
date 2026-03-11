"""
SQLite implementation of data repositories using aiosqlite.

This module provides full SQLite support with connection pooling,
transactions, and async database operations.
"""

import json
import logging
import aiosqlite
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager


# CS-002: StoredSummaryFilter dataclass to eliminate duplicated filter logic
@dataclass
class StoredSummaryFilter:
    """Filter parameters for stored summary queries.

    Used by find_by_guild and count_by_guild to avoid duplicating filter logic.
    """
    guild_id: str
    pinned_only: bool = False
    include_archived: bool = False
    tags: Optional[List[str]] = None
    source: Optional[str] = None  # ADR-008: Filter by source
    # ADR-017: Enhanced filtering
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    archive_period: Optional[str] = None
    channel_mode: Optional[str] = None  # "single" or "multi"
    has_grounding: Optional[bool] = None
    # ADR-018: Content-based filters
    has_key_points: Optional[bool] = None
    has_action_items: Optional[bool] = None
    has_participants: Optional[bool] = None
    min_message_count: Optional[int] = None
    max_message_count: Optional[int] = None
    # ADR-021: Content count filters
    min_key_points: Optional[int] = None
    max_key_points: Optional[int] = None
    min_action_items: Optional[int] = None
    max_action_items: Optional[int] = None
    min_participants: Optional[int] = None
    max_participants: Optional[int] = None
    # ADR-026: Platform filter
    platform: Optional[str] = None

logger = logging.getLogger(__name__)

from .base import (
    SummaryRepository,
    ConfigRepository,
    TaskRepository,
    FeedRepository,
    WebhookRepository,
    ErrorRepository,
    StoredSummaryRepository,
    SummaryJobRepository,
    IngestRepository,
    DatabaseConnection,
    Transaction,
    SearchCriteria
)
from ..models.ingest import IngestDocument, IngestBatch, ChannelType
from ..models.message import ProcessedMessage, SourceType, MessageType, AttachmentInfo, AttachmentType
from ..models.summary import (
    SummaryResult,
    SummaryOptions,
    ActionItem,
    TechnicalTerm,
    Participant,
    SummarizationContext,
    Priority,
    SummaryLength,
    SummaryWarning
)
from ..models.summary_job import SummaryJob, JobType, JobStatus
from ..models.task import (
    ScheduledTask,
    TaskResult,
    Destination,
    TaskStatus,
    ScheduleType,
    DestinationType,
    SummaryScope
)
from ..models.feed import FeedConfig, FeedType
from ..models.error_log import ErrorLog, ErrorType, ErrorSeverity
from ..models.stored_summary import StoredSummary, PushDelivery, SummarySource
from ..config.settings import GuildConfig, PermissionSettings


class SQLiteTransaction(Transaction):
    """SQLite transaction implementation."""

    def __init__(self, connection: aiosqlite.Connection):
        self.connection = connection
        self._active = False

    async def commit(self) -> None:
        """Commit the transaction."""
        if self._active:
            await self.connection.commit()
            self._active = False

    async def rollback(self) -> None:
        """Rollback the transaction."""
        if self._active:
            await self.connection.rollback()
            self._active = False

    async def __aenter__(self) -> 'SQLiteTransaction':
        """Enter transaction context."""
        await self.connection.execute("BEGIN")
        self._active = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit transaction context."""
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()


# Module-level write lock - shared across all SQLiteConnection instances
# to prevent concurrent writes from causing database lock errors
_global_write_lock: Optional[asyncio.Lock] = None


def _get_global_write_lock() -> asyncio.Lock:
    """Get the global write lock, creating it if necessary."""
    global _global_write_lock
    if _global_write_lock is None:
        _global_write_lock = asyncio.Lock()
    return _global_write_lock


class SQLiteConnection(DatabaseConnection):
    """SQLite database connection with single-connection mode for safety.

    Note: Pool size of 1 is used to prevent database locking issues.
    aiosqlite uses worker threads per connection, and multiple connections
    can cause database lock errors even with asyncio locks.
    """

    def __init__(self, db_path: str, pool_size: int = 1):
        self.db_path = db_path
        self.pool_size = pool_size
        self._connections: List[aiosqlite.Connection] = []
        self._available: asyncio.Queue = asyncio.Queue(maxsize=pool_size)
        self._lock = asyncio.Lock()
        self._initialized = False

    async def connect(self) -> None:
        """Establish database connection pool."""
        async with self._lock:
            if self._initialized:
                return

            # Ensure database directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            # Create connection pool
            for _ in range(self.pool_size):
                conn = await aiosqlite.connect(self.db_path)
                conn.row_factory = aiosqlite.Row
                # Enable WAL mode for better concurrency
                await conn.execute("PRAGMA journal_mode=WAL")
                # Enable foreign keys
                await conn.execute("PRAGMA foreign_keys=ON")
                # Set busy timeout to wait for locks (5 seconds)
                await conn.execute("PRAGMA busy_timeout=5000")
                self._connections.append(conn)
                await self._available.put(conn)

            self._initialized = True

    async def disconnect(self) -> None:
        """Close all database connections."""
        async with self._lock:
            if not self._initialized:
                return

            # Close all connections
            for conn in self._connections:
                await conn.close()

            self._connections.clear()
            self._initialized = False

    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection from the pool."""
        if not self._initialized:
            await self.connect()

        conn = await self._available.get()
        try:
            yield conn
        finally:
            await self._available.put(conn)

    async def execute(self, query: str, params: Optional[tuple] = None, max_retries: int = 5) -> Any:
        """Execute a database query with retry for lock errors.

        Uses a write lock to serialize write operations (INSERT, UPDATE, DELETE)
        to prevent SQLite locking issues with concurrent writes.

        Args:
            query: SQL query to execute
            params: Query parameters
            max_retries: Maximum retry attempts for transient errors
        """
        # Check if this is a write operation
        query_upper = query.strip().upper()
        is_write = query_upper.startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE', 'DROP', 'ALTER'))

        last_error = None
        for attempt in range(max_retries):
            try:
                if is_write:
                    # Serialize writes to prevent concurrent write conflicts
                    # Use global lock to coordinate across all SQLiteConnection instances
                    async with _get_global_write_lock():
                        async with self._get_connection() as conn:
                            cursor = await conn.execute(query, params or ())
                            await conn.commit()
                            return cursor
                else:
                    # Reads can proceed concurrently
                    async with self._get_connection() as conn:
                        cursor = await conn.execute(query, params or ())
                        await conn.commit()
                        return cursor
            except Exception as e:
                error_str = str(e).lower()
                if 'locked' in error_str or 'busy' in error_str:
                    last_error = e
                    # Longer waits: 0.5s, 1s, 2s, 4s, 8s = 15.5s total
                    wait_time = 0.5 * (2 ** attempt)
                    logger.warning(f"Database locked, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        # All retries failed
        raise last_error

    async def fetch_one(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """Fetch a single row from the database."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params or ())
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def fetch_all(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Fetch all rows from the database."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params or ())
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def begin_transaction(self) -> Transaction:
        """Begin a new database transaction."""
        conn = await self._available.get()
        return SQLiteTransaction(conn)


class SQLiteSummaryRepository(SummaryRepository):
    """SQLite implementation of summary repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_summary(self, summary: SummaryResult) -> str:
        """Save a summary to the database."""
        query = """
        INSERT OR REPLACE INTO summaries (
            id, channel_id, guild_id, start_time, end_time,
            message_count, summary_text, key_points, action_items,
            technical_terms, participants, metadata, created_at, context,
            prompt_system, prompt_user, prompt_template_id, source_content, warnings
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Serialize warnings
        warnings_data = []
        if hasattr(summary, 'warnings') and summary.warnings:
            warnings_data = [w.to_dict() if hasattr(w, 'to_dict') else {'code': w.code, 'message': w.message, 'details': getattr(w, 'details', {})} for w in summary.warnings]

        params = (
            summary.id,
            summary.channel_id,
            summary.guild_id,
            summary.start_time.isoformat(),
            summary.end_time.isoformat(),
            summary.message_count,
            summary.summary_text,
            json.dumps(summary.key_points),
            json.dumps([item.to_dict() for item in summary.action_items]),
            json.dumps([term.to_dict() for term in summary.technical_terms]),
            json.dumps([p.to_dict() for p in summary.participants]),
            json.dumps(summary.metadata),
            summary.created_at.isoformat(),
            json.dumps(summary.context.to_dict() if summary.context else {}),
            summary.prompt_system,
            summary.prompt_user,
            summary.prompt_template_id,
            summary.source_content,
            json.dumps(warnings_data),
        )

        await self.connection.execute(query, params)
        return summary.id

    async def get_summary(self, summary_id: str) -> Optional[SummaryResult]:
        """Retrieve a summary by its ID."""
        query = "SELECT * FROM summaries WHERE id = ?"
        row = await self.connection.fetch_one(query, (summary_id,))

        if not row:
            return None

        return self._row_to_summary(row)

    async def find_summaries(self, criteria: SearchCriteria) -> List[SummaryResult]:
        """Find summaries matching the given criteria."""
        conditions = []
        params = []

        if criteria.guild_id:
            conditions.append("guild_id = ?")
            params.append(criteria.guild_id)

        if criteria.channel_id:
            conditions.append("channel_id = ?")
            params.append(criteria.channel_id)

        if criteria.start_time:
            conditions.append("created_at >= ?")
            params.append(criteria.start_time.isoformat())

        if criteria.end_time:
            conditions.append("created_at <= ?")
            params.append(criteria.end_time.isoformat())

        if criteria.perspective:
            conditions.append("json_extract(metadata, '$.perspective') = ?")
            params.append(criteria.perspective)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
        SELECT * FROM summaries
        {where_clause}
        ORDER BY {criteria.order_by} {criteria.order_direction}
        LIMIT ? OFFSET ?
        """

        params.extend([criteria.limit, criteria.offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_summary(row) for row in rows]

    async def delete_summary(self, summary_id: str) -> bool:
        """Delete a summary from the database."""
        query = "DELETE FROM summaries WHERE id = ?"
        cursor = await self.connection.execute(query, (summary_id,))
        return cursor.rowcount > 0

    async def count_summaries(self, criteria: SearchCriteria) -> int:
        """Count summaries matching the given criteria."""
        conditions = []
        params = []

        if criteria.guild_id:
            conditions.append("guild_id = ?")
            params.append(criteria.guild_id)

        if criteria.channel_id:
            conditions.append("channel_id = ?")
            params.append(criteria.channel_id)

        if criteria.start_time:
            conditions.append("created_at >= ?")
            params.append(criteria.start_time.isoformat())

        if criteria.end_time:
            conditions.append("created_at <= ?")
            params.append(criteria.end_time.isoformat())

        if criteria.perspective:
            conditions.append("json_extract(metadata, '$.perspective') = ?")
            params.append(criteria.perspective)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"SELECT COUNT(*) as count FROM summaries {where_clause}"

        row = await self.connection.fetch_one(query, tuple(params))
        return row['count'] if row else 0

    async def get_summaries_by_channel(
        self,
        channel_id: str,
        limit: int = 10
    ) -> List[SummaryResult]:
        """Get recent summaries for a specific channel."""
        criteria = SearchCriteria(
            channel_id=channel_id,
            limit=limit,
            order_by="created_at",
            order_direction="DESC"
        )
        return await self.find_summaries(criteria)

    def _row_to_summary(self, row: Dict[str, Any]) -> SummaryResult:
        """Convert database row to SummaryResult object."""
        context_data = json.loads(row['context'])
        context = SummarizationContext(**context_data) if context_data else None

        # Load warnings if present
        warnings_data = json.loads(row.get('warnings') or '[]')
        warnings = [SummaryWarning(**w) for w in warnings_data]

        return SummaryResult(
            id=row['id'],
            channel_id=row['channel_id'],
            guild_id=row['guild_id'],
            start_time=datetime.fromisoformat(row['start_time']),
            end_time=datetime.fromisoformat(row['end_time']),
            message_count=row['message_count'],
            key_points=json.loads(row['key_points']),
            action_items=[ActionItem(**item) for item in json.loads(row['action_items'])],
            technical_terms=[TechnicalTerm(**term) for term in json.loads(row['technical_terms'])],
            participants=[Participant(**p) for p in json.loads(row['participants'])],
            summary_text=row['summary_text'],
            metadata=json.loads(row['metadata']),
            created_at=datetime.fromisoformat(row['created_at']),
            context=context,
            prompt_system=row.get('prompt_system'),
            prompt_user=row.get('prompt_user'),
            prompt_template_id=row.get('prompt_template_id'),
            source_content=row.get('source_content'),
            warnings=warnings,
        )


class SQLiteConfigRepository(ConfigRepository):
    """SQLite implementation of configuration repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_guild_config(self, config: GuildConfig) -> None:
        """Save or update a guild configuration."""
        query = """
        INSERT OR REPLACE INTO guild_configs (
            guild_id, enabled_channels, excluded_channels,
            default_summary_options, permission_settings,
            webhook_enabled, webhook_secret
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            config.guild_id,
            json.dumps(config.enabled_channels),
            json.dumps(config.excluded_channels),
            json.dumps(config.default_summary_options.to_dict()),
            json.dumps(config.permission_settings.to_dict()),
            config.webhook_enabled,
            config.webhook_secret
        )

        await self.connection.execute(query, params)

    async def get_guild_config(self, guild_id: str) -> Optional[GuildConfig]:
        """Retrieve configuration for a specific guild."""
        query = "SELECT * FROM guild_configs WHERE guild_id = ?"
        row = await self.connection.fetch_one(query, (guild_id,))

        if not row:
            return None

        return self._row_to_guild_config(row)

    async def delete_guild_config(self, guild_id: str) -> bool:
        """Delete a guild configuration."""
        query = "DELETE FROM guild_configs WHERE guild_id = ?"
        cursor = await self.connection.execute(query, (guild_id,))
        return cursor.rowcount > 0

    async def get_all_guild_configs(self) -> List[GuildConfig]:
        """Retrieve all guild configurations."""
        query = "SELECT * FROM guild_configs"
        rows = await self.connection.fetch_all(query)
        return [self._row_to_guild_config(row) for row in rows]

    def _row_to_guild_config(self, row: Dict[str, Any]) -> GuildConfig:
        """Convert database row to GuildConfig object."""
        options_data = json.loads(row['default_summary_options'])
        permission_data = json.loads(row['permission_settings'])

        # Convert summary options
        options_data['summary_length'] = SummaryLength(options_data['summary_length'])

        # Handle legacy field name: claude_model -> summarization_model
        if 'claude_model' in options_data:
            options_data['summarization_model'] = options_data.pop('claude_model')

        summary_options = SummaryOptions(**options_data)

        # Convert permission settings
        permission_settings = PermissionSettings(**permission_data)

        return GuildConfig(
            guild_id=row['guild_id'],
            enabled_channels=json.loads(row['enabled_channels']),
            excluded_channels=json.loads(row['excluded_channels']),
            default_summary_options=summary_options,
            permission_settings=permission_settings,
            webhook_enabled=bool(row['webhook_enabled']),
            webhook_secret=row['webhook_secret']
        )


class SQLiteTaskRepository(TaskRepository):
    """SQLite implementation of task repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_task(self, task: ScheduledTask) -> str:
        """Save or update a scheduled task."""
        # Get scope value safely
        scope_value = None
        if hasattr(task, 'scope') and task.scope is not None:
            scope_value = task.scope.value if hasattr(task.scope, 'value') else str(task.scope)

        query = """
        INSERT OR REPLACE INTO scheduled_tasks (
            id, name, channel_id, guild_id, schedule_type,
            schedule_time, schedule_days, cron_expression,
            destinations, summary_options, is_active,
            created_at, created_by, last_run, next_run,
            run_count, failure_count, max_failures, retry_delay_minutes,
            scope, channel_ids, category_id, excluded_channel_ids,
            resolve_category_at_runtime, timezone
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            task.id,
            task.name,
            task.channel_id,
            task.guild_id,
            task.schedule_type.value,
            task.schedule_time,
            json.dumps(task.schedule_days),
            task.cron_expression,
            json.dumps([dest.to_dict() for dest in task.destinations]),
            json.dumps(task.summary_options.to_dict()),
            task.is_active,
            task.created_at.isoformat(),
            task.created_by,
            task.last_run.isoformat() if task.last_run else None,
            task.next_run.isoformat() if task.next_run else None,
            task.run_count,
            task.failure_count,
            task.max_failures,
            task.retry_delay_minutes,
            scope_value,
            json.dumps(getattr(task, 'channel_ids', [])),
            getattr(task, 'category_id', None),
            json.dumps(getattr(task, 'excluded_channel_ids', [])),
            1 if getattr(task, 'resolve_category_at_runtime', False) else 0,
            getattr(task, 'timezone', 'UTC')
        )

        await self.connection.execute(query, params)
        return task.id

    async def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Retrieve a task by its ID."""
        query = "SELECT * FROM scheduled_tasks WHERE id = ?"
        row = await self.connection.fetch_one(query, (task_id,))

        if not row:
            return None

        return self._row_to_task(row)

    async def get_tasks_by_guild(self, guild_id: str) -> List[ScheduledTask]:
        """Get all tasks for a specific guild."""
        query = "SELECT * FROM scheduled_tasks WHERE guild_id = ? ORDER BY created_at DESC"
        rows = await self.connection.fetch_all(query, (guild_id,))
        return [self._row_to_task(row) for row in rows]

    async def get_active_tasks(self) -> List[ScheduledTask]:
        """Get all active tasks across all guilds."""
        query = "SELECT * FROM scheduled_tasks WHERE is_active = 1 ORDER BY next_run ASC"
        rows = await self.connection.fetch_all(query)
        return [self._row_to_task(row) for row in rows]

    async def delete_task(self, task_id: str) -> bool:
        """Delete a scheduled task."""
        query = "DELETE FROM scheduled_tasks WHERE id = ?"
        cursor = await self.connection.execute(query, (task_id,))
        return cursor.rowcount > 0

    async def save_task_result(self, result: TaskResult) -> str:
        """Save a task execution result."""
        query = """
        INSERT INTO task_results (
            task_id, execution_id, status, started_at, completed_at,
            summary_id, error_message, error_details, delivery_results,
            execution_time_seconds
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            result.task_id,
            result.execution_id,
            result.status.value,
            result.started_at.isoformat(),
            result.completed_at.isoformat() if result.completed_at else None,
            result.summary_id,
            result.error_message,
            json.dumps(result.error_details) if result.error_details else None,
            json.dumps(result.delivery_results),
            result.execution_time_seconds
        )

        await self.connection.execute(query, params)
        return result.execution_id

    async def get_task_results(
        self,
        task_id: str,
        limit: int = 10
    ) -> List[TaskResult]:
        """Get execution results for a specific task."""
        query = """
        SELECT * FROM task_results
        WHERE task_id = ?
        ORDER BY started_at DESC
        LIMIT ?
        """
        rows = await self.connection.fetch_all(query, (task_id, limit))
        return [self._row_to_task_result(row) for row in rows]

    def _row_to_task(self, row: Dict[str, Any]) -> ScheduledTask:
        """Convert database row to ScheduledTask object."""
        destinations_data = json.loads(row['destinations'])
        destinations = []
        for dest in destinations_data:
            # Convert type string to enum (database stores string values)
            if isinstance(dest.get('type'), str):
                dest['type'] = DestinationType(dest['type'])
            destinations.append(Destination(**dest))

        options_data = json.loads(row['summary_options'])
        options_data['summary_length'] = SummaryLength(options_data['summary_length'])
        summary_options = SummaryOptions(**options_data)

        # Parse scope (ADR-011)
        scope_str = row.get('scope')
        scope = None
        if scope_str:
            try:
                scope = SummaryScope(scope_str)
            except (ValueError, KeyError):
                scope = SummaryScope.CHANNEL

        # Parse channel_ids and excluded_channel_ids
        channel_ids_str = row.get('channel_ids', '[]')
        channel_ids = json.loads(channel_ids_str) if channel_ids_str else []

        excluded_str = row.get('excluded_channel_ids', '[]')
        excluded_channel_ids = json.loads(excluded_str) if excluded_str else []

        return ScheduledTask(
            id=row['id'],
            name=row['name'],
            channel_id=row['channel_id'],
            channel_ids=channel_ids,
            category_id=row.get('category_id'),
            excluded_channel_ids=excluded_channel_ids,
            scope=scope,
            resolve_category_at_runtime=bool(row.get('resolve_category_at_runtime', 0)),
            guild_id=row['guild_id'],
            schedule_type=ScheduleType(row['schedule_type']),
            schedule_time=row['schedule_time'],
            schedule_days=json.loads(row['schedule_days']),
            cron_expression=row['cron_expression'],
            destinations=destinations,
            summary_options=summary_options,
            is_active=bool(row['is_active']),
            timezone=row.get('timezone', 'UTC'),
            created_at=datetime.fromisoformat(row['created_at']),
            created_by=row['created_by'],
            last_run=datetime.fromisoformat(row['last_run']) if row['last_run'] else None,
            next_run=datetime.fromisoformat(row['next_run']) if row['next_run'] else None,
            run_count=row['run_count'],
            failure_count=row['failure_count'],
            max_failures=row['max_failures'],
            retry_delay_minutes=row['retry_delay_minutes']
        )

    def _row_to_task_result(self, row: Dict[str, Any]) -> TaskResult:
        """Convert database row to TaskResult object."""
        return TaskResult(
            task_id=row['task_id'],
            execution_id=row['execution_id'],
            status=TaskStatus(row['status']),
            started_at=datetime.fromisoformat(row['started_at']),
            completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
            summary_id=row['summary_id'],
            error_message=row['error_message'],
            error_details=json.loads(row['error_details']) if row['error_details'] else None,
            delivery_results=json.loads(row['delivery_results']),
            execution_time_seconds=row['execution_time_seconds']
        )


class SQLiteFeedRepository(FeedRepository):
    """SQLite implementation of feed repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_feed(self, feed: FeedConfig) -> str:
        """Save or update a feed configuration."""
        query = """
        INSERT OR REPLACE INTO feed_configs (
            id, guild_id, channel_id, feed_type, is_public, token,
            title, description, max_items, include_full_content,
            created_at, created_by, last_accessed, access_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            feed.id,
            feed.guild_id,
            feed.channel_id,
            feed.feed_type.value if isinstance(feed.feed_type, FeedType) else feed.feed_type,
            1 if feed.is_public else 0,
            feed.token,
            feed.title,
            feed.description,
            feed.max_items,
            1 if feed.include_full_content else 0,
            feed.created_at.isoformat(),
            feed.created_by,
            feed.last_accessed.isoformat() if feed.last_accessed else None,
            feed.access_count
        )

        await self.connection.execute(query, params)
        return feed.id

    async def get_feed(self, feed_id: str) -> Optional[FeedConfig]:
        """Retrieve a feed by its ID."""
        query = "SELECT * FROM feed_configs WHERE id = ?"
        row = await self.connection.fetch_one(query, (feed_id,))

        if not row:
            return None

        return self._row_to_feed(row)

    async def get_feed_by_token(self, token: str) -> Optional[FeedConfig]:
        """Retrieve a feed by its authentication token."""
        query = "SELECT * FROM feed_configs WHERE token = ?"
        row = await self.connection.fetch_one(query, (token,))

        if not row:
            return None

        return self._row_to_feed(row)

    async def get_feeds_by_guild(self, guild_id: str) -> List[FeedConfig]:
        """Get all feeds for a specific guild."""
        query = """
        SELECT * FROM feed_configs
        WHERE guild_id = ?
        ORDER BY created_at DESC
        """
        rows = await self.connection.fetch_all(query, (guild_id,))
        return [self._row_to_feed(row) for row in rows]

    async def delete_feed(self, feed_id: str) -> bool:
        """Delete a feed configuration."""
        query = "DELETE FROM feed_configs WHERE id = ?"
        cursor = await self.connection.execute(query, (feed_id,))
        return cursor.rowcount > 0

    async def update_access_stats(self, feed_id: str) -> None:
        """Update access statistics for a feed."""
        query = """
        UPDATE feed_configs
        SET last_accessed = ?, access_count = access_count + 1
        WHERE id = ?
        """
        await self.connection.execute(query, (datetime.utcnow().isoformat(), feed_id))

    def _row_to_feed(self, row: Dict[str, Any]) -> FeedConfig:
        """Convert database row to FeedConfig object."""
        return FeedConfig(
            id=row['id'],
            guild_id=row['guild_id'],
            channel_id=row['channel_id'],
            feed_type=FeedType(row['feed_type']),
            is_public=bool(row['is_public']),
            token=row['token'],
            title=row['title'],
            description=row['description'],
            max_items=row['max_items'],
            include_full_content=bool(row['include_full_content']),
            created_at=datetime.fromisoformat(row['created_at']),
            created_by=row['created_by'],
            last_accessed=datetime.fromisoformat(row['last_accessed']) if row['last_accessed'] else None,
            access_count=row['access_count']
        )


class SQLiteWebhookRepository(WebhookRepository):
    """SQLite implementation of webhook repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_webhook(self, webhook: Dict[str, Any]) -> str:
        """Save or update a webhook."""
        query = """
        INSERT OR REPLACE INTO webhooks (
            id, guild_id, name, url, type, headers, enabled,
            last_delivery, last_status, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            webhook['id'],
            webhook['guild_id'],
            webhook['name'],
            webhook['url'],
            webhook.get('type', 'generic'),
            json.dumps(webhook.get('headers', {})),
            1 if webhook.get('enabled', True) else 0,
            webhook.get('last_delivery').isoformat() if webhook.get('last_delivery') else None,
            webhook.get('last_status'),
            webhook['created_by'],
            webhook['created_at'].isoformat() if isinstance(webhook['created_at'], datetime) else webhook['created_at'],
        )

        await self.connection.execute(query, params)
        return webhook['id']

    async def get_webhook(self, webhook_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a webhook by its ID."""
        query = "SELECT * FROM webhooks WHERE id = ?"
        row = await self.connection.fetch_one(query, (webhook_id,))

        if not row:
            return None

        return self._row_to_webhook(row)

    async def get_webhooks_by_guild(self, guild_id: str) -> List[Dict[str, Any]]:
        """Get all webhooks for a specific guild."""
        query = """
        SELECT * FROM webhooks
        WHERE guild_id = ?
        ORDER BY created_at DESC
        """
        rows = await self.connection.fetch_all(query, (guild_id,))
        return [self._row_to_webhook(row) for row in rows]

    async def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook."""
        query = "DELETE FROM webhooks WHERE id = ?"
        cursor = await self.connection.execute(query, (webhook_id,))
        return cursor.rowcount > 0

    async def update_delivery_status(
        self,
        webhook_id: str,
        status: str,
        delivery_time: Optional[datetime] = None
    ) -> None:
        """Update delivery status for a webhook."""
        delivery_time = delivery_time or datetime.utcnow()
        query = """
        UPDATE webhooks
        SET last_delivery = ?, last_status = ?
        WHERE id = ?
        """
        await self.connection.execute(query, (delivery_time.isoformat(), status, webhook_id))

    def _row_to_webhook(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database row to webhook dictionary."""
        return {
            'id': row['id'],
            'guild_id': row['guild_id'],
            'name': row['name'],
            'url': row['url'],
            'type': row['type'],
            'headers': json.loads(row['headers']),
            'enabled': bool(row['enabled']),
            'last_delivery': datetime.fromisoformat(row['last_delivery']) if row['last_delivery'] else None,
            'last_status': row['last_status'],
            'created_by': row['created_by'],
            'created_at': datetime.fromisoformat(row['created_at']),
        }


class SQLiteErrorRepository(ErrorRepository):
    """SQLite implementation of error log repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_error(self, error: ErrorLog) -> str:
        """Save an error log entry."""
        query = """
        INSERT OR REPLACE INTO error_logs (
            id, guild_id, channel_id, error_type, severity, error_code,
            message, details, operation, user_id, stack_trace,
            created_at, resolved_at, resolution_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            error.id,
            error.guild_id,
            error.channel_id,
            error.error_type.value if isinstance(error.error_type, ErrorType) else error.error_type,
            error.severity.value if isinstance(error.severity, ErrorSeverity) else error.severity,
            error.error_code,
            error.message,
            json.dumps(error.details),
            error.operation,
            error.user_id,
            error.stack_trace,
            error.created_at.isoformat(),
            error.resolved_at.isoformat() if error.resolved_at else None,
            error.resolution_notes,
        )

        await self.connection.execute(query, params)
        return error.id

    async def get_error(self, error_id: str) -> Optional[ErrorLog]:
        """Retrieve an error by its ID."""
        query = "SELECT * FROM error_logs WHERE id = ?"
        row = await self.connection.fetch_one(query, (error_id,))

        if not row:
            return None

        return self._row_to_error(row)

    async def get_errors_by_guild(
        self,
        guild_id: str,
        limit: int = 50,
        error_type: Optional[ErrorType] = None,
        severity: Optional[ErrorSeverity] = None,
        include_resolved: bool = False,
    ) -> List[ErrorLog]:
        """Get errors for a specific guild."""
        query = "SELECT * FROM error_logs WHERE guild_id = ?"
        params = [guild_id]

        if error_type:
            query += " AND error_type = ?"
            params.append(error_type.value if isinstance(error_type, ErrorType) else error_type)

        if severity:
            query += " AND severity = ?"
            params.append(severity.value if isinstance(severity, ErrorSeverity) else severity)

        if not include_resolved:
            query += " AND resolved_at IS NULL"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_error(row) for row in rows]

    async def get_recent_errors(
        self,
        limit: int = 100,
        error_type: Optional[ErrorType] = None,
        severity: Optional[ErrorSeverity] = None,
    ) -> List[ErrorLog]:
        """Get recent errors across all guilds."""
        query = "SELECT * FROM error_logs WHERE 1=1"
        params = []

        if error_type:
            query += " AND error_type = ?"
            params.append(error_type.value if isinstance(error_type, ErrorType) else error_type)

        if severity:
            query += " AND severity = ?"
            params.append(severity.value if isinstance(severity, ErrorSeverity) else severity)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_error(row) for row in rows]

    async def resolve_error(
        self,
        error_id: str,
        notes: Optional[str] = None,
    ) -> bool:
        """Mark an error as resolved."""
        query = """
        UPDATE error_logs
        SET resolved_at = ?, resolution_notes = ?
        WHERE id = ?
        """
        cursor = await self.connection.execute(
            query,
            (datetime.utcnow().isoformat(), notes, error_id)
        )
        return cursor.rowcount > 0

    async def delete_old_errors(self, days: int = 7) -> int:
        """Delete errors older than specified days."""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        query = "DELETE FROM error_logs WHERE created_at < ?"
        cursor = await self.connection.execute(query, (cutoff,))
        return cursor.rowcount

    async def get_error_counts(
        self,
        guild_id: Optional[str] = None,
        hours: int = 24,
    ) -> Dict[str, int]:
        """Get error counts grouped by type."""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        if guild_id:
            query = """
            SELECT error_type, COUNT(*) as count
            FROM error_logs
            WHERE guild_id = ? AND created_at >= ?
            GROUP BY error_type
            """
            rows = await self.connection.fetch_all(query, (guild_id, cutoff))
        else:
            query = """
            SELECT error_type, COUNT(*) as count
            FROM error_logs
            WHERE created_at >= ?
            GROUP BY error_type
            """
            rows = await self.connection.fetch_all(query, (cutoff,))

        return {row['error_type']: row['count'] for row in rows}

    async def bulk_resolve_by_type(
        self,
        guild_id: str,
        error_type: ErrorType,
        notes: Optional[str] = None,
    ) -> int:
        """Resolve all unresolved errors of a specific type for a guild."""
        query = """
        UPDATE error_logs
        SET resolved_at = ?, resolution_notes = ?
        WHERE guild_id = ? AND error_type = ? AND resolved_at IS NULL
        """
        error_type_value = error_type.value if isinstance(error_type, ErrorType) else error_type
        cursor = await self.connection.execute(
            query,
            (datetime.utcnow().isoformat(), notes, guild_id, error_type_value)
        )
        return cursor.rowcount

    def _row_to_error(self, row: Dict[str, Any]) -> ErrorLog:
        """Convert database row to ErrorLog object."""
        return ErrorLog(
            id=row['id'],
            guild_id=row['guild_id'],
            channel_id=row['channel_id'],
            error_type=ErrorType(row['error_type']),
            severity=ErrorSeverity(row['severity']),
            error_code=row['error_code'],
            message=row['message'],
            details=json.loads(row['details']) if row['details'] else {},
            operation=row['operation'],
            user_id=row['user_id'],
            stack_trace=row['stack_trace'],
            created_at=datetime.fromisoformat(row['created_at']),
            resolved_at=datetime.fromisoformat(row['resolved_at']) if row['resolved_at'] else None,
            resolution_notes=row['resolution_notes'],
        )


class SQLiteStoredSummaryRepository(StoredSummaryRepository):
    """SQLite implementation of stored summary repository (ADR-005)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save(self, summary: StoredSummary) -> str:
        """Save a stored summary to the database."""
        # ADR-016: Validate regeneration capability and log warnings
        regen_status = summary.validate_regeneration()
        if not regen_status["can_regenerate"]:
            logger.warning(
                f"Storing summary {summary.id} without regeneration capability: "
                f"{', '.join(regen_status['issues'])}"
            )
        elif regen_status["issues"]:
            logger.info(
                f"Summary {summary.id} can regenerate via {regen_status['method']}, "
                f"but has issues: {', '.join(regen_status['issues'])}"
            )

        # ADR-017: Extract message_count from summary_result for sortable column
        message_count = 0
        participant_count = 0
        if summary.summary_result:
            message_count = summary.summary_result.message_count or 0
            participant_count = len(summary.summary_result.participants) if summary.summary_result.participants else 0

        query = """
        INSERT OR REPLACE INTO stored_summaries (
            id, guild_id, source_channel_ids, schedule_id,
            summary_json, created_at, viewed_at, pushed_at,
            push_deliveries, title, is_pinned, is_archived, tags,
            source, archive_period, archive_granularity, archive_source_key,
            message_count, participant_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            summary.id,
            summary.guild_id,
            json.dumps(summary.source_channel_ids),
            summary.schedule_id,
            json.dumps(summary.summary_result.to_dict() if summary.summary_result else {}),
            summary.created_at.isoformat(),
            summary.viewed_at.isoformat() if summary.viewed_at else None,
            summary.pushed_at.isoformat() if summary.pushed_at else None,
            json.dumps([d.to_dict() for d in summary.push_deliveries]),
            summary.title,
            summary.is_pinned,
            summary.is_archived,
            json.dumps(summary.tags),
            # ADR-008: Source tracking
            summary.source.value,
            summary.archive_period,
            summary.archive_granularity,
            summary.archive_source_key,
            # ADR-017: Sortable columns
            message_count,
            participant_count,
        )

        await self.connection.execute(query, params)

        # ADR-020: Populate FTS table for search
        await self._update_fts(summary)

        return summary.id

    async def _update_fts(self, summary: StoredSummary) -> None:
        """Update FTS index for a summary (ADR-020)."""
        try:
            # Delete existing FTS entry
            await self.connection.execute(
                "DELETE FROM summary_fts WHERE summary_id = ?",
                (summary.id,)
            )

            # Extract searchable content
            sr = summary.summary_result
            if not sr:
                return

            summary_text = sr.summary_text or ""
            key_points = " ".join(sr.key_points) if sr.key_points else ""
            action_items = " ".join(
                item.description for item in sr.action_items
            ) if sr.action_items else ""
            participants = " ".join(
                f"{p.display_name} {p.user_id}" for p in sr.participants
            ) if sr.participants else ""
            technical_terms = " ".join(
                term.term for term in sr.technical_terms
            ) if sr.technical_terms else ""

            # Insert into FTS
            await self.connection.execute(
                """INSERT INTO summary_fts
                   (summary_id, guild_id, summary_text, key_points, action_items, participants, technical_terms)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (summary.id, summary.guild_id, summary_text, key_points, action_items, participants, technical_terms)
            )
        except Exception as e:
            # FTS is optional - don't fail the save if FTS update fails
            logger.warning(f"Failed to update FTS for summary {summary.id}: {e}")

    async def get(self, summary_id: str) -> Optional[StoredSummary]:
        """Retrieve a stored summary by its ID."""
        query = "SELECT * FROM stored_summaries WHERE id = ?"
        row = await self.connection.fetch_one(query, (summary_id,))

        if not row:
            return None

        return self._row_to_stored_summary(row)

    def _build_filter_clause(self, filter: StoredSummaryFilter) -> Tuple[str, List[Any]]:
        """Build WHERE clause and params from filter.

        CS-002: Shared filter logic for find_by_guild and count_by_guild.

        Args:
            filter: StoredSummaryFilter with all filter parameters

        Returns:
            Tuple of (where_clause, params_list)
        """
        conditions = ["guild_id = ?"]
        params: List[Any] = [filter.guild_id]

        if filter.pinned_only:
            conditions.append("is_pinned = 1")

        if not filter.include_archived:
            conditions.append("is_archived = 0")

        # ADR-008: Source filtering
        if filter.source and filter.source != "all":
            conditions.append("source = ?")
            params.append(filter.source)

        # ADR-017: Date range filtering
        if filter.created_after:
            conditions.append("created_at >= ?")
            params.append(filter.created_after.isoformat())

        if filter.created_before:
            conditions.append("created_at <= ?")
            params.append(filter.created_before.isoformat())

        # ADR-017: Archive period filtering
        if filter.archive_period:
            conditions.append("archive_period = ?")
            params.append(filter.archive_period)

        # ADR-017: Channel mode filtering (single vs multi-channel)
        if filter.channel_mode == "single":
            conditions.append("json_array_length(source_channel_ids) = 1")
        elif filter.channel_mode == "multi":
            conditions.append("json_array_length(source_channel_ids) > 1")

        # ADR-017: Grounding filter
        if filter.has_grounding is True:
            conditions.append("json_array_length(json_extract(summary_json, '$.reference_index')) > 0")
        elif filter.has_grounding is False:
            conditions.append("(json_extract(summary_json, '$.reference_index') IS NULL OR json_array_length(json_extract(summary_json, '$.reference_index')) = 0)")

        # ADR-018: Content-based filters
        if filter.has_key_points is True:
            conditions.append("json_array_length(json_extract(summary_json, '$.key_points')) > 0")
        elif filter.has_key_points is False:
            conditions.append("(json_extract(summary_json, '$.key_points') IS NULL OR json_array_length(json_extract(summary_json, '$.key_points')) = 0)")

        if filter.has_action_items is True:
            conditions.append("json_array_length(json_extract(summary_json, '$.action_items')) > 0")
        elif filter.has_action_items is False:
            conditions.append("(json_extract(summary_json, '$.action_items') IS NULL OR json_array_length(json_extract(summary_json, '$.action_items')) = 0)")

        if filter.has_participants is True:
            conditions.append("json_array_length(json_extract(summary_json, '$.participants')) > 0")
        elif filter.has_participants is False:
            conditions.append("(json_extract(summary_json, '$.participants') IS NULL OR json_array_length(json_extract(summary_json, '$.participants')) = 0)")

        if filter.min_message_count is not None:
            conditions.append("message_count >= ?")
            params.append(filter.min_message_count)

        if filter.max_message_count is not None:
            conditions.append("message_count <= ?")
            params.append(filter.max_message_count)

        # ADR-021: Content count filters
        if filter.min_key_points is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.key_points')), 0) >= ?")
            params.append(filter.min_key_points)

        if filter.max_key_points is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.key_points')), 0) <= ?")
            params.append(filter.max_key_points)

        if filter.min_action_items is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.action_items')), 0) >= ?")
            params.append(filter.min_action_items)

        if filter.max_action_items is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.action_items')), 0) <= ?")
            params.append(filter.max_action_items)

        if filter.min_participants is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.participants')), 0) >= ?")
            params.append(filter.min_participants)

        if filter.max_participants is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.participants')), 0) <= ?")
            params.append(filter.max_participants)

        # ADR-026: Platform filter (filters by archive_source_key prefix)
        if filter.platform and filter.platform != "all":
            conditions.append("archive_source_key LIKE ?")
            params.append(f"{filter.platform}:%")

        where_clause = " AND ".join(conditions)
        return where_clause, params

    async def find_by_guild(
        self,
        guild_id: str,
        limit: int = 20,
        offset: int = 0,
        pinned_only: bool = False,
        include_archived: bool = False,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,  # ADR-008: Filter by source
        # ADR-017: Enhanced filtering
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        archive_period: Optional[str] = None,
        channel_mode: Optional[str] = None,  # "single" or "multi"
        has_grounding: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        # ADR-018: Content-based filters
        has_key_points: Optional[bool] = None,
        has_action_items: Optional[bool] = None,
        has_participants: Optional[bool] = None,
        min_message_count: Optional[int] = None,
        max_message_count: Optional[int] = None,
        # ADR-021: Content count filters
        min_key_points: Optional[int] = None,
        max_key_points: Optional[int] = None,
        min_action_items: Optional[int] = None,
        max_action_items: Optional[int] = None,
        min_participants: Optional[int] = None,
        max_participants: Optional[int] = None,
        # ADR-026: Platform filter (discord, whatsapp, etc.)
        platform: Optional[str] = None,
    ) -> List[StoredSummary]:
        """Find stored summaries for a guild.

        Args:
            guild_id: Discord guild/server ID
            limit: Maximum number of results
            offset: Pagination offset
            pinned_only: Only return pinned summaries
            include_archived: Include archived summaries
            tags: Filter by any of these tags
            source: ADR-008 - Filter by source type (realtime, archive, etc.)
                    Use "all" or None for no filtering
            created_after: ADR-017 - Filter by creation date (after)
            created_before: ADR-017 - Filter by creation date (before)
            archive_period: ADR-017 - Filter by archive period (e.g., "2026-01-15")
            channel_mode: ADR-017 - "single" for single-channel, "multi" for multi-channel
            has_grounding: ADR-017 - Filter by grounding status
            sort_by: ADR-017 - Sort field (created_at, message_count)
            sort_order: ADR-017 - Sort direction (asc, desc)

        Returns:
            List of matching StoredSummary objects
        """
        # CS-002: Use shared filter builder
        filter_obj = StoredSummaryFilter(
            guild_id=guild_id,
            pinned_only=pinned_only,
            include_archived=include_archived,
            tags=tags,
            source=source,
            created_after=created_after,
            created_before=created_before,
            archive_period=archive_period,
            channel_mode=channel_mode,
            has_grounding=has_grounding,
            has_key_points=has_key_points,
            has_action_items=has_action_items,
            has_participants=has_participants,
            min_message_count=min_message_count,
            max_message_count=max_message_count,
            min_key_points=min_key_points,
            max_key_points=max_key_points,
            min_action_items=min_action_items,
            max_action_items=max_action_items,
            min_participants=min_participants,
            max_participants=max_participants,
            platform=platform,
        )
        where_clause, params = self._build_filter_clause(filter_obj)

        # ADR-017: Dynamic sorting
        valid_sort_fields = {"created_at", "message_count", "archive_period"}
        if sort_by not in valid_sort_fields:
            sort_by = "created_at"
        sort_direction = "ASC" if sort_order.lower() == "asc" else "DESC"

        # Handle NULL values for sorting - use COALESCE for message_count
        if sort_by == "message_count":
            sort_field = f"COALESCE({sort_by}, 0)"
        else:
            sort_field = sort_by

        # Always sort pinned first, then by the selected field
        order_clause = f"is_pinned DESC, {sort_field} {sort_direction}"

        query = f"""
        SELECT * FROM stored_summaries
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        summaries = [self._row_to_stored_summary(row) for row in rows]

        # Filter by tags in Python (SQLite JSON support is limited)
        if tags:
            summaries = [
                s for s in summaries
                if any(tag in s.tags for tag in tags)
            ]

        return summaries

    async def count_by_guild(
        self,
        guild_id: str,
        include_archived: bool = False,
        source: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        archive_period: Optional[str] = None,
        channel_mode: Optional[str] = None,
        has_grounding: Optional[bool] = None,
        # ADR-018: Content-based filters
        has_key_points: Optional[bool] = None,
        has_action_items: Optional[bool] = None,
        has_participants: Optional[bool] = None,
        min_message_count: Optional[int] = None,
        max_message_count: Optional[int] = None,
        # ADR-021: Content count filters
        min_key_points: Optional[int] = None,
        max_key_points: Optional[int] = None,
        min_action_items: Optional[int] = None,
        max_action_items: Optional[int] = None,
        min_participants: Optional[int] = None,
        max_participants: Optional[int] = None,
        # ADR-026: Platform filter
        platform: Optional[str] = None,
    ) -> int:
        """Count stored summaries for a guild with optional filters (ADR-017, ADR-018, ADR-021, ADR-026)."""
        # CS-002: Use shared filter builder
        filter_obj = StoredSummaryFilter(
            guild_id=guild_id,
            include_archived=include_archived,
            source=source,
            created_after=created_after,
            created_before=created_before,
            archive_period=archive_period,
            channel_mode=channel_mode,
            has_grounding=has_grounding,
            has_key_points=has_key_points,
            has_action_items=has_action_items,
            has_participants=has_participants,
            min_message_count=min_message_count,
            max_message_count=max_message_count,
            min_key_points=min_key_points,
            max_key_points=max_key_points,
            min_action_items=min_action_items,
            max_action_items=max_action_items,
            min_participants=min_participants,
            max_participants=max_participants,
            platform=platform,
        )
        where_clause, params = self._build_filter_clause(filter_obj)

        query = f"SELECT COUNT(*) as count FROM stored_summaries WHERE {where_clause}"

        row = await self.connection.fetch_one(query, tuple(params))
        return row['count'] if row else 0

    async def get_calendar_data(
        self,
        guild_id: str,
        year: int,
        month: int,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get summary counts grouped by day for calendar view (ADR-017).

        Returns list of dicts with: date, count, sources, has_incomplete.
        Uses archive_period for archive summaries, created_at for others.
        """
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        if not include_archived:
            conditions.append("is_archived = 0")

        # Use archive_period for archive summaries, created_at for others
        # This ensures archive summaries appear on their content date, not generation date
        date_expr = "COALESCE(archive_period, DATE(created_at))"

        # Filter by year and month using the effective date
        conditions.append(f"strftime('%Y', {date_expr}) = ?")
        conditions.append(f"strftime('%m', {date_expr}) = ?")
        params.extend([str(year), f"{month:02d}"])

        where_clause = " AND ".join(conditions)

        query = f"""
        SELECT
            {date_expr} as date,
            COUNT(*) as count,
            GROUP_CONCAT(DISTINCT source) as sources,
            SUM(CASE WHEN source_channel_ids = '[]' OR source_channel_ids IS NULL THEN 1 ELSE 0 END) as incomplete_count
        FROM stored_summaries
        WHERE {where_clause}
        GROUP BY {date_expr}
        ORDER BY date
        """

        rows = await self.connection.fetch_all(query, tuple(params))
        return [
            {
                "date": row["date"],
                "count": row["count"],
                "sources": row["sources"].split(",") if row["sources"] else [],
                "has_incomplete": row["incomplete_count"] > 0,
            }
            for row in rows
        ]

    async def update(self, summary: StoredSummary) -> bool:
        """Update a stored summary.

        Note: This also updates summary_json to support regeneration where
        the summary_result is replaced with new content.
        """
        query = """
        UPDATE stored_summaries SET
            summary_json = ?,
            viewed_at = ?,
            pushed_at = ?,
            push_deliveries = ?,
            title = ?,
            is_pinned = ?,
            is_archived = ?,
            tags = ?
        WHERE id = ?
        """

        params = (
            json.dumps(summary.summary_result.to_dict() if summary.summary_result else {}),
            summary.viewed_at.isoformat() if summary.viewed_at else None,
            summary.pushed_at.isoformat() if summary.pushed_at else None,
            json.dumps([d.to_dict() for d in summary.push_deliveries]),
            summary.title,
            summary.is_pinned,
            summary.is_archived,
            json.dumps(summary.tags),
            summary.id,
        )

        cursor = await self.connection.execute(query, params)

        # ADR-020: Update FTS index
        if cursor.rowcount > 0:
            await self._update_fts(summary)

        return cursor.rowcount > 0

    async def delete(self, summary_id: str) -> bool:
        """Delete a stored summary."""
        # ADR-020: Delete from FTS first
        try:
            await self.connection.execute(
                "DELETE FROM summary_fts WHERE summary_id = ?",
                (summary_id,)
            )
        except Exception:
            pass  # FTS table might not exist yet

        query = "DELETE FROM stored_summaries WHERE id = ?"
        cursor = await self.connection.execute(query, (summary_id,))
        return cursor.rowcount > 0

    async def bulk_delete(self, summary_ids: List[str], guild_id: str) -> Dict[str, Any]:
        """Delete multiple stored summaries (ADR-018).

        Args:
            summary_ids: List of summary IDs to delete
            guild_id: Guild ID for access control

        Returns:
            Dict with deleted_count, failed_ids, errors
        """
        if not summary_ids:
            return {"deleted_count": 0, "failed_ids": [], "errors": []}

        deleted_count = 0
        failed_ids = []
        errors = []

        # Delete in batches to avoid SQL parameter limits
        batch_size = 100
        for i in range(0, len(summary_ids), batch_size):
            batch = summary_ids[i:i + batch_size]
            placeholders = ",".join(["?" for _ in batch])

            # Only delete summaries belonging to this guild
            query = f"""
            DELETE FROM stored_summaries
            WHERE id IN ({placeholders}) AND guild_id = ?
            """

            try:
                cursor = await self.connection.execute(query, tuple(batch) + (guild_id,))
                deleted_count += cursor.rowcount
            except Exception as e:
                logger.error(f"Bulk delete batch failed: {e}")
                failed_ids.extend(batch)
                errors.append(str(e))

        return {
            "deleted_count": deleted_count,
            "failed_ids": failed_ids,
            "errors": errors,
        }

    async def find_by_schedule(
        self,
        schedule_id: str,
        limit: int = 10,
    ) -> List[StoredSummary]:
        """Find stored summaries created by a specific schedule."""
        query = """
        SELECT * FROM stored_summaries
        WHERE schedule_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """

        rows = await self.connection.fetch_all(query, (schedule_id, limit))
        return [self._row_to_stored_summary(row) for row in rows]

    def _row_to_stored_summary(self, row: Dict[str, Any]) -> StoredSummary:
        """Convert database row to StoredSummary object."""
        # Parse summary_result JSON back to SummaryResult
        summary_data = json.loads(row['summary_json'])
        summary_result = None
        if summary_data:
            # Reconstruct SummaryResult from dict
            summary_result = self._dict_to_summary_result(summary_data)

        # Parse push deliveries
        push_deliveries_data = json.loads(row.get('push_deliveries') or '[]')
        push_deliveries = [PushDelivery.from_dict(d) for d in push_deliveries_data]

        # ADR-008: Parse source enum
        source_str = row.get('source', 'realtime')
        try:
            source = SummarySource(source_str)
        except ValueError:
            source = SummarySource.REALTIME

        return StoredSummary(
            id=row['id'],
            guild_id=row['guild_id'],
            source_channel_ids=json.loads(row['source_channel_ids']),
            schedule_id=row['schedule_id'],
            summary_result=summary_result,
            created_at=datetime.fromisoformat(row['created_at']),
            viewed_at=datetime.fromisoformat(row['viewed_at']) if row['viewed_at'] else None,
            pushed_at=datetime.fromisoformat(row['pushed_at']) if row['pushed_at'] else None,
            push_deliveries=push_deliveries,
            title=row['title'],
            is_pinned=bool(row['is_pinned']),
            is_archived=bool(row['is_archived']),
            tags=json.loads(row.get('tags') or '[]'),
            # ADR-008: Source tracking
            source=source,
            archive_period=row.get('archive_period'),
            archive_granularity=row.get('archive_granularity'),
            archive_source_key=row.get('archive_source_key'),
        )

    def _dict_to_summary_result(self, data: Dict[str, Any]) -> SummaryResult:
        """Convert dictionary to SummaryResult object."""
        # Handle nested objects
        # ActionItem expects 'description' but JSON may have 'text'
        action_items = []
        for item in data.get('action_items', []):
            if 'text' in item and 'description' not in item:
                item = {**item, 'description': item.pop('text')}
            action_items.append(ActionItem(**item))
        technical_terms = [TechnicalTerm(**term) for term in data.get('technical_terms', [])]
        participants = [Participant(**p) for p in data.get('participants', [])]

        context = None
        if data.get('context'):
            context = SummarizationContext(**data['context'])

        # Parse warnings
        warnings = []
        if data.get('warnings'):
            warnings = [SummaryWarning(**w) for w in data['warnings']]

        return SummaryResult(
            id=data.get('id', ''),
            channel_id=data.get('channel_id', ''),
            guild_id=data.get('guild_id', ''),
            start_time=datetime.fromisoformat(data['start_time']) if data.get('start_time') else datetime.utcnow(),
            end_time=datetime.fromisoformat(data['end_time']) if data.get('end_time') else datetime.utcnow(),
            message_count=data.get('message_count', 0),
            key_points=data.get('key_points', []),
            action_items=action_items,
            technical_terms=technical_terms,
            participants=participants,
            summary_text=data.get('summary_text', ''),
            metadata=data.get('metadata', {}),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.utcnow(),
            context=context,
            prompt_system=data.get('prompt_system'),
            prompt_user=data.get('prompt_user'),
            prompt_template_id=data.get('prompt_template_id'),
            source_content=data.get('source_content'),
            warnings=warnings,
            referenced_key_points=data.get('referenced_key_points', []),
            referenced_action_items=data.get('referenced_action_items', []),
            referenced_decisions=data.get('referenced_decisions', []),
            reference_index=data.get('reference_index', []),
        )

    # ADR-020: Navigation and Search

    async def get_navigation(
        self,
        summary_id: str,
        guild_id: str,
        source: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """Get previous/next summary IDs for navigation."""
        # First, get the current summary's created_at
        current_query = "SELECT created_at FROM stored_summaries WHERE id = ? AND guild_id = ?"
        current_row = await self.connection.fetch_one(current_query, (summary_id, guild_id))

        if not current_row:
            return {"previous_id": None, "previous_date": None, "next_id": None, "next_date": None}

        current_time = current_row["created_at"]

        # Build conditions
        base_conditions = ["guild_id = ?"]
        params_base: List[Any] = [guild_id]

        if source and source != "all":
            base_conditions.append("source = ?")
            params_base.append(source)

        base_where = " AND ".join(base_conditions)

        # Get previous (older) summary
        prev_query = f"""
        SELECT id, archive_period, created_at
        FROM stored_summaries
        WHERE {base_where} AND created_at < ?
        ORDER BY created_at DESC
        LIMIT 1
        """
        prev_row = await self.connection.fetch_one(
            prev_query, tuple(params_base) + (current_time,)
        )

        # Get next (newer) summary
        next_query = f"""
        SELECT id, archive_period, created_at
        FROM stored_summaries
        WHERE {base_where} AND created_at > ?
        ORDER BY created_at ASC
        LIMIT 1
        """
        next_row = await self.connection.fetch_one(
            next_query, tuple(params_base) + (current_time,)
        )

        return {
            "previous_id": prev_row["id"] if prev_row else None,
            "previous_date": prev_row["archive_period"] or prev_row["created_at"][:10] if prev_row else None,
            "next_id": next_row["id"] if next_row else None,
            "next_date": next_row["archive_period"] or next_row["created_at"][:10] if next_row else None,
        }

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
        """Full-text search across summary content using FTS5."""
        # Build the FTS query with optional field restrictions
        if fields:
            # Search specific fields: {field1 field2}: query
            field_spec = " ".join(fields)
            fts_match = f"{{summary_text key_points action_items participants technical_terms}}: {query}"
            if all(f in ["summary_text", "key_points", "action_items", "participants", "technical_terms"] for f in fields):
                fts_match = f"{{{field_spec}}}: {query}"
        else:
            fts_match = query

        # Build the main query with joins
        conditions = ["fts.guild_id = ?"]
        params: List[Any] = [guild_id]

        if source and source != "all":
            conditions.append("s.source = ?")
            params.append(source)

        if date_from:
            conditions.append("s.created_at >= ?")
            params.append(date_from.isoformat())

        if date_to:
            conditions.append("s.created_at <= ?")
            params.append(date_to.isoformat())

        where_clause = " AND ".join(conditions)

        # Count total matches
        count_query = f"""
        SELECT COUNT(*) as total
        FROM summary_fts fts
        JOIN stored_summaries s ON fts.summary_id = s.id
        WHERE fts MATCH ? AND {where_clause}
        """
        count_row = await self.connection.fetch_one(count_query, (fts_match,) + tuple(params))
        total = count_row["total"] if count_row else 0

        # Get matching results with snippets
        search_query = f"""
        SELECT
            s.id,
            s.title,
            s.archive_period,
            s.created_at,
            s.source,
            bm25(fts) as relevance_score,
            snippet(fts, 1, '<mark>', '</mark>', '...', 32) as summary_snippet,
            snippet(fts, 2, '<mark>', '</mark>', '...', 32) as key_points_snippet,
            snippet(fts, 3, '<mark>', '</mark>', '...', 32) as action_items_snippet
        FROM summary_fts fts
        JOIN stored_summaries s ON fts.summary_id = s.id
        WHERE fts MATCH ? AND {where_clause}
        ORDER BY relevance_score
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = await self.connection.fetch_all(search_query, (fts_match,) + tuple(params))

        items = []
        for row in rows:
            highlights = []
            if row["summary_snippet"] and "<mark>" in row["summary_snippet"]:
                highlights.append({"field": "summary_text", "snippet": row["summary_snippet"]})
            if row["key_points_snippet"] and "<mark>" in row["key_points_snippet"]:
                highlights.append({"field": "key_points", "snippet": row["key_points_snippet"]})
            if row["action_items_snippet"] and "<mark>" in row["action_items_snippet"]:
                highlights.append({"field": "action_items", "snippet": row["action_items_snippet"]})

            items.append({
                "id": row["id"],
                "title": row["title"],
                "archive_period": row["archive_period"],
                "created_at": row["created_at"],
                "source": row["source"],
                "relevance_score": abs(row["relevance_score"]),  # bm25 returns negative values
                "highlights": highlights,
            })

        return {
            "query": query,
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }

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
        """Find summaries by participant."""
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        # Build participant search condition
        participant_conditions = []
        if user_id:
            participant_conditions.append(
                "EXISTS (SELECT 1 FROM json_each(json_extract(summary_json, '$.participants')) "
                "WHERE json_extract(value, '$.user_id') = ?)"
            )
            params.append(user_id)

        if display_name:
            participant_conditions.append(
                "EXISTS (SELECT 1 FROM json_each(json_extract(summary_json, '$.participants')) "
                "WHERE json_extract(value, '$.display_name') LIKE ?)"
            )
            params.append(f"%{display_name}%")

        if participant_conditions:
            conditions.append(f"({' OR '.join(participant_conditions)})")

        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from.isoformat())

        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to.isoformat())

        where_clause = " AND ".join(conditions)

        # Count total
        count_query = f"SELECT COUNT(*) as total FROM stored_summaries WHERE {where_clause}"
        count_row = await self.connection.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        # Get matching summaries
        search_query = f"""
        SELECT id, title, archive_period, created_at, source,
               json_extract(summary_json, '$.participants') as participants,
               json_extract(summary_json, '$.message_count') as message_count
        FROM stored_summaries
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = await self.connection.fetch_all(search_query, tuple(params))

        # Build participant info from first result if searching by user_id
        participant_info = None
        if user_id and rows:
            # Aggregate participant stats across all matching summaries
            total_messages = 0
            found_name = None
            for row in rows:
                participants = json.loads(row["participants"] or "[]")
                for p in participants:
                    if p.get("user_id") == user_id:
                        found_name = found_name or p.get("display_name")
                        total_messages += p.get("message_count", 0)

            participant_info = {
                "user_id": user_id,
                "display_name": found_name or display_name or "Unknown",
                "total_summaries": total,
                "total_messages": total_messages,
            }

        items = []
        for row in rows:
            participants = json.loads(row["participants"] or "[]")

            # Find key contributions from matching participant
            contributions = []
            for p in participants:
                if (user_id and p.get("user_id") == user_id) or \
                   (display_name and display_name.lower() in (p.get("display_name") or "").lower()):
                    contributions = p.get("contributions", [])[:3] if p.get("contributions") else []
                    break

            items.append({
                "id": row["id"],
                "title": row["title"],
                "archive_period": row["archive_period"],
                "created_at": row["created_at"],
                "source": row["source"],
                "message_count": row["message_count"] or 0,
                "key_contributions": contributions,
            })

        return {
            "participant": participant_info,
            "total": total,
            "limit": limit,
            "offset": offset,
            "summaries": items,
        }


class SQLiteIngestRepository(IngestRepository):
    """SQLite implementation of ingest repository (ADR-002)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def store_batch(
        self,
        batch_id: str,
        document: IngestDocument,
        processed_messages: List[ProcessedMessage],
    ) -> str:
        """Store an ingest batch with its processed messages."""
        # Store the batch record
        batch_query = """
        INSERT INTO ingest_batches (
            id, source_type, channel_id, channel_name, channel_type,
            message_count, time_range_start, time_range_end, raw_payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        batch_params = (
            batch_id,
            document.source_type if isinstance(document.source_type, str) else document.source_type.value,
            document.channel_id,
            document.channel_name,
            document.channel_type if isinstance(document.channel_type, str) else document.channel_type.value,
            document.total_message_count,
            document.time_range_start.isoformat(),
            document.time_range_end.isoformat(),
            document.model_dump_json(),
        )

        await self.connection.execute(batch_query, batch_params)

        # Store individual messages
        msg_query = """
        INSERT INTO ingest_messages (
            id, batch_id, source_type, channel_id, sender_id, sender_name,
            timestamp, content, has_attachments, attachments_json,
            reply_to_id, is_forwarded, is_edited, is_deleted, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # PERF-002: Use executemany for batch inserts (10-100x faster)
        msg_params_list = []
        for msg in processed_messages:
            attachments_json = json.dumps([
                {
                    'filename': a.filename,
                    'size': a.size,
                    'type': a.type.value if a.type else None,
                    'content_type': a.content_type,
                }
                for a in msg.attachments
            ])

            msg_params = (
                msg.id,
                batch_id,
                msg.source_type.value if isinstance(msg.source_type, SourceType) else msg.source_type,
                msg.channel_id,
                msg.author_id,
                msg.author_name,
                msg.timestamp.isoformat(),
                msg.content,
                1 if msg.attachments else 0,
                attachments_json,
                msg.reply_to_id,
                1 if msg.is_forwarded else 0,
                1 if msg.is_edited else 0,
                1 if msg.is_deleted else 0,
                json.dumps({'phone_number': msg.phone_number}) if msg.phone_number else '{}',
            )
            msg_params_list.append(msg_params)

        # Batch insert all messages at once
        if msg_params_list:
            await self.connection.executemany(msg_query, msg_params_list)

        # Update channel stats
        await self._update_channel_stats(document)

        return batch_id

    async def _update_channel_stats(self, document: IngestDocument) -> None:
        """Update channel statistics after ingesting messages."""
        source_type = document.source_type if isinstance(document.source_type, str) else document.source_type.value
        channel_type = document.channel_type if isinstance(document.channel_type, str) else document.channel_type.value

        # Upsert channel stats
        query = """
        INSERT INTO channel_stats (
            source_type, channel_id, channel_name, channel_type,
            message_count, participant_count, first_message_at, last_message_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(source_type, channel_id) DO UPDATE SET
            channel_name = COALESCE(excluded.channel_name, channel_name),
            message_count = message_count + excluded.message_count,
            participant_count = MAX(participant_count, excluded.participant_count),
            first_message_at = MIN(COALESCE(first_message_at, excluded.first_message_at), excluded.first_message_at),
            last_message_at = MAX(COALESCE(last_message_at, excluded.last_message_at), excluded.last_message_at),
            updated_at = datetime('now')
        """

        params = (
            source_type,
            document.channel_id,
            document.channel_name,
            channel_type,
            document.total_message_count,
            len(document.participants),
            document.time_range_start.isoformat(),
            document.time_range_end.isoformat(),
        )

        await self.connection.execute(query, params)

    async def get_batch(self, batch_id: str) -> Optional[IngestBatch]:
        """Retrieve an ingest batch by ID."""
        query = "SELECT * FROM ingest_batches WHERE id = ?"
        row = await self.connection.fetch_one(query, (batch_id,))

        if not row:
            return None

        return IngestBatch(
            id=row['id'],
            source_type=SourceType(row['source_type']),
            channel_id=row['channel_id'],
            channel_name=row['channel_name'],
            channel_type=ChannelType(row['channel_type']),
            message_count=row['message_count'],
            time_range_start=datetime.fromisoformat(row['time_range_start']),
            time_range_end=datetime.fromisoformat(row['time_range_end']),
            raw_payload=row['raw_payload'],
            processed=bool(row['processed']),
            document_id=row['document_id'],
            created_at=datetime.fromisoformat(row['created_at']),
        )

    async def get_messages(
        self,
        source_type: str,
        channel_id: str,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[ProcessedMessage]:
        """Get processed messages for a channel."""
        conditions = ["source_type = ?", "channel_id = ?"]
        params: List[Any] = [source_type, channel_id]

        if time_from:
            conditions.append("timestamp >= ?")
            params.append(time_from.isoformat())

        if time_to:
            conditions.append("timestamp <= ?")
            params.append(time_to.isoformat())

        where_clause = " AND ".join(conditions)

        query = f"""
        SELECT * FROM ingest_messages
        WHERE {where_clause}
        ORDER BY timestamp ASC
        LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_processed_message(row) for row in rows]

    def _row_to_processed_message(self, row: Dict[str, Any]) -> ProcessedMessage:
        """Convert database row to ProcessedMessage."""
        # Parse attachments
        attachments = []
        if row.get('attachments_json'):
            att_data = json.loads(row['attachments_json'])
            for att in att_data:
                attachments.append(AttachmentInfo(
                    id=att.get('filename', ''),
                    filename=att.get('filename', ''),
                    size=att.get('size', 0),
                    url='',
                    proxy_url='',
                    type=AttachmentType(att['type']) if att.get('type') else AttachmentType.UNKNOWN,
                    content_type=att.get('content_type'),
                ))

        # Parse metadata
        metadata = json.loads(row.get('metadata') or '{}')

        return ProcessedMessage(
            id=row['id'],
            author_id=row['sender_id'],
            author_name=row['sender_name'],
            content=row['content'] or '',
            timestamp=datetime.fromisoformat(row['timestamp']),
            source_type=SourceType(row['source_type']),
            message_type=MessageType.WHATSAPP_TEXT,  # Default for ingested messages
            attachments=attachments,
            channel_id=row['channel_id'],
            is_forwarded=bool(row['is_forwarded']),
            is_edited=bool(row['is_edited']),
            is_deleted=bool(row['is_deleted']),
            reply_to_id=row['reply_to_id'],
            phone_number=metadata.get('phone_number'),
        )

    async def list_channels(
        self,
        source_type: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List channels with ingested messages."""
        query = """
        SELECT * FROM channel_stats
        WHERE source_type = ?
        ORDER BY last_message_at DESC
        LIMIT ? OFFSET ?
        """

        rows = await self.connection.fetch_all(query, (source_type, limit, offset))

        return [
            {
                'chat_id': row['channel_id'],
                'chat_name': row['channel_name'] or row['channel_id'],
                'chat_type': row['channel_type'],
                'message_count': row['message_count'],
                'participant_count': row['participant_count'],
                'first_message_at': datetime.fromisoformat(row['first_message_at']) if row['first_message_at'] else None,
                'last_message_at': datetime.fromisoformat(row['last_message_at']) if row['last_message_at'] else None,
            }
            for row in rows
        ]

    async def count_channels(self, source_type: str) -> int:
        """Count channels with ingested messages."""
        query = "SELECT COUNT(*) as count FROM channel_stats WHERE source_type = ?"
        row = await self.connection.fetch_one(query, (source_type,))
        return row['count'] if row else 0

    async def get_channel_stats(
        self,
        source_type: str,
        channel_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific channel."""
        query = """
        SELECT * FROM channel_stats
        WHERE source_type = ? AND channel_id = ?
        """

        row = await self.connection.fetch_one(query, (source_type, channel_id))

        if not row:
            return None

        return {
            'chat_id': row['channel_id'],
            'chat_name': row['channel_name'] or row['channel_id'],
            'chat_type': row['channel_type'],
            'message_count': row['message_count'],
            'participant_count': row['participant_count'],
            'first_message_at': datetime.fromisoformat(row['first_message_at']) if row['first_message_at'] else None,
            'last_message_at': datetime.fromisoformat(row['last_message_at']) if row['last_message_at'] else None,
        }

    async def delete_batch(self, batch_id: str) -> bool:
        """Delete an ingest batch and its messages."""
        # Messages are deleted via CASCADE
        query = "DELETE FROM ingest_batches WHERE id = ?"
        cursor = await self.connection.execute(query, (batch_id,))
        return cursor.rowcount > 0


class SQLiteSummaryJobRepository(SummaryJobRepository):
    """SQLite implementation of summary job repository (ADR-013)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save(self, job: SummaryJob) -> str:
        """Save a job to the database."""
        query = """
        INSERT INTO summary_jobs (
            id, guild_id, job_type, status, scope, channel_ids, category_id,
            schedule_id, period_start, period_end, date_range_start, date_range_end,
            granularity, summary_type, perspective, force_regenerate,
            progress_current, progress_total, progress_message, current_period,
            cost_usd, tokens_input, tokens_output, summary_id, summary_ids,
            error, pause_reason, created_at, started_at, completed_at,
            created_by, source_key, server_name, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            job.id,
            job.guild_id,
            job.job_type.value,
            job.status.value,
            job.scope,
            json.dumps(job.channel_ids) if job.channel_ids else None,
            job.category_id,
            job.schedule_id,
            job.period_start.isoformat() if job.period_start else None,
            job.period_end.isoformat() if job.period_end else None,
            job.date_range_start.isoformat() if job.date_range_start else None,
            job.date_range_end.isoformat() if job.date_range_end else None,
            job.granularity,
            job.summary_type,
            job.perspective,
            1 if job.force_regenerate else 0,
            job.progress_current,
            job.progress_total,
            job.progress_message,
            job.current_period,
            job.cost_usd,
            job.tokens_input,
            job.tokens_output,
            job.summary_id,
            json.dumps(job.summary_ids) if job.summary_ids else None,
            job.error,
            job.pause_reason,
            job.created_at.isoformat(),
            job.started_at.isoformat() if job.started_at else None,
            job.completed_at.isoformat() if job.completed_at else None,
            job.created_by,
            job.source_key,
            job.server_name,
            json.dumps(job.metadata) if job.metadata else None,
        )

        await self.connection.execute(query, params)
        return job.id

    async def get(self, job_id: str) -> Optional[SummaryJob]:
        """Get a job by ID."""
        query = "SELECT * FROM summary_jobs WHERE id = ?"
        row = await self.connection.fetch_one(query, (job_id,))
        if not row:
            return None
        return SummaryJob.from_dict(dict(row))

    async def update(self, job: SummaryJob) -> bool:
        """Update an existing job."""
        query = """
        UPDATE summary_jobs SET
            status = ?,
            progress_current = ?,
            progress_total = ?,
            progress_message = ?,
            current_period = ?,
            cost_usd = ?,
            tokens_input = ?,
            tokens_output = ?,
            summary_id = ?,
            summary_ids = ?,
            error = ?,
            pause_reason = ?,
            started_at = ?,
            completed_at = ?
        WHERE id = ?
        """

        params = (
            job.status.value,
            job.progress_current,
            job.progress_total,
            job.progress_message,
            job.current_period,
            job.cost_usd,
            job.tokens_input,
            job.tokens_output,
            job.summary_id,
            json.dumps(job.summary_ids) if job.summary_ids else None,
            job.error,
            job.pause_reason,
            job.started_at.isoformat() if job.started_at else None,
            job.completed_at.isoformat() if job.completed_at else None,
            job.id,
        )

        cursor = await self.connection.execute(query, params)
        return cursor.rowcount > 0

    async def find_by_guild(
        self,
        guild_id: str,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SummaryJob]:
        """Find jobs for a guild with optional filters."""
        conditions = ["guild_id = ?"]
        params = [guild_id]

        if status:
            conditions.append("status = ?")
            params.append(status)

        if job_type:
            conditions.append("job_type = ?")
            params.append(job_type)

        query = f"""
        SELECT * FROM summary_jobs
        WHERE {' AND '.join(conditions)}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        return [SummaryJob.from_dict(dict(row)) for row in rows]

    async def find_active(self, guild_id: Optional[str] = None) -> List[SummaryJob]:
        """Find all active (pending/running) jobs."""
        if guild_id:
            query = """
            SELECT * FROM summary_jobs
            WHERE guild_id = ? AND status IN ('pending', 'running', 'paused')
            ORDER BY created_at DESC
            """
            rows = await self.connection.fetch_all(query, (guild_id,))
        else:
            query = """
            SELECT * FROM summary_jobs
            WHERE status IN ('pending', 'running', 'paused')
            ORDER BY created_at DESC
            """
            rows = await self.connection.fetch_all(query, ())

        return [SummaryJob.from_dict(dict(row)) for row in rows]

    async def delete(self, job_id: str) -> bool:
        """Delete a job by ID."""
        query = "DELETE FROM summary_jobs WHERE id = ?"
        cursor = await self.connection.execute(query, (job_id,))
        return cursor.rowcount > 0

    async def cleanup_old(self, days: int = 7) -> int:
        """Delete jobs older than specified days."""
        query = """
        DELETE FROM summary_jobs
        WHERE completed_at IS NOT NULL
        AND completed_at < datetime('now', '-' || ? || ' days')
        """
        cursor = await self.connection.execute(query, (days,))
        return cursor.rowcount

    async def count_by_guild(
        self,
        guild_id: str,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> int:
        """Count jobs for a guild."""
        conditions = ["guild_id = ?"]
        params = [guild_id]

        if status:
            conditions.append("status = ?")
            params.append(status)

        if job_type:
            conditions.append("job_type = ?")
            params.append(job_type)

        query = f"""
        SELECT COUNT(*) as count FROM summary_jobs
        WHERE {' AND '.join(conditions)}
        """

        row = await self.connection.fetch_one(query, tuple(params))
        return row['count'] if row else 0

    async def mark_interrupted_jobs(self, reason: str = "server_restart") -> int:
        """
        Mark all RUNNING jobs as PAUSED due to server restart.

        ADR-013: Startup recovery - when the server restarts, any jobs that were
        RUNNING are marked as PAUSED so users can see they were interrupted and
        can choose to resume them.

        Args:
            reason: The pause reason to set (default: 'server_restart')

        Returns:
            Number of jobs that were marked as paused
        """
        query = """
        UPDATE summary_jobs
        SET status = 'paused', pause_reason = ?
        WHERE status = 'running'
        """
        cursor = await self.connection.execute(query, (reason,))
        return cursor.rowcount
