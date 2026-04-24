"""
Google Admin Groups routes for dashboard API (ADR-050).

Manages Google Workspace group-based admin access for guilds.
System admins or guild admins can configure which Google groups
grant admin permissions for a given guild.
"""

import os
import re
import logging
import secrets
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, field_validator

from ..auth import get_current_user, require_guild_admin, is_guild_admin
from ...logging import get_audit_service

logger = logging.getLogger(__name__)

router = APIRouter()

# System admin emails from environment (comma-separated)
SYSTEM_ADMIN_EMAILS_VAR = "SYSTEM_ADMIN_EMAILS"


def _get_system_admin_emails() -> set:
    """Get set of system admin email addresses from environment."""
    emails_str = os.environ.get(SYSTEM_ADMIN_EMAILS_VAR, "")
    if not emails_str:
        return set()
    return {email.strip().lower() for email in emails_str.split(",") if email.strip()}


def _is_system_admin(user: dict) -> bool:
    """Check if user is a system admin based on their email."""
    system_admins = _get_system_admin_emails()
    if not system_admins:
        return False

    # Check for Google SSO email in JWT
    user_email = user.get("email", "").lower()
    return user_email in system_admins


def _check_admin_access(guild_id: str, user: dict):
    """Check user has admin access to guild (guild admin OR system admin).

    Args:
        guild_id: Discord guild ID
        user: JWT payload dict

    Raises:
        HTTPException: If user lacks admin access
    """
    # System admins can manage any guild
    if _is_system_admin(user):
        return

    # Check guild access first
    if guild_id not in user.get("guilds", []):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You don't have permission to access this guild"},
        )

    # Check guild admin permission
    if not is_guild_admin(user, guild_id):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "This action requires admin permissions"},
        )


# =============================================================================
# Request/Response Models
# =============================================================================


class GoogleAdminGroupResponse(BaseModel):
    """Response model for a Google admin group mapping."""

    id: str
    guild_id: str
    google_group_email: str
    created_at: datetime
    created_by: Optional[str] = None


class GoogleAdminGroupsListResponse(BaseModel):
    """Response for listing Google admin groups."""

    groups: List[GoogleAdminGroupResponse]
    total: int


class AddGoogleAdminGroupRequest(BaseModel):
    """Request to add a Google admin group mapping."""

    google_group_email: str = Field(
        ...,
        min_length=5,
        max_length=254,
        description="Google Workspace group email address",
    )

    @field_validator("google_group_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        v = v.strip().lower()

        # Basic email format validation
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")

        return v


# =============================================================================
# Repository Access
# =============================================================================


async def _get_google_admin_groups_repo():
    """Get the Google admin groups repository.

    For now, we use direct database access since the table is simple.
    This could be refactored to use a proper repository class later.
    """
    try:
        from ...data.repositories import get_repository_factory

        factory = get_repository_factory()
        connection = await factory.get_connection()
        return connection
    except RuntimeError:
        return None


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/guilds/{guild_id}/google-admin-groups",
    response_model=GoogleAdminGroupsListResponse,
    summary="List Google admin groups",
    description="Get all Google Workspace groups that grant admin access for a guild.",
    responses={
        403: {"description": "No permission"},
    },
)
async def list_google_admin_groups(
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """List Google admin groups for a guild."""
    _check_admin_access(guild_id, user)

    connection = await _get_google_admin_groups_repo()
    if not connection:
        raise HTTPException(
            status_code=503,
            detail={"code": "DB_UNAVAILABLE", "message": "Database not available"},
        )

    query = """
    SELECT id, guild_id, google_group_email, created_at, created_by
    FROM guild_google_admin_groups
    WHERE guild_id = ?
    ORDER BY created_at DESC
    """

    rows = await connection.fetch_all(query, (guild_id,))

    groups = [
        GoogleAdminGroupResponse(
            id=row["id"],
            guild_id=row["guild_id"],
            google_group_email=row["google_group_email"],
            created_at=datetime.fromisoformat(row["created_at"])
            if row["created_at"]
            else datetime.utcnow(),
            created_by=row["created_by"],
        )
        for row in rows
    ]

    return GoogleAdminGroupsListResponse(groups=groups, total=len(groups))


@router.post(
    "/guilds/{guild_id}/google-admin-groups",
    response_model=GoogleAdminGroupResponse,
    summary="Add Google admin group",
    description="Add a Google Workspace group that grants admin access for a guild.",
    responses={
        400: {"description": "Invalid request or duplicate group"},
        403: {"description": "No permission"},
    },
)
async def add_google_admin_group(
    body: AddGoogleAdminGroupRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Add a Google admin group mapping."""
    _check_admin_access(guild_id, user)

    connection = await _get_google_admin_groups_repo()
    if not connection:
        raise HTTPException(
            status_code=503,
            detail={"code": "DB_UNAVAILABLE", "message": "Database not available"},
        )

    # Generate ID
    group_id = f"gag_{secrets.token_urlsafe(16)}"
    now = datetime.utcnow()

    # Get user identifier for created_by
    created_by = user.get("sub") or user.get("email") or "unknown"

    try:
        query = """
        INSERT INTO guild_google_admin_groups (id, guild_id, google_group_email, created_at, created_by)
        VALUES (?, ?, ?, ?, ?)
        """
        await connection.execute(
            query,
            (group_id, guild_id, body.google_group_email, now.isoformat(), created_by),
        )
    except Exception as e:
        error_str = str(e).lower()
        if "unique constraint" in error_str or "duplicate" in error_str:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "DUPLICATE_GROUP",
                    "message": f"Group {body.google_group_email} is already configured for this guild",
                },
            )
        logger.error(f"Failed to add Google admin group: {e}")
        raise HTTPException(
            status_code=500,
            detail={"code": "DB_ERROR", "message": "Failed to add admin group"},
        )

    # Audit log
    try:
        audit_service = await get_audit_service()
        await audit_service.log(
            "google_admin_group.added",
            user_id=user.get("sub"),
            user_name=user.get("username") or user.get("email"),
            guild_id=guild_id,
            resource_type="google_admin_group",
            resource_id=group_id,
            resource_name=body.google_group_email,
            action="create",
            details={"google_group_email": body.google_group_email},
        )
    except Exception as e:
        logger.warning(f"Failed to audit Google admin group addition: {e}")

    return GoogleAdminGroupResponse(
        id=group_id,
        guild_id=guild_id,
        google_group_email=body.google_group_email,
        created_at=now,
        created_by=created_by,
    )


@router.delete(
    "/guilds/{guild_id}/google-admin-groups/{group_email}",
    summary="Remove Google admin group",
    description="Remove a Google Workspace group from granting admin access for a guild.",
    responses={
        403: {"description": "No permission"},
        404: {"description": "Group not found"},
    },
)
async def remove_google_admin_group(
    guild_id: str = Path(..., description="Discord guild ID"),
    group_email: str = Path(..., description="Google group email to remove"),
    user: dict = Depends(get_current_user),
):
    """Remove a Google admin group mapping."""
    _check_admin_access(guild_id, user)

    # Normalize email
    group_email = group_email.strip().lower()

    connection = await _get_google_admin_groups_repo()
    if not connection:
        raise HTTPException(
            status_code=503,
            detail={"code": "DB_UNAVAILABLE", "message": "Database not available"},
        )

    # Check if exists first
    check_query = """
    SELECT id FROM guild_google_admin_groups
    WHERE guild_id = ? AND google_group_email = ?
    """
    row = await connection.fetch_one(check_query, (guild_id, group_email))

    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NOT_FOUND",
                "message": f"Google admin group {group_email} not found for this guild",
            },
        )

    group_id = row["id"]

    # Delete
    delete_query = """
    DELETE FROM guild_google_admin_groups
    WHERE guild_id = ? AND google_group_email = ?
    """
    await connection.execute(delete_query, (guild_id, group_email))

    # Audit log
    try:
        audit_service = await get_audit_service()
        await audit_service.log(
            "google_admin_group.removed",
            user_id=user.get("sub"),
            user_name=user.get("username") or user.get("email"),
            guild_id=guild_id,
            resource_type="google_admin_group",
            resource_id=group_id,
            resource_name=group_email,
            action="delete",
            details={"google_group_email": group_email},
        )
    except Exception as e:
        logger.warning(f"Failed to audit Google admin group removal: {e}")

    return {"success": True, "deleted_group": group_email}
