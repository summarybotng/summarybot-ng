"""
Slack Events API webhook handler (ADR-043 Section 5).

Handles incoming events from Slack including:
- URL verification challenges
- Message events
- App lifecycle events (uninstall, token revocation)
"""

import json
import logging
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Response

from .signature import verify_request_signature, SlackSignatureError
from .dedup import get_deduplicator
from .auth import get_slack_auth
from .models import SlackMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack/events", tags=["slack-events"])

# Event handler registry
EventHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]
_event_handlers: Dict[str, EventHandler] = {}


def register_event_handler(event_type: str, handler: EventHandler):
    """Register a handler for a Slack event type.

    Args:
        event_type: Slack event type (e.g., 'message', 'reaction_added')
        handler: Async function taking (workspace_id, event_data)
    """
    _event_handlers[event_type] = handler
    logger.info(f"Registered Slack event handler for: {event_type}")


async def _default_message_handler(workspace_id: str, event: Dict[str, Any]):
    """Default handler for message events."""
    # Skip bot messages and subtypes we don't care about
    subtype = event.get("subtype")
    if subtype in ("bot_message", "message_changed", "message_deleted"):
        return

    channel_id = event.get("channel")
    user_id = event.get("user")
    text = event.get("text", "")
    ts = event.get("ts")
    thread_ts = event.get("thread_ts")

    logger.info(
        f"Slack message received: workspace={workspace_id}, "
        f"channel={channel_id}, user={user_id}, ts={ts}"
    )

    # Store message for later summarization
    # In a real implementation, this would queue the message
    # for processing by the summarization engine


async def _handle_app_uninstalled(workspace_id: str, event: Dict[str, Any]):
    """Handle app_uninstalled event."""
    logger.warning(f"Slack app uninstalled from workspace: {workspace_id}")

    # Disable the workspace in database
    try:
        from ..data.repositories import get_slack_repository
        repo = await get_slack_repository()
        workspace = await repo.get_workspace(workspace_id)
        if workspace:
            workspace.enabled = False
            await repo.save_workspace(workspace)
    except Exception as e:
        logger.error(f"Failed to disable workspace {workspace_id}: {e}")


async def _handle_tokens_revoked(workspace_id: str, event: Dict[str, Any]):
    """Handle tokens_revoked event."""
    tokens = event.get("tokens", {})
    bot_tokens = tokens.get("bot", [])

    if bot_tokens:
        logger.warning(
            f"Slack bot tokens revoked for workspace {workspace_id}: {bot_tokens}"
        )
        # Disable workspace similar to uninstall
        await _handle_app_uninstalled(workspace_id, event)


# Register default handlers
register_event_handler("message", _default_message_handler)
register_event_handler("app_uninstalled", _handle_app_uninstalled)
register_event_handler("tokens_revoked", _handle_tokens_revoked)


@router.post("")
async def handle_slack_event(request: Request):
    """Handle incoming Slack Events API webhooks.

    This endpoint handles:
    1. URL verification challenges (type: url_verification)
    2. Event callbacks (type: event_callback)

    All requests are verified using HMAC-SHA256 signature.
    """
    # Get signing secret
    slack_auth = get_slack_auth()
    if not slack_auth or not slack_auth.signing_secret:
        logger.error("Slack signing secret not configured")
        raise HTTPException(
            status_code=503,
            detail="Slack webhook not configured",
        )

    # Read body
    body = await request.body()

    # Verify signature
    try:
        await verify_request_signature(
            body=body,
            headers=dict(request.headers),
            signing_secret=slack_auth.signing_secret,
        )
    except SlackSignatureError as e:
        logger.warning(f"Slack signature verification failed: {e.code}")
        raise HTTPException(
            status_code=401,
            detail=f"Signature verification failed: {e.code}",
        )

    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Handle URL verification challenge
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        logger.info("Slack URL verification challenge received")
        return Response(
            content=challenge,
            media_type="text/plain",
        )

    # Handle event callbacks
    if payload.get("type") == "event_callback":
        return await _process_event_callback(payload)

    # Unknown type
    logger.warning(f"Unknown Slack event type: {payload.get('type')}")
    return {"ok": True}


async def _process_event_callback(payload: Dict[str, Any]) -> Dict[str, str]:
    """Process an event_callback payload.

    Args:
        payload: Slack event callback payload

    Returns:
        Acknowledgement response
    """
    event_id = payload.get("event_id")
    workspace_id = payload.get("team_id")
    event = payload.get("event", {})
    event_type = event.get("type")

    if not event_id or not workspace_id:
        logger.warning("Invalid event callback: missing event_id or team_id")
        return {"ok": True}

    # Check deduplication
    dedup = get_deduplicator()
    if not await dedup.should_process(event_id):
        logger.debug(f"Skipping duplicate event: {event_id}")
        return {"ok": True}

    try:
        # Find and execute handler
        handler = _event_handlers.get(event_type)
        if handler:
            await handler(workspace_id, event)
        else:
            logger.debug(f"No handler for event type: {event_type}")

        # Mark as processed
        await dedup.mark_processed(event_id)

    except Exception as e:
        logger.error(f"Error processing Slack event {event_id}: {e}")
        await dedup.mark_failed(event_id)
        # Don't raise - Slack will retry if we fail

    return {"ok": True}


@router.get("/status")
async def events_status():
    """Get Slack Events API status and statistics."""
    slack_auth = get_slack_auth()
    dedup = get_deduplicator()

    return {
        "configured": slack_auth is not None and slack_auth.signing_secret is not None,
        "handlers_registered": list(_event_handlers.keys()),
        "deduplication_stats": await dedup.get_stats(),
    }
