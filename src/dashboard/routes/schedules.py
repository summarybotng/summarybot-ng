"""
Schedule routes for dashboard API.
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path

from ..auth import get_current_user
from ..models import (
    SchedulesResponse,
    ScheduleListItem,
    ScheduleCreateRequest,
    ScheduleUpdateRequest,
    ScheduleRunResponse,
    ExecutionHistoryResponse,
    ExecutionHistoryItem,
    DestinationResponse,
    SummaryOptionsResponse,
    SummaryScope,
    ErrorResponse,
)
from ..utils.scope_resolver import resolve_channels_for_scope
from . import get_discord_bot, get_task_scheduler, get_task_repository

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


def _task_to_response(task, category_name: str = None) -> ScheduleListItem:
    """Convert ScheduledTask to API response."""
    destinations = []
    for dest in task.destinations:
        destinations.append(
            DestinationResponse(
                type=dest.type.value,
                target=dest.target,
                format=dest.format,
            )
        )

    # ADR-011: Include scope info
    scope_value = getattr(task, 'scope', None)
    if scope_value:
        scope_str = scope_value.value if hasattr(scope_value, 'value') else str(scope_value)
    else:
        # Infer scope from existing fields for backward compatibility
        if task.category_id:
            scope_str = "category"
        elif len(task.get_all_channel_ids()) > 1 or not task.get_all_channel_ids():
            scope_str = "guild"
        else:
            scope_str = "channel"

    return ScheduleListItem(
        id=task.id,
        name=task.name,
        scope=scope_str,
        channel_ids=task.get_all_channel_ids(),
        category_id=task.category_id,
        category_name=category_name,
        schedule_type=task.schedule_type.value,
        schedule_time=task.schedule_time or "00:00",
        schedule_days=task.schedule_days if task.schedule_days else None,
        timezone=getattr(task, 'timezone', 'UTC'),
        is_active=task.is_active,
        destinations=destinations,
        summary_options=SummaryOptionsResponse(
            summary_length=task.summary_options.summary_length.value,
            perspective="general",
            include_action_items=task.summary_options.extract_action_items,
            include_technical_terms=task.summary_options.extract_technical_terms,
        ),
        last_run=task.last_run,
        next_run=task.next_run,
        run_count=task.run_count,
        failure_count=task.failure_count,
    )


@router.get(
    "/guilds/{guild_id}/schedules",
    response_model=SchedulesResponse,
    summary="List schedules",
    description="Get all scheduled tasks for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def list_schedules(
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """List schedules for a guild."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    scheduler = get_task_scheduler()
    if not scheduler:
        return SchedulesResponse(schedules=[])

    # Get tasks for this guild
    tasks = await scheduler.get_scheduled_tasks(guild_id)

    # Build category name lookup
    schedules = []
    for task in tasks:
        category_name = None
        if task.category_id:
            try:
                category = guild.get_channel(int(task.category_id))
                if category:
                    category_name = category.name
            except Exception:
                pass
        schedules.append(_task_to_response(task, category_name=category_name))

    return SchedulesResponse(schedules=schedules)


@router.post(
    "/guilds/{guild_id}/schedules",
    response_model=ScheduleListItem,
    summary="Create schedule",
    description="Create a new scheduled task.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def create_schedule(
    body: ScheduleCreateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Create a new schedule."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    scheduler = get_task_scheduler()
    if not scheduler:
        raise HTTPException(
            status_code=503,
            detail={"code": "SCHEDULER_UNAVAILABLE", "message": "Scheduler not available"},
        )

    # ADR-011: Resolve channels based on scope
    from ...models.task import ScheduledTask, ScheduleType, Destination, DestinationType, SummaryScope as TaskScope
    from ...models.summary import SummaryOptions, SummaryLength

    # Convert scope to task scope enum
    try:
        task_scope = TaskScope(body.scope.value if hasattr(body.scope, 'value') else body.scope)
    except ValueError:
        task_scope = TaskScope.CHANNEL

    # Resolve channels for scope
    resolved = await resolve_channels_for_scope(
        guild=guild,
        scope=body.scope,
        channel_ids=body.channel_ids,
        category_id=body.category_id,
    )

    # Get resolved channel IDs
    channel_ids = [str(ch.id) for ch in resolved.channels]
    category_id = body.category_id
    category_name = None

    if resolved.category_info:
        category_name = resolved.category_info.name

    # Convert destinations
    destinations = []
    for dest in body.destinations:
        dest_type = DestinationType(dest.type)
        destinations.append(
            Destination(
                type=dest_type,
                target=dest.target,
                format=dest.format,
            )
        )

    # Convert schedule type
    schedule_type = ScheduleType(body.schedule_type)

    # Create summary options
    summary_opts = SummaryOptions(
        summary_length=SummaryLength(body.summary_options.summary_length if body.summary_options else "detailed"),
        extract_action_items=body.summary_options.include_action_items if body.summary_options else True,
        extract_technical_terms=body.summary_options.include_technical_terms if body.summary_options else True,
    )

    task = ScheduledTask(
        name=body.name,
        scope=task_scope,
        channel_id=channel_ids[0] if channel_ids else "",
        channel_ids=channel_ids,
        category_id=category_id,
        guild_id=guild_id,
        schedule_type=schedule_type,
        schedule_time=body.schedule_time,
        schedule_days=body.schedule_days or [],
        timezone=body.timezone or "UTC",
        destinations=destinations,
        summary_options=summary_opts,
        is_active=True,
        created_by=user["sub"],
        resolve_category_at_runtime=(task_scope in (TaskScope.CATEGORY, TaskScope.GUILD)),
    )

    # Calculate next run
    task.next_run = task.calculate_next_run()

    # Add to scheduler
    await scheduler.schedule_task(task)

    return _task_to_response(task, category_name=category_name)


@router.get(
    "/guilds/{guild_id}/schedules/{schedule_id}",
    response_model=ScheduleListItem,
    summary="Get schedule",
    description="Get details of a specific schedule.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Schedule not found"},
    },
)
async def get_schedule(
    guild_id: str = Path(..., description="Discord guild ID"),
    schedule_id: str = Path(..., description="Schedule ID"),
    user: dict = Depends(get_current_user),
):
    """Get schedule details."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    scheduler = get_task_scheduler()
    if not scheduler:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    task = scheduler.get_task(schedule_id)
    if not task or task.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    # Get category name if applicable
    category_name = None
    if task.category_id:
        try:
            category = guild.get_channel(int(task.category_id))
            if category:
                category_name = category.name
        except Exception:
            pass

    return _task_to_response(task, category_name=category_name)


@router.patch(
    "/guilds/{guild_id}/schedules/{schedule_id}",
    response_model=ScheduleListItem,
    summary="Update schedule",
    description="Update an existing schedule.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Schedule not found"},
    },
)
async def update_schedule(
    body: ScheduleUpdateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    schedule_id: str = Path(..., description="Schedule ID"),
    user: dict = Depends(get_current_user),
):
    """Update a schedule."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    scheduler = get_task_scheduler()
    if not scheduler:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    task = scheduler.get_task(schedule_id)
    if not task or task.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    # Update fields
    if body.name is not None:
        task.name = body.name

    # ADR-011: Handle scope updates
    category_name = None
    if body.scope is not None or body.category_id is not None or body.channel_ids is not None:
        from ...models.task import SummaryScope as TaskScope

        # Determine which scope to use
        scope = body.scope if body.scope is not None else task.scope
        category_id = body.category_id if body.category_id is not None else task.category_id
        channel_ids = body.channel_ids if body.channel_ids is not None else task.channel_ids

        # Convert to enum if needed
        if hasattr(scope, 'value'):
            scope_enum = SummaryScope(scope.value)
        elif isinstance(scope, str):
            scope_enum = SummaryScope(scope)
        else:
            scope_enum = scope

        # Resolve channels based on scope
        resolved = await resolve_channels_for_scope(
            guild=guild,
            scope=scope_enum,
            channel_ids=channel_ids,
            category_id=category_id,
        )

        # Update task with resolved scope
        try:
            task.scope = TaskScope(scope_enum.value)
        except ValueError:
            task.scope = TaskScope.CHANNEL

        task.channel_ids = [str(ch.id) for ch in resolved.channels]
        task.channel_id = task.channel_ids[0] if task.channel_ids else ""
        task.category_id = category_id if scope_enum == SummaryScope.CATEGORY else None
        task.resolve_category_at_runtime = scope_enum in (SummaryScope.CATEGORY, SummaryScope.GUILD)

        if resolved.category_info:
            category_name = resolved.category_info.name

    if body.schedule_type is not None:
        from ...models.task import ScheduleType
        task.schedule_type = ScheduleType(body.schedule_type)

    if body.schedule_time is not None:
        task.schedule_time = body.schedule_time

    if body.schedule_days is not None:
        task.schedule_days = body.schedule_days

    if body.timezone is not None:
        task.timezone = body.timezone

    if body.is_active is not None:
        task.is_active = body.is_active

    if body.destinations is not None:
        from ...models.task import Destination, DestinationType
        task.destinations = [
            Destination(
                type=DestinationType(d.type),
                target=d.target,
                format=d.format,
            )
            for d in body.destinations
        ]

    if body.summary_options is not None:
        from ...models.summary import SummaryLength
        task.summary_options.summary_length = SummaryLength(body.summary_options.summary_length)
        task.summary_options.extract_action_items = body.summary_options.include_action_items
        task.summary_options.extract_technical_terms = body.summary_options.include_technical_terms

    # Recalculate next run
    task.next_run = task.calculate_next_run()

    # Update in scheduler
    await scheduler.update_task(task)

    return _task_to_response(task, category_name=category_name)


@router.delete(
    "/guilds/{guild_id}/schedules/{schedule_id}",
    summary="Delete schedule",
    description="Delete a scheduled task.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Schedule not found"},
    },
)
async def delete_schedule(
    guild_id: str = Path(..., description="Discord guild ID"),
    schedule_id: str = Path(..., description="Schedule ID"),
    user: dict = Depends(get_current_user),
):
    """Delete a schedule."""
    _check_guild_access(guild_id, user)

    scheduler = get_task_scheduler()
    if not scheduler:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    task = scheduler.get_task(schedule_id)
    if not task or task.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    await scheduler.cancel_task(schedule_id)

    return {"success": True}


@router.post(
    "/guilds/{guild_id}/schedules/{schedule_id}/run",
    response_model=ScheduleRunResponse,
    summary="Run schedule now",
    description="Trigger immediate execution of a schedule.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Schedule not found"},
    },
)
async def run_schedule(
    guild_id: str = Path(..., description="Discord guild ID"),
    schedule_id: str = Path(..., description="Schedule ID"),
    user: dict = Depends(get_current_user),
):
    """Run schedule immediately."""
    _check_guild_access(guild_id, user)

    scheduler = get_task_scheduler()
    if not scheduler:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    task = scheduler.get_task(schedule_id)
    if not task or task.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    # Trigger execution
    import secrets
    execution_id = f"exec_{secrets.token_urlsafe(16)}"

    # Run in background
    import asyncio
    asyncio.create_task(scheduler.execute_task(task))

    return ScheduleRunResponse(
        execution_id=execution_id,
        status="started",
    )


@router.get(
    "/guilds/{guild_id}/schedules/{schedule_id}/history",
    response_model=ExecutionHistoryResponse,
    summary="Get execution history",
    description="Get execution history for a schedule.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Schedule not found"},
    },
)
async def get_execution_history(
    guild_id: str = Path(..., description="Discord guild ID"),
    schedule_id: str = Path(..., description="Schedule ID"),
    user: dict = Depends(get_current_user),
):
    """Get execution history."""
    _check_guild_access(guild_id, user)

    scheduler = get_task_scheduler()
    if not scheduler:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    task = scheduler.get_task(schedule_id)
    if not task or task.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Schedule not found"},
        )

    # Fetch execution history from database
    task_repo = await get_task_repository()
    if not task_repo:
        return ExecutionHistoryResponse(executions=[])

    results = await task_repo.get_task_results(schedule_id, limit=50)

    executions = [
        ExecutionHistoryItem(
            execution_id=result.execution_id,
            status=result.status.value if hasattr(result.status, 'value') else result.status,
            started_at=result.started_at,
            completed_at=result.completed_at,
            summary_id=result.summary_id,
            error=result.error_message,
        )
        for result in results
    ]

    return ExecutionHistoryResponse(executions=executions)
