"""
Authentication routes for dashboard API.

ADR-045: Integrated with audit logging for security monitoring.
"""

import os
import logging
from typing import Optional, List
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from ..auth import (
    get_auth,
    get_current_user,
    security,
    DashboardAuth,
)
from ..models import (
    AuthLoginResponse,
    AuthCallbackRequest,
    AuthCallbackResponse,
    AuthRefreshResponse,
    UserResponse,
    GuildBriefResponse,
    GuildRole,
    ErrorResponse,
)
from . import get_discord_bot

logger = logging.getLogger(__name__)


async def _audit_auth_event(
    event_type: str,
    request: Request,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    details: Optional[dict] = None,
):
    """Log an authentication event to the audit log."""
    try:
        from ...logging import get_audit_service
        service = await get_audit_service()

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

        await service.log(
            event_type,
            user_id=user_id,
            user_name=user_name,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
            details=details or {},
        )
    except Exception as e:
        # Don't let audit logging failures break authentication
        logger.warning(f"Failed to log audit event: {e}")

router = APIRouter()


@router.get(
    "/login",
    response_model=AuthLoginResponse,
    summary="Initiate Discord OAuth login",
    description="Returns the Discord OAuth authorization URL to redirect the user to.",
)
async def login():
    """Get Discord OAuth authorization URL."""
    auth = get_auth()
    state = auth.create_oauth_state()
    redirect_url = auth.get_oauth_url(state=state)
    return AuthLoginResponse(redirect_url=redirect_url, state=state)


@router.post(
    "/callback",
    response_model=AuthCallbackResponse,
    summary="Handle OAuth callback",
    description="Exchange OAuth code for tokens and create session.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid code"},
        502: {"model": ErrorResponse, "description": "Discord API error"},
    },
)
async def callback(request: Request, body: AuthCallbackRequest):
    """Handle Discord OAuth callback."""
    auth = get_auth()

    # Validate CSRF state
    if not auth.validate_oauth_state(body.state):
        # Log failed auth attempt (ADR-045)
        await _audit_auth_event(
            "auth.login.failed",
            request,
            success=False,
            error_message="Invalid or expired OAuth state parameter",
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_STATE", "message": "Invalid or expired OAuth state parameter"},
        )

    # Exchange code for tokens
    access_token, refresh_token, expires_in = await auth.exchange_code(body.code)

    # Get user info
    user = await auth.get_user(access_token)

    # Get user's guilds
    all_guilds = await auth.get_user_guilds(access_token)

    # Filter to guilds where bot is present (allow members, not just admins)
    bot = get_discord_bot()
    bot_guild_ids = set()
    if bot and bot.client:
        bot_guild_ids = {str(g.id) for g in bot.client.guilds}

    # Include all guilds where the bot is present (members can now access)
    accessible_guilds = [
        g for g in all_guilds
        if g.id in bot_guild_ids
    ]

    # Create session
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    jwt_token, session = await auth.create_session(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        manageable_guilds=accessible_guilds,  # Now includes members
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Build response with proper roles
    guild_responses = []
    for guild in accessible_guilds:
        guild_responses.append(
            GuildBriefResponse(
                id=guild.id,
                name=guild.name,
                icon_url=guild.icon_url,
                role=guild.get_role(),
            )
        )

    # Log successful login (ADR-045)
    await _audit_auth_event(
        "auth.login.success",
        request,
        user_id=user.id,
        user_name=user.username,
        success=True,
        details={
            "guilds_count": len(accessible_guilds),
            "guild_ids": [g.id for g in accessible_guilds[:10]],  # First 10 for privacy
        },
    )

    return AuthCallbackResponse(
        token=jwt_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            avatar_url=user.avatar_url,
            email=user.email,  # ADR-070: Include email for issue tracker pre-fill
        ),
        guilds=guild_responses,
    )


@router.post(
    "/refresh",
    response_model=AuthRefreshResponse,
    summary="Refresh JWT token",
    description="Get a new JWT token with a fresh guild list from Discord.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or expired token"},
    },
)
async def refresh(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Refresh JWT token with fresh guild list."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Not authenticated"},
        )

    auth = get_auth()

    # Get current bot guild IDs (same pattern as /callback)
    bot = get_discord_bot()
    bot_guild_ids = set()
    if bot and bot.client:
        bot_guild_ids = {str(g.id) for g in bot.client.guilds}

    new_token, guild_ids = await auth.refresh_jwt_with_guilds(
        credentials.credentials, bot_guild_ids
    )
    return AuthRefreshResponse(token=new_token, guilds=guild_ids)


@router.post(
    "/logout",
    summary="Logout and invalidate session",
    description="Invalidate the current session.",
)
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Logout and invalidate session."""
    user_id = None
    user_name = None

    if credentials is not None:
        auth = get_auth()

        # Try to decode token to get user info for audit log
        try:
            payload = auth.decode_jwt(credentials.credentials)
            user_id = payload.get("sub")
            user_name = payload.get("username")
        except Exception:
            pass

        await auth.invalidate_session(credentials.credentials)

    # Log logout (ADR-045)
    await _audit_auth_event(
        "auth.logout",
        request,
        user_id=user_id,
        user_name=user_name,
        success=True,
    )

    return {"success": True}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get the currently authenticated user's information.",
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
    },
)
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info."""
    # Build avatar URL - Google users have direct URL, Discord uses CDN pattern
    avatar = user.get("avatar")
    if avatar and avatar.startswith("http"):
        avatar_url = avatar  # Google users have direct URL
    elif avatar:
        avatar_url = f"https://cdn.discordapp.com/avatars/{user['sub']}/{avatar}.png"
    else:
        avatar_url = None

    return UserResponse(
        id=user["sub"],
        username=user["username"],
        avatar_url=avatar_url,
        email=user.get("email"),  # ADR-070: Include email for issue tracker pre-fill
    )


# =============================================================================
# Development/Testing Endpoints (only available when DEV_AUTH_ENABLED=true)
# =============================================================================

class DevTokenRequest(BaseModel):
    """Request body for dev token endpoint."""
    user_id: str = "123456789012345678"
    username: str = "TestUser"
    avatar: Optional[str] = None
    guild_ids: List[str] = []


class DevTokenResponse(BaseModel):
    """Response from dev token endpoint."""
    token: str
    user: UserResponse
    guilds: List[GuildBriefResponse]


@router.post(
    "/dev-token",
    response_model=DevTokenResponse,
    summary="Generate dev token (DEV ONLY)",
    description="Generate a JWT token for testing. Only available when DEV_AUTH_ENABLED=true.",
    responses={
        403: {"model": ErrorResponse, "description": "Dev auth not enabled"},
    },
)
async def dev_token(body: DevTokenRequest):
    """Generate a development token for UI testing.

    This endpoint is only available when DEV_AUTH_ENABLED=true environment variable is set.
    It creates a valid JWT token without requiring Discord OAuth.
    """
    if os.environ.get("DEV_AUTH_ENABLED", "").lower() != "true":
        raise HTTPException(
            status_code=403,
            detail={"code": "DEV_AUTH_DISABLED", "message": "Dev auth is not enabled"},
        )

    auth = get_auth()

    # If no guild_ids provided, try to get from bot
    guild_ids = body.guild_ids
    if not guild_ids:
        bot = get_discord_bot()
        if bot and bot.client:
            guild_ids = [str(g.id) for g in bot.client.guilds]

    # Create a mock user
    from ..models import DashboardUser
    user = DashboardUser(
        id=body.user_id,
        username=body.username,
        discriminator=None,
        avatar=body.avatar,
    )

    # Create JWT token
    token = auth.create_jwt(user, guild_ids)

    # Build response
    guild_responses = [
        GuildBriefResponse(
            id=gid,
            name=f"Guild {gid[-4:]}",
            icon_url=None,
            role=GuildRole.ADMIN,
        )
        for gid in guild_ids
    ]

    return DevTokenResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            avatar_url=f"https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.png"
            if user.avatar
            else None,
            email=user.email,  # ADR-070: Include email for issue tracker pre-fill
        ),
        guilds=guild_responses,
    )
