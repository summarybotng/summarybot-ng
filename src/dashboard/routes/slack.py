"""
Slack integration API routes (ADR-043).

Provides OAuth installation flow and workspace management endpoints.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..auth import get_current_user, is_guild_admin, require_guild_admin
from ...slack.auth import get_slack_auth, SlackOAuthError
from ...slack.models import SlackScopeTier, SlackWorkspace, SlackChannel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SlackInstallRequest(BaseModel):
    """Request to generate Slack install URL."""
    guild_id: str = Field(..., description="Discord guild ID to link workspace to")
    scope_tier: str = Field("public", description="OAuth scope tier: 'public' or 'full'")


class SlackInstallResponse(BaseModel):
    """Response with Slack install URL."""
    install_url: str
    scope_tier: str
    scopes: List[str]


class SlackWorkspaceResponse(BaseModel):
    """Slack workspace info for API responses."""
    workspace_id: str
    workspace_name: str
    workspace_domain: Optional[str]
    bot_user_id: str
    scope_tier: str
    is_enterprise: bool
    enabled: bool
    installed_at: Optional[str]
    last_sync_at: Optional[str]
    linked_guild_id: Optional[str]


class SlackChannelResponse(BaseModel):
    """Slack channel info for API responses."""
    channel_id: str
    channel_name: str
    channel_type: str
    is_shared: bool
    is_archived: bool
    is_sensitive: bool
    auto_summarize: bool
    member_count: int
    topic: Optional[str]
    purpose: Optional[str]


class SlackChannelUpdateRequest(BaseModel):
    """Request to update channel settings."""
    auto_summarize: Optional[bool] = None
    is_sensitive: Optional[bool] = None
    summary_schedule: Optional[str] = None


class SlackLinkRequest(BaseModel):
    """Request to link workspace to guild."""
    workspace_id: str


# ============================================================================
# OAuth Routes
# ============================================================================

@router.post(
    "/install",
    response_model=SlackInstallResponse,
    summary="Get Slack app installation URL",
    description="Generate a URL to install the Slack app to a workspace.",
)
async def get_install_url(
    request: SlackInstallRequest,
    user: dict = Depends(get_current_user),
):
    """Generate Slack OAuth installation URL.

    Requires admin permissions on the target Discord guild.
    """
    # Lazy initialization if not already done
    slack_auth = get_slack_auth()
    if not slack_auth:
        from ...slack.auth import initialize_slack_auth
        slack_auth = initialize_slack_auth()

    if not slack_auth:
        raise HTTPException(
            status_code=503,
            detail={"code": "SLACK_NOT_CONFIGURED", "message": "Slack integration not configured"},
        )

    # Verify user has admin access to the guild
    require_guild_admin(request.guild_id, user)

    # Parse scope tier
    try:
        scope_tier = SlackScopeTier(request.scope_tier)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_SCOPE_TIER", "message": f"Invalid scope tier: {request.scope_tier}"},
        )

    # Get Discord user ID from JWT
    discord_user_id = user.get("sub")

    # Generate install URL with guild_id for linking
    install_url = slack_auth.get_install_url(
        discord_user_id=discord_user_id,
        scope_tier=scope_tier,
        guild_id=request.guild_id,
    )

    scopes = slack_auth.get_scopes_for_tier(scope_tier)

    return SlackInstallResponse(
        install_url=install_url,
        scope_tier=scope_tier.value,
        scopes=scopes,
    )


@router.get(
    "/callback",
    summary="Slack OAuth callback",
    description="Handle OAuth callback from Slack after app installation.",
)
async def oauth_callback(
    code: str = Query(..., description="Authorization code from Slack"),
    state: str = Query(..., description="OAuth state for CSRF protection"),
    error: Optional[str] = Query(None, description="Error code if authorization failed"),
    error_description: Optional[str] = Query(None, description="Error description"),
):
    """Handle Slack OAuth callback.

    This endpoint is called by Slack after the user authorizes the app.
    It exchanges the code for tokens and stores the workspace.
    """
    # Lazy initialization if not already done
    slack_auth = get_slack_auth()
    if not slack_auth:
        from ...slack.auth import initialize_slack_auth
        slack_auth = initialize_slack_auth()

    if not slack_auth:
        raise HTTPException(
            status_code=503,
            detail={"code": "SLACK_NOT_CONFIGURED", "message": "Slack integration not configured"},
        )

    # Handle authorization errors
    if error:
        logger.warning(f"Slack OAuth error: {error} - {error_description}")
        raise HTTPException(
            status_code=400,
            detail={
                "code": f"SLACK_{error.upper()}",
                "message": error_description or error,
            },
        )

    # Get frontend URL for redirects
    import os
    frontend_url = os.getenv("FRONTEND_URL", "https://summarybot-ng.fly.dev")

    try:
        # Exchange code for token
        workspace, discord_user_id, guild_id = await slack_auth.exchange_code(code, state)

        # Link workspace to guild
        if guild_id:
            workspace.linked_guild_id = guild_id
            workspace.linked_at = datetime.utcnow()

        # Store workspace
        from . import get_slack_repository
        repo = await get_slack_repository()
        if repo:
            await repo.save_workspace(workspace)
            logger.info(f"Slack workspace saved: {workspace.workspace_name} ({workspace.workspace_id}) linked to guild {guild_id}")

        # Redirect to frontend Slack page with success message
        return RedirectResponse(
            url=f"{frontend_url}/slack?success=true&workspace={workspace.workspace_name}",
            status_code=302,
        )

    except SlackOAuthError as e:
        logger.error(f"Slack OAuth exchange failed: {e}")
        # Redirect to frontend with error
        return RedirectResponse(
            url=f"{frontend_url}/slack?error={e.code}&message={e.description}",
            status_code=302,
        )


# ============================================================================
# Workspace Management Routes
# ============================================================================

@router.get(
    "/workspaces",
    response_model=List[SlackWorkspaceResponse],
    summary="List connected Slack workspaces",
    description="List all Slack workspaces the user has access to.",
)
async def list_workspaces(
    user: dict = Depends(get_current_user),
):
    """List Slack workspaces accessible to the user.

    Returns workspaces linked to guilds the user has access to.
    """
    from . import get_slack_repository
    repo = await get_slack_repository()
    if not repo:
        return []

    # Get user's accessible guild IDs
    user_guilds = set(user.get("guilds", []))

    workspaces = await repo.list_workspaces()

    # Filter to workspaces linked to user's guilds
    accessible = [
        w for w in workspaces
        if w.linked_guild_id in user_guilds
    ]

    return [
        SlackWorkspaceResponse(
            workspace_id=w.workspace_id,
            workspace_name=w.workspace_name,
            workspace_domain=w.workspace_domain,
            bot_user_id=w.bot_user_id,
            scope_tier=w.scope_tier.value,
            is_enterprise=w.is_enterprise,
            enabled=w.enabled,
            installed_at=w.installed_at.isoformat() if w.installed_at else None,
            last_sync_at=w.last_sync_at.isoformat() if w.last_sync_at else None,
            linked_guild_id=w.linked_guild_id,
        )
        for w in accessible
    ]


@router.get(
    "/workspaces/{workspace_id}",
    response_model=SlackWorkspaceResponse,
    summary="Get Slack workspace details",
)
async def get_workspace(
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    """Get details for a specific Slack workspace."""
    from . import get_slack_repository
    repo = await get_slack_repository()
    if not repo:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace = await repo.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check user has access to linked guild
    if workspace.linked_guild_id and workspace.linked_guild_id not in user.get("guilds", []):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You don't have access to this workspace"},
        )

    return SlackWorkspaceResponse(
        workspace_id=workspace.workspace_id,
        workspace_name=workspace.workspace_name,
        workspace_domain=workspace.workspace_domain,
        bot_user_id=workspace.bot_user_id,
        scope_tier=workspace.scope_tier.value,
        is_enterprise=workspace.is_enterprise,
        enabled=workspace.enabled,
        installed_at=workspace.installed_at.isoformat() if workspace.installed_at else None,
        last_sync_at=workspace.last_sync_at.isoformat() if workspace.last_sync_at else None,
        linked_guild_id=workspace.linked_guild_id,
    )


@router.post(
    "/workspaces/{workspace_id}/link",
    summary="Link workspace to Discord guild",
)
async def link_workspace_to_guild(
    workspace_id: str,
    request: SlackLinkRequest,
    user: dict = Depends(get_current_user),
):
    """Link a Slack workspace to a Discord guild."""
    from . import get_slack_repository
    repo = await get_slack_repository()
    if not repo:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Verify user has admin access to the guild
    guild_id = request.workspace_id  # Actually the guild_id from request body
    require_guild_admin(guild_id, user)

    workspace = await repo.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Link the workspace
    success = await repo.link_workspace_to_guild(workspace_id, guild_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to link workspace")

    return {"status": "success", "message": f"Workspace linked to guild {guild_id}"}


@router.delete(
    "/workspaces/{workspace_id}",
    summary="Disconnect Slack workspace",
)
async def delete_workspace(
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    """Disconnect and remove a Slack workspace."""
    from . import get_slack_repository
    repo = await get_slack_repository()
    if not repo:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace = await repo.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Verify user has admin access to linked guild
    if workspace.linked_guild_id:
        require_guild_admin(workspace.linked_guild_id, user)

    # Revoke token with Slack
    slack_auth = get_slack_auth()
    if slack_auth:
        await slack_auth.revoke_token(workspace.encrypted_bot_token)

    # Delete from database
    await repo.delete_workspace(workspace_id)

    return {"status": "success", "message": "Workspace disconnected"}


# ============================================================================
# Channel Management Routes
# ============================================================================

@router.get(
    "/workspaces/{workspace_id}/channels",
    response_model=List[SlackChannelResponse],
    summary="List Slack channels",
)
async def list_channels(
    workspace_id: str,
    include_archived: bool = Query(False, description="Include archived channels"),
    user: dict = Depends(get_current_user),
):
    """List channels for a Slack workspace."""
    from . import get_slack_repository
    repo = await get_slack_repository()
    if not repo:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace = await repo.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check access
    if workspace.linked_guild_id and workspace.linked_guild_id not in user.get("guilds", []):
        raise HTTPException(status_code=403, detail="Access denied")

    channels = await repo.list_channels(
        workspace_id=workspace_id,
        include_archived=include_archived,
    )

    return [
        SlackChannelResponse(
            channel_id=ch.channel_id,
            channel_name=ch.channel_name,
            channel_type=ch.channel_type.value,
            is_shared=ch.is_shared,
            is_archived=ch.is_archived,
            is_sensitive=ch.is_sensitive,
            auto_summarize=ch.auto_summarize,
            member_count=ch.member_count,
            topic=ch.topic,
            purpose=ch.purpose,
        )
        for ch in channels
    ]


@router.post(
    "/workspaces/{workspace_id}/sync",
    summary="Sync channels and users from Slack",
)
async def sync_workspace(
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    """Sync channels and users from Slack API."""
    from . import get_slack_repository
    from ...slack.client import SlackClient

    repo = await get_slack_repository()
    if not repo:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace = await repo.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check admin access
    if workspace.linked_guild_id:
        require_guild_admin(workspace.linked_guild_id, user)

    try:
        # Create client and sync
        client = SlackClient(workspace)

        # Sync channels
        channels = await client.get_all_channels(
            include_private=workspace.can_access_private()
        )
        await repo.save_channels_batch(channels)

        # Sync users
        users = await client.get_all_users()
        await repo.save_users_batch(users)

        await client.close()

        # Update last sync time
        workspace.last_sync_at = datetime.utcnow()
        await repo.save_workspace(workspace)

        return {
            "status": "success",
            "channels_synced": len(channels),
            "users_synced": len(users),
        }

    except Exception as e:
        logger.error(f"Failed to sync workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.patch(
    "/channels/{channel_id}",
    summary="Update channel settings",
)
async def update_channel(
    channel_id: str,
    request: SlackChannelUpdateRequest,
    user: dict = Depends(get_current_user),
):
    """Update settings for a Slack channel."""
    from . import get_slack_repository
    repo = await get_slack_repository()
    if not repo:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel = await repo.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Get workspace to check access
    workspace = await repo.get_workspace(channel.workspace_id)
    if workspace and workspace.linked_guild_id:
        require_guild_admin(workspace.linked_guild_id, user)

    # Apply updates
    if request.auto_summarize is not None:
        channel.auto_summarize = request.auto_summarize
    if request.is_sensitive is not None:
        channel.is_sensitive = request.is_sensitive
    if request.summary_schedule is not None:
        channel.summary_schedule = request.summary_schedule

    await repo.save_channel(channel)

    return {"status": "success", "message": "Channel updated"}


# ============================================================================
# Status Route
# ============================================================================

@router.get(
    "/status",
    summary="Get Slack integration status",
)
async def get_status():
    """Get Slack integration configuration status."""
    # Lazy initialization if not already done (startup event may not have fired)
    slack_auth = get_slack_auth()
    if not slack_auth:
        from ...slack.auth import initialize_slack_auth
        slack_auth = initialize_slack_auth()

    return {
        "configured": slack_auth is not None,
        "scopes": {
            "public": slack_auth.get_scopes_for_tier(SlackScopeTier.PUBLIC) if slack_auth else [],
            "full": slack_auth.get_scopes_for_tier(SlackScopeTier.FULL) if slack_auth else [],
        },
    }


# ============================================================================
# Guild Links (ADR-085: Multi-Guild Slack Access)
# ============================================================================

class GuildLinkRequest(BaseModel):
    """Request to link a Slack workspace to a Discord guild."""
    workspace_id: str = Field(..., description="Slack workspace ID to link")
    can_view: bool = Field(True, description="Whether guild members can view Slack content")
    can_summarize: bool = Field(False, description="Whether guild can generate summaries")


class GuildLinkResponse(BaseModel):
    """Response for guild link operations."""
    workspace_id: str
    workspace_name: str
    guild_id: str
    can_view: bool
    can_summarize: bool
    linked_at: str


@router.post(
    "/guilds/{guild_id}/links",
    response_model=GuildLinkResponse,
    summary="Link Slack workspace to guild",
    description="ADR-085: Enable a Discord guild to access a Slack workspace",
)
async def add_guild_link(
    guild_id: str,
    request: GuildLinkRequest,
    user: dict = Depends(get_current_user),
):
    """Link a Slack workspace to a Discord guild for multi-guild access."""
    require_guild_admin(guild_id, user)

    from . import get_slack_repository
    repo = await get_slack_repository()
    if not repo:
        raise HTTPException(status_code=500, detail="Database not available")

    # Verify workspace exists
    workspace = await repo.get_workspace(request.workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # User must have access to the workspace's primary guild to add links
    if workspace.linked_guild_id and workspace.linked_guild_id not in user.get("guilds", []):
        raise HTTPException(
            status_code=403,
            detail="You must be a member of the workspace's primary guild to add links"
        )

    # Add the link
    success = await repo.add_guild_link(
        workspace_id=request.workspace_id,
        guild_id=guild_id,
        linked_by=user.get("sub", "unknown"),
        can_view=request.can_view,
        can_summarize=request.can_summarize,
    )

    if not success:
        # Link already exists - that's fine
        pass

    logger.info(f"Linked Slack workspace {request.workspace_id} to guild {guild_id}")

    return GuildLinkResponse(
        workspace_id=workspace.workspace_id,
        workspace_name=workspace.workspace_name,
        guild_id=guild_id,
        can_view=request.can_view,
        can_summarize=request.can_summarize,
        linked_at=datetime.utcnow().isoformat(),
    )


@router.delete(
    "/guilds/{guild_id}/links/{workspace_id}",
    summary="Remove Slack workspace link",
    description="ADR-085: Remove a Discord guild's access to a Slack workspace",
)
async def remove_guild_link(
    guild_id: str,
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    """Remove a Slack workspace link from a Discord guild."""
    require_guild_admin(guild_id, user)

    from . import get_slack_repository
    repo = await get_slack_repository()
    if not repo:
        raise HTTPException(status_code=500, detail="Database not available")

    # Verify workspace exists
    workspace = await repo.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Cannot unlink the primary guild
    if workspace.linked_guild_id == guild_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot unlink the primary guild. Use workspace disconnect instead."
        )

    # Remove the link
    success = await repo.remove_guild_link(workspace_id, guild_id)

    if not success:
        raise HTTPException(status_code=404, detail="Link not found")

    logger.info(f"Unlinked Slack workspace {workspace_id} from guild {guild_id}")

    return {"status": "success", "message": "Workspace unlinked from guild"}


@router.get(
    "/guilds/{guild_id}/links",
    summary="List linked Slack workspaces",
    description="ADR-085: Get all Slack workspaces linked to a Discord guild",
)
async def list_guild_links(
    guild_id: str,
    user: dict = Depends(get_current_user),
):
    """List all Slack workspaces accessible to a Discord guild."""
    if guild_id not in user.get("guilds", []):
        raise HTTPException(status_code=403, detail="Not a member of this guild")

    from . import get_slack_repository
    repo = await get_slack_repository()
    if not repo:
        return {"workspaces": []}

    workspaces = await repo.get_workspaces_for_guild(guild_id)

    return {
        "workspaces": [
            {
                "workspace_id": ws.workspace_id,
                "workspace_name": ws.workspace_name,
                "workspace_domain": ws.workspace_domain,
                "is_primary": ws.linked_guild_id == guild_id,
            }
            for ws in workspaces
        ]
    }
