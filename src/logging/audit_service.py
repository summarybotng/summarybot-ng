"""
Audit logging service for tracking user actions and system events.

ADR-045: Audit Logging System

This service provides a non-blocking, async queue-based approach to audit logging
that doesn't slow down user operations.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from functools import wraps
from datetime import datetime, timedelta

from ..models.audit_log import AuditLog, AuditEventCategory, AuditSeverity, AuditSummary
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Global audit service instance
_audit_service: Optional["AuditService"] = None


class AuditService:
    """
    Central service for audit logging.

    Uses async queue for non-blocking operation. Logs are batched
    and flushed to the database periodically.
    """

    # Retention periods by category (days)
    DEFAULT_RETENTION = {
        AuditEventCategory.AUTH: 365,      # 1 year for auth events
        AuditEventCategory.ACCESS: 90,     # 90 days for access logs
        AuditEventCategory.ACTION: 365,    # 1 year for mutations
        AuditEventCategory.SOURCE: 365,    # 1 year for source changes
        AuditEventCategory.ADMIN: 730,     # 2 years for admin actions
        AuditEventCategory.SYSTEM: 90,     # 90 days for system events
    }

    # IP anonymization period
    IP_ANONYMIZATION_DAYS = 30

    def __init__(
        self,
        max_queue_size: int = 10000,
        flush_interval: float = 5.0,
        batch_size: int = 100,
    ):
        """
        Initialize the audit service.

        Args:
            max_queue_size: Maximum items in queue before dropping
            flush_interval: Seconds between flushes
            batch_size: Items to flush at once
        """
        self.max_queue_size = max_queue_size
        self.flush_interval = flush_interval
        self.batch_size = batch_size

        self._queue: asyncio.Queue[AuditLog] = asyncio.Queue(maxsize=max_queue_size)
        self._repository = None
        self._worker_task: Optional[asyncio.Task] = None
        self._started = False
        self._stopping = False

    async def start(self) -> None:
        """Start the audit service background worker."""
        if self._started:
            return

        try:
            from ..data import get_audit_repository
            self._repository = await get_audit_repository()
            logger.info("AuditService: Repository initialized")
        except Exception as e:
            logger.warning(f"AuditService: Could not initialize repository: {e}")
            # Continue without repository - logs will be queued

        self._worker_task = asyncio.create_task(self._flush_worker())
        self._started = True
        logger.info("AuditService: Started")

    async def stop(self) -> None:
        """Stop the service, flushing remaining logs."""
        if not self._started:
            return

        self._stopping = True

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._flush_queue()
        self._started = False
        logger.info("AuditService: Stopped")

    async def log(
        self,
        event_type: str,
        *,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        guild_id: Optional[str] = None,
        guild_name: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        changes: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Log an audit event.

        This method returns immediately; logging happens asynchronously.
        """
        entry = AuditLog.create(
            event_type=event_type,
            user_id=user_id,
            user_name=user_name,
            guild_id=guild_id,
            guild_name=guild_name,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            action=action,
            details=details,
            changes=changes,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            duration_ms=duration_ms,
            session_id=session_id,
        )

        # Non-blocking enqueue
        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            logger.warning(f"AuditService: Queue full, dropping event: {event_type}")

    async def log_from_request(
        self,
        event_type: str,
        request,  # FastAPI Request
        user: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        """
        Log an audit event with context extracted from a FastAPI request.
        """
        # Extract context from request
        ip_address = None
        user_agent = None
        request_id = None

        if request:
            if hasattr(request, "client") and request.client:
                ip_address = request.client.host
            if hasattr(request, "headers"):
                user_agent = request.headers.get("user-agent", "")[:500]
                request_id = request.headers.get("x-request-id")
            if hasattr(request, "state") and hasattr(request.state, "request_id"):
                request_id = request.state.request_id

        # Extract user info
        user_id = None
        user_name = None
        session_id = None
        if user:
            user_id = user.get("id")
            user_name = user.get("username")
            session_id = user.get("session_id")

        await self.log(
            event_type,
            user_id=user_id,
            user_name=user_name,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            **kwargs,
        )

    async def _flush_worker(self) -> None:
        """Background worker that flushes audit logs to database."""
        batch: List[AuditLog] = []

        while not self._stopping:
            try:
                # Collect items with timeout
                try:
                    item = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=self.flush_interval
                    )
                    batch.append(item)
                except asyncio.TimeoutError:
                    pass

                # Flush if batch is full or timeout elapsed
                if len(batch) >= self.batch_size or (batch and self._queue.empty()):
                    await self._flush_batch(batch)
                    batch = []

            except asyncio.CancelledError:
                # Final flush on shutdown
                if batch:
                    await self._flush_batch(batch)
                raise
            except Exception as e:
                logger.error(f"AuditService: Worker error: {e}")
                await asyncio.sleep(1)  # Prevent tight loop on errors

    async def _flush_batch(self, batch: List[AuditLog]) -> None:
        """Flush a batch of audit logs to the database."""
        if not batch:
            return

        if self._repository:
            try:
                count = await self._repository.save_batch(batch)
                logger.debug(f"AuditService: Flushed {count} entries")
            except Exception as e:
                logger.error(f"AuditService: Failed to flush batch: {e}")
                # TODO: Could write to fallback file
        else:
            logger.debug(f"AuditService: No repository, dropping {len(batch)} entries")

    async def _flush_queue(self) -> None:
        """Flush all remaining items in the queue."""
        batch: List[AuditLog] = []

        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                batch.append(item)
            except asyncio.QueueEmpty:
                break

        if batch:
            await self._flush_batch(batch)

    async def cleanup_old_entries(self) -> Dict[str, int]:
        """
        Remove expired audit logs based on retention policy.

        Returns dict of category -> deleted count.
        """
        if not self._repository:
            return {}

        deleted = {}
        now = utc_now_naive()

        for category, days in self.DEFAULT_RETENTION.items():
            cutoff = now - timedelta(days=days)
            try:
                count = await self._repository.delete_before(category, cutoff)
                deleted[category.value] = count
            except Exception as e:
                logger.error(f"AuditService: Cleanup error for {category.value}: {e}")

        # Anonymize old IP addresses
        try:
            ip_cutoff = now - timedelta(days=self.IP_ANONYMIZATION_DAYS)
            anonymized = await self._repository.anonymize_ips_before(ip_cutoff)
            deleted["_ip_anonymized"] = anonymized
        except Exception as e:
            logger.error(f"AuditService: IP anonymization error: {e}")

        # Log the cleanup
        total_deleted = sum(v for k, v in deleted.items() if not k.startswith("_"))
        if total_deleted > 0:
            await self.log(
                "system.retention.cleanup",
                details={
                    "deleted_by_category": {k: v for k, v in deleted.items() if not k.startswith("_")},
                    "total_deleted": total_deleted,
                    "ips_anonymized": deleted.get("_ip_anonymized", 0),
                },
            )

        return deleted


async def get_audit_service() -> AuditService:
    """Get the global audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
        await _audit_service.start()
    return _audit_service


async def audit_log(event_type: str, **kwargs) -> None:
    """
    Convenience function for audit logging.

    Usage:
        await audit_log("action.summary.generate", user_id="123", guild_id="456")
    """
    service = await get_audit_service()
    await service.log(event_type, **kwargs)


def audit_action(
    event_type: str,
    resource_type: Optional[str] = None,
    include_result: bool = False,
):
    """
    Decorator to automatically audit endpoint actions.

    Usage:
        @router.post("/guilds/{guild_id}/summaries/generate")
        @audit_action("action.summary.generate", resource_type="summary")
        async def generate_summary(...):
            ...

    Args:
        event_type: The audit event type
        resource_type: Type of resource being acted on
        include_result: Whether to include result details in audit
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            import time
            start_time = time.time()

            # Extract common parameters
            request = kwargs.get("request")
            user = kwargs.get("user", {})
            guild_id = kwargs.get("guild_id")
            resource_id = kwargs.get("summary_id") or kwargs.get("schedule_id") or kwargs.get("template_id") or kwargs.get("job_id")

            try:
                result = await func(*args, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)

                # Extract resource_id from result if available
                result_resource_id = None
                result_details = None
                if include_result and result:
                    if hasattr(result, "id"):
                        result_resource_id = result.id
                    elif hasattr(result, "summary_id"):
                        result_resource_id = result.summary_id
                    elif hasattr(result, "job_id"):
                        result_resource_id = result.job_id

                service = await get_audit_service()
                await service.log_from_request(
                    event_type,
                    request,
                    user=user,
                    guild_id=guild_id,
                    resource_type=resource_type,
                    resource_id=resource_id or result_resource_id,
                    success=True,
                    duration_ms=duration_ms,
                )

                return result

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)

                service = await get_audit_service()
                await service.log_from_request(
                    event_type,
                    request,
                    user=user,
                    guild_id=guild_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    success=False,
                    error_message=str(e)[:500],
                    duration_ms=duration_ms,
                )
                raise

        return wrapper
    return decorator
