"""
Automatic cleanup of expired logs.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from .repository import CommandLogRepository
from .models import LoggingConfig
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class LogCleanupService:
    """
    Service for cleaning up expired command logs.

    Enforces retention policy by deleting old logs.
    """

    def __init__(
        self,
        repository: CommandLogRepository,
        config: LoggingConfig
    ):
        """
        Initialize cleanup service.

        Args:
            repository: Command log repository
            config: Logging configuration
        """
        self.repository = repository
        self.config = config

    async def cleanup_expired_logs(self) -> int:
        """
        Delete logs older than retention period.

        Returns:
            Count of deleted records
        """
        if not self.config.enabled:
            return 0

        cutoff_date = utc_now_naive() - timedelta(days=self.config.retention_days)

        logger.info(f"Starting log cleanup. Deleting logs older than {cutoff_date}")

        try:
            deleted_count = await self.repository.delete_older_than(cutoff_date)

            logger.info(f"Log cleanup completed. Deleted {deleted_count} records")

            return deleted_count

        except Exception as e:
            logger.error(f"Log cleanup failed: {e}")
            return 0

    async def cleanup_by_guild(
        self,
        guild_id: str,
        retention_days: Optional[int] = None
    ) -> int:
        """
        Clean up logs for a specific guild.

        Allows per-guild retention policies.

        Args:
            guild_id: Guild ID to clean up
            retention_days: Optional custom retention period

        Returns:
            Count of deleted records
        """
        days = retention_days or self.config.retention_days
        cutoff_date = utc_now_naive() - timedelta(days=days)

        query = """
        DELETE FROM command_logs
        WHERE guild_id = ? AND started_at < ?
        """

        try:
            result = await self.repository.connection.execute(
                query,
                (guild_id, cutoff_date.isoformat())
            )
            deleted = getattr(result, 'rowcount', 0)
            logger.info(f"Deleted {deleted} logs for guild {guild_id}")
            return deleted
        except Exception as e:
            logger.error(f"Guild cleanup failed for {guild_id}: {e}")
            return 0
