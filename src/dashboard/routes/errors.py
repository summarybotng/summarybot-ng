"""
Error log routes for dashboard API.

Provides endpoints for viewing and managing operational errors.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ..auth import get_current_user
from ..models import (
    ErrorLogsResponse,
    ErrorLogItem,
    ErrorLogDetail,
    ErrorCountsResponse,
    ResolveErrorRequest,
    BulkResolveRequest,
    BulkResolveResponse,
    ErrorRetryResponse,
    ErrorExportResponse,
    ErrorResponse,
)
from . import get_discord_bot

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/errors/health",
    summary="Error system health check",
    description="Check if error tracking system is working.",
)
async def error_health_check():
    """Check error tracking health."""
    result = {
        "repository_available": False,
        "tracker_initialized": False,
        "table_exists": False,
        "error": None,
    }

    # Check repository
    try:
        from ...data import get_error_repository as _get_repo
        repo = await _get_repo()
        result["repository_available"] = repo is not None
        if repo:
            # Try a simple query to check table exists
            errors = await repo.get_recent_errors(limit=1)
            result["table_exists"] = True
    except Exception as e:
        result["error"] = str(e)

    # Check tracker
    try:
        from ...logging.error_tracker import get_error_tracker
        tracker = get_error_tracker()
        result["tracker_initialized"] = tracker._initialized
        result["pending_errors"] = len(tracker._pending_errors)
    except Exception as e:
        result["tracker_error"] = str(e)

    return result


async def get_error_repository():
    """Get error repository instance."""
    try:
        from ...data import get_error_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


def _check_guild_access(guild_id: str, user: dict):
    """Check user has access to guild."""
    if guild_id not in user.get("guilds", []):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You don't have permission to view this guild"},
        )


def _get_channel_name(guild_id: str, channel_id: Optional[str]) -> Optional[str]:
    """Get channel name from guild."""
    if not channel_id:
        return None
    bot = get_discord_bot()
    if not bot or not bot.client:
        return None
    guild = bot.client.get_guild(int(guild_id))
    if not guild:
        return None
    # Handle Slack channel IDs (non-numeric, e.g., "C09F2NNJRB7")
    try:
        channel = guild.get_channel(int(channel_id))
        return channel.name if channel else None
    except ValueError:
        # Non-numeric channel ID (likely Slack) - return ID as name
        return channel_id


def _error_to_list_item(error, guild_id: Optional[str] = None) -> ErrorLogItem:
    """Convert ErrorLog to API list item."""
    channel_name = None
    if guild_id and error.channel_id:
        channel_name = _get_channel_name(guild_id, error.channel_id)

    return ErrorLogItem(
        id=error.id,
        guild_id=error.guild_id,
        channel_id=error.channel_id,
        channel_name=channel_name,
        error_type=error.error_type.value if hasattr(error.error_type, 'value') else error.error_type,
        severity=error.severity.value if hasattr(error.severity, 'value') else error.severity,
        error_code=error.error_code,
        message=error.message,
        operation=error.operation,
        created_at=error.created_at,
        is_resolved=error.is_resolved,
    )


def _error_to_detail(error, guild_id: Optional[str] = None) -> ErrorLogDetail:
    """Convert ErrorLog to API detail response."""
    channel_name = None
    if guild_id and error.channel_id:
        channel_name = _get_channel_name(guild_id, error.channel_id)

    return ErrorLogDetail(
        id=error.id,
        guild_id=error.guild_id,
        channel_id=error.channel_id,
        channel_name=channel_name,
        error_type=error.error_type.value if hasattr(error.error_type, 'value') else error.error_type,
        severity=error.severity.value if hasattr(error.severity, 'value') else error.severity,
        error_code=error.error_code,
        message=error.message,
        details=error.details,
        operation=error.operation,
        user_id=error.user_id,
        stack_trace=error.stack_trace,
        created_at=error.created_at,
        resolved_at=error.resolved_at,
        resolution_notes=error.resolution_notes,
    )


# =============================================================================
# STATIC PATH ROUTES - Must come before dynamic {error_id} routes
# =============================================================================

@router.get(
    "/guilds/{guild_id}/errors",
    response_model=ErrorLogsResponse,
    summary="List errors",
    description="Get recent errors for a guild with optional filtering.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def list_errors(
    guild_id: str = Path(..., description="Discord guild ID"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    include_resolved: bool = Query(False, description="Include resolved errors"),
    limit: int = Query(50, ge=1, le=200, description="Number of items to return"),
    user: dict = Depends(get_current_user),
):
    """List errors for a guild."""
    _check_guild_access(guild_id, user)

    error_repo = await get_error_repository()
    if not error_repo:
        return ErrorLogsResponse(errors=[], total=0, unresolved_count=0)

    # Convert string filters to enums
    from ...models.error_log import ErrorType, ErrorSeverity
    type_filter = None
    severity_filter = None

    if error_type:
        try:
            type_filter = ErrorType(error_type)
        except ValueError:
            pass

    if severity:
        try:
            severity_filter = ErrorSeverity(severity)
        except ValueError:
            pass

    # Fetch errors
    errors = await error_repo.get_errors_by_guild(
        guild_id=guild_id,
        limit=limit,
        error_type=type_filter,
        severity=severity_filter,
        include_resolved=include_resolved,
    )

    # Count unresolved
    all_errors = await error_repo.get_errors_by_guild(
        guild_id=guild_id,
        limit=1000,
        include_resolved=False,
    )
    unresolved_count = len(all_errors)

    error_items = [_error_to_list_item(e, guild_id) for e in errors]

    return ErrorLogsResponse(
        errors=error_items,
        total=len(errors),
        unresolved_count=unresolved_count,
    )


@router.get(
    "/guilds/{guild_id}/errors/counts",
    response_model=ErrorCountsResponse,
    summary="Get error counts",
    description="Get error counts grouped by type for the last N hours.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def get_error_counts(
    guild_id: str = Path(..., description="Discord guild ID"),
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    user: dict = Depends(get_current_user),
):
    """Get error counts by type."""
    _check_guild_access(guild_id, user)

    error_repo = await get_error_repository()
    if not error_repo:
        return ErrorCountsResponse(counts={}, total=0, period_hours=hours)

    counts = await error_repo.get_error_counts(guild_id=guild_id, hours=hours)
    total = sum(counts.values())

    return ErrorCountsResponse(
        counts=counts,
        total=total,
        period_hours=hours,
    )


@router.post(
    "/guilds/{guild_id}/errors/bulk-resolve",
    response_model=BulkResolveResponse,
    summary="Bulk resolve errors",
    description="Resolve all unresolved errors of a specific type for a guild.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid error type"},
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def bulk_resolve_errors(
    body: BulkResolveRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Bulk resolve errors by type."""
    _check_guild_access(guild_id, user)

    error_repo = await get_error_repository()
    if not error_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    # Convert string to ErrorType enum
    from ...models.error_log import ErrorType
    try:
        error_type = ErrorType(body.error_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ERROR_TYPE", "message": f"Invalid error type: {body.error_type}"},
        )

    # Bulk resolve
    resolved_count = await error_repo.bulk_resolve_by_type(
        guild_id=guild_id,
        error_type=error_type,
        notes=body.notes,
    )

    logger.info(f"Bulk resolved {resolved_count} errors of type {body.error_type} for guild {guild_id}")

    return BulkResolveResponse(resolved_count=resolved_count)


@router.get(
    "/guilds/{guild_id}/errors/export",
    response_model=ErrorExportResponse,
    summary="Export errors",
    description="Export errors for a guild in CSV or JSON format.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def export_errors(
    guild_id: str = Path(..., description="Discord guild ID"),
    format: str = Query("csv", description="Export format: csv or json"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
    include_resolved: bool = Query(True, description="Include resolved errors"),
    limit: int = Query(500, ge=1, le=1000, description="Maximum errors to export"),
    user: dict = Depends(get_current_user),
):
    """Export errors in CSV or JSON format."""
    _check_guild_access(guild_id, user)

    error_repo = await get_error_repository()
    if not error_repo:
        return ErrorExportResponse(format=format, count=0, data="")

    # Convert filter
    from ...models.error_log import ErrorType
    type_filter = None
    if error_type:
        try:
            type_filter = ErrorType(error_type)
        except ValueError:
            pass

    # Fetch errors
    errors = await error_repo.get_errors_by_guild(
        guild_id=guild_id,
        limit=limit,
        error_type=type_filter,
        include_resolved=include_resolved,
    )

    if format.lower() == "json":
        import json
        error_dicts = []
        for err in errors:
            error_dicts.append({
                "id": err.id,
                "error_type": err.error_type.value if hasattr(err.error_type, 'value') else err.error_type,
                "severity": err.severity.value if hasattr(err.severity, 'value') else err.severity,
                "error_code": err.error_code,
                "message": err.message,
                "operation": err.operation,
                "channel_id": err.channel_id,
                "created_at": err.created_at.isoformat() if err.created_at else None,
                "resolved_at": err.resolved_at.isoformat() if err.resolved_at else None,
                "resolution_notes": err.resolution_notes,
                "details": err.details,
            })
        data = json.dumps(error_dicts, indent=2)
    else:
        # CSV format
        import io
        import csv
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "ID", "Error Type", "Severity", "Error Code", "Message",
            "Operation", "Channel ID", "Created At", "Resolved At", "Resolution Notes"
        ])

        # Data rows
        for err in errors:
            writer.writerow([
                err.id,
                err.error_type.value if hasattr(err.error_type, 'value') else err.error_type,
                err.severity.value if hasattr(err.severity, 'value') else err.severity,
                err.error_code or "",
                err.message,
                err.operation,
                err.channel_id or "",
                err.created_at.isoformat() if err.created_at else "",
                err.resolved_at.isoformat() if err.resolved_at else "",
                err.resolution_notes or "",
            ])

        data = output.getvalue()

    logger.info(f"Exported {len(errors)} errors for guild {guild_id} in {format} format")

    return ErrorExportResponse(
        format=format.lower(),
        count=len(errors),
        data=data,
    )


# =============================================================================
# DYNAMIC PATH ROUTES - Must come after static routes to avoid conflicts
# =============================================================================

@router.get(
    "/guilds/{guild_id}/errors/{error_id}",
    response_model=ErrorLogDetail,
    summary="Get error details",
    description="Get full details of a specific error.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Error not found"},
    },
)
async def get_error(
    guild_id: str = Path(..., description="Discord guild ID"),
    error_id: str = Path(..., description="Error ID"),
    user: dict = Depends(get_current_user),
):
    """Get error details."""
    _check_guild_access(guild_id, user)

    error_repo = await get_error_repository()
    if not error_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    error = await error_repo.get_error(error_id)
    if not error or error.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Error not found"},
        )

    return _error_to_detail(error, guild_id)


@router.post(
    "/guilds/{guild_id}/errors/{error_id}/resolve",
    response_model=ErrorLogDetail,
    summary="Resolve error",
    description="Mark an error as resolved with optional notes.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Error not found"},
    },
)
async def resolve_error(
    body: ResolveErrorRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    error_id: str = Path(..., description="Error ID"),
    user: dict = Depends(get_current_user),
):
    """Resolve an error."""
    _check_guild_access(guild_id, user)

    error_repo = await get_error_repository()
    if not error_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    # Verify error exists and belongs to guild
    error = await error_repo.get_error(error_id)
    if not error or error.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Error not found"},
        )

    # Resolve the error
    success = await error_repo.resolve_error(error_id, body.notes)
    if not success:
        raise HTTPException(
            status_code=500,
            detail={"code": "RESOLVE_FAILED", "message": "Failed to resolve error"},
        )

    # Return updated error
    error = await error_repo.get_error(error_id)
    return _error_to_detail(error, guild_id)


# Error types that can potentially be retried
RETRYABLE_ERROR_TYPES = {
    "summarization_error": {
        "retryable": True,
        "description": "Summary generation can be retried with the same parameters",
    },
    "discord_rate_limit": {
        "retryable": True,
        "description": "Rate limit has likely expired, operation can be retried",
    },
    "discord_connection": {
        "retryable": True,
        "description": "Connection issue may be resolved, operation can be retried",
    },
    "api_error": {
        "retryable": True,
        "description": "External API may be available again",
    },
    "webhook_error": {
        "retryable": True,
        "description": "Webhook delivery can be retried",
    },
}


@router.post(
    "/guilds/{guild_id}/errors/{error_id}/retry",
    response_model=ErrorRetryResponse,
    summary="Request error retry",
    description="Get retry context for an error. Returns whether the error is retryable and the context needed.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Error not found"},
    },
)
async def retry_error(
    guild_id: str = Path(..., description="Discord guild ID"),
    error_id: str = Path(..., description="Error ID"),
    user: dict = Depends(get_current_user),
):
    """Get retry context for an error."""
    _check_guild_access(guild_id, user)

    error_repo = await get_error_repository()
    if not error_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    # Verify error exists and belongs to guild
    error = await error_repo.get_error(error_id)
    if not error or error.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Error not found"},
        )

    # Check if error type is retryable
    error_type_str = error.error_type.value if hasattr(error.error_type, 'value') else error.error_type
    retry_info = RETRYABLE_ERROR_TYPES.get(error_type_str)

    if not retry_info or not retry_info["retryable"]:
        return ErrorRetryResponse(
            error_id=error_id,
            retryable=False,
            retry_context=None,
            message=f"Error type '{error_type_str}' cannot be automatically retried",
        )

    # Build retry context from error details
    retry_context = {
        "operation": error.operation,
        "error_type": error_type_str,
        "channel_id": error.channel_id,
        **error.details,  # Include any stored details (task_id, scope, etc.)
    }

    return ErrorRetryResponse(
        error_id=error_id,
        retryable=True,
        retry_context=retry_context,
        message=retry_info["description"],
    )
