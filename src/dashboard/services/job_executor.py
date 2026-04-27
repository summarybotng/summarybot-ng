"""
Job execution service for running summary jobs from database records.

ADR-042: Intelligent Job Retry Strategy
ADR-044: Deferred Technical Debt Tracker

This module enables:
1. Retry functionality (retry_job endpoint)
2. Future auto-retry worker (ADR-042)
3. Scheduled job recovery after server restart
"""

import asyncio
import logging
from typing import Optional

from ...models.summary_job import SummaryJob, JobType, JobStatus
from ...models.summary import SummaryOptions, SummaryLength, SummarizationContext
from ...models.stored_summary import StoredSummary, SummarySource
from ...utils.time import utc_now_naive
from ...data.repositories import get_summary_job_repository, get_stored_summary_repository

logger = logging.getLogger(__name__)


async def execute_job(job: SummaryJob) -> bool:
    """
    Execute a summary job based on its stored parameters.

    Returns True if execution started successfully, False otherwise.

    This is the central job execution entry point that routes to the
    appropriate executor based on job type.
    """
    if job.status not in (JobStatus.PENDING, JobStatus.PAUSED):
        logger.warning(f"[{job.id}] Cannot execute job with status {job.status.value}")
        return False

    if job.job_type == JobType.MANUAL:
        asyncio.create_task(_execute_manual_job(job))
        return True
    elif job.job_type == JobType.SCHEDULED:
        # Scheduled jobs should go through the scheduler
        # For retry, we treat them like manual jobs
        asyncio.create_task(_execute_manual_job(job))
        return True
    elif job.job_type == JobType.REGENERATE:
        asyncio.create_task(_execute_regenerate_job(job))
        return True
    elif job.job_type == JobType.RETROSPECTIVE:
        # Retrospective jobs have their own execution path in archive/generator.py
        # For now, we don't support retry of retrospective jobs
        logger.warning(f"[{job.id}] Retrospective job retry not yet implemented")
        return False
    else:
        logger.error(f"[{job.id}] Unknown job type: {job.job_type}")
        return False


async def _execute_manual_job(job: SummaryJob) -> None:
    """
    Execute a manual or scheduled summary job.

    This is extracted from the inline run_generation() in generate_summary endpoint.
    """
    job_id = job.id
    job_repo = await get_summary_job_repository()

    logger.info(f"[{job_id}] Starting job execution for guild {job.guild_id}")
    logger.info(f"[{job_id}] Scope: {job.scope}, Time range: {job.period_start} to {job.period_end}")
    logger.info(f"[{job_id}] Channels ({len(job.channel_ids)}): {job.channel_ids}")

    # Get required services (lazy import to avoid circular dependency)
    from ..routes import get_discord_bot, get_summarization_engine
    bot = get_discord_bot()
    engine = get_summarization_engine()

    if not bot or not engine:
        error_msg = "Required services not available"
        logger.error(f"[{job_id}] {error_msg}")
        job.fail(error_msg)
        if job_repo:
            await job_repo.update(job)
        return

    guild = bot.client.get_guild(int(job.guild_id))
    if not guild:
        error_msg = f"Guild {job.guild_id} not found"
        logger.error(f"[{job_id}] {error_msg}")
        job.fail(error_msg)
        if job_repo:
            await job_repo.update(job)
        return

    # Mark job as running
    job.start()
    job.update_progress(0, len(job.channel_ids) + 2, "Fetching messages")
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

        for idx, channel_id in enumerate(job.channel_ids):
            channel = guild.get_channel(int(channel_id))
            logger.info(f"[{job_id}] Fetching from channel {channel_id}: {channel.name if channel else 'NOT FOUND'}")

            if channel:
                try:
                    msg_count = 0
                    async for message in channel.history(
                        after=job.period_start,
                        before=job.period_end,
                        limit=1000,
                    ):
                        all_messages.append(message)
                        msg_count += 1
                    logger.info(f"[{job_id}] Fetched {msg_count} messages from {channel.name}")

                    job.update_progress(idx + 1, None, f"Fetched {channel.name}")
                    if job_repo:
                        try:
                            await job_repo.update(job)
                        except Exception:
                            pass
                except Exception as channel_error:
                    logger.error(f"[{job_id}] Error fetching from {channel.name}: {channel_error}")
                    channel_errors.append((channel_id, channel.name, channel_error))

        # Track channel-level errors
        if channel_errors:
            try:
                from ...logging.error_tracker import initialize_error_tracker
                from ...models.error_log import ErrorType

                tracker = await initialize_error_tracker()
                for ch_id, ch_name, ch_error in channel_errors:
                    error_type = ErrorType.DISCORD_PERMISSION if (
                        hasattr(ch_error, 'status') and ch_error.status == 403
                    ) else ErrorType.DISCORD_CONNECTION
                    await tracker.capture_error(
                        error=ch_error,
                        error_type=error_type,
                        guild_id=job.guild_id,
                        channel_id=ch_id,
                        operation=f"fetch_messages ({ch_name})",
                        details={"job_id": job_id, "channel_name": ch_name},
                    )
            except Exception as track_err:
                logger.warning(f"[{job_id}] Failed to track channel errors: {track_err}")

        logger.info(f"[{job_id}] Total messages collected: {len(all_messages)}")

        if not all_messages:
            error_msg = "No messages found in time range"
            logger.warning(f"[{job_id}] {error_msg}")
            job.fail(error_msg)
            if job_repo:
                await job_repo.update(job)
            return

        # Process messages
        job.update_progress(len(job.channel_ids), None, "Processing messages")
        if job_repo:
            try:
                await job_repo.update(job)
            except Exception:
                pass

        # Get options from job metadata
        requested_length = job.metadata.get("summary_length", job.summary_type or "detailed")
        logger.info(f"[{job_id}] Requested summary_length: {requested_length}")

        options = SummaryOptions(
            summary_length=SummaryLength(requested_length),
            extract_action_items=job.metadata.get("include_action_items", True),
            extract_technical_terms=job.metadata.get("include_technical_terms", True),
            min_messages=1,
        )

        processor = MessageProcessor(bot.client)
        processed = await processor.process_messages(all_messages, options)
        logger.info(f"[{job_id}] Processed {len(processed)} messages")

        # Build context
        primary_channel = guild.get_channel(int(job.channel_ids[0]))
        channel_name = primary_channel.name if primary_channel else "multiple channels"

        time_span_hours = (job.period_end - job.period_start).total_seconds() / 3600
        unique_authors = {msg.author_id for msg in processed}

        context = SummarizationContext(
            channel_name=channel_name if len(job.channel_ids) == 1 else f"{len(job.channel_ids)} channels",
            guild_name=guild.name,
            total_participants=len(unique_authors),
            time_span_hours=time_span_hours,
        )

        # Check for custom template in metadata
        custom_system_prompt = None
        template_name = None
        template_id = job.metadata.get("prompt_template_id")

        if template_id:
            try:
                from ...data.repositories import get_prompt_template_repository
                template_repo = await get_prompt_template_repository()
                template = await template_repo.get_template(template_id)
                if template:
                    custom_system_prompt = template.content
                    template_name = template.name
                    logger.info(f"[{job_id}] Using custom template '{template.name}'")
            except Exception as e:
                logger.warning(f"[{job_id}] Failed to fetch template: {e}")

        # Generate summary
        job.update_progress(len(job.channel_ids) + 1, None, "Generating summary")
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
            guild_id=job.guild_id,
            channel_id=job.channel_ids[0],
            custom_system_prompt=custom_system_prompt,
        )
        logger.info(f"[{job_id}] Summarization complete, result id: {result.id}")

        # Store template info in metadata
        if template_name:
            result.metadata["perspective"] = template_name
            result.metadata["prompt_template_id"] = template_id
            result.metadata["prompt_template_name"] = template_name

        # Mark as retry in metadata if applicable
        if job.metadata.get("retry_of"):
            result.metadata["retry_of"] = job.metadata["retry_of"]

        # Save to StoredSummaryRepository
        stored_repo = await get_stored_summary_repository()
        if stored_repo:
            channel_names = []
            for cid in job.channel_ids[:3]:
                ch = guild.get_channel(int(cid))
                if ch:
                    channel_names.append(f"#{ch.name}")
            if len(job.channel_ids) > 3:
                channel_names.append(f"+{len(job.channel_ids) - 3} more")
            title = f"{', '.join(channel_names) or 'Summary'} — {utc_now_naive().strftime('%b %d, %H:%M')}"

            # Determine source type based on job type
            source = SummarySource.MANUAL
            if job.job_type == JobType.SCHEDULED:
                source = SummarySource.SCHEDULED

            stored_summary = StoredSummary(
                id=result.id,
                guild_id=job.guild_id,
                source_channel_ids=job.channel_ids,
                summary_result=result,
                title=title,
                source=source,
                created_at=utc_now_naive(),
            )

            await stored_repo.save(stored_summary)
            logger.info(f"[{job_id}] Saved summary {result.id} to stored_summaries")

        # Mark job as completed
        job.complete(result.id)
        job.update_progress(len(job.channel_ids) + 2, len(job.channel_ids) + 2, "Complete")
        if job_repo:
            try:
                await job_repo.update(job)
                logger.info(f"[{job_id}] Job record updated to COMPLETED")
            except Exception as e:
                logger.warning(f"[{job_id}] Failed to update job completion: {e}")

        logger.info(f"[{job_id}] Job execution completed successfully")

    except Exception as e:
        logger.error(f"[{job_id}] Job execution failed: {e}", exc_info=True)
        job.fail(str(e))
        if job_repo:
            try:
                await job_repo.update(job)
                logger.info(f"[{job_id}] Job record updated to FAILED")
            except Exception as update_err:
                logger.warning(f"[{job_id}] Failed to update job failure: {update_err}")

        # Track error
        try:
            from ...logging.error_tracker import initialize_error_tracker
            from ...models.error_log import ErrorType, ErrorSeverity

            tracker = await initialize_error_tracker()
            await tracker.capture_error(
                error=e,
                error_type=ErrorType.SUMMARY_GENERATION,
                guild_id=job.guild_id,
                operation="job_execution",
                severity=ErrorSeverity.HIGH,
                details={"job_id": job_id, "job_type": job.job_type.value},
            )
        except Exception:
            pass


async def _execute_regenerate_job(job: SummaryJob) -> None:
    """
    Execute a regeneration job.

    Regeneration jobs recreate an existing summary with potentially different parameters.
    """
    job_id = job.id
    job_repo = await get_summary_job_repository()

    original_summary_id = job.metadata.get("original_summary_id")
    if not original_summary_id:
        error_msg = "No original_summary_id in job metadata"
        logger.error(f"[{job_id}] {error_msg}")
        job.fail(error_msg)
        if job_repo:
            await job_repo.update(job)
        return

    logger.info(f"[{job_id}] Regenerating summary {original_summary_id}")

    # Get the original summary
    stored_repo = await get_stored_summary_repository()
    if not stored_repo:
        job.fail("Stored summary repository not available")
        if job_repo:
            await job_repo.update(job)
        return

    original = await stored_repo.get(original_summary_id)
    if not original:
        job.fail(f"Original summary {original_summary_id} not found")
        if job_repo:
            await job_repo.update(job)
        return

    # Update job with channel info from original
    job.channel_ids = original.source_channel_ids
    job.period_start = original.summary_result.metadata.get("period_start")
    job.period_end = original.summary_result.metadata.get("period_end")

    # Execute as a manual job with the original's parameters
    await _execute_manual_job(job)
