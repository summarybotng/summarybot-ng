"""
SQLite implementation of data repositories using aiosqlite.

This module provides full SQLite support with connection pooling,
transactions, and async database operations.
"""

import json
import aiosqlite
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager

from .base import (
    SummaryRepository,
    ConfigRepository,
    TaskRepository,
    FeedRepository,
    WebhookRepository,
    ErrorRepository,
    StoredSummaryRepository,
    DatabaseConnection,
    Transaction,
    SearchCriteria
)
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
from ..models.task import (
    ScheduledTask,
    TaskResult,
    Destination,
    TaskStatus,
    ScheduleType,
    DestinationType
)
from ..models.feed import FeedConfig, FeedType
from ..models.error_log import ErrorLog, ErrorType, ErrorSeverity
from ..models.stored_summary import StoredSummary, PushDelivery
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


class SQLiteConnection(DatabaseConnection):
    """SQLite database connection with connection pooling."""

    def __init__(self, db_path: str, pool_size: int = 5):
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

    async def execute(self, query: str, params: Optional[tuple] = None) -> Any:
        """Execute a database query."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params or ())
            await conn.commit()
            return cursor

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
        query = """
        INSERT OR REPLACE INTO scheduled_tasks (
            id, name, channel_id, guild_id, schedule_type,
            schedule_time, schedule_days, cron_expression,
            destinations, summary_options, is_active,
            created_at, created_by, last_run, next_run,
            run_count, failure_count, max_failures, retry_delay_minutes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            task.retry_delay_minutes
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
        destinations = [Destination(**dest) for dest in destinations_data]

        options_data = json.loads(row['summary_options'])
        options_data['summary_length'] = SummaryLength(options_data['summary_length'])
        summary_options = SummaryOptions(**options_data)

        return ScheduledTask(
            id=row['id'],
            name=row['name'],
            channel_id=row['channel_id'],
            guild_id=row['guild_id'],
            schedule_type=ScheduleType(row['schedule_type']),
            schedule_time=row['schedule_time'],
            schedule_days=json.loads(row['schedule_days']),
            cron_expression=row['cron_expression'],
            destinations=destinations,
            summary_options=summary_options,
            is_active=bool(row['is_active']),
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
        query = """
        INSERT OR REPLACE INTO stored_summaries (
            id, guild_id, source_channel_ids, schedule_id,
            summary_json, created_at, viewed_at, pushed_at,
            push_deliveries, title, is_pinned, is_archived, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        )

        await self.connection.execute(query, params)
        return summary.id

    async def get(self, summary_id: str) -> Optional[StoredSummary]:
        """Retrieve a stored summary by its ID."""
        query = "SELECT * FROM stored_summaries WHERE id = ?"
        row = await self.connection.fetch_one(query, (summary_id,))

        if not row:
            return None

        return self._row_to_stored_summary(row)

    async def find_by_guild(
        self,
        guild_id: str,
        limit: int = 20,
        offset: int = 0,
        pinned_only: bool = False,
        include_archived: bool = False,
        tags: Optional[List[str]] = None,
    ) -> List[StoredSummary]:
        """Find stored summaries for a guild."""
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        if pinned_only:
            conditions.append("is_pinned = 1")

        if not include_archived:
            conditions.append("is_archived = 0")

        where_clause = " AND ".join(conditions)

        query = f"""
        SELECT * FROM stored_summaries
        WHERE {where_clause}
        ORDER BY is_pinned DESC, created_at DESC
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
    ) -> int:
        """Count stored summaries for a guild."""
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        if not include_archived:
            conditions.append("is_archived = 0")

        where_clause = " AND ".join(conditions)

        query = f"SELECT COUNT(*) as count FROM stored_summaries WHERE {where_clause}"

        row = await self.connection.fetch_one(query, tuple(params))
        return row['count'] if row else 0

    async def update(self, summary: StoredSummary) -> bool:
        """Update a stored summary."""
        query = """
        UPDATE stored_summaries SET
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
        return cursor.rowcount > 0

    async def delete(self, summary_id: str) -> bool:
        """Delete a stored summary."""
        query = "DELETE FROM stored_summaries WHERE id = ?"
        cursor = await self.connection.execute(query, (summary_id,))
        return cursor.rowcount > 0

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
        )

    def _dict_to_summary_result(self, data: Dict[str, Any]) -> SummaryResult:
        """Convert dictionary to SummaryResult object."""
        # Handle nested objects
        action_items = [ActionItem(**item) for item in data.get('action_items', [])]
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
