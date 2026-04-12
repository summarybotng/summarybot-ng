# ADR-045: Audit Logging System

**Status:** Proposed
**Date:** 2026-04-12
**Depends on:** ADR-044 (addresses P2-004: No audit trail)
**Related:** ADR-026 (source ownership), ADR-039 (problem reporting)

---

## 1. Context

System owners currently have no visibility into:
- Who is logging into the system
- What actions users are taking
- When critical operations occur
- How the system is being used

This creates problems for:
- **Security**: Can't detect unauthorized access or suspicious activity
- **Compliance**: Can't prove who did what when (GDPR, SOC2, audit requirements)
- **Debugging**: Can't trace user-reported issues to specific actions
- **Support**: Can't help users understand what happened to their data

### Current State

The existing `ErrorTracker` captures operational errors but NOT:
- Successful operations
- Authentication events
- User actions
- Configuration changes
- Data access patterns

---

## 2. Decision

Implement a comprehensive **Audit Logging System** that captures authentication events, user actions, and system operations with sufficient detail for security monitoring and compliance.

### 2.1 Design Principles

1. **Non-blocking**: Audit logging must not slow down user operations
2. **Complete**: Capture all security-relevant events
3. **Immutable**: Audit logs cannot be modified or deleted by users
4. **Queryable**: Easy to search and filter for investigations
5. **Retention-aware**: Configurable retention with automatic cleanup
6. **Privacy-conscious**: Don't log sensitive data (passwords, tokens, PII in content)

---

## 3. Event Categories

### 3.1 Authentication Events

| Event | Trigger | Data Captured |
|-------|---------|---------------|
| `auth.login.success` | User completes Discord OAuth | user_id, ip, user_agent, guilds_count |
| `auth.login.failure` | OAuth fails or denied | error_type, ip, user_agent |
| `auth.logout` | User logs out | user_id, session_duration |
| `auth.token.refresh` | JWT refreshed | user_id, ip |
| `auth.token.expired` | JWT expired, user redirected | user_id |
| `auth.token.revoked` | Admin revokes token | user_id, revoked_by |

### 3.2 Resource Access Events

| Event | Trigger | Data Captured |
|-------|---------|---------------|
| `access.guild.view` | User views guild dashboard | user_id, guild_id |
| `access.summary.view` | User views summary detail | user_id, guild_id, summary_id |
| `access.summary.list` | User lists summaries | user_id, guild_id, filter_params |
| `access.job.view` | User views job status | user_id, guild_id, job_id |
| `access.schedule.view` | User views schedule | user_id, guild_id, schedule_id |
| `access.feed.view` | User views feed | user_id, guild_id, feed_id |
| `access.denied` | User attempts unauthorized access | user_id, resource, reason |

### 3.3 Mutation Events

| Event | Trigger | Data Captured |
|-------|---------|---------------|
| `action.summary.generate` | User triggers generation | user_id, guild_id, channel_ids, options |
| `action.summary.regenerate` | User regenerates summary | user_id, guild_id, summary_id, changes |
| `action.summary.delete` | User deletes summary | user_id, guild_id, summary_id |
| `action.summary.bulk_delete` | User bulk deletes | user_id, guild_id, count, summary_ids |
| `action.summary.push` | User pushes to channel | user_id, guild_id, summary_id, channel_id |
| `action.job.retry` | User retries job | user_id, guild_id, job_id, new_job_id |
| `action.job.cancel` | User cancels job | user_id, guild_id, job_id |
| `action.schedule.create` | User creates schedule | user_id, guild_id, schedule_config |
| `action.schedule.update` | User updates schedule | user_id, guild_id, schedule_id, changes |
| `action.schedule.delete` | User deletes schedule | user_id, guild_id, schedule_id |
| `action.template.create` | User creates template | user_id, guild_id, template_name |
| `action.template.update` | User updates template | user_id, guild_id, template_id |
| `action.template.delete` | User deletes template | user_id, guild_id, template_id |
| `action.webhook.create` | User creates webhook | user_id, guild_id, webhook_url_masked |
| `action.webhook.delete` | User deletes webhook | user_id, guild_id, webhook_id |
| `action.feed.create` | User creates feed | user_id, guild_id, feed_config |
| `action.feed.update` | User updates feed | user_id, guild_id, feed_id |
| `action.feed.delete` | User deletes feed | user_id, guild_id, feed_id |

### 3.4 Source Management Events

| Event | Trigger | Data Captured |
|-------|---------|---------------|
| `source.link` | Source linked to guild | user_id, guild_id, source_key, source_type |
| `source.unlink` | Source unlinked | user_id, guild_id, source_key |
| `source.import` | WhatsApp/archive imported | user_id, guild_id, source_key, message_count |

### 3.5 Admin Events

| Event | Trigger | Data Captured |
|-------|---------|---------------|
| `admin.config.update` | System config changed | user_id, config_key, old_value_hash, new_value_hash |
| `admin.user.impersonate` | Admin impersonates user | admin_id, target_user_id |
| `admin.data.export` | Data export requested | user_id, guild_id, export_type |
| `admin.data.purge` | Data purge executed | admin_id, guild_id, scope |

### 3.6 System Events

| Event | Trigger | Data Captured |
|-------|---------|---------------|
| `system.startup` | Server starts | version, environment |
| `system.shutdown` | Server stops gracefully | uptime, reason |
| `system.job.scheduled.run` | Scheduled job executes | schedule_id, guild_id, job_id |
| `system.job.scheduled.fail` | Scheduled job fails | schedule_id, guild_id, error |
| `system.retention.cleanup` | Retention cleanup runs | deleted_count, freed_bytes |

---

## 4. Data Model

### 4.1 AuditLog Model

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

class AuditEventCategory(Enum):
    """Category of audit event."""
    AUTH = "auth"           # Authentication events
    ACCESS = "access"       # Resource access
    ACTION = "action"       # User actions/mutations
    SOURCE = "source"       # Source management
    ADMIN = "admin"         # Administrative actions
    SYSTEM = "system"       # System events


class AuditSeverity(Enum):
    """Severity/importance of audit event."""
    DEBUG = "debug"         # Verbose logging (disabled by default)
    INFO = "info"           # Normal operations
    NOTICE = "notice"       # Notable events (first login, etc.)
    WARNING = "warning"     # Potentially suspicious
    ALERT = "alert"         # Security-relevant (failed auth, access denied)


@dataclass
class AuditLog:
    """Immutable audit log entry."""
    id: str                              # Unique identifier (ulid for ordering)
    event_type: str                      # Full event type (e.g., "auth.login.success")
    category: AuditEventCategory         # Event category
    severity: AuditSeverity = AuditSeverity.INFO

    # Actor (who)
    user_id: Optional[str] = None        # Discord user ID
    user_name: Optional[str] = None      # Username for display (denormalized)
    session_id: Optional[str] = None     # JWT session identifier

    # Context (where)
    guild_id: Optional[str] = None       # Guild context
    guild_name: Optional[str] = None     # Guild name (denormalized)
    ip_address: Optional[str] = None     # Client IP (anonymized after 30 days)
    user_agent: Optional[str] = None     # Browser/client info

    # Target (what)
    resource_type: Optional[str] = None  # "summary", "schedule", "template", etc.
    resource_id: Optional[str] = None    # ID of affected resource
    resource_name: Optional[str] = None  # Name for display

    # Details (how)
    action: Optional[str] = None         # Specific action taken
    details: Dict[str, Any] = field(default_factory=dict)  # Additional context
    changes: Optional[Dict[str, Any]] = None  # Before/after for mutations

    # Result
    success: bool = True                 # Whether action succeeded
    error_message: Optional[str] = None  # Error if failed

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None     # Correlation ID for request tracing
    duration_ms: Optional[int] = None    # Operation duration

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "category": self.category.value,
            "severity": self.severity.value,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "session_id": self.session_id,
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "action": self.action,
            "details": self.details,
            "changes": self.changes,
            "success": self.success,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id,
            "duration_ms": self.duration_ms,
        }
```

### 4.2 Database Schema

```sql
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY,                    -- ULID for time-ordered IDs
    event_type TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',

    -- Actor
    user_id TEXT,
    user_name TEXT,
    session_id TEXT,

    -- Context
    guild_id TEXT,
    guild_name TEXT,
    ip_address TEXT,                        -- Anonymized after retention period
    user_agent TEXT,

    -- Target
    resource_type TEXT,
    resource_id TEXT,
    resource_name TEXT,

    -- Details
    action TEXT,
    details JSON,
    changes JSON,

    -- Result
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,

    -- Metadata
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    request_id TEXT,
    duration_ms INTEGER,

    -- Indexes for common queries
    CONSTRAINT audit_logs_category_check CHECK (category IN ('auth', 'access', 'action', 'source', 'admin', 'system'))
);

-- Indexes for efficient querying
CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX idx_audit_user ON audit_logs(user_id, timestamp DESC);
CREATE INDEX idx_audit_guild ON audit_logs(guild_id, timestamp DESC);
CREATE INDEX idx_audit_event_type ON audit_logs(event_type, timestamp DESC);
CREATE INDEX idx_audit_category ON audit_logs(category, timestamp DESC);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_severity ON audit_logs(severity, timestamp DESC) WHERE severity IN ('warning', 'alert');
CREATE INDEX idx_audit_session ON audit_logs(session_id);

-- Partial index for failed actions (security monitoring)
CREATE INDEX idx_audit_failures ON audit_logs(timestamp DESC) WHERE success = FALSE;
```

---

## 5. Service Architecture

### 5.1 AuditService

```python
class AuditService:
    """
    Central service for audit logging.

    Uses async queue for non-blocking operation.
    """

    def __init__(self, retention_days: int = 90):
        self.retention_days = retention_days
        self._queue: asyncio.Queue[AuditLog] = asyncio.Queue(maxsize=10000)
        self._repository: Optional[AuditLogRepository] = None
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the audit service background worker."""
        self._repository = await get_audit_repository()
        self._worker_task = asyncio.create_task(self._flush_worker())

    async def stop(self) -> None:
        """Stop the service, flushing remaining logs."""
        if self._worker_task:
            self._worker_task.cancel()
            # Flush remaining items
            await self._flush_queue()

    async def log(
        self,
        event_type: str,
        *,
        user_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        request: Optional[Request] = None,  # FastAPI request for context
    ) -> None:
        """
        Log an audit event.

        This method returns immediately; logging happens asynchronously.
        """
        from ulid import ULID

        # Parse event type
        parts = event_type.split(".")
        category = AuditEventCategory(parts[0])

        # Determine severity
        severity = self._determine_severity(event_type, success)

        # Extract request context
        ip_address = None
        user_agent = None
        request_id = None
        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent", "")[:500]
            request_id = request.headers.get("x-request-id")

        entry = AuditLog(
            id=str(ULID()),
            event_type=event_type,
            category=category,
            severity=severity,
            user_id=user_id,
            guild_id=guild_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            success=success,
            error_message=error_message,
            request_id=request_id,
        )

        # Non-blocking enqueue
        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            logger.warning("Audit queue full, dropping event: %s", event_type)

    def _determine_severity(self, event_type: str, success: bool) -> AuditSeverity:
        """Determine severity based on event type and success."""
        if not success:
            if "auth" in event_type or "access.denied" in event_type:
                return AuditSeverity.ALERT
            return AuditSeverity.WARNING

        if "admin" in event_type:
            return AuditSeverity.NOTICE
        if "delete" in event_type or "purge" in event_type:
            return AuditSeverity.NOTICE

        return AuditSeverity.INFO

    async def _flush_worker(self) -> None:
        """Background worker that flushes audit logs to database."""
        batch: List[AuditLog] = []
        batch_timeout = 5.0  # Flush every 5 seconds or 100 items

        while True:
            try:
                # Collect items with timeout
                try:
                    item = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=batch_timeout
                    )
                    batch.append(item)
                except asyncio.TimeoutError:
                    pass

                # Flush if batch is full or timeout elapsed
                if len(batch) >= 100 or (batch and self._queue.empty()):
                    await self._flush_batch(batch)
                    batch = []

            except asyncio.CancelledError:
                # Final flush on shutdown
                if batch:
                    await self._flush_batch(batch)
                raise

    async def _flush_batch(self, batch: List[AuditLog]) -> None:
        """Flush a batch of audit logs to the database."""
        if not batch or not self._repository:
            return

        try:
            await self._repository.save_batch(batch)
        except Exception as e:
            logger.error(f"Failed to flush audit batch: {e}")
            # Don't lose logs - could write to fallback file


# Global instance
_audit_service: Optional[AuditService] = None


async def get_audit_service() -> AuditService:
    """Get the global audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
        await _audit_service.start()
    return _audit_service


async def audit_log(event_type: str, **kwargs) -> None:
    """Convenience function for audit logging."""
    service = await get_audit_service()
    await service.log(event_type, **kwargs)
```

### 5.2 Middleware Integration

```python
# src/dashboard/middleware.py

from starlette.middleware.base import BaseHTTPMiddleware
from .services.audit import audit_log

class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware to capture request-level audit events."""

    # Routes that trigger access logging
    ACCESS_PATTERNS = {
        r"/guilds/(\w+)/summaries$": "access.summary.list",
        r"/guilds/(\w+)/summaries/(\w+)$": "access.summary.view",
        r"/guilds/(\w+)/jobs$": "access.job.list",
        r"/guilds/(\w+)/jobs/(\w+)$": "access.job.view",
    }

    async def dispatch(self, request: Request, call_next):
        # Generate request ID for correlation
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start_time) * 1000)

        # Log access events for matching routes
        await self._maybe_log_access(request, response, duration_ms)

        return response

    async def _maybe_log_access(self, request: Request, response, duration_ms: int):
        """Log access event if route matches."""
        # Implementation details...
```

### 5.3 Decorator for Action Logging

```python
def audit_action(event_type: str, resource_type: Optional[str] = None):
    """
    Decorator to automatically audit endpoint actions.

    Usage:
        @router.post("/guilds/{guild_id}/summaries/generate")
        @audit_action("action.summary.generate", resource_type="summary")
        async def generate_summary(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request") or next(
                (a for a in args if isinstance(a, Request)), None
            )
            user = kwargs.get("user", {})
            guild_id = kwargs.get("guild_id")

            try:
                result = await func(*args, **kwargs)

                # Log success
                await audit_log(
                    event_type,
                    user_id=user.get("id"),
                    guild_id=guild_id,
                    resource_type=resource_type,
                    success=True,
                    request=request,
                )

                return result

            except Exception as e:
                # Log failure
                await audit_log(
                    event_type,
                    user_id=user.get("id"),
                    guild_id=guild_id,
                    resource_type=resource_type,
                    success=False,
                    error_message=str(e)[:500],
                    request=request,
                )
                raise

        return wrapper
    return decorator
```

---

## 6. API Endpoints

### 6.1 Audit Log Endpoints (Admin Only)

```python
@router.get("/admin/audit-logs")
@require_system_admin
async def list_audit_logs(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_id: Optional[str] = None,
    guild_id: Optional[str] = None,
    event_type: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    success: Optional[bool] = None,
    page: int = 1,
    limit: int = 50,
) -> AuditLogListResponse:
    """List audit logs with filtering."""

@router.get("/admin/audit-logs/{log_id}")
@require_system_admin
async def get_audit_log(log_id: str) -> AuditLogDetail:
    """Get single audit log entry."""

@router.get("/admin/audit-logs/user/{user_id}")
@require_system_admin
async def get_user_activity(
    user_id: str,
    days: int = 30,
) -> UserActivityReport:
    """Get activity summary for a specific user."""

@router.get("/admin/audit-logs/summary")
@require_system_admin
async def get_audit_summary(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    guild_id: Optional[str] = None,
) -> AuditSummaryResponse:
    """Get aggregated audit statistics."""

@router.post("/admin/audit-logs/export")
@require_system_admin
async def export_audit_logs(
    body: AuditExportRequest,
) -> AuditExportResponse:
    """Export audit logs for compliance (CSV/JSON)."""
```

### 6.2 Per-Guild Audit Logs (Guild Admins)

```python
@router.get("/guilds/{guild_id}/audit-logs")
@require_guild_admin
async def list_guild_audit_logs(
    guild_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user: dict = Depends(get_current_user),
) -> AuditLogListResponse:
    """List audit logs for a specific guild."""
```

---

## 7. Dashboard UI

### 7.1 Admin Audit Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Audit Logs                                                    [Export] │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Filters:                                                               │
│  ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌─────────────┐           │
│  │Date Range│ │ Event Type ▼ │ │ User ▼    │ │ Guild ▼     │  [Apply]  │
│  └──────────┘ └──────────────┘ └───────────┘ └─────────────┘           │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ 2026-04-12 14:32:15  auth.login.success                     INFO   ││
│  │ User: alice#1234  IP: 192.168.x.x  Session started                 ││
│  ├────────────────────────────────────────────────────────────────────┤│
│  │ 2026-04-12 14:33:02  action.summary.generate               INFO   ││
│  │ User: alice#1234  Guild: Agentics Foundation                       ││
│  │ Generated summary for #general, #dev (24h period)                  ││
│  ├────────────────────────────────────────────────────────────────────┤│
│  │ 2026-04-12 14:35:18  access.denied                        ALERT   ││
│  │ User: bob#5678  Attempted: Guild "Secret Server"                   ││
│  │ Reason: User not member of guild                                   ││
│  ├────────────────────────────────────────────────────────────────────┤│
│  │ 2026-04-12 14:40:55  action.schedule.delete               NOTICE  ││
│  │ User: alice#1234  Guild: Agentics Foundation                       ││
│  │ Deleted schedule "Daily Digest" (sched_abc123)                     ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  Page 1 of 42                                         [< Prev] [Next >] │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 User Activity View

```
┌─────────────────────────────────────────────────────────────────────────┐
│  User Activity: alice#1234                                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Summary (Last 30 Days)                                                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ 47           │ │ 12           │ │ 3            │ │ 0            │   │
│  │ Logins       │ │ Summaries    │ │ Schedules    │ │ Failures     │   │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │
│                                                                         │
│  Guilds Accessed:                                                       │
│  • Agentics Foundation (42 actions)                                     │
│  • Test Server (5 actions)                                              │
│                                                                         │
│  Recent Activity:                                                       │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ Today                                                               ││
│  │   14:40 - Deleted schedule "Daily Digest"                          ││
│  │   14:33 - Generated summary (#general, #dev)                       ││
│  │   14:32 - Logged in from 192.168.x.x                               ││
│  │ Yesterday                                                           ││
│  │   09:15 - Created schedule "Weekly Recap"                          ││
│  │   09:10 - Viewed 3 summaries                                       ││
│  └────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Privacy & Retention

### 8.1 Data Minimization

| Field | Retention | Anonymization |
|-------|-----------|---------------|
| `ip_address` | 30 days | Hash after retention |
| `user_agent` | 90 days | Truncate to browser family |
| `details` (PII) | Never log | Redact at capture time |
| `changes` (content) | Truncate | Max 1KB, no message content |

### 8.2 Retention Policy

```python
class RetentionPolicy:
    """Configurable retention for audit logs."""

    # Default retention periods
    DEFAULT_RETENTION = {
        AuditEventCategory.AUTH: 365,      # 1 year for auth events
        AuditEventCategory.ACCESS: 90,     # 90 days for access logs
        AuditEventCategory.ACTION: 365,    # 1 year for mutations
        AuditEventCategory.SOURCE: 365,    # 1 year for source changes
        AuditEventCategory.ADMIN: 730,     # 2 years for admin actions
        AuditEventCategory.SYSTEM: 90,     # 90 days for system events
    }

    # Security-relevant events kept longer
    EXTENDED_RETENTION_EVENTS = [
        "auth.login.failure",
        "access.denied",
        "admin.*",
    ]
    EXTENDED_RETENTION_DAYS = 730  # 2 years
```

### 8.3 Cleanup Job

```python
async def cleanup_audit_logs() -> int:
    """
    Remove expired audit logs based on retention policy.

    Run daily via scheduler.
    """
    repository = await get_audit_repository()
    deleted_count = 0

    for category, days in RetentionPolicy.DEFAULT_RETENTION.items():
        cutoff = datetime.utcnow() - timedelta(days=days)
        count = await repository.delete_before(category, cutoff)
        deleted_count += count

    # Anonymize IP addresses older than 30 days
    ip_cutoff = datetime.utcnow() - timedelta(days=30)
    await repository.anonymize_ips_before(ip_cutoff)

    # Log cleanup
    await audit_log(
        "system.retention.cleanup",
        details={"deleted_count": deleted_count},
    )

    return deleted_count
```

---

## 9. Implementation Plan

### Phase 1: Core Infrastructure (1-2 weeks)
- [ ] Create `AuditLog` model
- [ ] Create database migration
- [ ] Implement `AuditService` with async queue
- [ ] Create `AuditLogRepository`

### Phase 2: Authentication Events (1 week)
- [ ] Add logging to Discord OAuth callback
- [ ] Add logging to JWT refresh
- [ ] Add logging to logout
- [ ] Add logging to auth failures

### Phase 3: Action Events (1-2 weeks)
- [ ] Create `@audit_action` decorator
- [ ] Apply to summary endpoints
- [ ] Apply to schedule endpoints
- [ ] Apply to template endpoints
- [ ] Apply to feed endpoints

### Phase 4: Access Events (1 week)
- [ ] Create `AuditMiddleware`
- [ ] Configure access logging routes
- [ ] Add access denied logging

### Phase 5: API & UI (1-2 weeks)
- [ ] Create admin audit API endpoints
- [ ] Create guild audit API endpoints
- [ ] Build audit log list page
- [ ] Build user activity view
- [ ] Add export functionality

### Phase 6: Retention & Cleanup (1 week)
- [ ] Implement retention policies
- [ ] Create cleanup scheduler job
- [ ] Implement IP anonymization
- [ ] Add retention config UI

---

## 10. Security Considerations

1. **Access Control**: Audit logs are admin-only or guild-admin scoped
2. **Immutability**: No update/delete API for audit logs (only retention cleanup)
3. **Non-repudiation**: Logs include enough detail to prove who did what
4. **Tamper Detection**: Consider adding log hashing for critical environments
5. **Rate Limiting**: Protect audit endpoints from abuse
6. **Log Injection**: Sanitize all user-provided data before logging

---

## 11. Consequences

### Positive
- Full visibility into system usage
- Security monitoring and alerting capability
- Compliance audit trail
- User activity debugging
- Usage analytics foundation

### Negative
- Additional storage requirements (~1KB per event)
- Slight latency increase (mitigated by async)
- Privacy considerations require careful handling
- Additional code in all endpoints

### Neutral
- Requires ongoing retention management
- May surface previously unknown access patterns
- Needs documentation for system owners

---

## 12. Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `src/models/audit_log.py` | AuditLog model and enums |
| `src/logging/audit_service.py` | AuditService with async queue |
| `src/data/sqlite/audit_repository.py` | SQLite repository |
| `src/data/migrations/045_audit_logs.sql` | Database schema |
| `src/dashboard/routes/audit.py` | API endpoints |
| `src/dashboard/middleware/audit.py` | Request middleware |
| `src/frontend/src/pages/AuditLogs.tsx` | Admin UI |
| `src/frontend/src/components/audit/*` | UI components |

### Modified Files
| File | Changes |
|------|---------|
| `src/dashboard/auth.py` | Add auth event logging |
| `src/dashboard/routes/summaries.py` | Add action decorators |
| `src/dashboard/routes/schedules.py` | Add action decorators |
| `src/dashboard/routes/templates.py` | Add action decorators |
| `src/scheduling/scheduler.py` | Log scheduled job execution |
| `src/main.py` | Initialize audit service |

---

## 13. References

- [ADR-044: Deferred Technical Debt Tracker](./ADR-044-deferred-technical-debt-tracker.md) - P2-004
- [ADR-026: Multi-Platform Source Architecture](./026-multi-platform-source-architecture.md) - Source ownership
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [GDPR Article 30](https://gdpr-info.eu/art-30-gdpr/) - Records of processing activities
- [SOC 2 Logging Requirements](https://www.aicpa.org/soc)
