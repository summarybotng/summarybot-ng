"""
Platform Fetcher Protocol (ADR-051).

Abstract base class defining the contract for platform-specific message fetching.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable
from datetime import datetime

from .types import FetchResult, PlatformContext, ChannelInfo


class PlatformFetcher(ABC):
    """
    Abstract base class for platform-specific message fetching.

    Implementations provide message retrieval, user resolution, and channel
    operations for their specific platform (Discord, Slack, etc.).
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return platform identifier: 'discord', 'slack', 'whatsapp', etc."""
        ...

    @property
    @abstractmethod
    def platform_display_name(self) -> str:
        """Return human-readable platform name: 'Discord', 'Slack', etc."""
        ...

    @property
    @abstractmethod
    def server_id(self) -> str:
        """Return the server/workspace ID this fetcher is bound to."""
        ...

    @property
    @abstractmethod
    def server_name(self) -> str:
        """Return the server/workspace name."""
        ...

    @abstractmethod
    async def fetch_messages(
        self,
        channel_ids: List[str],
        start_time: datetime,
        end_time: datetime,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> FetchResult:
        """
        Fetch messages from specified channels within time range.

        Args:
            channel_ids: List of channel IDs to fetch from
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)
            job_id: Optional job ID for tracking
            progress_callback: Optional callback(current, total, message) for progress

        Returns:
            FetchResult with messages, channel names, user names, and errors
        """
        ...

    @abstractmethod
    async def resolve_channels(
        self,
        scope: str,
        channel_ids: Optional[List[str]] = None,
        category_id: Optional[str] = None,
    ) -> List[str]:
        """
        Resolve channel IDs based on scope.

        Args:
            scope: "channel", "category", or "guild"/"workspace"
            channel_ids: Required for "channel" scope
            category_id: Required for "category" scope (Discord only)

        Returns:
            List of resolved channel IDs

        Raises:
            ValueError: If required parameters missing for scope
        """
        ...

    @abstractmethod
    async def get_channels(self) -> List[ChannelInfo]:
        """
        Get all accessible channels in the server/workspace.

        Returns:
            List of ChannelInfo for all summarizable channels
        """
        ...

    @abstractmethod
    async def get_context(
        self,
        channel_ids: List[str],
    ) -> PlatformContext:
        """
        Build summarization context with display names.

        Args:
            channel_ids: Channels being summarized

        Returns:
            PlatformContext with server/channel names
        """
        ...

    @abstractmethod
    def get_archive_source_key(self) -> str:
        """
        Return archive key for this platform/server.

        Returns:
            Key like 'discord:123456' or 'slack:T12345'
        """
        ...

    async def close(self) -> None:
        """
        Cleanup resources (HTTP clients, connections, etc.).

        Default implementation does nothing. Override if cleanup needed.
        """
        pass

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        await self.close()
        return False
