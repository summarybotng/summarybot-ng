"""
Base sync provider interface.

Phase 9: Google Drive Sync - Base component
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SyncStatus(Enum):
    """Status of a sync operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class SyncConfig:
    """Base configuration for sync providers."""
    enabled: bool = False
    sync_frequency: str = "hourly"  # "realtime", "hourly", "daily"
    sync_deletes: bool = False
    conflict_strategy: str = "local_wins"  # "local_wins", "remote_wins", "newest"


@dataclass
class SyncResult:
    """Result of a sync operation."""
    status: SyncStatus
    files_synced: int = 0
    files_failed: int = 0
    bytes_uploaded: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "files_synced": self.files_synced,
            "files_failed": self.files_failed,
            "bytes_uploaded": self.bytes_uploaded,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "errors": self.errors,
        }


class SyncProvider(ABC):
    """Abstract base class for sync providers."""

    @abstractmethod
    async def sync(self, source_path: Path) -> SyncResult:
        """
        Sync local files to remote storage.

        Args:
            source_path: Local path to sync

        Returns:
            Sync result
        """
        pass

    @abstractmethod
    async def download(self, remote_path: str, local_path: Path) -> bool:
        """
        Download a file from remote storage.

        Args:
            remote_path: Remote file path
            local_path: Local destination path

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def delete(self, remote_path: str) -> bool:
        """
        Delete a file from remote storage.

        Args:
            remote_path: Remote file path

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def list_files(self, remote_path: str) -> List[Dict[str, Any]]:
        """
        List files in remote storage.

        Args:
            remote_path: Remote directory path

        Returns:
            List of file info dictionaries
        """
        pass

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """
        Get provider status and quota info.

        Returns:
            Status information
        """
        pass
