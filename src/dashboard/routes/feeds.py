"""
RSS/Atom feed routes for dashboard API.
"""

import os
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from ..auth import get_current_user
from ..models import (
    FeedsResponse,
    FeedListItem,
    FeedCreateRequest,
    FeedUpdateRequest,
    FeedDetailResponse,
    FeedTokenResponse,
    ErrorResponse,
)
from . import get_discord_bot, get_summarization_engine, get_feed_repository, get_summary_repository
from ...models.feed import FeedConfig, FeedType
from ...feeds.generator import FeedGenerator
from ...data.base import SearchCriteria

logger = logging.getLogger(__name__)

router = APIRouter()

# Feed generator instance
_feed_generator: Optional[FeedGenerator] = None


def _get_feed_generator() -> FeedGenerator:
    """Get or create feed generator instance."""
    global _feed_generator
    if _feed_generator is None:
        base_url = os.environ.get("FEED_BASE_URL", "https://summarybot-ng.fly.dev")
        dashboard_url = os.environ.get("DASHBOARD_URL", "https://summarybot-ng.fly.dev")
        _feed_generator = FeedGenerator(base_url, dashboard_url)
    return _feed_generator


def _check_guild_access(guild_id: str, user: dict):
    """Check user has access to guild."""
    if guild_id not in user.get("guilds", []):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You don't have permission to manage this guild"},
        )


def _get_guild_or_404(guild_id: str):
    """Get guild from bot or raise 404."""
    bot = get_discord_bot()
    if not bot or not bot.client:
        raise HTTPException(
            status_code=503,
            detail={"code": "BOT_UNAVAILABLE", "message": "Discord bot not available"},
        )

    guild = bot.client.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Guild not found"},
        )

    return guild


def _get_channel_name(guild, channel_id: Optional[str]) -> Optional[str]:
    """Get channel name from guild."""
    if not channel_id:
        return None
    channel = guild.get_channel(int(channel_id))
    return channel.name if channel else None


def _feed_to_list_item(feed: FeedConfig, channel_name: Optional[str] = None) -> FeedListItem:
    """Convert FeedConfig to API list response."""
    generator = _get_feed_generator()
    return FeedListItem(
        id=feed.id,
        channel_id=feed.channel_id,
        channel_name=channel_name,
        feed_type=feed.feed_type.value if isinstance(feed.feed_type, FeedType) else feed.feed_type,
        is_public=feed.is_public,
        url=feed.get_feed_url(generator.base_url),
        title=feed.title or f"{'All Channels' if not feed.channel_id else '#' + (channel_name or 'channel')} Summaries",
        created_at=feed.created_at,
        last_accessed=feed.last_accessed,
        access_count=feed.access_count,
    )


def _feed_to_detail(feed: FeedConfig, guild_name: str, channel_name: Optional[str] = None) -> FeedDetailResponse:
    """Convert FeedConfig to API detail response."""
    generator = _get_feed_generator()
    default_title = f"{guild_name} - {'#' + channel_name if channel_name else 'All Channels'} Summaries"
    default_desc = f"AI-generated summaries from {guild_name}"

    return FeedDetailResponse(
        id=feed.id,
        guild_id=feed.guild_id,
        channel_id=feed.channel_id,
        channel_name=channel_name,
        feed_type=feed.feed_type.value if isinstance(feed.feed_type, FeedType) else feed.feed_type,
        is_public=feed.is_public,
        url=feed.get_feed_url(generator.base_url),
        token=feed.token if not feed.is_public else None,
        title=feed.title or default_title,
        description=feed.description or default_desc,
        max_items=feed.max_items,
        include_full_content=feed.include_full_content,
        created_at=feed.created_at,
        created_by=feed.created_by,
        last_accessed=feed.last_accessed,
        access_count=feed.access_count,
    )


# ============================================================================
# Feed Management Endpoints (JWT Auth Required)
# ============================================================================

@router.get(
    "/guilds/{guild_id}/feeds",
    response_model=FeedsResponse,
    summary="List feeds",
    description="Get all RSS/Atom feeds for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def list_feeds(
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """List feeds for a guild."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    # Get feeds from database
    feed_repo = await get_feed_repository()
    if not feed_repo:
        return FeedsResponse(feeds=[])

    feeds = await feed_repo.get_feeds_by_guild(guild_id)
    guild_feeds = []
    for feed in feeds:
        channel_name = _get_channel_name(guild, feed.channel_id)
        guild_feeds.append(_feed_to_list_item(feed, channel_name))

    return FeedsResponse(feeds=guild_feeds)


@router.post(
    "/guilds/{guild_id}/feeds",
    response_model=FeedDetailResponse,
    summary="Create feed",
    description="Create a new RSS/Atom feed for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def create_feed(
    body: FeedCreateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Create a new feed."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    # Validate feed type
    try:
        feed_type = FeedType(body.feed_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_FEED_TYPE", "message": "Feed type must be 'rss' or 'atom'"},
        )

    # Validate channel if specified
    channel_name = None
    if body.channel_id:
        channel = guild.get_channel(int(body.channel_id))
        if not channel:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_CHANNEL", "message": "Channel not found in this guild"},
            )
        channel_name = channel.name

    # Create feed
    feed = FeedConfig(
        guild_id=guild_id,
        channel_id=body.channel_id,
        feed_type=feed_type,
        is_public=body.is_public,
        title=body.title,
        description=body.description,
        max_items=body.max_items,
        include_full_content=body.include_full_content,
        created_by=user["sub"],
    )

    # Save to database
    feed_repo = await get_feed_repository()
    if not feed_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    await feed_repo.save_feed(feed)
    logger.info(f"Created feed {feed.id} for guild {guild_id}")

    return _feed_to_detail(feed, guild.name, channel_name)


@router.get(
    "/guilds/{guild_id}/feeds/{feed_id}",
    response_model=FeedDetailResponse,
    summary="Get feed",
    description="Get details of a specific feed.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Feed not found"},
    },
)
async def get_feed(
    guild_id: str = Path(..., description="Discord guild ID"),
    feed_id: str = Path(..., description="Feed ID"),
    user: dict = Depends(get_current_user),
):
    """Get feed details."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    feed_repo = await get_feed_repository()
    if not feed_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    feed = await feed_repo.get_feed(feed_id)
    if not feed or feed.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Feed not found"},
        )

    channel_name = _get_channel_name(guild, feed.channel_id)
    return _feed_to_detail(feed, guild.name, channel_name)


@router.patch(
    "/guilds/{guild_id}/feeds/{feed_id}",
    response_model=FeedDetailResponse,
    summary="Update feed",
    description="Update an existing feed.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Feed not found"},
    },
)
async def update_feed(
    body: FeedUpdateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    feed_id: str = Path(..., description="Feed ID"),
    user: dict = Depends(get_current_user),
):
    """Update a feed."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    feed_repo = await get_feed_repository()
    if not feed_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    feed = await feed_repo.get_feed(feed_id)
    if not feed or feed.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Feed not found"},
        )

    # Update fields
    if body.title is not None:
        feed.title = body.title

    if body.description is not None:
        feed.description = body.description

    if body.is_public is not None:
        feed.is_public = body.is_public
        # Generate token if making private
        if not body.is_public and not feed.token:
            feed.regenerate_token()

    if body.max_items is not None:
        feed.max_items = body.max_items

    if body.include_full_content is not None:
        feed.include_full_content = body.include_full_content

    # Save updates to database
    await feed_repo.save_feed(feed)

    channel_name = _get_channel_name(guild, feed.channel_id)
    return _feed_to_detail(feed, guild.name, channel_name)


@router.delete(
    "/guilds/{guild_id}/feeds/{feed_id}",
    summary="Delete feed",
    description="Delete a feed.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Feed not found"},
    },
)
async def delete_feed(
    guild_id: str = Path(..., description="Discord guild ID"),
    feed_id: str = Path(..., description="Feed ID"),
    user: dict = Depends(get_current_user),
):
    """Delete a feed."""
    _check_guild_access(guild_id, user)

    feed_repo = await get_feed_repository()
    if not feed_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    feed = await feed_repo.get_feed(feed_id)
    if not feed or feed.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Feed not found"},
        )

    await feed_repo.delete_feed(feed_id)
    logger.info(f"Deleted feed {feed_id}")

    return {"success": True}


@router.post(
    "/guilds/{guild_id}/feeds/{feed_id}/regenerate-token",
    response_model=FeedTokenResponse,
    summary="Regenerate feed token",
    description="Generate a new authentication token for the feed.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Feed not found"},
    },
)
async def regenerate_token(
    guild_id: str = Path(..., description="Discord guild ID"),
    feed_id: str = Path(..., description="Feed ID"),
    user: dict = Depends(get_current_user),
):
    """Regenerate feed token."""
    _check_guild_access(guild_id, user)

    feed_repo = await get_feed_repository()
    if not feed_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    feed = await feed_repo.get_feed(feed_id)
    if not feed or feed.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Feed not found"},
        )

    new_token = feed.regenerate_token()
    await feed_repo.save_feed(feed)

    generator = _get_feed_generator()

    return FeedTokenResponse(
        token=new_token,
        url=feed.get_feed_url(generator.base_url),
    )


# ============================================================================
# Public Feed Serving Endpoints (Token Auth or Public)
# ============================================================================

@router.get(
    "/feeds/{feed_id}.rss",
    summary="Get RSS feed",
    description="Get RSS 2.0 feed content.",
    responses={
        401: {"description": "Invalid or missing token"},
        404: {"description": "Feed not found"},
    },
)
async def get_rss_feed(
    request: Request,
    feed_id: str = Path(..., description="Feed ID"),
    token: Optional[str] = Query(None, description="Feed authentication token"),
):
    """Serve RSS 2.0 feed."""
    return await _serve_feed(request, feed_id, token, FeedType.RSS)


@router.get(
    "/feeds/{feed_id}.atom",
    summary="Get Atom feed",
    description="Get Atom 1.0 feed content.",
    responses={
        401: {"description": "Invalid or missing token"},
        404: {"description": "Feed not found"},
    },
)
async def get_atom_feed(
    request: Request,
    feed_id: str = Path(..., description="Feed ID"),
    token: Optional[str] = Query(None, description="Feed authentication token"),
):
    """Serve Atom 1.0 feed."""
    return await _serve_feed(request, feed_id, token, FeedType.ATOM)


async def _serve_feed(
    request: Request,
    feed_id: str,
    token: Optional[str],
    requested_type: FeedType,
) -> Response:
    """Serve feed content with proper caching headers."""
    feed_repo = await get_feed_repository()
    if not feed_repo:
        raise HTTPException(status_code=503, detail="Database not available")

    feed = await feed_repo.get_feed(feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    # Check authentication for private feeds
    if not feed.is_public:
        # Check query param token
        if token != feed.token:
            # Check Authorization header
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                header_token = auth_header[7:]
                if header_token != feed.token:
                    raise HTTPException(status_code=401, detail="Invalid feed token")
            else:
                raise HTTPException(status_code=401, detail="Feed token required")

    # Get guild info
    bot = get_discord_bot()
    if not bot or not bot.client:
        raise HTTPException(status_code=503, detail="Discord bot not available")

    guild = bot.client.get_guild(int(feed.guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    guild_name = guild.name
    channel_name = _get_channel_name(guild, feed.channel_id)

    # Get summaries from database
    summaries = []
    summary_repo = await get_summary_repository()
    if summary_repo:
        criteria = SearchCriteria(
            guild_id=feed.guild_id,
            channel_id=feed.channel_id,
            limit=feed.max_items,
            order_by="created_at",
            order_direction="DESC",
        )
        summaries = await summary_repo.find_summaries(criteria)

    # Generate feed content
    generator = _get_feed_generator()

    # Override feed type if different from requested
    original_type = feed.feed_type
    feed.feed_type = requested_type

    try:
        content = generator.generate(summaries, feed, guild_name, channel_name)
    finally:
        feed.feed_type = original_type

    # Update access stats in database
    await feed_repo.update_access_stats(feed_id)

    # Generate caching headers
    etag = FeedGenerator.generate_etag(feed_id, summaries)
    last_modified = FeedGenerator.get_last_modified(summaries)

    # Check If-None-Match header
    if_none_match = request.headers.get("If-None-Match", "").strip('"')
    if if_none_match == etag:
        return Response(status_code=304)

    # Check If-Modified-Since header
    if_modified_since = request.headers.get("If-Modified-Since")
    if if_modified_since:
        try:
            from email.utils import parsedate_to_datetime
            ims_dt = parsedate_to_datetime(if_modified_since)
            if ims_dt >= last_modified:
                return Response(status_code=304)
        except (ValueError, TypeError):
            pass

    # Build response
    content_type = feed.get_content_type()
    headers = {
        "ETag": f'"{etag}"',
        "Last-Modified": last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "Cache-Control": "public, max-age=300",
        "Vary": "Accept-Encoding",
    }

    return Response(
        content=content,
        media_type=content_type,
        headers=headers,
    )
