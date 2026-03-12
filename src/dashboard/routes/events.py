"""
Server-Sent Events (SSE) routes for real-time updates.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)

router = APIRouter()

# Event queues per guild (in production, use Redis pub/sub)
_event_queues: dict[str, list[asyncio.Queue]] = {}


def _check_guild_access(guild_id: str, user: dict):
    """Check user has access to guild."""
    if guild_id not in user.get("guilds", []):
        return False
    return True


async def _event_generator(
    guild_id: str,
    queue: asyncio.Queue,
    request: Request,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for a guild.

    Args:
        guild_id: Guild to receive events for
        queue: Event queue for this connection
        request: FastAPI request for disconnect detection

    Yields:
        SSE formatted event strings
    """
    try:
        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'guild_id': guild_id, 'timestamp': utc_now_naive().isoformat()})}\n\n"

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                # Wait for event with timeout (for keepalive)
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield ": keepalive\n\n"

    except asyncio.CancelledError:
        pass
    finally:
        # Remove queue from guild's queues
        if guild_id in _event_queues:
            try:
                _event_queues[guild_id].remove(queue)
                if not _event_queues[guild_id]:
                    del _event_queues[guild_id]
            except ValueError:
                pass


@router.get(
    "/guilds/{guild_id}/events",
    summary="Subscribe to guild events",
    description="Server-Sent Events endpoint for real-time guild updates.",
    response_class=StreamingResponse,
)
async def subscribe_events(
    request: Request,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Subscribe to real-time events for a guild via SSE."""
    if not _check_guild_access(guild_id, user):
        return StreamingResponse(
            iter([f"event: error\ndata: {json.dumps({'code': 'FORBIDDEN', 'message': 'No access to guild'})}\n\n"]),
            media_type="text/event-stream",
            status_code=403,
        )

    # Create queue for this connection
    queue: asyncio.Queue = asyncio.Queue()

    # Add to guild's queues
    if guild_id not in _event_queues:
        _event_queues[guild_id] = []
    _event_queues[guild_id].append(queue)

    return StreamingResponse(
        _event_generator(guild_id, queue, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ============================================================================
# Event Publishing API (for internal use by other modules)
# ============================================================================

async def publish_event(guild_id: str, event_type: str, data: dict):
    """Publish an event to all subscribers of a guild.

    Args:
        guild_id: Guild to publish to
        event_type: Event type (e.g., 'summary_completed', 'config_updated')
        data: Event data
    """
    if guild_id not in _event_queues:
        return

    event = {
        "type": event_type,
        "data": {
            **data,
            "timestamp": utc_now_naive().isoformat(),
        },
    }

    # Publish to all queues for this guild
    for queue in _event_queues[guild_id]:
        try:
            await queue.put(event)
        except Exception as e:
            logger.warning(f"Failed to publish event to queue: {e}")


def publish_event_sync(guild_id: str, event_type: str, data: dict):
    """Synchronous wrapper for publishing events.

    Use this from non-async contexts.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(publish_event(guild_id, event_type, data))
        else:
            loop.run_until_complete(publish_event(guild_id, event_type, data))
    except RuntimeError:
        # No event loop, create one
        asyncio.run(publish_event(guild_id, event_type, data))


# ============================================================================
# Predefined event types
# ============================================================================

async def emit_summary_started(guild_id: str, task_id: str, channel_ids: list[str]):
    """Emit event when summary generation starts."""
    await publish_event(guild_id, "summary_started", {
        "task_id": task_id,
        "channel_ids": channel_ids,
    })


async def emit_summary_completed(guild_id: str, task_id: str, summary_id: str):
    """Emit event when summary generation completes."""
    await publish_event(guild_id, "summary_completed", {
        "task_id": task_id,
        "summary_id": summary_id,
    })


async def emit_summary_failed(guild_id: str, task_id: str, error: str):
    """Emit event when summary generation fails."""
    await publish_event(guild_id, "summary_failed", {
        "task_id": task_id,
        "error": error,
    })


async def emit_schedule_executed(guild_id: str, schedule_id: str, status: str, summary_id: Optional[str] = None):
    """Emit event when scheduled task executes."""
    await publish_event(guild_id, "schedule_executed", {
        "schedule_id": schedule_id,
        "status": status,
        "summary_id": summary_id,
    })


async def emit_config_updated(guild_id: str, updated_by: str, changes: list[str]):
    """Emit event when guild config is updated."""
    await publish_event(guild_id, "config_updated", {
        "updated_by": updated_by,
        "changes": changes,
    })


async def emit_channel_sync(guild_id: str, added: int, removed: int):
    """Emit event when channels are synced."""
    await publish_event(guild_id, "channel_sync", {
        "added": added,
        "removed": removed,
    })
