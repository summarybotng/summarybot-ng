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
from ..models.summary_job import SummaryJob, JobType, JobStatus
from ..exceptions import (
    SummaryBotException, ConfigurationError, create_error_context
)

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Main task scheduler for automated summary generation and maintenance."""

    def __init__(self,
                 task_executor: TaskExecutor,
                 persistence: Optional[TaskPersistence] = None,
                 task_repository=None,
                 timezone: str = "UTC"):
        """Initialize task scheduler.

        Args:
            task_executor: Task executor instance
            persistence: Optional task persistence layer (file-based, legacy)
            task_repository: Optional database task repository (preferred)
            timezone: Timezone for scheduling (default: UTC)
        """
        self.executor = task_executor
        self.persistence = persistence
        self.task_repository = task_repository
        self.timezone = timezone

        # APScheduler instance
        self.scheduler = AsyncIOScheduler(timezone=timezone)

        # Task tracking
        self.active_tasks: Dict[str, ScheduledTask] = {}
        self.task_metadata: Dict[str, TaskMetadata] = {}

        # State
        self._running = False
        self._startup_complete = False

        # Guard against concurrent execution of the same task
        self._executing_tasks: set = set()

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

            # Persist to database (preferred) or file-based storage
            if self.task_repository:
                await self.task_repository.save_task(task)
                logger.debug(f"Saved task {task.id} to database")
            elif self.persistence:
                await self.persistence.save_task(task)
                logger.debug(f"Saved task {task.id} to file")

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
        """Cancel a scheduled task (pauses but keeps in storage).

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
                await self._persist_task(task)

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

    async def delete_task(self, task_id: str) -> bool:
        """Permanently delete a scheduled task.

        Args:
            task_id: ID of task to delete

        Returns:
            True if task was deleted, False if not found
        """
        try:
            # Remove from scheduler if active
            try:
                self.scheduler.remove_job(task_id)
            except JobLookupError:
                pass  # Not in scheduler, but may still be in persistence

            # Remove from active tracking
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]

            if task_id in self.task_metadata:
                del self.task_metadata[task_id]

            # Delete from persistence (database preferred, then files)
            deleted = False
            if self.task_repository:
                try:
                    deleted = await self.task_repository.delete_task(task_id)
                except Exception as e:
                    logger.warning(f"Failed to delete task {task_id} from database: {e}")

            if not deleted and self.persistence:
                deleted = await self.persistence.delete_task(task_id)

            if deleted:
                logger.info(f"Deleted task {task_id}")
            else:
                logger.warning(f"Task {task_id} not found in any storage")

            return deleted

        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {e}")
            return False

    async def get_scheduled_tasks(self, guild_id: Optional[str] = None, include_inactive: bool = True) -> List[ScheduledTask]:
        """Get all scheduled tasks, optionally filtered by guild.

        Args:
            guild_id: Optional guild ID to filter by
            include_inactive: Include inactive tasks from persistence (default True)

        Returns:
            List of scheduled tasks
        """
        # Start with active tasks
        tasks_by_id = {task.id: task for task in self.active_tasks.values()}

        # Include inactive tasks from persistence
        if include_inactive and self.persistence:
            try:
                all_persisted = await self.persistence.load_all_tasks()
                for task in all_persisted:
                    if task.id not in tasks_by_id:
                        tasks_by_id[task.id] = task
            except Exception as e:
                logger.warning(f"Failed to load inactive tasks: {e}")

        tasks = list(tasks_by_id.values())

        if guild_id:
            tasks = [task for task in tasks if task.guild_id == guild_id]

        return tasks

    async def get_task_async(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a single task by ID (async, includes inactive tasks).

        Args:
            task_id: Task ID

        Returns:
            ScheduledTask or None if not found
        """
        # Check active tasks first
        if task_id in self.active_tasks:
            return self.active_tasks[task_id]

        # Check persistence for inactive tasks
        if self.persistence:
            try:
                return await self.persistence.load_task(task_id)
            except Exception as e:
                logger.warning(f"Failed to load task {task_id} from persistence: {e}")

        return None

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a single task by ID (sync, active tasks only).

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
        # Preserve is_active from the updated task
        preserve_active = task.is_active

        # Cancel existing job if active (this sets is_active to False)
        if task.id in self.active_tasks:
            await self.cancel_task(task.id)

        # Restore the intended is_active value
        task.is_active = preserve_active

        # Re-schedule with new settings (or just persist if inactive)
        if task.is_active:
            await self.schedule_task(task)
        else:
            # Just persist the updated inactive task
            if self.persistence:
                await self.persistence.save_task(task)

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

        elif task.schedule_type == ScheduleType.FIFTEEN_MINUTES:
            # Every 15 minutes
            return IntervalTrigger(minutes=15, timezone=self.timezone)

        elif task.schedule_type == ScheduleType.HOURLY:
            # Every hour
            return IntervalTrigger(hours=1, timezone=self.timezone)

        elif task.schedule_type == ScheduleType.EVERY_4_HOURS:
            # Every 4 hours
            return IntervalTrigger(hours=4, timezone=self.timezone)

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

        # Guard against concurrent execution of the same task
        if task_id in self._executing_tasks:
            logger.warning(f"Task {task_id} is already running, skipping concurrent execution")
            return

        task = self.active_tasks[task_id]
        metadata = self.task_metadata.get(task_id)

        # Mark task as executing
        self._executing_tasks.add(task_id)

        logger.info(f"Executing scheduled task {task_id}: {task.name}")

        start_time = datetime.utcnow()

        # ADR-013: Create job record for tracking
        import secrets
        job_id = f"job_{secrets.token_urlsafe(16)}"
        job = SummaryJob(
            id=job_id,
            guild_id=task.guild_id,
            job_type=JobType.SCHEDULED,
            status=JobStatus.PENDING,
            scope=task.scope.value if hasattr(task, 'scope') and task.scope else "channel",
            channel_ids=task.channel_ids if task.channel_ids else ([task.channel_id] if task.channel_id else []),
            category_id=task.category_id if hasattr(task, 'category_id') else None,
            schedule_id=task.id,
            metadata={"task_name": task.name},
        )

        # Persist job to database
        job_repo = None
        try:
            from ..data.repositories import get_summary_job_repository
            job_repo = await get_summary_job_repository()
            if job_repo:
                await job_repo.save(job)
                logger.info(f"[{job_id}] Created scheduled job record")
        except Exception as e:
            logger.warning(f"[{job_id}] Failed to persist job: {e}")

        try:
            # Mark job as RUNNING
            job.start()
            job.update_progress(0, 3, "Starting scheduled task")
            if job_repo:
                try:
                    await job_repo.update(job)
                except Exception:
                    pass

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

            # Update job progress
            job.update_progress(1, 3, "Executing summary task")
            if job_repo:
                try:
                    await job_repo.update(job)
                except Exception:
                    pass

            # Execute task
            result = await self.executor.execute_summary_task(summary_task)

            # Update task status
            if result.success:
                task.mark_run_completed()
                logger.info(f"Task {task_id} completed successfully")

                # ADR-013: Mark job as completed
                job.complete(result.summary_result.id if result.summary_result else None)
                job.update_progress(3, 3, "Complete")
                if job_repo:
                    try:
                        await job_repo.update(job)
                        logger.info(f"[{job_id}] Job marked COMPLETED")
                    except Exception as e:
                        logger.warning(f"[{job_id}] Failed to update job completion: {e}")
            else:
                task.mark_run_failed()
                logger.error(f"Task {task_id} failed: {result.error_message}")

                # ADR-013: Mark job as failed
                job.fail(result.error_message or "Unknown error")
                if job_repo:
                    try:
                        await job_repo.update(job)
                        logger.info(f"[{job_id}] Job marked FAILED")
                    except Exception as e:
                        logger.warning(f"[{job_id}] Failed to update job failure: {e}")

            # Update metadata
            if metadata:
                duration = (datetime.utcnow() - start_time).total_seconds()
                metadata.update_execution(duration, failed=not result.success)
                metadata.next_execution = task.next_run

            # Persist updated task
            await self._persist_task(task)

        except Exception as e:
            logger.exception(f"Exception executing task {task_id}: {e}")

            # Handle task failure
            task.mark_run_failed()

            # ADR-013: Mark job as failed
            job.fail(str(e))
            if job_repo:
                try:
                    await job_repo.update(job)
                    logger.info(f"[{job_id}] Job marked FAILED (exception)")
                except Exception as update_err:
                    logger.warning(f"[{job_id}] Failed to update job: {update_err}")

            if metadata:
                duration = (datetime.utcnow() - start_time).total_seconds()
                metadata.update_execution(duration, failed=True)

            # Persist failure
            await self._persist_task(task)

            # Notify about failure
            await self.executor.handle_task_failure(
                task=task,
                error=e
            )

        finally:
            # Always remove from executing tasks when done
            self._executing_tasks.discard(task_id)

    async def _load_persisted_tasks(self) -> None:
        """Load persisted tasks from storage (database preferred, then files)."""
        tasks = []

        # Try database first
        if self.task_repository:
            try:
                tasks = await self.task_repository.get_active_tasks()
                logger.info(f"Loading {len(tasks)} tasks from database")
            except Exception as e:
                logger.error(f"Failed to load tasks from database: {e}")

        # Fall back to file-based persistence
        if not tasks and self.persistence:
            try:
                tasks = await self.persistence.load_all_tasks()
                logger.info(f"Loading {len(tasks)} tasks from files")
            except Exception as e:
                logger.error(f"Failed to load tasks from files: {e}")

        if not tasks:
            logger.info("No persisted tasks to load")
            return

        # Schedule each active task
        loaded_count = 0
        for task in tasks:
            if task.is_active:
                try:
                    await self.schedule_task(task)
                    loaded_count += 1
                except Exception as e:
                    logger.error(f"Failed to restore task {task.id}: {e}")

        logger.info(f"Restored {loaded_count} active tasks from {len(tasks)} total")

    async def _persist_task(self, task: ScheduledTask) -> None:
        """Persist a single task to storage (database preferred)."""
        try:
            if self.task_repository:
                await self.task_repository.save_task(task)
            elif self.persistence:
                await self.persistence.update_task(task)
        except Exception as e:
            logger.error(f"Failed to persist task {task.id}: {e}")

    async def _persist_all_tasks(self) -> None:
        """Persist all active tasks to storage."""
        if not self.task_repository and not self.persistence:
            return

        try:
            for task in self.active_tasks.values():
                await self._persist_task(task)

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
