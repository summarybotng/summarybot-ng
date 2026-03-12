"""
Fluent query interface for command logs.
"""

from typing import Optional, List
from datetime import datetime, timedelta

from .models import CommandLog, CommandType, CommandStatus
from .repository import CommandLogRepository
from src.utils.time import utc_now_naive


class CommandLogQuery:
    """
    Fluent query builder for command logs.

    Usage:
        logs = await CommandLogQuery(repository) \
            .by_guild("123456") \
            .in_last_hours(24) \
            .with_status(CommandStatus.FAILED) \
            .limit(50) \
            .execute()
    """

    def __init__(self, repository: CommandLogRepository):
        """
        Initialize query builder.

        Args:
            repository: Command log repository
        """
        self.repository = repository
        self._guild_id: Optional[str] = None
        self._user_id: Optional[str] = None
        self._channel_id: Optional[str] = None
        self._command_type: Optional[CommandType] = None
        self._status: Optional[CommandStatus] = None
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        self._limit: int = 100
        self._offset: int = 0

    def by_guild(self, guild_id: str) -> 'CommandLogQuery':
        """Filter by guild ID."""
        self._guild_id = guild_id
        return self

    def by_user(self, user_id: str) -> 'CommandLogQuery':
        """Filter by user ID."""
        self._user_id = user_id
        return self

    def by_channel(self, channel_id: str) -> 'CommandLogQuery':
        """Filter by channel ID."""
        self._channel_id = channel_id
        return self

    def of_type(self, command_type: CommandType) -> 'CommandLogQuery':
        """Filter by command type."""
        self._command_type = command_type
        return self

    def with_status(self, status: CommandStatus) -> 'CommandLogQuery':
        """Filter by execution status."""
        self._status = status
        return self

    def in_time_range(
        self,
        start: datetime,
        end: datetime
    ) -> 'CommandLogQuery':
        """Filter by time range."""
        self._start_time = start
        self._end_time = end
        return self

    def in_last_hours(self, hours: int) -> 'CommandLogQuery':
        """Filter to last N hours."""
        self._end_time = utc_now_naive()
        self._start_time = self._end_time - timedelta(hours=hours)
        return self

    def in_last_days(self, days: int) -> 'CommandLogQuery':
        """Filter to last N days."""
        self._end_time = utc_now_naive()
        self._start_time = self._end_time - timedelta(days=days)
        return self

    def limit(self, limit: int) -> 'CommandLogQuery':
        """Set result limit."""
        self._limit = limit
        return self

    def offset(self, offset: int) -> 'CommandLogQuery':
        """Set result offset for pagination."""
        self._offset = offset
        return self

    def page(self, page_num: int, page_size: int = 50) -> 'CommandLogQuery':
        """Set pagination by page number."""
        self._limit = page_size
        self._offset = (page_num - 1) * page_size
        return self

    async def execute(self) -> List[CommandLog]:
        """Execute query and return results."""
        return await self.repository.find(
            guild_id=self._guild_id,
            user_id=self._user_id,
            channel_id=self._channel_id,
            command_type=self._command_type,
            status=self._status,
            start_time=self._start_time,
            end_time=self._end_time,
            limit=self._limit,
            offset=self._offset
        )

    async def count(self) -> int:
        """Count matching records without fetching."""
        return await self.repository.count(
            guild_id=self._guild_id,
            user_id=self._user_id,
            command_type=self._command_type,
            status=self._status,
            start_time=self._start_time,
            end_time=self._end_time
        )

    async def first(self) -> Optional[CommandLog]:
        """Get first matching result."""
        results = await self.limit(1).execute()
        return results[0] if results else None
