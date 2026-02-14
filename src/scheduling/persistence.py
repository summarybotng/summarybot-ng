"""
Task state persistence to database for recovery after restarts.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from ..models.task import ScheduledTask, ScheduleType, Destination, DestinationType
from ..models.summary import SummaryOptions, SummaryLength
from ..config.constants import DEFAULT_SUMMARIZATION_MODEL
from ..exceptions import ConfigurationError, create_error_context

logger = logging.getLogger(__name__)


class TaskPersistence:
    """Handles persistence of scheduled tasks to survive bot restarts."""

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize task persistence.

        Args:
            storage_path: Path to storage directory (default: ./data/tasks)
        """
        self.storage_path = Path(storage_path or "./data/tasks")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Task persistence initialized at {self.storage_path}")

    async def save_task(self, task: ScheduledTask) -> None:
        """Save a task to persistent storage.

        Args:
            task: Task to save
        """
        try:
            task_file = self.storage_path / f"{task.id}.json"
            task_data = self._serialize_task(task)

            with open(task_file, 'w') as f:
                json.dump(task_data, f, indent=2)

            logger.debug(f"Saved task {task.id} to {task_file}")

        except Exception as e:
            logger.error(f"Failed to save task {task.id}: {e}")
            raise ConfigurationError(
                message=f"Failed to persist task: {str(e)}",
                error_code="TASK_PERSISTENCE_FAILED",
                context=create_error_context(operation="save_task"),
                user_message="Failed to save task configuration."
            )

    async def load_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Load a task from persistent storage.

        Args:
            task_id: ID of task to load

        Returns:
            Loaded task or None if not found
        """
        try:
            task_file = self.storage_path / f"{task_id}.json"

            if not task_file.exists():
                return None

            with open(task_file, 'r') as f:
                task_data = json.load(f)

            task = self._deserialize_task(task_data)
            logger.debug(f"Loaded task {task_id} from {task_file}")

            return task

        except Exception as e:
            logger.error(f"Failed to load task {task_id}: {e}")
            return None

    async def load_all_tasks(self) -> List[ScheduledTask]:
        """Load all persisted tasks.

        Returns:
            List of all tasks
        """
        tasks = []

        try:
            for task_file in self.storage_path.glob("*.json"):
                try:
                    with open(task_file, 'r') as f:
                        task_data = json.load(f)

                    task = self._deserialize_task(task_data)
                    tasks.append(task)

                except Exception as e:
                    logger.error(f"Failed to load task from {task_file}: {e}")
                    continue

            logger.info(f"Loaded {len(tasks)} tasks from persistent storage")
            return tasks

        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")
            return []

    async def update_task(self, task: ScheduledTask) -> None:
        """Update an existing task in storage.

        Args:
            task: Task with updated data
        """
        await self.save_task(task)  # Same as save - overwrites

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task from persistent storage.

        Args:
            task_id: ID of task to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            task_file = self.storage_path / f"{task_id}.json"

            if not task_file.exists():
                return False

            task_file.unlink()
            logger.info(f"Deleted task {task_id} from storage")
            return True

        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {e}")
            return False

    async def get_tasks_by_guild(self, guild_id: str) -> List[ScheduledTask]:
        """Get all tasks for a specific guild.

        Args:
            guild_id: Guild ID to filter by

        Returns:
            List of tasks for the guild
        """
        all_tasks = await self.load_all_tasks()
        return [task for task in all_tasks if task.guild_id == guild_id]

    def _serialize_task(self, task: ScheduledTask) -> Dict[str, Any]:
        """Convert task to JSON-serializable dictionary.

        Args:
            task: Task to serialize

        Returns:
            Serialized task data
        """
        return {
            "id": task.id,
            "name": task.name,
            "channel_id": task.channel_id,
            "guild_id": task.guild_id,
            "schedule_type": task.schedule_type.value,
            "schedule_time": task.schedule_time,
            "schedule_days": task.schedule_days,
            "cron_expression": task.cron_expression,
            "destinations": [
                {
                    "type": dest.type.value,
                    "target": dest.target,
                    "format": dest.format,
                    "enabled": dest.enabled
                }
                for dest in task.destinations
            ],
            "summary_options": {
                "summary_length": task.summary_options.summary_length.value,
                "include_bots": task.summary_options.include_bots,
                "include_attachments": task.summary_options.include_attachments,
                "excluded_users": task.summary_options.excluded_users,
                "min_messages": task.summary_options.min_messages,
                "claude_model": task.summary_options.summarization_model,
                "temperature": task.summary_options.temperature,
                "max_tokens": task.summary_options.max_tokens,
                "extract_action_items": task.summary_options.extract_action_items,
                "extract_technical_terms": task.summary_options.extract_technical_terms,
                "extract_key_points": task.summary_options.extract_key_points,
                "include_participant_analysis": task.summary_options.include_participant_analysis
            },
            "is_active": task.is_active,
            "timezone": task.timezone,
            "created_at": task.created_at.isoformat(),
            "created_by": task.created_by,
            "last_run": task.last_run.isoformat() if task.last_run else None,
            "next_run": task.next_run.isoformat() if task.next_run else None,
            "run_count": task.run_count,
            "failure_count": task.failure_count,
            "max_failures": task.max_failures,
            "retry_delay_minutes": task.retry_delay_minutes
        }

    def _deserialize_task(self, data: Dict[str, Any]) -> ScheduledTask:
        """Convert dictionary back to ScheduledTask.

        Args:
            data: Serialized task data

        Returns:
            Deserialized task
        """
        # Deserialize destinations
        destinations = [
            Destination(
                type=DestinationType(dest["type"]),
                target=dest["target"],
                format=dest["format"],
                enabled=dest["enabled"]
            )
            for dest in data.get("destinations", [])
        ]

        # Deserialize summary options
        summary_opts_data = data.get("summary_options", {})
        summary_options = SummaryOptions(
            summary_length=SummaryLength(summary_opts_data.get("summary_length", "detailed")),
            include_bots=summary_opts_data.get("include_bots", False),
            include_attachments=summary_opts_data.get("include_attachments", True),
            excluded_users=summary_opts_data.get("excluded_users", []),
            min_messages=summary_opts_data.get("min_messages", 5),
            summarization_model=summary_opts_data.get("claude_model", DEFAULT_SUMMARIZATION_MODEL),
            temperature=summary_opts_data.get("temperature", 0.3),
            max_tokens=summary_opts_data.get("max_tokens", 4000),
            extract_action_items=summary_opts_data.get("extract_action_items", True),
            extract_technical_terms=summary_opts_data.get("extract_technical_terms", True),
            extract_key_points=summary_opts_data.get("extract_key_points", True),
            include_participant_analysis=summary_opts_data.get("include_participant_analysis", True)
        )

        # Parse datetimes
        created_at = datetime.fromisoformat(data["created_at"])
        last_run = datetime.fromisoformat(data["last_run"]) if data.get("last_run") else None
        next_run = datetime.fromisoformat(data["next_run"]) if data.get("next_run") else None

        return ScheduledTask(
            id=data["id"],
            name=data.get("name", ""),
            channel_id=data["channel_id"],
            guild_id=data["guild_id"],
            schedule_type=ScheduleType(data["schedule_type"]),
            schedule_time=data.get("schedule_time"),
            schedule_days=data.get("schedule_days", []),
            cron_expression=data.get("cron_expression"),
            destinations=destinations,
            summary_options=summary_options,
            is_active=data.get("is_active", True),
            timezone=data.get("timezone", "UTC"),
            created_at=created_at,
            created_by=data.get("created_by", ""),
            last_run=last_run,
            next_run=next_run,
            run_count=data.get("run_count", 0),
            failure_count=data.get("failure_count", 0),
            max_failures=data.get("max_failures", 3),
            retry_delay_minutes=data.get("retry_delay_minutes", 5)
        )

    async def cleanup_old_tasks(self, days: int = 90) -> int:
        """Clean up tasks that haven't run in a specified period.

        Args:
            days: Number of days of inactivity before cleanup

        Returns:
            Number of tasks cleaned up
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        cleaned_count = 0

        try:
            all_tasks = await self.load_all_tasks()

            for task in all_tasks:
                # Remove inactive tasks that haven't run recently
                if not task.is_active and (
                    not task.last_run or task.last_run < cutoff_date
                ):
                    if await self.delete_task(task.id):
                        cleaned_count += 1

            logger.info(f"Cleaned up {cleaned_count} old tasks")
            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup old tasks: {e}")
            return 0

    async def export_tasks(self, output_file: str) -> bool:
        """Export all tasks to a backup file.

        Args:
            output_file: Path to output file

        Returns:
            True if successful
        """
        try:
            all_tasks = await self.load_all_tasks()
            task_data = [self._serialize_task(task) for task in all_tasks]

            with open(output_file, 'w') as f:
                json.dump({
                    "export_date": datetime.utcnow().isoformat(),
                    "task_count": len(task_data),
                    "tasks": task_data
                }, f, indent=2)

            logger.info(f"Exported {len(task_data)} tasks to {output_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to export tasks: {e}")
            return False

    async def import_tasks(self, input_file: str) -> int:
        """Import tasks from a backup file.

        Args:
            input_file: Path to input file

        Returns:
            Number of tasks imported
        """
        try:
            with open(input_file, 'r') as f:
                data = json.load(f)

            tasks_data = data.get("tasks", [])
            imported_count = 0

            for task_data in tasks_data:
                try:
                    task = self._deserialize_task(task_data)
                    await self.save_task(task)
                    imported_count += 1
                except Exception as e:
                    logger.error(f"Failed to import task {task_data.get('id')}: {e}")

            logger.info(f"Imported {imported_count} tasks from {input_file}")
            return imported_count

        except Exception as e:
            logger.error(f"Failed to import tasks: {e}")
            return 0


# For database-backed persistence (future implementation)
class DatabaseTaskPersistence(TaskPersistence):
    """Database-backed task persistence using SQLAlchemy."""

    def __init__(self, database_url: str):
        """Initialize database persistence.

        Args:
            database_url: Database connection URL
        """
        # TODO: Implement database persistence
        # This would use SQLAlchemy to persist tasks to a database
        # instead of JSON files
        raise NotImplementedError("Database persistence not yet implemented")
