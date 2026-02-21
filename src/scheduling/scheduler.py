"""
Main task scheduler using APScheduler for automated task execution.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError

from .tasks import SummaryTask, CleanupTask, TaskType, TaskMetadata
from .executor import TaskExecutor
from .persistence import TaskPersistence
from ..models.task import ScheduledTask, ScheduleType, TaskStatus
from ..exceptions import (
    SummaryBotException, ConfigurationError, create_error_context
)

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Main task scheduler for automated summary generation and maintenance."""

    def __init__(self,
                 task_executor: TaskExecutor,
                 persistence: Optional[TaskPersistence] = None,
                 timezone: str = "UTC"):
        """Initialize task scheduler.

        Args:
            task_executor: Task executor instance
            persistence: Optional task persistence layer
            timezone: Timezone for scheduling (default: UTC)
        """
        self.executor = task_executor
        self.persistence = persistence
        self.timezone = timezone

        # APScheduler instance
        self.scheduler = AsyncIOScheduler(timezone=timezone)

        # Task tracking
        self.active_tasks: Dict[str, ScheduledTask] = {}
        self.task_metadata: Dict[str, TaskMetadata] = {}

        # State
        self._running = False
        self._startup_complete = False

    async def start(self) -> None:
        """Start the task scheduler."""
        if self._running:
            logger.warning("Task scheduler already running")
            return

        logger.info("Starting task scheduler...")

        try:
            # Start the scheduler first so schedule_task() works
            self.scheduler.start()
            self._running = True

            # Load persisted tasks after scheduler is running
            if self.persistence:
                await self._load_persisted_tasks()

            self._startup_complete = True

            logger.info(f"Task scheduler started with {len(self.active_tasks)} tasks")

        except Exception as e:
            logger.error(f"Failed to start task scheduler: {e}")
            raise ConfigurationError(
                message=f"Failed to start scheduler: {str(e)}",
                error_code="SCHEDULER_START_FAILED",
                context=create_error_context(operation="scheduler_start"),
                user_message="Failed to start the task scheduler. Please check the configuration."
            )

    async def stop(self, wait: bool = True) -> None:
        """Stop the task scheduler.

        Args:
            wait: Wait for running jobs to complete
        """
        if not self._running:
            logger.warning("Task scheduler not running")
            return

        logger.info("Stopping task scheduler...")

        # Persist current state
        if self.persistence:
            await self._persist_all_tasks()

        # Shutdown scheduler
        self.scheduler.shutdown(wait=wait)
        self._running = False
        self._startup_complete = False

        logger.info("Task scheduler stopped")

    async def schedule_task(self, task: ScheduledTask) -> str:
        """Schedule a new task.

        Args:
            task: Scheduled task to add

        Returns:
            Task ID

        Raises:
            ConfigurationError: Invalid task configuration
        """
        if not self._running:
            raise ConfigurationError(
                message="Cannot schedule task: scheduler not running",
                error_code="SCHEDULER_NOT_RUNNING",
                context=create_error_context(operation="schedule_task"),
                user_message="The scheduler is not running. Please start it first."
            )

        try:
            # Create appropriate trigger based on schedule type
            trigger = self._create_trigger(task)

            # Create task metadata
            metadata = TaskMetadata(
                task_id=task.id,
                task_type=TaskType.SUMMARY,  # Default, could be parameterized
                created_at=datetime.utcnow(),
                next_execution=task.next_run
            )

            # Add job to scheduler
            # Use 1 hour grace period to handle deployments/restarts
            # coalesce=True ensures only one execution if multiple are missed
            self.scheduler.add_job(
                func=self._execute_scheduled_task,
                trigger=trigger,
                args=[task.id],
                id=task.id,
                name=task.name or f"Task {task.id}",
                replace_existing=True,
                misfire_grace_time=3600,  # 1 hour grace period for deployments
                coalesce=True  # Run once if multiple executions missed
            )

            # Track task
            self.active_tasks[task.id] = task
            self.task_metadata[task.id] = metadata

            # Persist if available
            if self.persistence:
                await self.persistence.save_task(task)

            logger.info(f"Scheduled task {task.id}: {task.get_schedule_description()}")

            return task.id

        except Exception as e:
            logger.error(f"Failed to schedule task {task.id}: {e}")
            raise ConfigurationError(
                message=f"Failed to schedule task: {str(e)}",
                error_code="TASK_SCHEDULE_FAILED",
                context=create_error_context(operation="schedule_task"),
                user_message=f"Failed to schedule task: {str(e)}"
            )

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a scheduled task.

        Args:
            task_id: ID of task to cancel

        Returns:
            True if task was cancelled, False if not found
        """
        try:
            # Remove from scheduler
            self.scheduler.remove_job(task_id)

            # Update task status
            if task_id in self.active_tasks:
                task = self.active_tasks[task_id]
                task.is_active = False

                # Persist change
                if self.persistence:
                    await self.persistence.update_task(task)

                # Remove from tracking
                del self.active_tasks[task_id]

            logger.info(f"Cancelled task {task_id}")
            return True

        except JobLookupError:
            logger.warning(f"Task {task_id} not found for cancellation")
            return False
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return False

    async def get_scheduled_tasks(self, guild_id: Optional[str] = None) -> List[ScheduledTask]:
        """Get all scheduled tasks, optionally filtered by guild.

        Args:
            guild_id: Optional guild ID to filter by

        Returns:
            List of scheduled tasks
        """
        tasks = list(self.active_tasks.values())

        if guild_id:
            tasks = [task for task in tasks if task.guild_id == guild_id]

        return tasks

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a single task by ID.

        Args:
            task_id: Task ID

        Returns:
            ScheduledTask or None if not found
        """
        return self.active_tasks.get(task_id)

    async def update_task(self, task: ScheduledTask) -> bool:
        """Update an existing task.

        Args:
            task: Updated task

        Returns:
            True if updated successfully
        """
        if task.id not in self.active_tasks:
            return False

        # Cancel existing job
        await self.cancel_task(task.id)

        # Re-schedule with new settings
        await self.schedule_task(task)
        return True

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed status of a task.

        Args:
            task_id: Task ID

        Returns:
            Task status dictionary or None if not found
        """
        if task_id not in self.active_tasks:
            return None

        task = self.active_tasks[task_id]
        metadata = self.task_metadata.get(task_id)

        # Get next run time from scheduler
        job = self.scheduler.get_job(task_id)
        next_run = job.next_run_time if job else None

        return {
            **task.to_status_dict(),
            "metadata": metadata.to_dict() if metadata else None,
            "next_run_time": next_run.isoformat() if next_run else None,
            "scheduler_running": self._running
        }

    async def pause_task(self, task_id: str) -> bool:
        """Pause a scheduled task.

        Args:
            task_id: Task ID to pause

        Returns:
            True if paused successfully
        """
        try:
            self.scheduler.pause_job(task_id)

            if task_id in self.active_tasks:
                self.active_tasks[task_id].is_active = False

            logger.info(f"Paused task {task_id}")
            return True

        except JobLookupError:
            logger.warning(f"Task {task_id} not found for pausing")
            return False

    async def resume_task(self, task_id: str) -> bool:
        """Resume a paused task.

        Args:
            task_id: Task ID to resume

        Returns:
            True if resumed successfully
        """
        try:
            self.scheduler.resume_job(task_id)

            if task_id in self.active_tasks:
                self.active_tasks[task_id].is_active = True

            logger.info(f"Resumed task {task_id}")
            return True

        except JobLookupError:
            logger.warning(f"Task {task_id} not found for resuming")
            return False

    async def execute_task(self, task: ScheduledTask) -> bool:
        """Execute a task immediately.

        Args:
            task: Task to execute

        Returns:
            True if execution started successfully
        """
        try:
            logger.info(f"Manually executing task {task.id}")
            await self._execute_scheduled_task(task.id)
            return True
        except Exception as e:
            logger.error(f"Failed to execute task {task.id}: {e}")
            return False

    def _create_trigger(self, task: ScheduledTask):
        """Create APScheduler trigger from scheduled task."""
        if task.schedule_type == ScheduleType.ONCE:
            # One-time execution
            run_time = task.next_run or datetime.utcnow()
            return DateTrigger(run_date=run_time, timezone=self.timezone)

        elif task.schedule_type == ScheduleType.DAILY:
            # Daily execution
            if task.schedule_time:
                hour, minute = map(int, task.schedule_time.split(':'))
                return CronTrigger(hour=hour, minute=minute, timezone=self.timezone)
            else:
                return IntervalTrigger(days=1, timezone=self.timezone)

        elif task.schedule_type == ScheduleType.WEEKLY:
            # Weekly execution
            if task.schedule_time:
                hour, minute = map(int, task.schedule_time.split(':'))
            else:
                hour, minute = 0, 0

            # Convert schedule_days to day_of_week string
            day_of_week = ','.join([str(d) for d in sorted(task.schedule_days)]) if task.schedule_days else '*'

            return CronTrigger(
                day_of_week=day_of_week,
                hour=hour,
                minute=minute,
                timezone=self.timezone
            )

        elif task.schedule_type == ScheduleType.HALF_WEEKLY:
            # Half-weekly: specific days of the week (like weekly but with custom days)
            if not task.schedule_days:
                raise ValueError("Half-weekly schedule requires schedule_days to be specified")

            if task.schedule_time:
                hour, minute = map(int, task.schedule_time.split(':'))
            else:
                hour, minute = 0, 0

            # Convert schedule_days to day_of_week string
            day_of_week = ','.join([str(d) for d in sorted(task.schedule_days)])

            return CronTrigger(
                day_of_week=day_of_week,
                hour=hour,
                minute=minute,
                timezone=self.timezone
            )

        elif task.schedule_type == ScheduleType.MONTHLY:
            # Monthly execution
            if task.schedule_time:
                hour, minute = map(int, task.schedule_time.split(':'))
            else:
                hour, minute = 0, 0

            day = task.created_at.day

            return CronTrigger(
                day=day,
                hour=hour,
                minute=minute,
                timezone=self.timezone
            )

        elif task.schedule_type == ScheduleType.CUSTOM:
            # Custom cron expression
            if not task.cron_expression:
                raise ValueError("Custom schedule requires cron_expression")

            return CronTrigger.from_crontab(task.cron_expression, timezone=self.timezone)

        else:
            raise ValueError(f"Unsupported schedule type: {task.schedule_type}")

    async def _execute_scheduled_task(self, task_id: str) -> None:
        """Execute a scheduled task (called by APScheduler).

        Args:
            task_id: ID of task to execute
        """
        if task_id not in self.active_tasks:
            logger.error(f"Task {task_id} not found in active tasks")
            return

        task = self.active_tasks[task_id]
        metadata = self.task_metadata.get(task_id)

        logger.info(f"Executing scheduled task {task_id}: {task.name}")

        start_time = datetime.utcnow()

        try:
            # Mark task as started
            task.mark_run_started()

            # Create summary task
            summary_task = SummaryTask(
                scheduled_task=task,
                channel_id=task.channel_id,
                guild_id=task.guild_id,
                summary_options=task.summary_options,
                destinations=task.destinations
            )

            # Execute task
            result = await self.executor.execute_summary_task(summary_task)

            # Update task status
            if result.success:
                task.mark_run_completed()
                logger.info(f"Task {task_id} completed successfully")
            else:
                task.mark_run_failed()
                logger.error(f"Task {task_id} failed: {result.error_message}")

            # Update metadata
            if metadata:
                duration = (datetime.utcnow() - start_time).total_seconds()
                metadata.update_execution(duration, failed=not result.success)
                metadata.next_execution = task.next_run

            # Persist updated task
            if self.persistence:
                await self.persistence.update_task(task)

        except Exception as e:
            logger.exception(f"Exception executing task {task_id}: {e}")

            # Handle task failure
            task.mark_run_failed()

            if metadata:
                duration = (datetime.utcnow() - start_time).total_seconds()
                metadata.update_execution(duration, failed=True)

            # Persist failure
            if self.persistence:
                await self.persistence.update_task(task)

            # Notify about failure
            await self.executor.handle_task_failure(
                task=task,
                error=e
            )

    async def _load_persisted_tasks(self) -> None:
        """Load persisted tasks from storage."""
        if not self.persistence:
            return

        try:
            tasks = await self.persistence.load_all_tasks()

            for task in tasks:
                if task.is_active:
                    try:
                        await self.schedule_task(task)
                    except Exception as e:
                        logger.error(f"Failed to restore task {task.id}: {e}")

            logger.info(f"Loaded {len(tasks)} persisted tasks")

        except Exception as e:
            logger.error(f"Failed to load persisted tasks: {e}")

    async def _persist_all_tasks(self) -> None:
        """Persist all active tasks to storage."""
        if not self.persistence:
            return

        try:
            for task in self.active_tasks.values():
                await self.persistence.update_task(task)

            logger.info(f"Persisted {len(self.active_tasks)} tasks")

        except Exception as e:
            logger.error(f"Failed to persist tasks: {e}")

    def get_scheduler_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics.

        Returns:
            Dictionary with scheduler statistics
        """
        jobs = self.scheduler.get_jobs()

        return {
            "running": self._running,
            "startup_complete": self._startup_complete,
            "active_tasks": len(self.active_tasks),
            "scheduled_jobs": len(jobs),
            "timezone": self.timezone,
            "next_run_times": [
                {
                    "task_id": job.id,
                    "task_name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                }
                for job in sorted(jobs, key=lambda j: j.next_run_time or datetime.max)[:10]
            ]
        }
