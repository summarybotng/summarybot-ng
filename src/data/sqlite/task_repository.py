"""
SQLite implementation of task repository.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, date


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)

from ..base import TaskRepository
from ...models.summary import SummaryOptions, SummaryLength
from ...models.task import (
    ScheduledTask,
    TaskResult,
    Destination,
    TaskStatus,
    ScheduleType,
    DestinationType,
    SummaryScope
)
from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


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
            json.dumps(result.error_details, cls=DateTimeEncoder) if result.error_details else None,
            json.dumps(result.delivery_results, cls=DateTimeEncoder),
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
