"""
Webhook routes for dashboard API.
"""

import logging
import secrets
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path

import httpx

from ..auth import get_current_user
from ..models import (
    WebhooksResponse,
    WebhookListItem,
    WebhookCreateRequest,
    WebhookUpdateRequest,
    WebhookTestResponse,
    ErrorResponse,
)
from . import get_discord_bot, get_config_manager, get_webhook_repository

logger = logging.getLogger(__name__)

router = APIRouter()


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


def _mask_url(url: str) -> str:
    """Mask a URL for display."""
    if len(url) > 30:
        return url[:20] + "..." + url[-4:]
    return url


def _webhook_to_response(webhook: dict) -> WebhookListItem:
    """Convert webhook dict to API response."""
    return WebhookListItem(
        id=webhook["id"],
        name=webhook["name"],
        url_preview=_mask_url(webhook["url"]),
        type=webhook["type"],
        enabled=webhook["enabled"],
        last_delivery=webhook.get("last_delivery"),
        last_status=webhook.get("last_status"),
        created_at=webhook["created_at"],
    )


@router.get(
    "/guilds/{guild_id}/webhooks",
    response_model=WebhooksResponse,
    summary="List webhooks",
    description="Get all webhooks for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def list_webhooks(
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """List webhooks for a guild."""
    _check_guild_access(guild_id, user)
    _get_guild_or_404(guild_id)

    # Get webhooks from database
    webhook_repo = await get_webhook_repository()
    if not webhook_repo:
        return WebhooksResponse(webhooks=[])

    webhooks = await webhook_repo.get_webhooks_by_guild(guild_id)
    guild_webhooks = [_webhook_to_response(wh) for wh in webhooks]

    return WebhooksResponse(webhooks=guild_webhooks)


@router.post(
    "/guilds/{guild_id}/webhooks",
    response_model=WebhookListItem,
    summary="Create webhook",
    description="Create a new webhook for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def create_webhook(
    body: WebhookCreateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Create a new webhook."""
    _check_guild_access(guild_id, user)
    _get_guild_or_404(guild_id)

    # Validate URL
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_URL", "message": "URL must start with http:// or https://"},
        )

    webhook_repo = await get_webhook_repository()
    if not webhook_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    # Create webhook
    webhook_id = f"wh_{secrets.token_urlsafe(16)}"
    webhook = {
        "id": webhook_id,
        "guild_id": guild_id,
        "name": body.name,
        "url": body.url,
        "type": body.type,
        "headers": body.headers or {},
        "enabled": True,
        "last_delivery": None,
        "last_status": None,
        "created_by": user["sub"],
        "created_at": datetime.utcnow(),
    }

    await webhook_repo.save_webhook(webhook)

    return _webhook_to_response(webhook)


@router.get(
    "/guilds/{guild_id}/webhooks/{webhook_id}",
    response_model=WebhookListItem,
    summary="Get webhook",
    description="Get details of a specific webhook.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Webhook not found"},
    },
)
async def get_webhook(
    guild_id: str = Path(..., description="Discord guild ID"),
    webhook_id: str = Path(..., description="Webhook ID"),
    user: dict = Depends(get_current_user),
):
    """Get webhook details."""
    _check_guild_access(guild_id, user)

    webhook_repo = await get_webhook_repository()
    if not webhook_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    webhook = await webhook_repo.get_webhook(webhook_id)
    if not webhook or webhook["guild_id"] != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Webhook not found"},
        )

    return _webhook_to_response(webhook)


@router.patch(
    "/guilds/{guild_id}/webhooks/{webhook_id}",
    response_model=WebhookListItem,
    summary="Update webhook",
    description="Update an existing webhook.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Webhook not found"},
    },
)
async def update_webhook(
    body: WebhookUpdateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    webhook_id: str = Path(..., description="Webhook ID"),
    user: dict = Depends(get_current_user),
):
    """Update a webhook."""
    _check_guild_access(guild_id, user)

    webhook_repo = await get_webhook_repository()
    if not webhook_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    webhook = await webhook_repo.get_webhook(webhook_id)
    if not webhook or webhook["guild_id"] != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Webhook not found"},
        )

    # Update fields
    if body.name is not None:
        webhook["name"] = body.name

    if body.url is not None:
        if not body.url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_URL", "message": "URL must start with http:// or https://"},
            )
        webhook["url"] = body.url

    if body.type is not None:
        webhook["type"] = body.type

    if body.enabled is not None:
        webhook["enabled"] = body.enabled

    if body.headers is not None:
        webhook["headers"] = body.headers

    await webhook_repo.save_webhook(webhook)

    return _webhook_to_response(webhook)


@router.delete(
    "/guilds/{guild_id}/webhooks/{webhook_id}",
    summary="Delete webhook",
    description="Delete a webhook.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Webhook not found"},
    },
)
async def delete_webhook(
    guild_id: str = Path(..., description="Discord guild ID"),
    webhook_id: str = Path(..., description="Webhook ID"),
    user: dict = Depends(get_current_user),
):
    """Delete a webhook."""
    _check_guild_access(guild_id, user)

    webhook_repo = await get_webhook_repository()
    if not webhook_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    webhook = await webhook_repo.get_webhook(webhook_id)
    if not webhook or webhook["guild_id"] != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Webhook not found"},
        )

    await webhook_repo.delete_webhook(webhook_id)

    return {"success": True}


@router.post(
    "/guilds/{guild_id}/webhooks/{webhook_id}/test",
    response_model=WebhookTestResponse,
    summary="Test webhook",
    description="Send a test request to the webhook.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Webhook not found"},
    },
)
async def test_webhook(
    guild_id: str = Path(..., description="Discord guild ID"),
    webhook_id: str = Path(..., description="Webhook ID"),
    user: dict = Depends(get_current_user),
):
    """Test a webhook."""
    _check_guild_access(guild_id, user)

    webhook_repo = await get_webhook_repository()
    if not webhook_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    webhook = await webhook_repo.get_webhook(webhook_id)
    if not webhook or webhook["guild_id"] != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Webhook not found"},
        )

    # Build test payload based on webhook type
    webhook_type = webhook.get("type", "generic")
    test_message = "This is a test from SummaryBot Dashboard"

    if webhook_type == "discord":
        # Discord expects { "content": "..." }
        test_payload = {
            "content": test_message,
        }
    elif webhook_type == "slack":
        # Slack expects { "text": "..." }
        test_payload = {
            "text": test_message,
        }
    elif webhook_type == "notion":
        # Notion API format (simplified - real usage would need page_id etc.)
        test_payload = {
            "type": "test",
            "message": test_message,
        }
    else:
        # Generic webhook
        test_payload = {
            "type": "test",
            "message": test_message,
            "timestamp": datetime.utcnow().isoformat(),
        }

    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Content-Type": "application/json"}
            headers.update(webhook.get("headers", {}))

            response = await client.post(
                webhook["url"],
                json=test_payload,
                headers=headers,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Update webhook status in database
            status = "success" if response.is_success else "failed"
            await webhook_repo.update_delivery_status(webhook_id, status, datetime.utcnow())

            return WebhookTestResponse(
                success=response.is_success,
                response_code=response.status_code,
                response_time_ms=elapsed_ms,
            )

    except httpx.TimeoutException:
        await webhook_repo.update_delivery_status(webhook_id, "failed", datetime.utcnow())
        return WebhookTestResponse(
            success=False,
            response_code=None,
            response_time_ms=30000,
            error="Request timed out",
        )

    except httpx.RequestError as e:
        await webhook_repo.update_delivery_status(webhook_id, "failed", datetime.utcnow())
        return WebhookTestResponse(
            success=False,
            response_code=None,
            response_time_ms=None,
            error=str(e),
        )
