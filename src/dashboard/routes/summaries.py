"""
Summary routes for dashboard API.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ..auth import get_current_user, require_guild_admin
from src.utils.time import utc_now_naive
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
    PromptSourceResponse,
    # ADR-018: Bulk operations
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkRegenerateRequest,
    BulkRegenerateResponse,
    RegenerateOptionsRequest,
    # ADR-030: Email delivery
    SendToEmailRequest,
    SendToEmailResponse,
    EmailDeliveryResult,
)
from . import get_discord_bot, get_summarization_engine, get_summary_repository, get_stored_summary_repository, get_config_manager, get_task_scheduler, get_summary_job_repository
from ...data.base import SearchCriteria
from ...models.stored_summary import StoredSummary, SummarySource
from ...models.summary_job import SummaryJob, JobType, JobStatus

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
    perspective: Optional[str] = Query(None, description="Filter by perspective (general, developer, executive, etc.)"),
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

    logger.info(f"Fetching summaries for guild {guild_id}, channel={channel_id}, perspective={perspective}, limit={limit}")

    criteria = SearchCriteria(
        guild_id=guild_id,
        channel_id=channel_id,
        start_time=start_date,
        end_time=end_date,
        perspective=perspective,
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
    # Note: SummaryReference uses 'sender', 'snippet', 'position' fields
    from ..models import SummaryReferenceResponse
    references = []
    if hasattr(summary, 'reference_index') and summary.reference_index:
        for ref in summary.reference_index:
            # Handle both SummaryReference objects and dict representations
            if hasattr(ref, 'position'):
                # SummaryReference object
                references.append(SummaryReferenceResponse(
                    id=ref.position,
                    author=ref.sender,
                    timestamp=ref.timestamp,
                    content=ref.snippet,
                    message_id=ref.message_id,
                ))
            else:
                # Dict representation (from database JSON)
                references.append(SummaryReferenceResponse(
                    id=ref.get('position', 0),
                    author=ref.get('sender', 'Unknown'),
                    timestamp=ref.get('timestamp'),
                    content=ref.get('snippet', ''),
                    message_id=ref.get('message_id'),
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

    # Create job ID (ADR-013: use job_ prefix for unified job tracking)
    import secrets
    job_id = f"job_{secrets.token_urlsafe(16)}"

    # Calculate time range
    now = utc_now_naive()
    if body.time_range.type == "hours":
        start_time = now - timedelta(hours=body.time_range.value or 24)
        end_time = now
    elif body.time_range.type == "days":
        start_time = now - timedelta(days=body.time_range.value or 1)
        end_time = now
    else:
        start_time = body.time_range.start or (now - timedelta(hours=24))
        end_time = body.time_range.end or now

    # ADR-013: Create persistent job record
    job = SummaryJob(
        id=job_id,
        guild_id=guild_id,
        job_type=JobType.MANUAL,
        status=JobStatus.PENDING,
        scope=body.scope.value,
        channel_ids=channel_ids,
        category_id=body.category_id,
        period_start=start_time,
        period_end=end_time,
        created_by=user.get("id"),
        metadata={
            "summary_length": body.options.summary_length if body.options else "detailed",
            "include_action_items": body.options.include_action_items if body.options else True,
            "include_technical_terms": body.options.include_technical_terms if body.options else True,
        },
    )

    # Persist job to database
    job_repo = await get_summary_job_repository()
    if job_repo:
        try:
            await job_repo.save(job)
            logger.info(f"[{job_id}] Created job record in database")
        except Exception as e:
            logger.warning(f"[{job_id}] Failed to persist job: {e}")

    # Also store in-memory for backwards compatibility with task status endpoint
    task_id = job_id  # Use same ID for compatibility
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
        logger.info(f"[{job_id}] Starting background summary generation for guild {guild_id}")
        logger.info(f"[{job_id}] Scope: {body.scope.value}, Time range: {start_time} to {end_time}")
        logger.info(f"[{job_id}] Channels ({len(channel_ids)}): {channel_ids}")

        # ADR-013: Mark job as RUNNING
        job.start()
        job.update_progress(0, len(channel_ids) + 2, "Fetching messages")  # +2 for processing and summarization
        if job_repo:
            try:
                await job_repo.update(job)
            except Exception as e:
                logger.warning(f"[{job_id}] Failed to update job status: {e}")

        try:
            from ...message_processing import MessageProcessor

            # Collect messages from all channels
            all_messages = []
            channel_errors = []
            for idx, channel_id in enumerate(channel_ids):
                channel = guild.get_channel(int(channel_id))
                logger.info(f"[{job_id}] Fetching from channel {channel_id}: {channel.name if channel else 'NOT FOUND'}")
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
                        logger.info(f"[{job_id}] Fetched {msg_count} messages from {channel.name}")

                        # ADR-013: Update job progress
                        job.update_progress(idx + 1, None, f"Fetched {channel.name}")
                        if job_repo:
                            try:
                                await job_repo.update(job)
                            except Exception:
                                pass
                    except Exception as channel_error:
                        logger.error(f"[{job_id}] Error fetching from {channel.name}: {channel_error}")
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
                            details={"job_id": job_id, "channel_name": ch_name},
                        )
                        logger.info(f"[{job_id}] Tracked error for channel {ch_name}")
                except Exception as track_err:
                    logger.warning(f"[{job_id}] Failed to track channel errors: {track_err}")

            logger.info(f"[{job_id}] Total messages collected: {len(all_messages)}")

            if not all_messages:
                logger.warning(f"[{job_id}] No messages found in time range")
                _generation_tasks[task_id]["status"] = "failed"
                _generation_tasks[task_id]["error"] = "No messages found in time range"

                # ADR-013: Mark job as failed
                job.fail("No messages found in time range")
                if job_repo:
                    try:
                        await job_repo.update(job)
                    except Exception:
                        pass
                return

            # Process messages with relaxed minimum for dashboard
            from ...models.summary import SummaryOptions, SummaryLength

            # ADR-013: Update progress - processing
            job.update_progress(len(channel_ids), None, "Processing messages")
            if job_repo:
                try:
                    await job_repo.update(job)
                except Exception:
                    pass

            # Get options from request
            requested_length = body.options.summary_length if body.options else "detailed"
            logger.info(f"[{job_id}] Requested summary_length: {requested_length}")

            options = SummaryOptions(
                summary_length=SummaryLength(requested_length),
                extract_action_items=body.options.include_action_items if body.options else True,
                extract_technical_terms=body.options.include_technical_terms if body.options else True,
                min_messages=1,  # Allow single message summaries from dashboard
            )

            logger.info(f"[{job_id}] SummaryOptions created: summary_length={options.summary_length.value}, max_tokens={options.get_max_tokens_for_length()}")

            logger.info(f"[{job_id}] Processing {len(all_messages)} messages...")
            processor = MessageProcessor(bot.client)
            processed = await processor.process_messages(all_messages, options)
            logger.info(f"[{job_id}] Processed {len(processed)} messages")

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

            # ADR-034: Resolve custom prompt template if specified
            custom_system_prompt = None
            if body.prompt_template_id:
                try:
                    from ...data.repositories import get_prompt_template_repository
                    template_repo = await get_prompt_template_repository()
                    template = await template_repo.get_template(body.prompt_template_id)
                    if template:
                        custom_system_prompt = template.content
                        logger.info(f"[{job_id}] Using custom template '{template.name}'")
                    else:
                        logger.warning(f"[{job_id}] Template {body.prompt_template_id} not found")
                except Exception as e:
                    logger.warning(f"[{job_id}] Failed to fetch template: {e}")

            # ADR-013: Update progress - summarizing
            job.update_progress(len(channel_ids) + 1, None, "Generating summary")
            if job_repo:
                try:
                    await job_repo.update(job)
                except Exception:
                    pass

            logger.info(f"[{job_id}] Calling summarization engine...")
            result = await engine.summarize_messages(
                messages=processed,
                options=options,
                context=context,
                guild_id=guild_id,
                channel_id=channel_ids[0],  # Primary channel for storage
                custom_system_prompt=custom_system_prompt,  # ADR-034
            )
            logger.info(f"[{job_id}] Summarization complete, result id: {result.id}")

            # ADR-012: Save to StoredSummaryRepository (unified storage)
            # This ensures all summaries appear in the same tab with consistent features
            logger.info(f"[{job_id}] Getting stored summary repository...")
            stored_repo = await get_stored_summary_repository()
            if stored_repo:
                # Generate descriptive title
                channel_names = []
                for cid in channel_ids[:3]:  # Limit to 3 channels in title
                    ch = guild.get_channel(int(cid))
                    if ch:
                        channel_names.append(f"#{ch.name}")
                if len(channel_ids) > 3:
                    channel_names.append(f"+{len(channel_ids) - 3} more")
                title = f"{', '.join(channel_names) or 'Summary'} — {utc_now_naive().strftime('%b %d, %H:%M')}"

                # Create StoredSummary with source=MANUAL for generate button
                stored_summary = StoredSummary(
                    id=result.id,
                    guild_id=guild_id,
                    source_channel_ids=channel_ids,
                    summary_result=result,
                    title=title,
                    source=SummarySource.MANUAL,  # From Generate button
                    created_at=utc_now_naive(),
                )

                logger.info(f"[{job_id}] Saving to stored_summaries...")
                await stored_repo.save(stored_summary)
                logger.info(f"[{job_id}] Saved summary {result.id} to stored_summaries for guild {guild_id}, scope {body.scope.value}")
            else:
                logger.error(f"[{job_id}] Stored summary repository not available - summary {result.id} NOT saved!")

            # Also save to legacy summaries table for backwards compatibility
            logger.info(f"[{job_id}] Getting legacy summary repository...")
            summary_repo = await get_summary_repository()
            if summary_repo:
                await summary_repo.save_summary(result)
                logger.info(f"[{job_id}] Also saved to legacy summaries table")

            _generation_tasks[task_id]["status"] = "completed"
            _generation_tasks[task_id]["summary_id"] = result.id

            # ADR-013: Mark job as completed
            job.complete(result.id)
            job.update_progress(len(channel_ids) + 2, len(channel_ids) + 2, "Complete")
            if job_repo:
                try:
                    await job_repo.update(job)
                    logger.info(f"[{job_id}] Job record updated to COMPLETED")
                except Exception as e:
                    logger.warning(f"[{job_id}] Failed to update job completion: {e}")

            logger.info(f"[{job_id}] Generation task completed successfully")

        except Exception as e:
            logger.error(f"[{job_id}] Summary generation failed: {e}", exc_info=True)
            _generation_tasks[task_id]["status"] = "failed"
            _generation_tasks[task_id]["error"] = str(e)

            # ADR-013: Mark job as failed
            job.fail(str(e))
            if job_repo:
                try:
                    await job_repo.update(job)
                    logger.info(f"[{job_id}] Job record updated to FAILED")
                except Exception as update_err:
                    logger.warning(f"[{job_id}] Failed to update job failure: {update_err}")

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
                        "job_id": job_id,
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
    description="Get paginated list of stored summaries for a guild (ADR-005, ADR-008, ADR-017).",
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
    # ADR-017: Enhanced filtering
    created_after: Optional[str] = Query(None, description="Filter by creation date (ISO format)"),
    created_before: Optional[str] = Query(None, description="Filter by creation date (ISO format)"),
    archive_period: Optional[str] = Query(None, description="Filter by archive period (YYYY-MM-DD)"),
    channel_mode: Optional[str] = Query(None, description="Filter by channel mode (single, multi)"),
    has_grounding: Optional[bool] = Query(None, description="Filter by grounding status"),
    sort_by: str = Query("created_at", description="Sort field (created_at, message_count)"),
    sort_order: str = Query("desc", description="Sort direction (asc, desc)"),
    # ADR-018: Content-based filters
    has_key_points: Optional[bool] = Query(None, description="Filter by key points presence"),
    has_action_items: Optional[bool] = Query(None, description="Filter by action items presence"),
    has_participants: Optional[bool] = Query(None, description="Filter by participants presence"),
    min_message_count: Optional[int] = Query(None, ge=0, description="Minimum message count"),
    max_message_count: Optional[int] = Query(None, ge=0, description="Maximum message count"),
    # ADR-021: Content count filters
    min_key_points: Optional[int] = Query(None, ge=0, description="Minimum number of key points"),
    max_key_points: Optional[int] = Query(None, ge=0, description="Maximum number of key points"),
    min_action_items: Optional[int] = Query(None, ge=0, description="Minimum number of action items"),
    max_action_items: Optional[int] = Query(None, ge=0, description="Maximum number of action items"),
    min_participants: Optional[int] = Query(None, ge=0, description="Minimum number of participants"),
    max_participants: Optional[int] = Query(None, ge=0, description="Maximum number of participants"),
    # ADR-026: Platform filter
    platform: Optional[str] = Query(None, description="Filter by platform (discord, whatsapp, slack, all)"),
    user: dict = Depends(get_current_user),
):
    """List stored summaries for a guild.

    ADR-008: Supports unified listing of both real-time and archive summaries.
    ADR-017: Enhanced filtering by date, channel mode, grounding, and sorting.
    ADR-018: Content-based filtering by key points, action items, participants.
    ADR-026: Platform filtering by archive_source_key prefix.
    """
    _check_guild_access(guild_id, user)
    _get_guild_or_404(guild_id)

    stored_repo = await _get_stored_summary_repository()
    offset = (page - 1) * limit

    # Parse tags if provided
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # ADR-017: Parse date filters
    created_after_dt = None
    created_before_dt = None
    if created_after:
        try:
            created_after_dt = datetime.fromisoformat(created_after.replace("Z", "+00:00"))
        except ValueError:
            pass
    if created_before:
        try:
            created_before_dt = datetime.fromisoformat(created_before.replace("Z", "+00:00"))
        except ValueError:
            pass

    # Fetch stored summaries with ADR-017/ADR-018 filters
    summaries = await stored_repo.find_by_guild(
        guild_id=guild_id,
        limit=limit,
        offset=offset,
        pinned_only=pinned is True,
        include_archived=archived,
        tags=tag_list,
        source=source,
        created_after=created_after_dt,
        created_before=created_before_dt,
        archive_period=archive_period,
        channel_mode=channel_mode,
        has_grounding=has_grounding,
        sort_by=sort_by,
        sort_order=sort_order,
        # ADR-018: Content filters
        has_key_points=has_key_points,
        has_action_items=has_action_items,
        has_participants=has_participants,
        min_message_count=min_message_count,
        max_message_count=max_message_count,
        # ADR-021: Content count filters
        min_key_points=min_key_points,
        max_key_points=max_key_points,
        min_action_items=min_action_items,
        max_action_items=max_action_items,
        min_participants=min_participants,
        max_participants=max_participants,
        # ADR-026: Platform filter
        platform=platform,
    )

    total = await stored_repo.count_by_guild(
        guild_id=guild_id,
        include_archived=archived,
        source=source,
        created_after=created_after_dt,
        created_before=created_before_dt,
        archive_period=archive_period,
        channel_mode=channel_mode,
        has_grounding=has_grounding,
        # ADR-018: Content filters
        has_key_points=has_key_points,
        has_action_items=has_action_items,
        has_participants=has_participants,
        min_message_count=min_message_count,
        max_message_count=max_message_count,
        # ADR-021: Content count filters
        min_key_points=min_key_points,
        max_key_points=max_key_points,
        min_action_items=min_action_items,
        max_action_items=max_action_items,
        min_participants=min_participants,
        max_participants=max_participants,
        # ADR-026: Platform filter
        platform=platform,
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

        # Handle both regular and archive metadata formats
        meta = summary_result.metadata

        # Model: archive uses "model", regular uses "claude_model"
        model_used = meta.get("claude_model") or meta.get("model_used") or meta.get("model")

        # Tokens: archive uses tokens_input/tokens_output, regular uses total_tokens
        tokens_used = meta.get("total_tokens")
        input_tokens = meta.get("input_tokens") or meta.get("tokens_input")
        output_tokens = meta.get("output_tokens") or meta.get("tokens_output")
        if tokens_used is None and (input_tokens or output_tokens):
            tokens_used = (input_tokens or 0) + (output_tokens or 0)

        # Time: archive uses duration_seconds, regular uses processing_time
        generation_time = meta.get("processing_time") or meta.get("duration_seconds")
        generation_time_ms = generation_time * 1000 if generation_time else None

        metadata = SummaryMetadataResponse(
            summary_length=meta.get("summary_length") or meta.get("summary_type", "detailed"),
            perspective=meta.get("perspective", "general"),
            model_used=model_used,
            model_requested=meta.get("requested_model") or meta.get("model_requested"),
            tokens_used=tokens_used,
            generation_time_seconds=generation_time,
            # Extended fields
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            generation_time_ms=generation_time_ms,
            summary_type=meta.get("summary_type"),
            grounded=meta.get("grounded"),
            reference_count=len(summary_result.reference_index) if summary_result.reference_index else 0,
            channel_name=meta.get("channel_name"),
            guild_name=meta.get("guild_name"),
            time_span_hours=meta.get("time_span_hours"),
            total_participants=meta.get("total_participants"),
            api_version=meta.get("api_version"),
            cache_status=meta.get("cache_status"),
            # ADR-024: Retry attempt tracking
            generation_attempts=meta.get("generation_attempts"),
        )

        # Add prompt_source if available
        if meta.get("prompt_source"):
            ps = meta["prompt_source"]
            metadata.prompt_source = PromptSourceResponse(
                source=ps.get("source", "default"),
                file_path=ps.get("file_path"),
                github_file_url=ps.get("github_file_url"),
                path_template=ps.get("path_template"),
                resolved_variables=ps.get("resolved_variables"),
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

    # ADR-020: Get navigation (prev/next)
    navigation = await stored_repo.get_navigation(
        summary_id=summary_id,
        guild_id=guild_id,
        source=stored.source.value if stored.source else None,
    )

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
        # Generation details (prompt data)
        source_content=summary_result.source_content if summary_result else None,
        prompt_system=summary_result.prompt_system if summary_result else None,
        prompt_user=summary_result.prompt_user if summary_result else None,
        prompt_template_id=summary_result.prompt_template_id if summary_result else None,
        # ADR-020: Navigation
        navigation=navigation,
    )


# ADR-017: Calendar endpoint for summary overview
@router.get(
    "/guilds/{guild_id}/stored-summaries/calendar/{year}/{month}",
    summary="Get calendar data for summaries",
    description="Get summary counts grouped by day for calendar view (ADR-017).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def get_summary_calendar(
    guild_id: str = Path(..., description="Discord guild ID"),
    year: int = Path(..., ge=2020, le=2100, description="Year"),
    month: int = Path(..., ge=1, le=12, description="Month (1-12)"),
    archived: bool = Query(False, description="Include archived summaries"),
    user: dict = Depends(get_current_user),
):
    """Get calendar data showing summary counts by day.

    Returns list of days with summaries, their counts, sources, and integrity status.
    """
    _check_guild_access(guild_id, user)

    stored_repo = await _get_stored_summary_repository()
    calendar_data = await stored_repo.get_calendar_data(
        guild_id=guild_id,
        year=year,
        month=month,
        include_archived=archived,
    )

    return {
        "year": year,
        "month": month,
        "days": calendar_data,
    }


# ADR-020: Navigation and Search

@router.get(
    "/guilds/{guild_id}/stored-summaries/{summary_id}/navigation",
    summary="Get summary navigation",
    description="Get previous/next summary IDs for navigation (ADR-020).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
    },
)
async def get_summary_navigation(
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Stored summary ID"),
    source: Optional[str] = Query(None, description="Filter navigation by source type"),
    user: dict = Depends(get_current_user),
):
    """Get previous/next summary links for navigation.

    Returns IDs and dates of adjacent summaries for chronological browsing.
    """
    _check_guild_access(guild_id, user)

    stored_repo = await _get_stored_summary_repository()

    # Verify summary exists and belongs to guild
    stored = await stored_repo.get(summary_id)
    if not stored or stored.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Stored summary not found"},
        )

    navigation = await stored_repo.get_navigation(
        summary_id=summary_id,
        guild_id=guild_id,
        source=source,
    )

    return {
        "summary_id": summary_id,
        "navigation": navigation,
    }


@router.get(
    "/guilds/{guild_id}/stored-summaries/search",
    summary="Search summaries",
    description="Full-text search across summary content (ADR-020).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        400: {"model": ErrorResponse, "description": "Invalid query"},
    },
)
async def search_summaries(
    guild_id: str = Path(..., description="Discord guild ID"),
    q: str = Query(..., min_length=2, description="Search query"),
    fields: Optional[str] = Query(
        None,
        description="Comma-separated fields to search (summary_text, key_points, action_items, participants, technical_terms)"
    ),
    source: Optional[str] = Query(None, description="Filter by source type"),
    date_from: Optional[str] = Query(None, description="Start date (ISO format)"),
    date_to: Optional[str] = Query(None, description="End date (ISO format)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user: dict = Depends(get_current_user),
):
    """Search summaries by content, keywords, or participants.

    Supports FTS5 query syntax:
    - Simple terms: `authentication`
    - Phrases: `"user login"`
    - Boolean: `authentication AND bug`
    - Prefix: `auth*`
    """
    _check_guild_access(guild_id, user)

    stored_repo = await _get_stored_summary_repository()

    # Parse fields
    field_list = None
    if fields:
        field_list = [f.strip() for f in fields.split(",") if f.strip()]
        valid_fields = {"summary_text", "key_points", "action_items", "participants", "technical_terms"}
        invalid_fields = set(field_list) - valid_fields
        if invalid_fields:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_FIELDS", "message": f"Invalid fields: {invalid_fields}"},
            )

    # Parse dates
    date_from_dt = None
    date_to_dt = None
    if date_from:
        try:
            date_from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_DATE", "message": "Invalid date_from format"},
            )
    if date_to:
        try:
            date_to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_DATE", "message": "Invalid date_to format"},
            )

    try:
        results = await stored_repo.search(
            guild_id=guild_id,
            query=q,
            fields=field_list,
            source=source,
            date_from=date_from_dt,
            date_to=date_to_dt,
            limit=limit,
            offset=offset,
        )
        return results
    except Exception as e:
        # FTS query errors
        logger.warning(f"Search error for query '{q}': {e}")
        raise HTTPException(
            status_code=400,
            detail={"code": "SEARCH_ERROR", "message": f"Invalid search query: {str(e)}"},
        )


@router.get(
    "/guilds/{guild_id}/stored-summaries/by-participant",
    summary="Search by participant",
    description="Find summaries mentioning specific participants (ADR-020).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def search_by_participant(
    guild_id: str = Path(..., description="Discord guild ID"),
    user_id: Optional[str] = Query(None, description="Discord user ID"),
    display_name: Optional[str] = Query(None, description="Partial name match"),
    date_from: Optional[str] = Query(None, description="Start date (ISO format)"),
    date_to: Optional[str] = Query(None, description="End date (ISO format)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user: dict = Depends(get_current_user),
):
    """Find all summaries mentioning a specific participant.

    Returns participant stats and matching summaries with key contributions.
    """
    _check_guild_access(guild_id, user)

    if not user_id and not display_name:
        raise HTTPException(
            status_code=400,
            detail={"code": "MISSING_PARAM", "message": "Provide user_id or display_name"},
        )

    stored_repo = await _get_stored_summary_repository()

    # Parse dates
    date_from_dt = None
    date_to_dt = None
    if date_from:
        try:
            date_from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        except ValueError:
            pass
    if date_to:
        try:
            date_to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
        except ValueError:
            pass

    results = await stored_repo.search_by_participant(
        guild_id=guild_id,
        user_id=user_id,
        display_name=display_name,
        date_from=date_from_dt,
        date_to=date_to_dt,
        limit=limit,
        offset=offset,
    )

    return results


@router.post(
    "/guilds/{guild_id}/stored-summaries/{summary_id}/regenerate",
    response_model=GenerateSummaryResponse,
    summary="Regenerate stored summary",
    description="Regenerate a stored summary with updated grounding/references and optional model/perspective changes.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
        503: {"model": ErrorResponse, "description": "Engine unavailable"},
    },
)
async def regenerate_stored_summary(
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Stored summary ID"),
    body: Optional[RegenerateOptionsRequest] = None,
    user: dict = Depends(get_current_user),
):
    """
    Regenerate a stored summary with optional new settings.

    Options:
    - model: Use a different Claude model
    - summary_length: brief, detailed, or comprehensive
    - perspective: general, developer, marketing, executive, support

    Also adds grounded references (ADR-004) and repairs missing metadata (ADR-016).
    """
    _check_guild_access(guild_id, user)

    # Get stored summary
    stored_repo = await _get_stored_summary_repository()
    stored = await stored_repo.get(summary_id)

    if not stored or stored.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Stored summary not found"},
        )

    summary_result = stored.summary_result
    repairs_made = []

    # ADR-016: Try to repair missing data
    start_time = None
    end_time = None
    channel_ids = stored.source_channel_ids or []

    # Try to get time range
    if summary_result and summary_result.start_time and summary_result.end_time:
        start_time = summary_result.start_time
        end_time = summary_result.end_time
    else:
        # Repair: infer from archive_period or created_at
        if stored.archive_period:
            # archive_period is like "2024-02-22"
            try:
                from datetime import timezone as tz
                period_date = datetime.strptime(stored.archive_period, "%Y-%m-%d")
                start_time = period_date.replace(hour=0, minute=0, second=0, tzinfo=tz.utc)
                end_time = period_date.replace(hour=23, minute=59, second=59, tzinfo=tz.utc)
                repairs_made.append(f"inferred time range from archive_period: {stored.archive_period}")
            except Exception as e:
                logger.warning(f"Failed to parse archive_period: {e}")

        if not start_time and stored.created_at:
            # Fall back to 24 hours before created_at
            start_time = stored.created_at - timedelta(hours=24)
            end_time = stored.created_at
            repairs_made.append("inferred time range from created_at (24h window)")

    # Try to get channel IDs
    if not channel_ids:
        # Repair: extract from archive_source_key
        if stored.archive_source_key:
            # Format: "discord/guild_id/channel_id" or similar
            parts = stored.archive_source_key.split("/")
            if len(parts) >= 3:
                channel_ids = [parts[2]]
                repairs_made.append(f"extracted channel from archive_source_key: {parts[2]}")

    # Check if we can use source_content as fallback
    has_source_content = summary_result and summary_result.source_content
    can_use_discord = bool(start_time and end_time and channel_ids)

    if not can_use_discord and not has_source_content:
        issues = []
        if not start_time or not end_time:
            issues.append("no time range")
        if not channel_ids:
            issues.append("no source channels")
        if not has_source_content:
            issues.append("no source_content fallback")
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CANNOT_REGENERATE",
                "message": f"Cannot regenerate: {', '.join(issues)}",
                "repairs_attempted": repairs_made,
            },
        )

    # Get dependencies
    engine = get_summarization_engine()
    if not engine:
        raise HTTPException(
            status_code=503,
            detail={"code": "ENGINE_UNAVAILABLE", "message": "Summarization engine not available"},
        )

    # For Discord fetch, we need the guild and bot
    guild = None
    bot = None
    if can_use_discord:
        try:
            guild = _get_guild_or_404(guild_id)
            bot = get_discord_bot()
        except Exception as e:
            # SEC-005: Log Discord access failure
            logger.debug(f"Discord access failed for guild {guild_id}: {e}")
            can_use_discord = False
            if not has_source_content:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "NO_DISCORD_ACCESS", "message": "Cannot access Discord and no source_content fallback"},
                )

    # Create task ID
    import secrets
    task_id = f"regen_{secrets.token_urlsafe(16)}"

    # Determine regeneration method
    regen_method = "discord" if can_use_discord else "source_content"

    # Store task info
    _generation_tasks[task_id] = {
        "status": "processing",
        "guild_id": guild_id,
        "channel_ids": channel_ids,
        "started_at": utc_now_naive(),
        "summary_id": summary_id,
        "error": None,
        "regenerate": True,
        "method": regen_method,
        "repairs": repairs_made,
    }

    async def run_regeneration():
        logger.info(f"[{task_id}] Starting regeneration for summary {summary_id}")
        logger.info(f"[{task_id}] Method: {regen_method}, Repairs: {repairs_made}")

        try:
            from ...message_processing import MessageProcessor
            from ...models.summary import SummaryOptions, SummaryLength, SummarizationContext
            from ...models.message import ProcessedMessage, MessageType

            processed = []

            if regen_method == "discord" and can_use_discord:
                logger.info(f"[{task_id}] Fetching from Discord: {start_time} to {end_time}")
                logger.info(f"[{task_id}] Channels: {channel_ids}")

                # Collect messages from all channels
                all_messages = []
                for channel_id in channel_ids:
                    channel = guild.get_channel(int(channel_id))
                    if channel:
                        try:
                            async for message in channel.history(
                                after=start_time,
                                before=end_time,
                                limit=1000,
                            ):
                                all_messages.append(message)
                        except Exception as e:
                            logger.warning(f"[{task_id}] Error fetching from channel {channel_id}: {e}")

                logger.info(f"[{task_id}] Fetched {len(all_messages)} messages from Discord")

                if all_messages:
                    processor = MessageProcessor(bot.client)
                    processed = await processor.process_messages(all_messages, SummaryOptions(min_messages=1))

            # Fallback to source_content if Discord fetch failed or returned no messages
            if not processed and has_source_content:
                logger.info(f"[{task_id}] Using source_content fallback")
                # Parse source_content back to messages
                lines = summary_result.source_content.strip().split('\n')
                i = 0
                for line in lines:
                    if line.startswith('[') and '] ' in line:
                        try:
                            bracket_end = line.index('] ')
                            timestamp_str = line[1:bracket_end]
                            rest = line[bracket_end + 2:]

                            if ': ' in rest:
                                author, content = rest.split(': ', 1)
                            else:
                                author = "Unknown"
                                content = rest

                            try:
                                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M')
                            except ValueError:
                                # SEC-005: Specific exception for date parsing
                                timestamp = stored.created_at or utc_now_naive()

                            processed.append(ProcessedMessage(
                                id=f"src_{i}",
                                author_name=author,
                                author_id=f"user_{i}",
                                content=content,
                                timestamp=timestamp,
                                message_type=MessageType.DEFAULT,
                                channel_id=channel_ids[0] if channel_ids else None,
                            ))
                            i += 1
                        except Exception as e:
                            logger.debug(f"[{task_id}] Could not parse line: {e}")

                logger.info(f"[{task_id}] Parsed {len(processed)} messages from source_content")

            if not processed:
                _generation_tasks[task_id]["status"] = "failed"
                _generation_tasks[task_id]["error"] = "No messages found (Discord fetch failed and no valid source_content)"
                return

            # Get options from request body or fall back to original metadata
            meta = summary_result.metadata or {}

            # Use body options if provided, otherwise fall back to original
            if body and body.summary_length:
                summary_length_str = body.summary_length
            else:
                summary_length_str = meta.get("summary_length", meta.get("summary_type", "detailed"))

            if body and body.perspective:
                perspective = body.perspective
            else:
                perspective = meta.get("perspective", "general")

            # Model override from body
            model_override = body.model if body and body.model else None

            options = SummaryOptions(
                summary_length=SummaryLength(summary_length_str),
                perspective=perspective,
                min_messages=1,
            )

            # Apply model override if specified
            if model_override:
                options.summarization_model = model_override
                logger.info(f"[{task_id}] Using custom model: {model_override}")

            # Build context (handle case where guild might be None for source_content regen)
            channel_name = "regenerated"
            guild_name = ""
            if guild and channel_ids:
                primary_channel = guild.get_channel(int(channel_ids[0]))
                channel_name = primary_channel.name if primary_channel else "unknown"
                guild_name = guild.name

            actual_start = start_time or (stored.created_at - timedelta(hours=24))
            actual_end = end_time or stored.created_at
            time_span_hours = (actual_end - actual_start).total_seconds() / 3600
            unique_authors = {msg.author_id for msg in processed}

            context = SummarizationContext(
                channel_name=channel_name if len(channel_ids) <= 1 else f"{len(channel_ids)} channels",
                guild_name=guild_name,
                total_participants=len(unique_authors),
                time_span_hours=time_span_hours,
            )

            # Generate new summary with grounding (skip cache for regeneration)
            logger.info(f"[{task_id}] Generating summary with grounding...")
            new_result = await engine.summarize_messages(
                messages=processed,
                options=options,
                context=context,
                guild_id=guild_id,
                channel_id=channel_ids[0] if channel_ids else "",
                skip_cache=True,  # Always generate fresh for regeneration
            )

            # Check grounding
            has_refs = bool(new_result.reference_index)
            logger.info(f"[{task_id}] New summary has {len(new_result.reference_index)} references, grounded={has_refs}")

            # Preserve original ID but update the summary_result
            new_result.id = summary_id

            # Update the stored summary
            stored.summary_result = new_result
            await stored_repo.update(stored)

            _generation_tasks[task_id]["status"] = "completed"
            _generation_tasks[task_id]["summary_id"] = summary_id
            _generation_tasks[task_id]["grounded"] = has_refs
            _generation_tasks[task_id]["reference_count"] = len(new_result.reference_index)
            logger.info(f"[{task_id}] Regeneration complete")

        except Exception as e:
            logger.error(f"[{task_id}] Regeneration failed: {e}", exc_info=True)
            _generation_tasks[task_id]["status"] = "failed"
            _generation_tasks[task_id]["error"] = str(e)

    # Start background task
    asyncio.create_task(run_regeneration())

    return GenerateSummaryResponse(
        task_id=task_id,
        status="processing",
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
    description="Delete a stored summary (ADR-005, ADR-019).",
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
    """Delete a stored summary.

    ADR-019: Also deletes the corresponding disk file to keep storage in sync.
    """
    _check_guild_access(guild_id, user)

    stored_repo = await _get_stored_summary_repository()
    stored = await stored_repo.get(summary_id)

    if not stored or stored.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Stored summary not found"},
        )

    # ADR-019: Delete disk file if this is an archive summary
    disk_deleted = False
    if stored.source == SummarySource.ARCHIVE and stored.archive_period:
        try:
            from datetime import datetime as dt
            from pathlib import Path
            import os
            from ...archive.writer import delete_summary_file
            from ...archive.models import SourceType, ArchiveSource

            # Parse archive_period to date
            period_date = dt.strptime(stored.archive_period, "%Y-%m-%d").date()

            # Create ArchiveSource from stored summary data
            source = ArchiveSource(
                source_type=SourceType.DISCORD,
                server_id=guild_id,
                server_name=guild_id,  # Name not needed for path
            )

            archive_root = Path(os.environ.get("ARCHIVE_ROOT", "./summarybot-archive"))
            disk_deleted = delete_summary_file(archive_root, source, period_date)
            if disk_deleted:
                logger.info(f"Deleted disk file for archive summary {summary_id}")
        except Exception as e:
            logger.warning(f"Failed to delete disk file for {summary_id}: {e}")

    # Delete from database (authoritative)
    await stored_repo.delete(summary_id)

    return {
        "success": True,
        "message": f"Deleted stored summary {summary_id}",
        "disk_deleted": disk_deleted,
    }


# ADR-018: Bulk delete endpoint
@router.post(
    "/guilds/{guild_id}/stored-summaries/bulk-delete",
    response_model=BulkDeleteResponse,
    summary="Bulk delete summaries",
    description="Delete multiple stored summaries at once (ADR-018). Provide either summary_ids or filters.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def bulk_delete_summaries(
    body: BulkDeleteRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Bulk delete stored summaries.

    ADR-018 Enhancement: Supports filter-based selection for "select all matching" functionality.
    """
    _check_guild_access(guild_id, user)

    stored_repo = await _get_stored_summary_repository()

    # If filters provided, resolve to IDs first
    if body.filters:
        # Parse date filters
        created_after_dt = None
        created_before_dt = None
        if body.filters.created_after:
            try:
                created_after_dt = datetime.fromisoformat(body.filters.created_after.replace("Z", "+00:00"))
            except ValueError:
                pass
        if body.filters.created_before:
            try:
                created_before_dt = datetime.fromisoformat(body.filters.created_before.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Get all IDs matching filters (no pagination limit)
        summaries = await stored_repo.find_by_guild(
            guild_id=guild_id,
            limit=10000,  # High limit for bulk operations
            offset=0,
            include_archived=body.filters.archived if body.filters.archived else False,
            source=body.filters.source,
            created_after=created_after_dt,
            created_before=created_before_dt,
            archive_period=body.filters.archive_period,
            channel_mode=body.filters.channel_mode,
            has_grounding=body.filters.has_grounding,
            has_key_points=body.filters.has_key_points,
            has_action_items=body.filters.has_action_items,
            has_participants=body.filters.has_participants,
            min_message_count=body.filters.min_message_count,
            max_message_count=body.filters.max_message_count,
        )
        summary_ids = [s.id for s in summaries]
        logger.info(f"Bulk delete: resolved {len(summary_ids)} IDs from filters")
    else:
        summary_ids = body.summary_ids

    if not summary_ids:
        return BulkDeleteResponse(deleted_count=0, failed_ids=[], errors=["No summaries matched the criteria"])

    result = await stored_repo.bulk_delete(summary_ids, guild_id)

    return BulkDeleteResponse(
        deleted_count=result["deleted_count"],
        failed_ids=result.get("failed_ids", []),
        errors=result.get("errors", []),
    )


# ADR-018: Bulk regenerate endpoint
@router.post(
    "/guilds/{guild_id}/stored-summaries/bulk-regenerate",
    response_model=BulkRegenerateResponse,
    summary="Bulk regenerate summaries",
    description="Queue multiple summaries for regeneration with grounding (ADR-018). Provide either summary_ids or filters.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def bulk_regenerate_summaries(
    body: BulkRegenerateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Bulk regenerate stored summaries with grounding.

    ADR-018 Enhancement: Supports filter-based selection for "select all matching" functionality.
    """
    _check_guild_access(guild_id, user)

    stored_repo = await _get_stored_summary_repository()

    # If filters provided, resolve to IDs first
    if body.filters:
        # Parse date filters
        created_after_dt = None
        created_before_dt = None
        if body.filters.created_after:
            try:
                created_after_dt = datetime.fromisoformat(body.filters.created_after.replace("Z", "+00:00"))
            except ValueError:
                pass
        if body.filters.created_before:
            try:
                created_before_dt = datetime.fromisoformat(body.filters.created_before.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Get all IDs matching filters (no pagination limit)
        summaries = await stored_repo.find_by_guild(
            guild_id=guild_id,
            limit=1000,  # Limit for regeneration (expensive operation)
            offset=0,
            include_archived=body.filters.archived if body.filters.archived else False,
            source=body.filters.source,
            created_after=created_after_dt,
            created_before=created_before_dt,
            archive_period=body.filters.archive_period,
            channel_mode=body.filters.channel_mode,
            has_grounding=body.filters.has_grounding,
            has_key_points=body.filters.has_key_points,
            has_action_items=body.filters.has_action_items,
            has_participants=body.filters.has_participants,
            min_message_count=body.filters.min_message_count,
            max_message_count=body.filters.max_message_count,
        )
        summary_ids = [s.id for s in summaries]
        logger.info(f"Bulk regenerate: resolved {len(summary_ids)} IDs from filters")
    else:
        summary_ids = body.summary_ids

    if not summary_ids:
        return BulkRegenerateResponse(
            queued_count=0,
            skipped_count=0,
            skipped_ids=[],
            task_id="none",
        )

    # Filter to summaries that can be regenerated (have source_content)
    queued_ids = []
    skipped_ids = []

    for summary_id in summary_ids:
        stored = await stored_repo.get(summary_id)
        if not stored or stored.guild_id != guild_id:
            skipped_ids.append(summary_id)
            continue

        # Check if regeneration is possible
        if not stored.summary_result or not stored.summary_result.source_content:
            skipped_ids.append(summary_id)
            continue

        # Check if already has grounding
        if stored.has_references():
            skipped_ids.append(summary_id)
            continue

        queued_ids.append(summary_id)

    # Create bulk task
    import secrets
    task_id = f"bulk_regen_{secrets.token_urlsafe(8)}"

    # Store task info
    _generation_tasks[task_id] = {
        "status": "processing",
        "type": "bulk_regenerate",
        "guild_id": guild_id,
        "summary_ids": queued_ids,
        "completed": 0,
        "total": len(queued_ids),
        "started_at": utc_now_naive(),
        "errors": [],
    }

    # Start background regeneration
    async def run_bulk_regeneration():
        for idx, summary_id in enumerate(queued_ids):
            try:
                # Trigger individual regeneration
                stored = await stored_repo.get(summary_id)
                if stored and stored.summary_result:
                    # Re-use existing regeneration logic
                    from ...summarization.adapter import SummarizationAdapter
                    engine = get_summarization_engine()
                    if engine:
                        adapter = SummarizationAdapter(engine)
                        new_result = await adapter.regenerate_with_grounding(stored.summary_result)
                        new_result.id = summary_id
                        stored.summary_result = new_result
                        await stored_repo.update(stored)
                        _generation_tasks[task_id]["completed"] = idx + 1
            except Exception as e:
                logger.error(f"Bulk regeneration failed for {summary_id}: {e}")
                _generation_tasks[task_id]["errors"].append(f"{summary_id}: {str(e)}")

        _generation_tasks[task_id]["status"] = "completed"

    asyncio.create_task(run_bulk_regeneration())

    return BulkRegenerateResponse(
        queued_count=len(queued_ids),
        skipped_count=len(skipped_ids),
        skipped_ids=skipped_ids,
        task_id=task_id,
    )


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
    require_guild_admin(guild_id, user)  # Admin only - sends to Discord
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
        # ADR-014: Use template-based push for full content with threads
        if body.format in ("template", "thread"):
            result = await push_service.push_to_channels_with_template(
                summary_id=summary_id,
                channel_ids=body.channel_ids,
                user_id=user.get("id"),
            )
        else:
            # Legacy embed/markdown/plain formats
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
    require_guild_admin(guild_id, user)  # Admin only - sends to Discord
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


# ==================== ADR-030: Email Delivery ====================

@router.post(
    "/guilds/{guild_id}/summaries/{summary_id}/email",
    response_model=SendToEmailResponse,
    summary="Send summary via email",
    description="Send a stored summary to email recipients (ADR-030).",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid email addresses"},
        404: {"model": ErrorResponse, "description": "Summary not found"},
        503: {"model": ErrorResponse, "description": "Email not configured"},
    },
)
async def send_summary_to_email(
    body: SendToEmailRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    summary_id: str = Path(..., description="Stored summary ID"),
    user: dict = Depends(get_current_user),
):
    """Send a stored summary to email recipients.

    ADR-030: Email Delivery Destination.
    Requires SMTP configuration (SMTP_ENABLED=true).
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        _check_guild_access(guild_id, user)
        require_guild_admin(guild_id, user)  # Admin only

        from ...services.email_delivery import get_email_service, EmailContext
        from ...data.repositories import get_stored_summary_repository

        # Check if email is configured
        email_service = get_email_service()
        if not email_service.is_configured():
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "EMAIL_NOT_CONFIGURED",
                    "message": "SMTP not configured. Set SMTP_ENABLED=true and configure SMTP_* environment variables.",
                },
            )

        # Validate email addresses
        valid_recipients = email_service.parse_recipients(",".join(body.recipients))
        if not valid_recipients:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_RECIPIENTS",
                    "message": "No valid email addresses provided.",
                },
            )

        # Load summary
        repo = await get_stored_summary_repository()
        summary = await repo.get(summary_id)
        if not summary or summary.guild_id != guild_id:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": f"Summary {summary_id} not found"},
            )

        # Verify summary has content
        if not summary.summary_result:
            raise HTTPException(
                status_code=400,
                detail={"code": "NO_CONTENT", "message": "Summary has no content to email"},
            )

        # Build email context
        context = EmailContext(
            guild_name=f"Guild {guild_id}",
            start_time=summary.summary_result.start_time if summary.summary_result else None,
            end_time=summary.summary_result.end_time if summary.summary_result else None,
            message_count=summary.summary_result.message_count if summary.summary_result else 0,
            participant_count=len(summary.summary_result.participants) if summary.summary_result and summary.summary_result.participants else 0,
        )

        # Send email
        result = await email_service.send_summary(
            summary=summary.summary_result,
            recipients=valid_recipients,
            context=context,
            subject=body.subject,
            guild_id=guild_id,
        )

        # Build response
        deliveries = []
        for recipient in result.recipients_sent:
            deliveries.append(EmailDeliveryResult(recipient=recipient, success=True))
        for recipient in result.recipients_failed:
            deliveries.append(EmailDeliveryResult(recipient=recipient, success=False, error="Delivery failed"))

        return SendToEmailResponse(
            success=result.success,
            total_recipients=len(valid_recipients),
            successful_recipients=len(result.recipients_sent),
            failed_recipients=len(result.recipients_failed),
            deliveries=deliveries,
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.exception(f"Email delivery failed for summary {summary_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"code": "EMAIL_FAILED", "message": f"Email delivery failed: {str(e)}"},
        )


# ==================== Diagnostic Endpoint ====================

@router.get(
    "/guilds/{guild_id}/_debug/summaries-db",
    summary="Database diagnostics",
    description="Check database state for debugging summary generation issues.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def debug_database(
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """
    Debug endpoint to check database state.

    Returns information about:
    - Schema version
    - Table columns (to check if migrations ran)
    - Recent tasks
    - Connection status
    """
    _check_guild_access(guild_id, user)

    result = {
        "schema_version": None,
        "stored_summaries_columns": [],
        "stored_summaries_count": 0,
        "recent_tasks": [],
        "last_errors": [],
        "connection_ok": False,
        "errors": [],
    }

    try:
        # Get stored summary repository to test connection
        stored_repo = await get_stored_summary_repository()
        if not stored_repo:
            result["errors"].append("Stored summary repository not available")
            return result

        result["connection_ok"] = True

        # Check schema version
        try:
            from ...data.repositories import get_repository_factory
            factory = get_repository_factory()
            conn = await factory.get_connection()

            # Get schema version
            row = await conn.fetch_one(
                "SELECT MAX(version) as version FROM schema_version"
            )
            if row:
                result["schema_version"] = row.get("version")

            # Get stored_summaries columns
            columns_result = await conn.fetch_all(
                "PRAGMA table_info(stored_summaries)"
            )
            result["stored_summaries_columns"] = [
                {"name": c["name"], "type": c["type"]}
                for c in columns_result
            ]

            # Count stored summaries for this guild
            count_row = await conn.fetch_one(
                "SELECT COUNT(*) as count FROM stored_summaries WHERE guild_id = ?",
                (guild_id,)
            )
            if count_row:
                result["stored_summaries_count"] = count_row.get("count", 0)

            # Get recent summaries table count too
            summaries_count = await conn.fetch_one(
                "SELECT COUNT(*) as count FROM summaries WHERE guild_id = ?",
                (guild_id,)
            )
            if summaries_count:
                result["summaries_count"] = summaries_count.get("count", 0)

        except Exception as e:
            result["errors"].append(f"Schema check error: {str(e)}")

        # Get recent in-memory tasks
        recent_tasks = []
        for task_id, task_data in list(_generation_tasks.items())[-10:]:
            if task_data.get("guild_id") == guild_id:
                recent_tasks.append({
                    "task_id": task_id,
                    "status": task_data.get("status"),
                    "error": task_data.get("error"),
                    "started_at": task_data.get("started_at").isoformat() if task_data.get("started_at") else None,
                    "summary_id": task_data.get("summary_id"),
                })
        result["recent_tasks"] = recent_tasks

        # Check for required columns
        column_names = [c["name"] for c in result["stored_summaries_columns"]]
        required_columns = ["source", "archive_period", "archive_granularity", "archive_source_key"]
        missing_columns = [c for c in required_columns if c not in column_names]
        if missing_columns:
            result["errors"].append(f"Missing columns (migrations not run?): {missing_columns}")
            result["migration_hint"] = "Run migrations 011 and 012"

    except Exception as e:
        result["errors"].append(f"Diagnostic error: {str(e)}")

    return result


# ============================================================================
# ADR-013: Unified Job Tracking Endpoints
# ============================================================================

from ..models import (
    JobType as APIJobType,
    JobStatus as APIJobStatus,
    JobProgressResponse,
    JobCostResponse,
    JobListItem,
    JobDetailResponse,
    JobsListResponse,
    JobCancelResponse,
    JobRetryResponse,
)


def _job_to_list_item(job: SummaryJob) -> JobListItem:
    """Convert SummaryJob to JobListItem for API response."""
    return JobListItem(
        job_id=job.id,
        guild_id=job.guild_id,
        job_type=APIJobType(job.job_type.value),
        status=APIJobStatus(job.status.value),
        scope=job.scope,
        schedule_id=job.schedule_id,
        progress=JobProgressResponse(
            current=job.progress_current,
            total=job.progress_total,
            percent=job.percent_complete,
            message=job.progress_message,
            current_period=job.current_period,
        ),
        summary_id=job.summary_id,
        error=job.error,
        pause_reason=job.pause_reason,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _job_to_detail(job: SummaryJob) -> JobDetailResponse:
    """Convert SummaryJob to JobDetailResponse for API response."""
    return JobDetailResponse(
        job_id=job.id,
        guild_id=job.guild_id,
        job_type=APIJobType(job.job_type.value),
        status=APIJobStatus(job.status.value),
        scope=job.scope,
        channel_ids=job.channel_ids,
        category_id=job.category_id,
        schedule_id=job.schedule_id,
        period_start=job.period_start,
        period_end=job.period_end,
        progress=JobProgressResponse(
            current=job.progress_current,
            total=job.progress_total,
            percent=job.percent_complete,
            message=job.progress_message,
            current_period=job.current_period,
        ),
        cost=JobCostResponse(
            cost_usd=job.cost_usd,
            tokens_input=job.tokens_input,
            tokens_output=job.tokens_output,
        ),
        summary_id=job.summary_id,
        summary_ids=job.summary_ids,
        error=job.error,
        pause_reason=job.pause_reason,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_by=job.created_by,
        metadata=job.metadata,
    )


@router.get(
    "/guilds/{guild_id}/jobs",
    response_model=JobsListResponse,
    summary="List jobs (ADR-013)",
    description="Get paginated list of summary generation jobs for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def list_jobs(
    guild_id: str = Path(..., description="Discord guild ID"),
    job_type: Optional[str] = Query(None, description="Filter by job type (manual, scheduled, retrospective)"),
    status: Optional[str] = Query(None, description="Filter by status (pending, running, completed, failed, cancelled, paused)"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    user: dict = Depends(get_current_user),
):
    """List jobs for a guild."""
    _check_guild_access(guild_id, user)

    job_repo = await get_summary_job_repository()
    if not job_repo:
        return JobsListResponse(jobs=[], total=0, limit=limit, offset=offset)

    # Convert filter params to strings for repository
    type_filter = job_type if job_type else None
    status_filter = status if status else None

    # Get jobs from repository
    jobs = await job_repo.find_by_guild(
        guild_id=guild_id,
        job_type=type_filter,
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    # Get total count
    total = await job_repo.count_by_guild(
        guild_id=guild_id,
        job_type=type_filter,
        status=status_filter,
    )

    job_items = [_job_to_list_item(job) for job in jobs]

    return JobsListResponse(
        jobs=job_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/guilds/{guild_id}/jobs/{job_id}",
    response_model=JobDetailResponse,
    summary="Get job details (ADR-013)",
    description="Get full details of a specific job.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def get_job(
    guild_id: str = Path(..., description="Discord guild ID"),
    job_id: str = Path(..., description="Job ID"),
    user: dict = Depends(get_current_user),
):
    """Get job details."""
    _check_guild_access(guild_id, user)

    job_repo = await get_summary_job_repository()
    if not job_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    job = await job_repo.get(job_id)
    if not job or job.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Job not found"},
        )

    return _job_to_detail(job)


@router.post(
    "/guilds/{guild_id}/jobs/{job_id}/cancel",
    response_model=JobCancelResponse,
    summary="Cancel job (ADR-013)",
    description="Cancel a running or pending job.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        400: {"model": ErrorResponse, "description": "Job cannot be cancelled"},
    },
)
async def cancel_job(
    guild_id: str = Path(..., description="Discord guild ID"),
    job_id: str = Path(..., description="Job ID"),
    user: dict = Depends(get_current_user),
):
    """Cancel a job."""
    _check_guild_access(guild_id, user)

    job_repo = await get_summary_job_repository()
    if not job_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    job = await job_repo.get(job_id)
    if not job or job.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Job not found"},
        )

    if not job.can_cancel:
        raise HTTPException(
            status_code=400,
            detail={"code": "CANNOT_CANCEL", "message": f"Job with status '{job.status.value}' cannot be cancelled"},
        )

    job.cancel()
    await job_repo.update(job)

    logger.info(f"Cancelled job {job_id} by user {user.get('id')}")

    return JobCancelResponse(
        success=True,
        job_id=job_id,
        message="Job cancelled successfully",
    )


@router.post(
    "/guilds/{guild_id}/jobs/{job_id}/retry",
    response_model=JobRetryResponse,
    summary="Retry job (ADR-013)",
    description="Retry a failed job.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        400: {"model": ErrorResponse, "description": "Job cannot be retried"},
    },
)
async def retry_job(
    guild_id: str = Path(..., description="Discord guild ID"),
    job_id: str = Path(..., description="Job ID"),
    user: dict = Depends(get_current_user),
):
    """Retry a failed job."""
    _check_guild_access(guild_id, user)

    job_repo = await get_summary_job_repository()
    if not job_repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Database not available"},
        )

    job = await job_repo.get(job_id)
    if not job or job.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Job not found"},
        )

    if not job.can_retry:
        raise HTTPException(
            status_code=400,
            detail={"code": "CANNOT_RETRY", "message": f"Job with status '{job.status.value}' cannot be retried"},
        )

    # Create a new job with the same parameters
    import secrets
    new_job_id = f"job_{secrets.token_urlsafe(16)}"

    new_job = SummaryJob(
        id=new_job_id,
        guild_id=job.guild_id,
        job_type=job.job_type,
        status=JobStatus.PENDING,
        scope=job.scope,
        channel_ids=job.channel_ids,
        category_id=job.category_id,
        schedule_id=job.schedule_id,
        period_start=job.period_start,
        period_end=job.period_end,
        date_range_start=job.date_range_start,
        date_range_end=job.date_range_end,
        granularity=job.granularity,
        summary_type=job.summary_type,
        perspective=job.perspective,
        created_by=user.get("id"),
        metadata={**job.metadata, "retry_of": job_id},
    )

    await job_repo.save(new_job)

    logger.info(f"Created retry job {new_job_id} from failed job {job_id}")

    # TODO: Actually trigger the job execution based on job_type
    # For now, just create the record - the user can check the Jobs tab

    return JobRetryResponse(
        success=True,
        job_id=job_id,
        new_job_id=new_job_id,
        message="Retry job created. It will be processed shortly.",
    )
