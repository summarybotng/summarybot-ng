"""
Summary routes for dashboard API.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ..auth import get_current_user
from ..models import (
    SummariesResponse,
    SummaryListItem,
    SummaryDetailResponse,
    SummaryPromptResponse,
    ActionItemResponse,
    TechnicalTermResponse,
    ParticipantResponse,
    SummaryMetadataResponse,
    PromptSourceResponse,
    GenerateSummaryRequest,
    GenerateSummaryResponse,
    TaskStatusResponse,
    ErrorResponse,
    # ADR-005: Stored summaries
    StoredSummaryListItem,
    StoredSummaryListResponse,
    StoredSummaryDetailResponse,
    StoredSummaryUpdateRequest,
    PushToChannelRequest,
    PushToChannelResponse,
    PushDeliveryResult,
)
from . import get_discord_bot, get_summarization_engine, get_summary_repository, get_config_manager, get_task_scheduler
from ...data.base import SearchCriteria

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory task tracking (replace with proper task queue in production)
_generation_tasks: dict[str, dict] = {}


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


@router.get(
    "/guilds/{guild_id}/summaries",
    response_model=SummariesResponse,
    summary="List summaries",
    description="Get paginated list of summaries for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def list_summaries(
    guild_id: str = Path(..., description="Discord guild ID"),
    channel_id: Optional[str] = Query(None, description="Filter by channel ID"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    user: dict = Depends(get_current_user),
):
    """List summaries for a guild."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    # Query database for summaries
    summary_repo = await get_summary_repository()
    if not summary_repo:
        logger.warning(f"Summary repository not available for guild {guild_id}")
        return SummariesResponse(summaries=[], total=0, limit=limit, offset=offset)

    logger.info(f"Fetching summaries for guild {guild_id}, channel={channel_id}, limit={limit}")

    criteria = SearchCriteria(
        guild_id=guild_id,
        channel_id=channel_id,
        start_time=start_date,
        end_time=end_date,
        limit=limit,
        offset=offset,
        order_by="created_at",
        order_direction="DESC",
    )

    summaries = await summary_repo.find_summaries(criteria)
    total = await summary_repo.count_summaries(criteria)
    logger.info(f"Found {len(summaries)} summaries (total={total}) for guild {guild_id}")

    # Convert to response format
    summary_items = []
    for summary in summaries:
        # Get channel name - prefer context (handles multi-channel), fall back to Discord lookup
        channel_name = None
        if summary.context and summary.context.channel_name:
            channel_name = summary.context.channel_name
        elif summary.channel_id:
            channel = guild.get_channel(int(summary.channel_id))
            channel_name = channel.name if channel else None

        # Get summary_length from metadata if available
        summary_length = "detailed"
        if hasattr(summary, 'metadata') and summary.metadata:
            summary_length = summary.metadata.get("summary_length", "detailed")

        summary_items.append(
            SummaryListItem(
                id=summary.id,
                channel_id=summary.channel_id,
                channel_name=channel_name or "unknown",
                start_time=summary.start_time,
                end_time=summary.end_time,
                message_count=summary.message_count,
                summary_length=summary_length,
                preview=summary.summary_text[:200] + "..." if len(summary.summary_text) > 200 else summary.summary_text,
                created_at=summary.created_at,
            )
        )

    return SummariesResponse(
        summaries=summary_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/guilds/{guild_id}/summaries/{summary_id}",
    response_model=SummaryDetailResponse,
    summary="Get summary details",
    description="Get full details of a specific summary.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
    },
)
async def get_summary(
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Summary ID"),
    user: dict = Depends(get_current_user),
):
    """Get summary details."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)

    # Fetch from database
    summary_repo = await get_summary_repository()
    if not summary_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    summary = await summary_repo.get_summary(summary_id)
    if not summary or summary.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Summary not found"},
        )

    # Get channel name - prefer context (handles multi-channel), fall back to Discord lookup
    channel_name = None
    if summary.context and summary.context.channel_name:
        channel_name = summary.context.channel_name
    elif summary.channel_id:
        channel = guild.get_channel(int(summary.channel_id))
        channel_name = channel.name if channel else None

    # Convert action items
    action_items = [
        ActionItemResponse(
            text=item.description,
            assignee=item.assignee,
            priority=item.priority.value if hasattr(item.priority, 'value') else item.priority,
        )
        for item in summary.action_items
    ]

    # Convert technical terms
    technical_terms = [
        TechnicalTermResponse(
            term=term.term,
            definition=term.definition,
            category=term.category,
        )
        for term in summary.technical_terms
    ]

    # Convert participants
    participants = [
        ParticipantResponse(
            user_id=p.user_id,
            display_name=p.display_name,
            message_count=p.message_count,
            key_contributions=p.key_contributions,
        )
        for p in summary.participants
    ]

    # Build warnings list
    from ..models import SummaryWarning
    warnings = []
    if hasattr(summary, 'warnings') and summary.warnings:
        for w in summary.warnings:
            warnings.append(SummaryWarning(
                code=w.code,
                message=w.message,
                details=w.details if hasattr(w, 'details') else {}
            ))

    # Debug: log what's in the metadata
    logger.info(f"Summary {summary.id} metadata keys: {list(summary.metadata.keys())}")
    logger.info(f"Summary {summary.id} claude_model: {summary.metadata.get('claude_model')}")
    logger.info(f"Summary {summary.id} total_tokens: {summary.metadata.get('total_tokens')}")

    # Build prompt source info if available
    prompt_source = None
    if summary.metadata.get("prompt_source"):
        ps = summary.metadata["prompt_source"]
        prompt_source = PromptSourceResponse(
            source=ps.get("source", "default"),
            file_path=ps.get("file_path"),
            tried_paths=ps.get("tried_paths", []),
            repo_url=ps.get("repo_url"),
            github_file_url=ps.get("github_file_url"),
            version=ps.get("version", "v1"),
            is_stale=ps.get("is_stale", False),
        )

    # Build metadata (engine stores claude_model, requested_model, total_tokens, processing_time)
    metadata = SummaryMetadataResponse(
        summary_length=summary.metadata.get("summary_length", "detailed"),
        perspective=summary.metadata.get("perspective", "general"),
        model_used=summary.metadata.get("claude_model"),
        model_requested=summary.metadata.get("requested_model"),
        tokens_used=summary.metadata.get("total_tokens"),
        generation_time_seconds=summary.metadata.get("processing_time"),
        warnings=warnings,
        prompt_source=prompt_source,
    )

    # Check if prompt data is available
    has_prompt_data = bool(summary.prompt_system or summary.prompt_user or summary.source_content)

    # Convert references if available (ADR-004)
    from ..models import SummaryReferenceResponse
    references = []
    if hasattr(summary, 'reference_index') and summary.reference_index:
        for ref in summary.reference_index:
            references.append(SummaryReferenceResponse(
                id=ref.id if hasattr(ref, 'id') else ref.get('id', 0),
                author=ref.author if hasattr(ref, 'author') else ref.get('author', 'Unknown'),
                timestamp=ref.timestamp if hasattr(ref, 'timestamp') else ref.get('timestamp'),
                content=ref.content if hasattr(ref, 'content') else ref.get('content', ''),
                message_id=ref.message_id if hasattr(ref, 'message_id') else ref.get('message_id'),
            ))

    return SummaryDetailResponse(
        id=summary.id,
        channel_id=summary.channel_id,
        channel_name=channel_name,
        start_time=summary.start_time,
        end_time=summary.end_time,
        message_count=summary.message_count,
        summary_text=summary.summary_text,
        key_points=summary.key_points,
        action_items=action_items,
        technical_terms=technical_terms,
        participants=participants,
        metadata=metadata,
        created_at=summary.created_at,
        has_prompt_data=has_prompt_data,
        references=references,
    )


@router.get(
    "/guilds/{guild_id}/summaries/{summary_id}/prompt",
    response_model=SummaryPromptResponse,
    summary="Get summary prompt details",
    description="Get the prompt content and source messages used to generate a summary.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
    },
)
async def get_summary_prompt(
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Summary ID"),
    user: dict = Depends(get_current_user),
):
    """Get prompt and source content for a summary."""
    _check_guild_access(guild_id, user)

    # Fetch from database
    summary_repo = await get_summary_repository()
    if not summary_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    summary = await summary_repo.get_summary(summary_id)
    if not summary or summary.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Summary not found"},
        )

    return SummaryPromptResponse(
        summary_id=summary.id,
        prompt_system=summary.prompt_system,
        prompt_user=summary.prompt_user,
        prompt_template_id=summary.prompt_template_id,
        source_content=summary.source_content,
    )


@router.post(
    "/guilds/{guild_id}/summaries/generate",
    response_model=GenerateSummaryResponse,
    summary="Generate summary",
    description="Start generating a new summary for specified channels.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def generate_summary(
    body: GenerateSummaryRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Generate a new summary."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)
    bot = get_discord_bot()
    engine = get_summarization_engine()

    if not engine:
        raise HTTPException(
            status_code=503,
            detail={"code": "ENGINE_UNAVAILABLE", "message": "Summarization engine not available"},
        )

    # Resolve channel_ids based on scope
    from ..models import SummaryScope
    channel_ids = []

    if body.scope == SummaryScope.CHANNEL:
        # Use provided channel IDs
        if not body.channel_ids:
            raise HTTPException(
                status_code=400,
                detail={"code": "MISSING_CHANNELS", "message": "channel_ids required for channel scope"},
            )
        channel_ids = body.channel_ids

    elif body.scope == SummaryScope.CATEGORY:
        # Get all text channels in the specified category
        if not body.category_id:
            raise HTTPException(
                status_code=400,
                detail={"code": "MISSING_CATEGORY", "message": "category_id required for category scope"},
            )
        category = guild.get_channel(int(body.category_id))
        if not category:
            raise HTTPException(
                status_code=404,
                detail={"code": "CATEGORY_NOT_FOUND", "message": "Category not found"},
            )
        # Get text channels in this category
        channel_ids = [str(c.id) for c in guild.text_channels if c.category_id == category.id]
        if not channel_ids:
            raise HTTPException(
                status_code=400,
                detail={"code": "NO_CHANNELS", "message": "No text channels found in category"},
            )

    elif body.scope == SummaryScope.GUILD:
        # Get all enabled channels from guild config
        config_manager = get_config_manager()
        if config_manager:
            config = config_manager.get_current_config()
            guild_config = config.guild_configs.get(guild_id) if config else None
            if guild_config and guild_config.enabled_channels:
                channel_ids = guild_config.enabled_channels
            else:
                # Fall back to all text channels
                channel_ids = [str(c.id) for c in guild.text_channels]
        else:
            channel_ids = [str(c.id) for c in guild.text_channels]

    # Validate channels exist in guild
    guild_channels = {str(c.id) for c in guild.text_channels}
    invalid_channels = set(channel_ids) - guild_channels
    if invalid_channels:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_CHANNELS",
                "message": f"Invalid channel IDs: {', '.join(invalid_channels)}",
            },
        )

    # Create task ID
    import secrets
    task_id = f"gen_{secrets.token_urlsafe(16)}"

    # Calculate time range
    now = datetime.utcnow()
    if body.time_range.type == "hours":
        start_time = now - timedelta(hours=body.time_range.value or 24)
        end_time = now
    elif body.time_range.type == "days":
        start_time = now - timedelta(days=body.time_range.value or 1)
        end_time = now
    else:
        start_time = body.time_range.start or (now - timedelta(hours=24))
        end_time = body.time_range.end or now

    # Store task info
    _generation_tasks[task_id] = {
        "status": "processing",
        "guild_id": guild_id,
        "channel_ids": channel_ids,
        "started_at": now,
        "summary_id": None,
        "error": None,
    }

    # Start generation in background
    async def run_generation():
        logger.info(f"[{task_id}] Starting background summary generation for guild {guild_id}")
        logger.info(f"[{task_id}] Scope: {body.scope.value}, Time range: {start_time} to {end_time}")
        logger.info(f"[{task_id}] Channels ({len(channel_ids)}): {channel_ids}")
        try:
            from ...message_processing import MessageProcessor

            # Collect messages from all channels
            all_messages = []
            channel_errors = []
            for channel_id in channel_ids:
                channel = guild.get_channel(int(channel_id))
                logger.info(f"[{task_id}] Fetching from channel {channel_id}: {channel.name if channel else 'NOT FOUND'}")
                if channel:
                    try:
                        msg_count = 0
                        async for message in channel.history(
                            after=start_time,
                            before=end_time,
                            limit=1000,
                        ):
                            all_messages.append(message)
                            msg_count += 1
                        logger.info(f"[{task_id}] Fetched {msg_count} messages from {channel.name}")
                    except Exception as channel_error:
                        logger.error(f"[{task_id}] Error fetching from {channel.name}: {channel_error}")
                        channel_errors.append((channel_id, channel.name, channel_error))

            # Track any channel-level errors
            if channel_errors:
                try:
                    from ...logging.error_tracker import initialize_error_tracker
                    from ...models.error_log import ErrorType, ErrorSeverity

                    tracker = await initialize_error_tracker()
                    for ch_id, ch_name, ch_error in channel_errors:
                        error_type = ErrorType.DISCORD_PERMISSION if (hasattr(ch_error, 'status') and ch_error.status == 403) else ErrorType.DISCORD_CONNECTION
                        await tracker.capture_error(
                            error=ch_error,
                            error_type=error_type,
                            guild_id=guild_id,
                            channel_id=ch_id,
                            operation=f"fetch_messages ({ch_name})",
                            details={"task_id": task_id, "channel_name": ch_name},
                        )
                        logger.info(f"[{task_id}] Tracked error for channel {ch_name}")
                except Exception as track_err:
                    logger.warning(f"[{task_id}] Failed to track channel errors: {track_err}")

            logger.info(f"[{task_id}] Total messages collected: {len(all_messages)}")

            if not all_messages:
                logger.warning(f"[{task_id}] No messages found in time range")
                _generation_tasks[task_id]["status"] = "failed"
                _generation_tasks[task_id]["error"] = "No messages found in time range"
                return

            # Process messages with relaxed minimum for dashboard
            from ...models.summary import SummaryOptions, SummaryLength

            # Get options from request
            requested_length = body.options.summary_length if body.options else "detailed"
            logger.info(f"[{task_id}] Requested summary_length: {requested_length}")

            options = SummaryOptions(
                summary_length=SummaryLength(requested_length),
                extract_action_items=body.options.include_action_items if body.options else True,
                extract_technical_terms=body.options.include_technical_terms if body.options else True,
                min_messages=1,  # Allow single message summaries from dashboard
            )

            logger.info(f"[{task_id}] SummaryOptions created: summary_length={options.summary_length.value}, max_tokens={options.get_max_tokens_for_length()}")

            logger.info(f"[{task_id}] Processing {len(all_messages)} messages...")
            processor = MessageProcessor(bot.client)
            processed = await processor.process_messages(all_messages, options)
            logger.info(f"[{task_id}] Processed {len(processed)} messages")

            # Get channel and guild info for context
            primary_channel = guild.get_channel(int(channel_ids[0]))
            channel_name = primary_channel.name if primary_channel else "multiple channels"

            # Calculate time span and participant count
            time_span_hours = (end_time - start_time).total_seconds() / 3600
            unique_authors = {msg.author_id for msg in processed}

            # Create summarization context
            from ...models.summary import SummarizationContext
            context = SummarizationContext(
                channel_name=channel_name if len(channel_ids) == 1 else f"{len(channel_ids)} channels",
                guild_name=guild.name,
                total_participants=len(unique_authors),
                time_span_hours=time_span_hours,
            )

            logger.info(f"[{task_id}] Calling summarization engine...")
            result = await engine.summarize_messages(
                messages=processed,
                options=options,
                context=context,
                guild_id=guild_id,
                channel_id=channel_ids[0],  # Primary channel for storage
            )
            logger.info(f"[{task_id}] Summarization complete, result id: {result.id}")

            # Save summary to database
            logger.info(f"[{task_id}] Getting summary repository...")
            summary_repo = await get_summary_repository()
            if summary_repo:
                logger.info(f"[{task_id}] Saving summary to database...")
                await summary_repo.save_summary(result)
                logger.info(f"[{task_id}] Saved summary {result.id} to database for guild {guild_id}, scope {body.scope.value}")
            else:
                logger.error(f"[{task_id}] Summary repository not available - summary {result.id} NOT saved!")

            _generation_tasks[task_id]["status"] = "completed"
            _generation_tasks[task_id]["summary_id"] = result.id
            logger.info(f"[{task_id}] Generation task completed successfully")

        except Exception as e:
            logger.error(f"[{task_id}] Summary generation failed: {e}", exc_info=True)
            _generation_tasks[task_id]["status"] = "failed"
            _generation_tasks[task_id]["error"] = str(e)

            # Track the error for dashboard visibility
            try:
                from ...logging.error_tracker import initialize_error_tracker
                from ...models.error_log import ErrorType, ErrorSeverity

                tracker = await initialize_error_tracker()

                # Determine error type
                error_type = ErrorType.SUMMARIZATION_ERROR
                if hasattr(e, 'status'):
                    if e.status == 403:
                        error_type = ErrorType.DISCORD_PERMISSION
                    elif e.status == 404:
                        error_type = ErrorType.DISCORD_NOT_FOUND

                await tracker.capture_error(
                    error=e,
                    error_type=error_type,
                    guild_id=guild_id,
                    channel_id=channel_ids[0] if channel_ids else None,
                    operation=f"generate_summary ({body.scope.value})",
                    details={
                        "task_id": task_id,
                        "channel_count": len(channel_ids),
                        "scope": body.scope.value,
                    },
                )
            except Exception as track_error:
                logger.warning(f"Failed to track error: {track_error}")

    # Start background task
    asyncio.create_task(run_generation())

    return GenerateSummaryResponse(
        task_id=task_id,
        status="processing",
    )


@router.get(
    "/guilds/{guild_id}/summaries/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Check generation status",
    description="Check the status of a summary generation task.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Task not found"},
    },
)
async def get_task_status(
    guild_id: str = Path(..., description="Discord guild ID"),
    task_id: str = Path(..., description="Task ID"),
    user: dict = Depends(get_current_user),
):
    """Get task status."""
    _check_guild_access(guild_id, user)

    task = _generation_tasks.get(task_id)
    if not task or task["guild_id"] != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Task not found"},
        )

    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        summary_id=task.get("summary_id"),
        error=task.get("error"),
    )


# ============================================================================
# Stored Summaries (ADR-005)
# ============================================================================


async def _get_stored_summary_repository():
    """Get the stored summary repository."""
    from ...data.repositories import get_stored_summary_repository
    return await get_stored_summary_repository()


@router.get(
    "/guilds/{guild_id}/stored-summaries",
    response_model=StoredSummaryListResponse,
    summary="List stored summaries",
    description="Get paginated list of stored summaries for a guild (ADR-005, ADR-008).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def list_stored_summaries(
    guild_id: str = Path(..., description="Discord guild ID"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    pinned: Optional[bool] = Query(None, description="Filter by pinned status"),
    archived: bool = Query(False, description="Include archived summaries"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    source: Optional[str] = Query(
        None,
        description="ADR-008: Filter by source (realtime, archive, scheduled, manual, all)"
    ),
    user: dict = Depends(get_current_user),
):
    """List stored summaries for a guild.

    ADR-008: Supports unified listing of both real-time and archive summaries.
    Use source parameter to filter by summary origin.
    """
    _check_guild_access(guild_id, user)
    _get_guild_or_404(guild_id)

    stored_repo = await _get_stored_summary_repository()
    offset = (page - 1) * limit

    # Parse tags if provided
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Fetch stored summaries
    summaries = await stored_repo.find_by_guild(
        guild_id=guild_id,
        limit=limit,
        offset=offset,
        pinned_only=pinned is True,
        include_archived=archived,
        tags=tag_list,
        source=source,  # ADR-008: Source filtering
    )

    total = await stored_repo.count_by_guild(
        guild_id=guild_id,
        include_archived=archived,
    )

    # ADR-009: Build schedule name lookup for summaries with schedule_ids
    schedule_names: dict[str, str] = {}
    scheduler = get_task_scheduler()
    if scheduler:
        schedule_ids = {s.schedule_id for s in summaries if s.schedule_id}
        for schedule_id in schedule_ids:
            task = scheduler.get_task(schedule_id)
            if task:
                schedule_names[schedule_id] = task.name

    # Convert to response items
    items = []
    for s in summaries:
        item_dict = s.to_list_item_dict()
        # ADR-009: Add schedule_name if available
        if s.schedule_id and s.schedule_id in schedule_names:
            item_dict["schedule_name"] = schedule_names[s.schedule_id]
        items.append(StoredSummaryListItem(**item_dict))

    return StoredSummaryListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/guilds/{guild_id}/stored-summaries/{summary_id}",
    response_model=StoredSummaryDetailResponse,
    summary="Get stored summary details",
    description="Get full details of a stored summary (ADR-005).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
    },
)
async def get_stored_summary(
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Stored summary ID"),
    user: dict = Depends(get_current_user),
):
    """Get stored summary details."""
    _check_guild_access(guild_id, user)

    stored_repo = await _get_stored_summary_repository()
    stored = await stored_repo.get(summary_id)

    if not stored or stored.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Stored summary not found"},
        )

    # Mark as viewed
    if not stored.viewed_at:
        stored.mark_viewed()
        await stored_repo.update(stored)

    # Build response
    summary_result = stored.summary_result
    action_items = []
    participants = []
    metadata = None

    if summary_result:
        action_items = [
            ActionItemResponse(
                text=item.description,
                assignee=item.assignee,
                priority=item.priority.value if hasattr(item.priority, 'value') else item.priority,
            )
            for item in summary_result.action_items
        ]

        participants = [
            ParticipantResponse(
                user_id=p.user_id,
                display_name=p.display_name,
                message_count=p.message_count,
                key_contributions=p.key_contributions,
            )
            for p in summary_result.participants
        ]

        metadata = SummaryMetadataResponse(
            summary_length=summary_result.metadata.get("summary_length", "detailed"),
            perspective=summary_result.metadata.get("perspective", "general"),
            model_used=summary_result.metadata.get("claude_model"),
            model_requested=summary_result.metadata.get("requested_model"),
            tokens_used=summary_result.metadata.get("total_tokens"),
            generation_time_seconds=summary_result.metadata.get("processing_time"),
        )

    # Build references from summary_result if available (ADR-004)
    from ..models import SummaryReferenceResponse
    references = []
    if summary_result and hasattr(summary_result, 'reference_index') and summary_result.reference_index:
        for ref in summary_result.reference_index:
            # Handle both object and dict formats
            if hasattr(ref, 'position'):
                # Object format
                references.append(SummaryReferenceResponse(
                    id=ref.position,
                    author=ref.sender,
                    timestamp=ref.timestamp,
                    content=ref.snippet,
                    message_id=ref.message_id,
                ))
            elif isinstance(ref, dict):
                # Dict format (from DB)
                from datetime import datetime
                ts = ref.get('timestamp')
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                references.append(SummaryReferenceResponse(
                    id=ref.get('position', 0),
                    author=ref.get('sender', 'Unknown'),
                    timestamp=ts,
                    content=ref.get('snippet', ''),
                    message_id=ref.get('message_id'),
                ))

    return StoredSummaryDetailResponse(
        id=stored.id,
        title=stored.title,
        guild_id=stored.guild_id,
        source_channel_ids=stored.source_channel_ids,
        schedule_id=stored.schedule_id,
        created_at=stored.created_at,
        viewed_at=stored.viewed_at,
        pushed_at=stored.pushed_at,
        is_pinned=stored.is_pinned,
        is_archived=stored.is_archived,
        tags=stored.tags,
        summary_text=summary_result.summary_text if summary_result else "",
        key_points=summary_result.key_points if summary_result else [],
        action_items=action_items,
        participants=participants,
        message_count=stored.get_message_count(),
        start_time=summary_result.start_time if summary_result else None,
        end_time=summary_result.end_time if summary_result else None,
        metadata=metadata,
        push_deliveries=[d.to_dict() for d in stored.push_deliveries],
        has_references=stored.has_references(),
        references=references,
        # ADR-008: Source tracking
        source=stored.source.value,
        archive_period=stored.archive_period,
        archive_granularity=stored.archive_granularity,
        archive_source_key=stored.archive_source_key,
    )


@router.patch(
    "/guilds/{guild_id}/stored-summaries/{summary_id}",
    response_model=StoredSummaryDetailResponse,
    summary="Update stored summary",
    description="Update stored summary metadata (title, tags, pin, archive) (ADR-005).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
    },
)
async def update_stored_summary(
    body: StoredSummaryUpdateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Stored summary ID"),
    user: dict = Depends(get_current_user),
):
    """Update stored summary metadata."""
    _check_guild_access(guild_id, user)

    stored_repo = await _get_stored_summary_repository()
    stored = await stored_repo.get(summary_id)

    if not stored or stored.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Stored summary not found"},
        )

    # Apply updates
    if body.title is not None:
        stored.title = body.title
    if body.is_pinned is not None:
        stored.is_pinned = body.is_pinned
    if body.is_archived is not None:
        stored.is_archived = body.is_archived
    if body.tags is not None:
        stored.tags = body.tags

    await stored_repo.update(stored)

    # Return updated summary
    return await get_stored_summary(guild_id, summary_id, user)


@router.delete(
    "/guilds/{guild_id}/stored-summaries/{summary_id}",
    summary="Delete stored summary",
    description="Delete a stored summary (ADR-005).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
    },
)
async def delete_stored_summary(
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Stored summary ID"),
    user: dict = Depends(get_current_user),
):
    """Delete a stored summary."""
    _check_guild_access(guild_id, user)

    stored_repo = await _get_stored_summary_repository()
    stored = await stored_repo.get(summary_id)

    if not stored or stored.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Stored summary not found"},
        )

    await stored_repo.delete(summary_id)

    return {"success": True, "message": f"Deleted stored summary {summary_id}"}


@router.post(
    "/guilds/{guild_id}/stored-summaries/{summary_id}/push",
    response_model=PushToChannelResponse,
    summary="Push to channel",
    description="Push a stored summary to Discord channel(s) (ADR-005).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
    },
)
async def push_to_channel(
    body: PushToChannelRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Stored summary ID"),
    user: dict = Depends(get_current_user),
):
    """Push a stored summary to Discord channels."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)
    bot = get_discord_bot()

    if not bot or not bot.client:
        raise HTTPException(
            status_code=503,
            detail={"code": "BOT_UNAVAILABLE", "message": "Discord bot not available"},
        )

    # Validate channel IDs belong to guild
    guild_channel_ids = {str(c.id) for c in guild.text_channels}
    invalid_channels = set(body.channel_ids) - guild_channel_ids
    if invalid_channels:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_CHANNELS",
                "message": f"Invalid channel IDs: {', '.join(invalid_channels)}",
            },
        )

    # Use push service
    from ...services.summary_push import SummaryPushService

    push_service = SummaryPushService(discord_client=bot.client)

    try:
        result = await push_service.push_to_channels(
            summary_id=summary_id,
            channel_ids=body.channel_ids,
            format=body.format,
            include_references=body.include_references,
            custom_message=body.custom_message,
            user_id=user.get("id"),
            include_key_points=body.include_key_points,
            include_action_items=body.include_action_items,
            include_participants=body.include_participants,
            include_technical_terms=body.include_technical_terms,
        )

        return PushToChannelResponse(
            success=result.success,
            total_channels=result.total_channels,
            successful_channels=result.successful_channels,
            deliveries=[
                PushDeliveryResult(
                    channel_id=d.channel_id,
                    success=d.success,
                    message_id=d.message_id,
                    error=d.error,
                )
                for d in result.deliveries
            ],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": str(e)},
        )


@router.post(
    "/guilds/{guild_id}/summaries/{summary_id}/push",
    response_model=PushToChannelResponse,
    summary="Push summary to channel",
    description="Push a summary from history to Discord channel(s).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
    },
)
async def push_summary_to_channel(
    body: PushToChannelRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Summary ID"),
    user: dict = Depends(get_current_user),
):
    """Push a summary to Discord channels."""
    _check_guild_access(guild_id, user)
    guild = _get_guild_or_404(guild_id)
    bot = get_discord_bot()

    if not bot or not bot.client:
        raise HTTPException(
            status_code=503,
            detail={"code": "BOT_UNAVAILABLE", "message": "Discord bot not available"},
        )

    # Validate channels belong to guild
    guild_channels = {str(c.id) for c in guild.text_channels}
    invalid_channels = set(body.channel_ids) - guild_channels
    if invalid_channels:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_CHANNELS",
                "message": f"Invalid channel IDs: {', '.join(invalid_channels)}",
            },
        )

    # Use push service
    from ...services.summary_push import SummaryPushService

    push_service = SummaryPushService(discord_client=bot.client)

    try:
        result = await push_service.push_summary_to_channels(
            summary_id=summary_id,
            channel_ids=body.channel_ids,
            format=body.format,
            include_references=body.include_references,
            custom_message=body.custom_message,
            user_id=user.get("id"),
            include_key_points=body.include_key_points,
            include_action_items=body.include_action_items,
            include_participants=body.include_participants,
            include_technical_terms=body.include_technical_terms,
        )

        return PushToChannelResponse(
            success=result.success,
            total_channels=result.total_channels,
            successful_channels=result.successful_channels,
            deliveries=[
                PushDeliveryResult(
                    channel_id=d.channel_id,
                    success=d.success,
                    message_id=d.message_id,
                    error=d.error,
                )
                for d in result.deliveries
            ],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": str(e)},
        )
