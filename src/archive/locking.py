"""
Generation lock management for preventing duplicate summary generation.

Implements ADR-006 Section 7: Generation Locking.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import uuid

from .models import GenerationLock, SummaryStatus

logger = logging.getLogger(__name__)


class LockManager:
    """
    Manages locks for summary generation.

    Prevents concurrent generation of the same summary through
    file-based locking with automatic expiration.
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        lock_ttl_seconds: int = DEFAULT_TTL_SECONDS,
        worker_id: Optional[str] = None
    ):
        """
        Initialize lock manager.

        Args:
            lock_ttl_seconds: Lock time-to-live in seconds
            worker_id: Unique identifier for this worker
        """
        self.lock_ttl_seconds = lock_ttl_seconds
        self.worker_id = worker_id or f"worker-{os.getpid()}"

    async def acquire_lock(
        self,
        meta_path: Path,
        job_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Attempt to acquire lock for generation.

        Args:
            meta_path: Path to the .meta.json file
            job_id: Optional job ID (generated if not provided)

        Returns:
            Job ID if lock acquired, None if already locked
        """
        job_id = job_id or str(uuid.uuid4())

        try:
            # Read existing metadata if present
            if meta_path.exists():
                meta = self._read_meta(meta_path)

                # Already complete
                if meta.get("status") == SummaryStatus.COMPLETE.value:
                    logger.debug(f"Summary already complete: {meta_path}")
                    return None

                # Check existing lock
                if meta.get("status") == SummaryStatus.GENERATING.value:
                    lock_data = meta.get("lock", {})
                    if lock_data:
                        expires_at = datetime.fromisoformat(
                            lock_data.get("expires_at", "2000-01-01")
                        )

                        # Lock still valid
                        if datetime.utcnow() < expires_at:
                            logger.debug(
                                f"Lock held by {lock_data.get('job_id')}: {meta_path}"
                            )
                            return None

                        # Lock expired - we can take over
                        logger.warning(
                            f"Taking over expired lock from {lock_data.get('job_id')}"
                        )

            # Acquire lock
            lock = GenerationLock(
                job_id=job_id,
                acquired_at=datetime.utcnow(),
                acquired_by=self.worker_id,
                expires_at=datetime.utcnow() + timedelta(seconds=self.lock_ttl_seconds),
            )

            meta = self._create_lock_meta(lock)
            self._atomic_write(meta_path, meta)

            logger.info(f"Acquired lock {job_id} for {meta_path}")
            return job_id

        except Exception as e:
            logger.error(f"Failed to acquire lock for {meta_path}: {e}")
            return None

    async def release_lock(
        self,
        meta_path: Path,
        status: SummaryStatus,
        summary_data: Optional[dict] = None
    ) -> None:
        """
        Release lock and update status.

        Args:
            meta_path: Path to the .meta.json file
            status: New status for the summary
            summary_data: Optional additional metadata to merge
        """
        try:
            meta = self._read_meta(meta_path) if meta_path.exists() else {}
            meta["status"] = status.value
            meta["lock"] = None

            if summary_data:
                meta.update(summary_data)

            self._atomic_write(meta_path, meta)
            logger.info(f"Released lock for {meta_path}, status={status.value}")

        except Exception as e:
            logger.error(f"Failed to release lock for {meta_path}: {e}")
            raise

    async def extend_lock(
        self,
        meta_path: Path,
        job_id: str,
        extension_seconds: Optional[int] = None
    ) -> bool:
        """
        Extend an existing lock.

        Args:
            meta_path: Path to the .meta.json file
            job_id: Job ID that holds the lock
            extension_seconds: Additional time (default: original TTL)

        Returns:
            True if lock was extended
        """
        try:
            if not meta_path.exists():
                return False

            meta = self._read_meta(meta_path)
            lock_data = meta.get("lock", {})

            # Verify we own the lock
            if lock_data.get("job_id") != job_id:
                logger.warning(f"Cannot extend lock: not owned by {job_id}")
                return False

            # Extend expiration
            extension = extension_seconds or self.lock_ttl_seconds
            new_expiry = datetime.utcnow() + timedelta(seconds=extension)
            lock_data["expires_at"] = new_expiry.isoformat()
            meta["lock"] = lock_data

            self._atomic_write(meta_path, meta)
            logger.debug(f"Extended lock {job_id} until {new_expiry}")
            return True

        except Exception as e:
            logger.error(f"Failed to extend lock: {e}")
            return False

    async def check_lock(self, meta_path: Path) -> Optional[GenerationLock]:
        """
        Check if a path is locked.

        Args:
            meta_path: Path to check

        Returns:
            Lock info if locked and valid, None otherwise
        """
        try:
            if not meta_path.exists():
                return None

            meta = self._read_meta(meta_path)

            if meta.get("status") != SummaryStatus.GENERATING.value:
                return None

            lock_data = meta.get("lock")
            if not lock_data:
                return None

            lock = GenerationLock.from_dict(lock_data)

            if lock.is_expired():
                return None

            return lock

        except Exception as e:
            logger.error(f"Failed to check lock: {e}")
            return None

    async def force_release(self, meta_path: Path) -> bool:
        """
        Force release a lock (admin action).

        Args:
            meta_path: Path to the .meta.json file

        Returns:
            True if lock was released
        """
        try:
            if not meta_path.exists():
                return False

            meta = self._read_meta(meta_path)
            meta["lock"] = None
            meta["status"] = SummaryStatus.PENDING.value

            self._atomic_write(meta_path, meta)
            logger.warning(f"Force released lock for {meta_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to force release lock: {e}")
            return False

    async def cleanup_expired_locks(self, archive_root: Path) -> int:
        """
        Clean up expired locks across the archive.

        Args:
            archive_root: Root path of the archive

        Returns:
            Number of locks cleaned up
        """
        cleaned = 0

        for meta_path in archive_root.glob("**/*.meta.json"):
            try:
                meta = self._read_meta(meta_path)

                if meta.get("status") != SummaryStatus.GENERATING.value:
                    continue

                lock_data = meta.get("lock")
                if not lock_data:
                    continue

                lock = GenerationLock.from_dict(lock_data)
                if lock.is_expired():
                    meta["lock"] = None
                    meta["status"] = SummaryStatus.PENDING.value
                    self._atomic_write(meta_path, meta)
                    cleaned += 1
                    logger.info(f"Cleaned up expired lock: {meta_path}")

            except Exception as e:
                logger.error(f"Error cleaning lock {meta_path}: {e}")

        return cleaned

    def _read_meta(self, path: Path) -> dict:
        """Read metadata from JSON file."""
        with open(path, 'r') as f:
            return json.load(f)

    def _create_lock_meta(self, lock: GenerationLock) -> dict:
        """Create initial locked metadata."""
        return {
            "status": SummaryStatus.GENERATING.value,
            "lock": lock.to_dict(),
        }

    def _atomic_write(self, path: Path, data: dict) -> None:
        """Write atomically using rename."""
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file in same directory
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, 'w') as f:
            json.dump(data, f, indent=2)

        # Atomic rename (POSIX)
        tmp_path.rename(path)
