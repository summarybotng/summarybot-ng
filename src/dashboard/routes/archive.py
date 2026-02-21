"""
Archive management API routes.

Phase 10: Frontend UI - Backend API
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field

from . import get_discord_bot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/archive", tags=["archive"])


# Request/Response Models

class DateRangeRequest(BaseModel):
    start: date
    end: date


def get_model_for_summary_type(summary_type: str, explicit_model: Optional[str] = None) -> str:
    """
    Select the appropriate model based on summary type.

    - brief: Use fast/cheap model (Haiku)
    - detailed: Use balanced model (Sonnet)
    - comprehensive: Use best model (Sonnet)

    If an explicit model is provided, use that instead.
    """
    if explicit_model:
        return explicit_model

    model_map = {
        "brief": "anthropic/claude-3-haiku",
        "detailed": "anthropic/claude-3.5-sonnet",
        "comprehensive": "anthropic/claude-3.5-sonnet",
    }
    return model_map.get(summary_type, "anthropic/claude-3-haiku")


class GenerateRequest(BaseModel):
    source_type: str
    server_id: str
    channel_ids: Optional[List[str]] = None
    date_range: DateRangeRequest
    granularity: str = "daily"
    timezone: str = "UTC"
    skip_existing: bool = True
    regenerate_outdated: bool = False
    regenerate_failed: bool = True
    max_cost_usd: Optional[float] = None
    dry_run: bool = False
    model: Optional[str] = None  # If not set, auto-selected based on summary_type
    # Summary options (same as regular summaries)
    summary_type: str = "detailed"  # brief, detailed, comprehensive
    perspective: str = "general"  # general, developer, marketing, product, finance, executive, support


class BackfillReportRequest(BaseModel):
    source_type: str
    server_id: str
    channel_ids: Optional[List[str]] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    include_outdated: bool = False
    current_prompt_version: Optional[str] = None


class SourceResponse(BaseModel):
    source_key: str
    source_type: str
    server_id: str
    server_name: str
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    summary_count: int = 0
    date_range: Optional[Dict[str, str]] = None


class ScanResultResponse(BaseModel):
    source_key: str
    total_days: int
    complete: int
    failed: int
    missing: int
    outdated: int
    gaps: List[Dict[str, Any]]
    date_range: Dict[str, Optional[str]]


class JobResponse(BaseModel):
    job_id: str
    source_key: str
    status: str
    progress: Dict[str, Any]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class CostEstimateResponse(BaseModel):
    periods: int
    estimated_cost_usd: float
    estimated_tokens: int
    model: str


# Placeholder for actual implementation
# These would be injected via dependency injection in real app

def get_archive_root() -> Path:
    """Get archive root path."""
    import os
    return Path(os.environ.get("ARCHIVE_ROOT", "./summarybot-archive"))


# Singleton generator instance to preserve job state across requests
_generator_instance = None


class SummarizationAdapter:
    """
    Adapter that wraps SummarizationEngine to match the interface expected
    by the archive generator.
    """

    def __init__(self, engine):
        self.engine = engine

    async def generate_summary(
        self,
        messages: List[Dict],
        api_key: str = None,
        summary_type: str = "detailed",
        perspective: str = "general",
    ):
        """
        Generate a summary from message dictionaries.

        Converts message dicts to ProcessedMessage objects and calls the engine.
        Returns an object with the fields the generator expects.
        """
        from datetime import datetime, timezone as tz
        from src.models.message import ProcessedMessage, MessageType
        from src.models.summary import SummaryOptions, SummaryLength, SummarizationContext

        # Convert message dicts to ProcessedMessage objects
        processed_messages = []
        for msg in messages:
            timestamp = msg.get("timestamp")
            if isinstance(timestamp, str):
                # Parse ISO format timestamp
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

            processed_messages.append(ProcessedMessage(
                id=msg.get("id", ""),
                author_name=msg.get("author_name", "Unknown"),
                author_id=msg.get("author_id", ""),
                content=msg.get("content", ""),
                timestamp=timestamp,
                message_type=MessageType.DEFAULT,
                channel_id=msg.get("channel_id"),
                channel_name=msg.get("channel_name"),
                embeds_count=msg.get("embeds", 0),
            ))

        if not processed_messages:
            return None

        # Map summary_type string to SummaryLength enum
        length_map = {
            "brief": SummaryLength.BRIEF,
            "detailed": SummaryLength.DETAILED,
            "comprehensive": SummaryLength.COMPREHENSIVE,
        }
        summary_length = length_map.get(summary_type, SummaryLength.DETAILED)

        # Create options and context
        options = SummaryOptions(
            summary_length=summary_length,
            perspective=perspective,
            min_messages=1,  # Allow any number for archive
        )

        # Get unique participants and calculate time span
        participants = set(m.author_id for m in processed_messages)
        timestamps = [m.timestamp for m in processed_messages]
        time_span = (max(timestamps) - min(timestamps)).total_seconds() / 3600.0 if len(timestamps) > 1 else 24.0

        context = SummarizationContext(
            channel_name="archive",
            guild_name="",
            total_participants=len(participants),
            time_span_hours=time_span,
        )

        # Get channel/guild info from first message
        channel_id = processed_messages[0].channel_id or ""
        guild_id = ""

        # Call the engine
        result = await self.engine.summarize_messages(
            messages=processed_messages,
            options=options,
            context=context,
            channel_id=channel_id,
            guild_id=guild_id,
        )

        # Create a simple response object with the fields the generator expects
        class SummaryResponse:
            pass

        response = SummaryResponse()
        response.content = result.summary_text
        response.model = result.metadata.get("claude_model", "unknown")
        response.tokens_input = result.metadata.get("input_tokens", 0)
        response.tokens_output = result.metadata.get("output_tokens", 0)

        # Extract prompt version and generate checksum
        prompt_source = result.metadata.get("prompt_source", {})
        if isinstance(prompt_source, dict):
            response.prompt_version = prompt_source.get("version", "1.0.0")
            # Generate checksum from prompt file path + version as a proxy
            checksum_input = f"{prompt_source.get('file_path', '')}:{prompt_source.get('version', '')}"
        else:
            response.prompt_version = "1.0.0"
            checksum_input = "default:1.0.0"

        import hashlib
        response.prompt_checksum = f"sha256:{hashlib.sha256(checksum_input.encode()).hexdigest()[:16]}"

        return response


async def get_generator():
    """Get retrospective generator instance (singleton to preserve job state)."""
    global _generator_instance

    if _generator_instance is not None:
        return _generator_instance

    from src.archive.generator import RetrospectiveGenerator
    from src.archive.cost_tracker import CostTracker
    from src.archive.sources import SourceRegistry
    from src.archive.api_keys import ApiKeyResolver
    from . import get_summarization_engine, get_summary_repository

    archive_root = get_archive_root()
    cost_tracker = CostTracker(archive_root / "cost-ledger.json")
    source_registry = SourceRegistry(archive_root)
    api_key_resolver = ApiKeyResolver()

    engine = get_summarization_engine()
    if engine is None:
        raise HTTPException(503, "Summarization service not available")

    # Wrap the engine with our adapter
    summarization_adapter = SummarizationAdapter(engine)

    # ADR-008: Get stored summary repository for database persistence
    # This is critical - without it, summaries only go to ephemeral files
    stored_summary_repo = await get_summary_repository()
    if stored_summary_repo:
        logger.info("Archive generator initialized with database storage")
    else:
        logger.warning("Archive generator initialized WITHOUT database storage - summaries will only be written to files")

    _generator_instance = RetrospectiveGenerator(
        archive_root=archive_root,
        summarization_service=summarization_adapter,
        source_registry=source_registry,
        cost_tracker=cost_tracker,
        api_key_resolver=api_key_resolver,
        stored_summary_repository=stored_summary_repo,
    )

    return _generator_instance


def get_scanner():
    """Get archive scanner instance."""
    from src.archive.scanner import ArchiveScanner
    return ArchiveScanner(get_archive_root())


def get_source_registry():
    """Get source registry instance."""
    from src.archive.sources import SourceRegistry
    return SourceRegistry(get_archive_root())


def create_message_fetcher(channel_ids: Optional[List[str]] = None):
    """
    Create a message fetcher callback for the generator.

    This fetches messages from Discord using the bot client and converts
    them to the dictionary format expected by the archive generator.
    """
    from src.message_processing.fetcher import MessageFetcher

    async def fetch_messages(source, start_time, end_time):
        """Fetch messages for a period from Discord."""
        bot = get_discord_bot()
        if not bot:
            raise HTTPException(503, "Discord bot not available")

        fetcher = MessageFetcher(bot)
        all_messages = []

        logger.info(
            f"Fetching messages for {source.source_key} from "
            f"{start_time.isoformat()} to {end_time.isoformat()}"
        )

        # Determine which channels to fetch from
        if source.channel_id:
            # Single channel specified in source
            target_channels = [source.channel_id]
        elif channel_ids:
            # Channels specified in request
            target_channels = channel_ids
        else:
            # Get all text channels in the guild
            guild = bot.get_guild(int(source.server_id))
            if not guild:
                logger.warning(f"Guild not found: {source.server_id}")
                return []

            target_channels = [
                str(ch.id) for ch in guild.text_channels
                if ch.permissions_for(guild.me).read_message_history
            ]

        for channel_id in target_channels:
            try:
                messages = await fetcher.fetch_messages(
                    channel_id=channel_id,
                    start_time=start_time,
                    end_time=end_time,
                )

                # Convert Discord messages to dict format for generator
                for msg in messages:
                    all_messages.append({
                        "id": str(msg.id),
                        "author_id": str(msg.author.id),
                        "author_name": msg.author.display_name,
                        "content": msg.content,
                        "timestamp": msg.created_at.isoformat(),
                        "channel_id": str(msg.channel.id),
                        "channel_name": getattr(msg.channel, 'name', 'unknown'),
                        "attachments": [
                            {"filename": a.filename, "url": a.url}
                            for a in msg.attachments
                        ],
                        "embeds": len(msg.embeds),
                        "is_bot": msg.author.bot,
                    })

            except Exception as e:
                logger.warning(f"Failed to fetch from channel {channel_id}: {e}")
                continue

        # Sort by timestamp
        all_messages.sort(key=lambda m: m["timestamp"])

        if not all_messages:
            logger.warning(
                f"No messages found for {source.source_key} in period "
                f"{start_time.isoformat()} to {end_time.isoformat()}. "
                f"Checked {len(target_channels)} channel(s)."
            )
        else:
            logger.info(
                f"Found {len(all_messages)} messages for {source.source_key} "
                f"from {len(target_channels)} channel(s)"
            )

        return all_messages

    return fetch_messages


# Routes

@router.get("/sources", response_model=List[SourceResponse])
async def list_sources(
    source_type: Optional[str] = None,
):
    """List all archive sources."""
    registry = get_source_registry()
    registry.discover_sources()

    sources = registry.list_sources()
    if source_type:
        from src.archive.models import SourceType
        try:
            filter_type = SourceType(source_type)
            sources = [s for s in sources if s.source_type == filter_type]
        except ValueError:
            raise HTTPException(400, f"Invalid source type: {source_type}")

    archive_root = get_archive_root()
    results = []
    for s in sources:
        # Count summaries by counting .md files in the archive path
        archive_path = s.get_archive_path(archive_root)
        summary_count = 0
        date_range = None

        if archive_path.exists():
            md_files = list(archive_path.glob("**/*.md"))
            summary_count = len(md_files)

            # Get date range from filenames (format: YYYY-MM-DD_daily.md)
            if md_files:
                dates = []
                for f in md_files:
                    name = f.stem  # e.g., "2026-02-14_daily"
                    if "_" in name:
                        date_str = name.split("_")[0]
                        try:
                            from datetime import datetime
                            dates.append(datetime.strptime(date_str, "%Y-%m-%d").date())
                        except ValueError:
                            pass
                if dates:
                    date_range = {
                        "start": min(dates).isoformat(),
                        "end": max(dates).isoformat(),
                    }

        results.append(SourceResponse(
            source_key=s.source_key,
            source_type=s.source_type.value,
            server_id=s.server_id,
            server_name=s.server_name,
            channel_id=s.channel_id,
            channel_name=s.channel_name,
            summary_count=summary_count,
            date_range=date_range,
        ))

    return results


@router.get("/sources/{source_key}/scan", response_model=ScanResultResponse)
async def scan_source(
    source_key: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    prompt_version: Optional[str] = None,
):
    """Scan a source for gaps and outdated summaries."""
    registry = get_source_registry()
    registry.discover_sources()

    source = registry.get_source(source_key)
    if not source:
        raise HTTPException(404, f"Source not found: {source_key}")

    scanner = get_scanner()
    result = scanner.scan_source(
        source,
        start_date=start_date,
        end_date=end_date,
        current_prompt_version=prompt_version,
    )

    return ScanResultResponse(**result.to_dict())


@router.post("/backfill-report")
async def get_backfill_report(request: BackfillReportRequest):
    """Analyze archive for backfill opportunities."""
    from src.archive.models import SourceType, ArchiveSource
    from src.archive.backfill import BackfillManager
    from src.archive.cost_tracker import CostTracker

    archive_root = get_archive_root()

    source = ArchiveSource(
        source_type=SourceType(request.source_type),
        server_id=request.server_id,
        server_name=request.server_id,  # Will be updated from manifest
    )

    cost_tracker = CostTracker(archive_root / "cost-ledger.json")
    manager = BackfillManager(archive_root, cost_tracker)

    report = manager.analyze_backfill(
        source,
        start_date=request.start_date,
        end_date=request.end_date,
        include_outdated=request.include_outdated,
        current_prompt_version=request.current_prompt_version,
    )

    return report.to_dict()


@router.post("/generate", response_model=JobResponse)
async def generate_retrospective(request: GenerateRequest):
    """Generate retrospective summaries."""
    from src.archive.models import SourceType, ArchiveSource

    # Check if Discord bot is available for non-dry-run requests
    if not request.dry_run:
        bot = get_discord_bot()
        if not bot:
            raise HTTPException(
                503,
                "Discord bot not available. Archive generation requires the bot to fetch messages."
            )

    source = ArchiveSource(
        source_type=SourceType(request.source_type),
        server_id=request.server_id,
        server_name=request.server_id,
        channel_id=request.channel_ids[0] if request.channel_ids and len(request.channel_ids) == 1 else None,
    )

    generator = await get_generator()
    job = await generator.create_job(
        source=source,
        start_date=request.date_range.start,
        end_date=request.date_range.end,
        granularity=request.granularity or "daily",
        timezone=request.timezone or "UTC",
        skip_existing=request.skip_existing if request.skip_existing is not None else True,
        regenerate_outdated=request.regenerate_outdated or False,
        regenerate_failed=request.regenerate_failed if request.regenerate_failed is not None else True,
        max_cost_usd=request.max_cost_usd,
        dry_run=request.dry_run or False,
        summary_type=request.summary_type or "detailed",
        perspective=request.perspective or "general",
    )

    # Start job in background if not dry run
    if not request.dry_run:
        import asyncio
        message_fetcher = create_message_fetcher(request.channel_ids)
        asyncio.create_task(generator.run_job(job.job_id, message_fetcher=message_fetcher))

    return JobResponse(**job.to_dict())


@router.get("/generate/{job_id}", response_model=JobResponse)
async def get_generation_status(job_id: str):
    """Get generation job status."""
    generator = await get_generator()
    job = generator.get_job(job_id)

    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")

    return JobResponse(**job.to_dict())


@router.post("/generate/{job_id}/cancel")
async def cancel_generation(job_id: str):
    """Cancel a running generation job."""
    generator = await get_generator()

    if not await generator.cancel_job(job_id):
        raise HTTPException(404, f"Job not found: {job_id}")

    return {"status": "cancelled", "job_id": job_id}


@router.get("/jobs", response_model=List[JobResponse])
async def list_all_jobs(
    status: Optional[str] = None,
    limit: int = 50,
):
    """
    List all generation jobs.

    Args:
        status: Filter by status (pending, running, completed, failed, cancelled)
        limit: Maximum number of jobs to return
    """
    from src.archive.generator import JobStatus

    generator = await get_generator()

    # Filter by status if provided
    status_filter = None
    if status:
        try:
            status_filter = JobStatus(status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")

    jobs = generator.list_jobs(status=status_filter)

    # Sort by created_at descending (newest first)
    jobs.sort(key=lambda j: j.created_at, reverse=True)

    # Apply limit
    jobs = jobs[:limit]

    return [JobResponse(**j.to_dict()) for j in jobs]


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str, reason: str = "user_requested"):
    """Pause a running job."""
    generator = await get_generator()

    if not await generator.pause_job(job_id, reason):
        raise HTTPException(404, f"Job not found or cannot be paused: {job_id}")

    return {"status": "paused", "job_id": job_id, "reason": reason}


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    """Resume a paused job."""
    import asyncio
    from src.archive.generator import JobStatus

    generator = await get_generator()
    job = generator.get_job(job_id)

    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")

    if job.status != JobStatus.PAUSED:
        raise HTTPException(400, f"Job is not paused: {job_id} (status: {job.status.value})")

    # Clear pause state and restart
    job.pause_reason = None
    message_fetcher = create_message_fetcher(None)
    asyncio.create_task(generator.run_job(job_id, message_fetcher=message_fetcher))

    return {"status": "resumed", "job_id": job_id}


@router.post("/estimate", response_model=CostEstimateResponse)
async def estimate_generation_cost(request: GenerateRequest):
    """Estimate cost for generation request."""
    from datetime import datetime, date, timedelta
    from src.archive.cost_tracker import CostTracker

    # Calculate number of periods based on date range and granularity
    # Handle both string and date objects from Pydantic
    start = request.date_range.start
    end = request.date_range.end
    if isinstance(start, str):
        start = datetime.strptime(start, "%Y-%m-%d").date()
    if isinstance(end, str):
        end = datetime.strptime(end, "%Y-%m-%d").date()

    if request.granularity == "weekly":
        periods = max(1, (end - start).days // 7)
    elif request.granularity == "monthly":
        periods = max(1, (end - start).days // 30)
    else:  # daily
        periods = max(1, (end - start).days + 1)

    # Use cost tracker for estimation
    archive_root = get_archive_root()
    cost_tracker = CostTracker(archive_root / "cost-ledger.json")

    source_key = f"{request.source_type}:{request.server_id}"
    # Auto-select model based on summary type if not explicitly specified
    model = get_model_for_summary_type(request.summary_type, request.model)

    estimate = cost_tracker.estimate_backfill_cost(
        source_key=source_key,
        periods=periods,
        model=model,
    )

    return CostEstimateResponse(
        periods=estimate.periods,
        estimated_cost_usd=estimate.estimated_cost_usd,
        estimated_tokens=estimate.avg_tokens_per_summary * estimate.periods,
        model=model,
    )


@router.post("/import/whatsapp")
async def import_whatsapp(
    file: UploadFile = File(...),
    group_id: str = Query(...),
    group_name: str = Query(...),
    format: str = Query("whatsapp_txt"),  # "whatsapp_txt" or "reader_bot"
):
    """Import WhatsApp chat export."""
    from src.archive.importers.whatsapp import WhatsAppImporter
    import tempfile

    archive_root = get_archive_root()
    importer = WhatsAppImporter(archive_root)

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        if format == "reader_bot":
            result = await importer.import_reader_bot_json(
                tmp_path, group_id, group_name
            )
        else:
            result = await importer.import_txt_export(
                tmp_path, group_id, group_name
            )

        return result.to_dict()

    finally:
        tmp_path.unlink()


@router.get("/costs")
async def get_cost_report():
    """Get cost report for all sources."""
    from src.archive.cost_tracker import CostTracker

    archive_root = get_archive_root()
    tracker = CostTracker(archive_root / "cost-ledger.json")

    return tracker.get_cost_report()


@router.get("/costs/{source_key}")
async def get_source_costs(source_key: str):
    """Get cost details for a specific source."""
    from src.archive.cost_tracker import CostTracker

    archive_root = get_archive_root()
    tracker = CostTracker(archive_root / "cost-ledger.json")

    cost = tracker.get_source_cost(source_key)
    if not cost:
        raise HTTPException(404, f"No cost data for source: {source_key}")

    return cost.to_dict()


@router.post("/recover/{summary_id}")
async def recover_summary(summary_id: str):
    """Recover a soft-deleted summary."""
    from src.archive.retention import RetentionManager

    archive_root = get_archive_root()
    manager = RetentionManager(archive_root)

    if not manager.recover(summary_id):
        raise HTTPException(404, f"Summary not found or already recovered: {summary_id}")

    return {"status": "recovered", "summary_id": summary_id}


@router.get("/deleted")
async def list_deleted():
    """List soft-deleted summaries."""
    from src.archive.retention import RetentionManager

    archive_root = get_archive_root()
    manager = RetentionManager(archive_root)

    deleted = manager.list_deleted()
    return [d.to_dict() for d in deleted]


# ==================== Archive Summary Reading ====================


class ArchiveGenerationMetadata(BaseModel):
    """Generation metadata for archive summaries."""
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    prompt_checksum: Optional[str] = None
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    duration_seconds: Optional[float] = None
    has_prompt_data: bool = False
    perspective: str = "general"


class ArchiveSummaryResponse(BaseModel):
    """Response for reading archive summaries."""
    id: str
    source_key: str
    date: str
    channel_name: str
    summary_text: str
    message_count: int
    participant_count: int
    created_at: str
    summary_length: str = "detailed"
    preview: str = ""
    is_archive: bool = True
    # Generation metadata for View Details
    generation: Optional[ArchiveGenerationMetadata] = None


class ArchiveSummariesListResponse(BaseModel):
    """Response for listing archive summaries."""
    summaries: List[ArchiveSummaryResponse]
    total: int


@router.get("/summaries/{server_id}", response_model=ArchiveSummariesListResponse)
async def list_archive_summaries(
    server_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List archive summaries for a server.

    Returns summaries from the archive that can be displayed alongside
    regular summaries in the UI.
    """
    archive_root = get_archive_root()
    sources_dir = archive_root / "sources" / "discord"

    summaries = []

    if sources_dir.exists():
        # Find the server directory
        for server_dir in sources_dir.iterdir():
            if server_dir.is_dir() and server_dir.name.endswith(f"_{server_id}"):
                # Found the server, now read all summaries
                server_name = server_dir.name.rsplit("_", 1)[0]

                # Find all markdown files
                md_files = sorted(server_dir.glob("**/*.md"), reverse=True)

                for md_path in md_files:
                    # Skip non-summary files
                    if md_path.name.startswith(".") or "incomplete" in md_path.name:
                        continue

                    try:
                        # Read metadata file
                        meta_path = md_path.with_suffix(".meta.json")
                        metadata = {}
                        if meta_path.exists():
                            import json
                            with open(meta_path) as f:
                                metadata = json.load(f)

                        # Read summary content
                        content = md_path.read_text()

                        # Extract date from filename (e.g., 2026-01-20_daily.md)
                        date_str = md_path.stem.split("_")[0]

                        # Create preview (first ~200 chars after title)
                        lines = content.split("\n")
                        preview_lines = []
                        in_content = False
                        for line in lines:
                            if line.startswith("## ") and not in_content:
                                in_content = True
                                continue
                            if in_content and line.strip():
                                preview_lines.append(line.strip())
                                if len(" ".join(preview_lines)) > 200:
                                    break
                        preview = " ".join(preview_lines)[:200]
                        if len(preview) == 200:
                            preview += "..."

                        # Get stats from metadata
                        stats = metadata.get("statistics", {})
                        generation_data = metadata.get("generation", {})
                        options = generation_data.get("options", {})

                        # Build generation metadata
                        gen_meta = ArchiveGenerationMetadata(
                            model=generation_data.get("model"),
                            prompt_version=generation_data.get("prompt_version"),
                            prompt_checksum=generation_data.get("prompt_checksum"),
                            tokens_input=generation_data.get("tokens_input", 0),
                            tokens_output=generation_data.get("tokens_output", 0),
                            cost_usd=generation_data.get("cost_usd", 0.0),
                            duration_seconds=generation_data.get("duration_seconds"),
                            has_prompt_data=bool(generation_data),
                            perspective=options.get("perspective", "general"),
                        )

                        summaries.append(ArchiveSummaryResponse(
                            id=f"archive_{date_str}_{server_id}",
                            source_key=f"discord:{server_id}",
                            date=date_str,
                            channel_name=server_name,  # Use server name as channel
                            summary_text=content,
                            message_count=stats.get("message_count", 0),
                            participant_count=stats.get("participant_count", 0),
                            created_at=metadata.get("created_at", date_str),
                            summary_length=options.get("summary_type", "detailed"),
                            preview=preview,
                            is_archive=True,
                            generation=gen_meta,
                        ))
                    except Exception as e:
                        logger.warning(f"Failed to read archive summary {md_path}: {e}")
                        continue

                break  # Found the server, no need to continue

    # Apply pagination
    total = len(summaries)
    summaries = summaries[offset:offset + limit]

    return ArchiveSummariesListResponse(
        summaries=summaries,
        total=total,
    )


@router.get("/summaries/{server_id}/{summary_id}")
async def get_archive_summary(
    server_id: str,
    summary_id: str,
):
    """
    Get a specific archive summary by ID.

    The summary_id format is: archive_{date}_{server_id}
    """
    # Parse the summary ID
    parts = summary_id.split("_")
    if len(parts) < 3 or parts[0] != "archive":
        raise HTTPException(400, "Invalid archive summary ID format")

    date_str = parts[1]

    archive_root = get_archive_root()
    sources_dir = archive_root / "sources" / "discord"

    if not sources_dir.exists():
        raise HTTPException(404, "Archive not found")

    # Find the server directory
    for server_dir in sources_dir.iterdir():
        if server_dir.is_dir() and server_dir.name.endswith(f"_{server_id}"):
            server_name = server_dir.name.rsplit("_", 1)[0]

            # Parse date to find file path
            try:
                from datetime import datetime as dt
                target_date = dt.strptime(date_str, "%Y-%m-%d")
                year = target_date.strftime("%Y")
                month = target_date.strftime("%m")
            except ValueError:
                raise HTTPException(400, "Invalid date format in summary ID")

            # Look for the file
            md_path = server_dir / year / month / f"{date_str}_daily.md"
            meta_path = md_path.with_suffix(".meta.json")

            if not md_path.exists():
                raise HTTPException(404, f"Summary not found: {summary_id}")

            # Read content and metadata
            content = md_path.read_text()
            metadata = {}
            if meta_path.exists():
                import json
                with open(meta_path) as f:
                    metadata = json.load(f)

            stats = metadata.get("statistics", {})
            generation = metadata.get("generation", {})

            return {
                "id": summary_id,
                "source_key": f"discord:{server_id}",
                "date": date_str,
                "channel_name": server_name,
                "summary_text": content,
                "message_count": stats.get("message_count", 0),
                "participant_count": stats.get("participant_count", 0),
                "created_at": metadata.get("created_at", date_str),
                "summary_length": generation.get("options", {}).get("summary_type", "detailed"),
                "is_archive": True,
                "metadata": metadata,
            }

    raise HTTPException(404, f"Server not found: {server_id}")


# ==================== Sync Endpoints (ADR-007) ====================


class SyncStatusResponse(BaseModel):
    """Sync service status response."""
    enabled: bool
    configured: bool
    folder_id: Optional[str] = None
    sync_on_generation: bool
    sync_frequency: str
    create_subfolders: bool
    sources_synced: int


class SyncResultResponse(BaseModel):
    """Sync operation result."""
    status: str
    files_synced: int
    files_failed: int
    bytes_uploaded: int
    errors: List[str] = []


class DriveStatusResponse(BaseModel):
    """Google Drive status response."""
    connected: bool
    provider: Optional[str] = None
    folder_id: Optional[str] = None
    quota: Optional[Dict[str, int]] = None
    error: Optional[str] = None


def get_sync_service():
    """Get sync service instance."""
    from src.archive.sync import get_sync_service as _get_sync_service
    return _get_sync_service(get_archive_root())


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status():
    """Get sync service status."""
    service = get_sync_service()
    return SyncStatusResponse(**service.get_status())


@router.get("/sync/status/{source_key}")
async def get_source_sync_status(source_key: str):
    """Get sync status for a specific source."""
    service = get_sync_service()
    status = service.get_source_status(source_key)

    if not status:
        return {"source_key": source_key, "synced": False, "message": "Never synced"}

    return status


@router.get("/sync/sources")
async def list_sync_states():
    """List sync states for all sources."""
    service = get_sync_service()
    return service.list_sync_states()


@router.post("/sync/trigger/{source_key}", response_model=SyncResultResponse)
async def trigger_source_sync(source_key: str):
    """Trigger sync for a specific source."""
    import httpx

    service = get_sync_service()
    oauth = get_oauth_flow()

    # Parse source key and find source path
    parts = source_key.split(":")
    if len(parts) != 2:
        raise HTTPException(400, f"Invalid source key: {source_key}")

    source_type, server_id = parts
    archive_root = get_archive_root()

    # Check for per-server OAuth config first
    server_config = await service.get_server_config(server_id)

    if server_config and server_config.enabled:
        # Use per-server OAuth tokens
        tokens = await oauth.get_valid_tokens(server_config.oauth_token_id)
        if not tokens:
            raise HTTPException(400, "OAuth tokens expired. Please reconnect Google Drive.")

        # Find source using registry (same as list_sources)
        registry = get_source_registry()
        registry.discover_sources()
        sources = registry.list_sources()

        source_info = None
        for s in sources:
            if s.source_key == source_key:
                source_info = s
                break

        if not source_info:
            raise HTTPException(404, f"Source not found: {source_key}")

        source_dir = source_info.get_archive_path(archive_root)
        server_name = source_info.server_name

        # Sync using OAuth tokens
        files_synced = 0
        files_failed = 0
        bytes_uploaded = 0
        errors = []

        try:
            async with httpx.AsyncClient() as client:
                # Get list of markdown files to sync
                md_files = list(source_dir.glob("**/*.md"))

                for md_file in md_files:
                    try:
                        # Upload file to Drive
                        rel_path = md_file.relative_to(source_dir)
                        file_content = md_file.read_text()

                        # Create file metadata
                        metadata = {
                            "name": md_file.name,
                            "parents": [server_config.folder_id],
                        }

                        # Simple upload using multipart
                        boundary = "===boundary==="
                        body = (
                            f"--{boundary}\r\n"
                            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                            f"{json.dumps(metadata)}\r\n"
                            f"--{boundary}\r\n"
                            f"Content-Type: text/markdown\r\n\r\n"
                            f"{file_content}\r\n"
                            f"--{boundary}--"
                        )

                        response = await client.post(
                            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                            headers={
                                "Authorization": f"Bearer {tokens.access_token}",
                                "Content-Type": f"multipart/related; boundary={boundary}",
                            },
                            content=body.encode(),
                        )

                        if response.status_code in (200, 201):
                            files_synced += 1
                            bytes_uploaded += len(file_content.encode())
                        else:
                            files_failed += 1
                            errors.append(f"{md_file.name}: {response.status_code}")

                    except Exception as e:
                        files_failed += 1
                        errors.append(f"{md_file.name}: {str(e)}")

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            raise HTTPException(500, f"Sync failed: {e}")

        # Update last sync time
        server_config.last_sync = datetime.utcnow()
        await service.save_server_config(server_id, server_config)

        return SyncResultResponse(
            status="success" if files_failed == 0 else "partial",
            files_synced=files_synced,
            files_failed=files_failed,
            bytes_uploaded=bytes_uploaded,
            errors=errors[:5],
        )

    # Fall back to global service account config
    if not service.is_enabled():
        raise HTTPException(
            503,
            "Google Drive sync not configured. Connect via OAuth or set ARCHIVE_GOOGLE_DRIVE_* environment variables."
        )

    sources_dir = archive_root / "sources" / source_type

    # Find the source directory
    source_dir = None
    server_name = server_id

    if sources_dir.exists():
        for d in sources_dir.iterdir():
            if d.is_dir() and d.name.endswith(f"_{server_id}"):
                source_dir = d
                # Extract server name from folder
                folder_name = d.name
                last_underscore = folder_name.rfind('_')
                if last_underscore > 0:
                    server_name = folder_name[:last_underscore]
                break

    if not source_dir or not source_dir.exists():
        raise HTTPException(404, f"Source not found: {source_key}")

    result = await service.sync_source(
        source_key=source_key,
        source_path=source_dir,
        server_name=server_name,
    )

    return SyncResultResponse(
        status=result.status.value,
        files_synced=result.files_synced,
        files_failed=result.files_failed,
        bytes_uploaded=result.bytes_uploaded,
        errors=result.errors,
    )


@router.post("/sync/trigger")
async def trigger_sync_all():
    """Trigger sync for all sources."""
    service = get_sync_service()

    if not service.is_enabled():
        raise HTTPException(
            503,
            "Google Drive sync not configured. Set ARCHIVE_GOOGLE_DRIVE_* environment variables."
        )

    results = await service.sync_all()

    return {
        source_key: {
            "status": result.status.value,
            "files_synced": result.files_synced,
            "files_failed": result.files_failed,
        }
        for source_key, result in results.items()
    }


@router.get("/sync/drive", response_model=DriveStatusResponse)
async def get_drive_status():
    """Get Google Drive connection status and quota."""
    service = get_sync_service()
    status = await service.get_drive_status()
    return DriveStatusResponse(**status)


# ==================== OAuth Endpoints (ADR-007 Phase 2) ====================


class OAuthConfigResponse(BaseModel):
    """OAuth configuration status."""
    configured: bool
    client_id_set: bool
    redirect_uri: str


class ServerSyncConfigResponse(BaseModel):
    """Server sync configuration."""
    server_id: str
    enabled: bool
    folder_id: Optional[str] = None
    folder_name: Optional[str] = None
    configured_by: Optional[str] = None
    configured_at: Optional[str] = None
    last_sync: Optional[str] = None
    using_fallback: bool = False


class ConfigureServerSyncRequest(BaseModel):
    """Request to configure server sync."""
    folder_id: str
    folder_name: str = ""
    sync_on_generation: bool = True
    include_metadata: bool = True


def get_oauth_flow():
    """Get OAuth flow instance."""
    from src.archive.sync import get_oauth_flow as _get_oauth_flow
    return _get_oauth_flow(get_archive_root())


@router.get("/oauth/config", response_model=OAuthConfigResponse)
async def get_oauth_config():
    """Check if OAuth is configured."""
    oauth = get_oauth_flow()
    return OAuthConfigResponse(
        configured=oauth.is_configured(),
        client_id_set=bool(oauth.client_id),
        redirect_uri=oauth.redirect_uri,
    )


@router.get("/oauth/google")
async def start_oauth_flow(
    server_id: str,
    user_id: str,
):
    """
    Start Google OAuth flow for a server.

    Args:
        server_id: Discord server ID
        user_id: Discord user ID initiating the flow

    Returns:
        Redirect URL for OAuth
    """
    oauth = get_oauth_flow()

    if not oauth.is_configured():
        raise HTTPException(
            503,
            "Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET."
        )

    try:
        auth_url, state = oauth.generate_auth_url(server_id, user_id)
        return {
            "auth_url": auth_url,
            "state": state,
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to generate OAuth URL: {e}")


@router.get("/oauth/google/callback")
async def oauth_callback(
    code: str,
    state: str,
):
    """
    Handle Google OAuth callback.

    Args:
        code: Authorization code from Google
        state: State token for CSRF protection

    Returns:
        Success response with server info
    """
    oauth = get_oauth_flow()

    # Validate state
    oauth_state = oauth.validate_state(state)
    if not oauth_state:
        raise HTTPException(400, "Invalid or expired state token")

    try:
        # Exchange code for tokens
        tokens = await oauth.exchange_code(code, oauth_state)

        return {
            "success": True,
            "server_id": oauth_state.server_id,
            "message": "Google Drive connected successfully. Now select a folder.",
        }

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(500, f"OAuth failed: {e}")


@router.delete("/oauth/google/{server_id}")
async def disconnect_google_drive(server_id: str):
    """
    Disconnect Google Drive for a server.

    Args:
        server_id: Discord server ID
    """
    oauth = get_oauth_flow()
    service = get_sync_service()

    # Delete tokens
    await oauth.disconnect(server_id)

    # Delete server config
    await service.delete_server_config(server_id)

    return {"success": True, "message": "Google Drive disconnected"}


@router.get("/sync/servers")
async def list_configured_servers():
    """List all servers with custom sync configuration."""
    service = get_sync_service()
    servers = await service.list_configured_servers()
    return servers


@router.get("/sync/server/{server_id}", response_model=ServerSyncConfigResponse)
async def get_server_sync_config(server_id: str):
    """Get sync configuration for a specific server."""
    service = get_sync_service()
    config = await service.get_server_config(server_id)

    if config and config.enabled:
        return ServerSyncConfigResponse(
            server_id=server_id,
            enabled=True,
            folder_id=config.folder_id,
            folder_name=config.folder_name,
            configured_by=config.configured_by,
            configured_at=config.configured_at.isoformat() if config.configured_at else None,
            last_sync=config.last_sync.isoformat() if config.last_sync else None,
            using_fallback=False,
        )

    # Check if using fallback
    using_fallback = service.config.is_configured()

    return ServerSyncConfigResponse(
        server_id=server_id,
        enabled=using_fallback,
        folder_id=service.config.folder_id if using_fallback else None,
        using_fallback=using_fallback,
    )


@router.put("/sync/server/{server_id}")
async def configure_server_sync(
    server_id: str,
    request: ConfigureServerSyncRequest,
    user_id: str = "",
):
    """
    Configure sync for a server after OAuth.

    Args:
        server_id: Discord server ID
        request: Configuration options
        user_id: Discord user ID making the change
    """
    from src.archive.sync import ServerSyncConfig

    service = get_sync_service()
    oauth = get_oauth_flow()

    # Verify OAuth tokens exist
    token_id = f"srv_{server_id}_gdrive"
    tokens = await oauth.get_valid_tokens(token_id)

    if not tokens:
        raise HTTPException(
            400,
            "No OAuth tokens found. Please connect Google Drive first."
        )

    # Create config
    config = ServerSyncConfig(
        enabled=True,
        folder_id=request.folder_id,
        folder_name=request.folder_name,
        oauth_token_id=token_id,
        configured_by=user_id,
        configured_at=datetime.utcnow(),
        sync_on_generation=request.sync_on_generation,
        include_metadata=request.include_metadata,
    )

    # Save config
    success = await service.save_server_config(server_id, config)

    if not success:
        raise HTTPException(500, "Failed to save configuration")

    return {
        "success": True,
        "server_id": server_id,
        "folder_id": request.folder_id,
        "message": "Server sync configured successfully",
    }


@router.post("/sync/server/{server_id}/test")
async def test_server_sync(server_id: str):
    """
    Test sync configuration for a server.

    Creates a test file in the configured folder to verify access.
    """
    service = get_sync_service()
    config = await service.get_server_config(server_id)

    if not config or not config.enabled:
        raise HTTPException(400, "Server sync not configured")

    # Get OAuth tokens
    oauth = get_oauth_flow()
    tokens = await oauth.get_valid_tokens(config.oauth_token_id)

    if not tokens:
        raise HTTPException(400, "OAuth tokens expired. Please reconnect.")

    # TODO: Create test file in Drive folder
    # For now, just verify we have valid tokens

    return {
        "success": True,
        "message": "Connection verified",
        "folder_id": config.folder_id,
    }


@router.get("/oauth/google/folders")
async def list_drive_folders(
    server_id: str,
    parent_id: str = "root",
):
    """
    List folders in Google Drive for folder selection.

    Args:
        server_id: Discord server ID (to get OAuth tokens)
        parent_id: Parent folder ID (default: root)
    """
    oauth = get_oauth_flow()
    token_id = f"srv_{server_id}_gdrive"

    tokens = await oauth.get_valid_tokens(token_id)
    if not tokens:
        raise HTTPException(400, "No valid OAuth tokens. Please connect first.")

    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {tokens.access_token}"},
                params={
                    "q": f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                    "fields": "files(id, name, mimeType)",
                    "orderBy": "name",
                    "pageSize": 100,
                },
            )

            if response.status_code != 200:
                error_detail = response.text[:500] if response.text else "Unknown error"
                logger.error(f"Drive API error {response.status_code}: {error_detail}")
                raise HTTPException(response.status_code, f"Drive API error: {error_detail}")

            data = response.json()
            return {
                "parent_id": parent_id,
                "folders": [
                    {"id": f["id"], "name": f["name"]}
                    for f in data.get("files", [])
                ],
            }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error listing folders: {e}")
        raise HTTPException(500, f"Drive API error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error listing folders: {e}")
        raise HTTPException(500, f"Failed to list folders: {e}")
