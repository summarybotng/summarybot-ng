"""
Authentication routes for dashboard API.
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
    redirect_url = auth.get_oauth_url()
    return AuthLoginResponse(redirect_url=redirect_url)


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

    # Exchange code for tokens
    access_token, refresh_token, expires_in = await auth.exchange_code(body.code)

    # Get user info
    user = await auth.get_user(access_token)

    # Get user's guilds
    all_guilds = await auth.get_user_guilds(access_token)

    # Filter to guilds user can manage AND bot is in
    bot = get_discord_bot()
    bot_guild_ids = set()
    if bot and bot.client:
        bot_guild_ids = {str(g.id) for g in bot.client.guilds}

    manageable_guilds = [
        g for g in all_guilds
        if g.can_manage() and g.id in bot_guild_ids
    ]

    # Create session
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    jwt_token, session = await auth.create_session(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        manageable_guilds=manageable_guilds,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Build response
    guild_responses = []
    for guild in manageable_guilds:
        role = GuildRole.OWNER if guild.owner else GuildRole.ADMIN
        guild_responses.append(
            GuildBriefResponse(
                id=guild.id,
                name=guild.name,
                icon_url=guild.icon_url,
                role=role,
            )
        )

    return AuthCallbackResponse(
        token=jwt_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            avatar_url=user.avatar_url,
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
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Logout and invalidate session."""
    if credentials is None:
        return {"success": True}

    auth = get_auth()
    await auth.invalidate_session(credentials.credentials)
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
    return UserResponse(
        id=user["sub"],
        username=user["username"],
        avatar_url=f"https://cdn.discordapp.com/avatars/{user['sub']}/{user.get('avatar')}.png"
        if user.get("avatar")
        else None,
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
        ),
        guilds=guild_responses,
    )
