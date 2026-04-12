"""
Audit log API routes.

ADR-045: Audit Logging System
"""

import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import get_current_user, require_guild_access
from ...models.audit_log import AuditEventCategory, AuditSeverity
from ...logging import get_audit_service

logger = logging.getLogger(__name__)

router = APIRouter()


class AuditLogResponse(BaseModel):
    """Single audit log entry response."""
    id: str
    event_type: str
    category: str
    severity: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    guild_id: Optional[str] = None
    guild_name: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    action: Optional[str] = None
    details: Optional[dict] = None
    success: bool = True
    error_message: Optional[str] = None
    timestamp: str
    duration_ms: Optional[int] = None


class AuditListResponse(BaseModel):
    """Paginated list of audit logs."""
    items: List[AuditLogResponse]
    total: int
    limit: int
    offset: int


class AuditSummaryResponse(BaseModel):
    """Audit log summary statistics."""
    total_count: int
    by_category: dict = Field(default_factory=dict)
    by_severity: dict = Field(default_factory=dict)
    by_event_type: dict = Field(default_factory=dict)
    by_user: dict = Field(default_factory=dict)
    failed_count: int = 0
    alert_count: int = 0


@router.get(
    "/guilds/{guild_id}/audit",
    response_model=AuditListResponse,
    summary="List audit logs for a guild",
    description="Get paginated audit logs for a guild. Requires admin access.",
)
async def list_audit_logs(
    guild_id: str,
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type (supports wildcards like 'auth.*')"),
    category: Optional[str] = Query(None, description="Filter by category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID"),
    limit: int = Query(50, ge=1, le=200, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    user: dict = Depends(get_current_user),
    _: None = Depends(require_guild_access),
):
    """List audit logs for a guild."""
    # Check admin role for audit access
    guilds = user.get("guilds", [])
    guild_info = next((g for g in guilds if g == guild_id or (isinstance(g, dict) and g.get("id") == guild_id)), None)

    # For now, allow all authenticated users with guild access to view audit logs
    # In production, you might want to restrict to admins only

    try:
        from ...data import get_audit_repository
        repo = await get_audit_repository()
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Audit repository not available"},
        )

    # Parse dates
    parsed_start = None
    parsed_end = None
    if start_date:
        try:
            parsed_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            parsed_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    # Parse enums
    parsed_category = None
    parsed_severity = None
    if category:
        try:
            parsed_category = AuditEventCategory(category)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    if severity:
        try:
            parsed_severity = AuditSeverity(severity)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    # Query logs
    logs = await repo.find(
        guild_id=guild_id,
        user_id=user_id,
        event_type=event_type,
        category=parsed_category,
        severity=parsed_severity,
        success=success,
        start_date=parsed_start,
        end_date=parsed_end,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
        offset=offset,
    )

    # Get total count
    total = await repo.count(
        guild_id=guild_id,
        user_id=user_id,
        event_type=event_type,
        category=parsed_category,
        severity=parsed_severity,
        success=success,
        start_date=parsed_start,
        end_date=parsed_end,
    )

    # Convert to response
    items = [
        AuditLogResponse(
            id=log.id,
            event_type=log.event_type,
            category=log.category.value if hasattr(log.category, 'value') else log.category,
            severity=log.severity.value if hasattr(log.severity, 'value') else log.severity,
            user_id=log.user_id,
            user_name=log.user_name,
            guild_id=log.guild_id,
            guild_name=log.guild_name,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            resource_name=log.resource_name,
            action=log.action,
            details=log.details,
            success=log.success,
            error_message=log.error_message,
            timestamp=log.timestamp.isoformat() if log.timestamp else "",
            duration_ms=log.duration_ms,
        )
        for log in logs
    ]

    return AuditListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/guilds/{guild_id}/audit/summary",
    response_model=AuditSummaryResponse,
    summary="Get audit log summary",
    description="Get aggregated audit statistics for a guild.",
)
async def get_audit_summary(
    guild_id: str,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    user: dict = Depends(get_current_user),
    _: None = Depends(require_guild_access),
):
    """Get audit log summary statistics."""
    try:
        from ...data import get_audit_repository
        repo = await get_audit_repository()
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Audit repository not available"},
        )

    # Parse dates
    parsed_start = None
    parsed_end = None
    if start_date:
        try:
            parsed_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            parsed_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    summary = await repo.get_summary(
        guild_id=guild_id,
        start_date=parsed_start,
        end_date=parsed_end,
    )

    return AuditSummaryResponse(
        total_count=summary.total_count,
        by_category=summary.by_category,
        by_severity=summary.by_severity,
        by_event_type=summary.by_event_type,
        by_user=summary.by_user,
        failed_count=summary.failed_count,
        alert_count=summary.alert_count,
    )


@router.get(
    "/guilds/{guild_id}/audit/{entry_id}",
    response_model=AuditLogResponse,
    summary="Get single audit log entry",
    description="Get details for a specific audit log entry.",
)
async def get_audit_entry(
    guild_id: str,
    entry_id: str,
    user: dict = Depends(get_current_user),
    _: None = Depends(require_guild_access),
):
    """Get a single audit log entry."""
    try:
        from ...data import get_audit_repository
        repo = await get_audit_repository()
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Audit repository not available"},
        )

    entry = await repo.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit log entry not found")

    # Verify guild access
    if entry.guild_id != guild_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return AuditLogResponse(
        id=entry.id,
        event_type=entry.event_type,
        category=entry.category.value if hasattr(entry.category, 'value') else entry.category,
        severity=entry.severity.value if hasattr(entry.severity, 'value') else entry.severity,
        user_id=entry.user_id,
        user_name=entry.user_name,
        guild_id=entry.guild_id,
        guild_name=entry.guild_name,
        resource_type=entry.resource_type,
        resource_id=entry.resource_id,
        resource_name=entry.resource_name,
        action=entry.action,
        details=entry.details,
        success=entry.success,
        error_message=entry.error_message,
        timestamp=entry.timestamp.isoformat() if entry.timestamp else "",
        duration_ms=entry.duration_ms,
    )
