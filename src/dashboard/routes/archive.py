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
from ..models import SummaryScope
from src.utils.time import utc_now_naive

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
    # ADR-011: Unified scope selection
    scope: SummaryScope = SummaryScope.GUILD  # Default to guild for retrospective
    channel_ids: Optional[List[str]] = None  # For CHANNEL scope
    category_id: Optional[str] = None  # For CATEGORY scope
    date_range: DateRangeRequest
    granularity: str = "daily"
    timezone: str = "UTC"
    skip_existing: bool = True
    regenerate_outdated: bool = False
    regenerate_failed: bool = True
    # ADR-019: Force regeneration (delete existing and regenerate)
    force_regenerate: bool = False
    max_cost_usd: Optional[float] = None
    dry_run: bool = False
    model: Optional[str] = None  # If not set, auto-selected based on summary_type
    # Summary options (same as regular summaries)
    summary_type: str = "detailed"  # brief, detailed, comprehensive
    perspective: str = "general"  # general, developer, marketing, product, finance, executive, support


class BackfillReportRequest(BaseModel):
    source_type: str
    server_id: str
    # ADR-011: Unified scope selection
    scope: SummaryScope = SummaryScope.GUILD
    channel_ids: Optional[List[str]] = None  # For CHANNEL scope
    category_id: Optional[str] = None  # For CATEGORY scope
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
    cost: Optional[Dict[str, Any]] = None
    date_range: Optional[Dict[str, str]] = None
    granularity: Optional[str] = None
    summary_type: Optional[str] = None
    perspective: Optional[str] = None
    server_name: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    pause_reason: Optional[str] = None
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
        guild_id: str = "",
    ):
        """
        Generate a summary from message dictionaries.

        Converts message dicts to ProcessedMessage objects and calls the engine.
        Returns an object with the fields the generator expects.

        Args:
            messages: List of message dictionaries
            api_key: Optional API key (unused, engine has its own)
            summary_type: Type of summary (brief, detailed, comprehensive)
            perspective: Summary perspective (general, developer, etc.)
            guild_id: Discord guild ID for jump link generation (ADR-014)
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
        # ADR-014: Use passed guild_id for jump link generation

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

        # ADR-004: Copy structured summary data for grounded citations
        response.key_points = result.key_points
        response.action_items = result.action_items
        response.participants = result.participants
        response.technical_terms = result.technical_terms
        response.reference_index = result.reference_index

        # ADR-016: Copy source_content for regeneration fallback
        response.source_content = result.source_content
        response.prompt_system = result.prompt_system
        response.prompt_user = result.prompt_user

        # ADR-024: Pass through full metadata including generation_attempts
        response.metadata = result.metadata

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

    # Check if existing instance needs its repository reinitialized
    if _generator_instance is not None:
        if _generator_instance.stored_summary_repository is None:
            # Repository wasn't available when generator was created, try again
            from . import get_stored_summary_repository
            stored_summary_repo = await get_stored_summary_repository()
            if stored_summary_repo:
                _generator_instance.stored_summary_repository = stored_summary_repo
                logger.info("Archive generator: reattached database storage")
        return _generator_instance

    from src.archive.generator import RetrospectiveGenerator
    from src.archive.cost_tracker import CostTracker
    from src.archive.sources import SourceRegistry
    from src.archive.api_keys import ApiKeyResolver
    from . import get_summarization_engine, get_stored_summary_repository
    from ...data.repositories import get_summary_job_repository

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
    stored_summary_repo = await get_stored_summary_repository()
    if stored_summary_repo:
        logger.info("Archive generator initialized with database storage")
    else:
        logger.warning("Archive generator initialized WITHOUT database storage - summaries will only be written to files")

    # ADR-013: Get job repository for persistent job tracking
    try:
        job_repo = await get_summary_job_repository()
        logger.info("Archive generator initialized with job tracking")
    except Exception as e:
        logger.warning(f"Job tracking not available: {e}")
        job_repo = None

    _generator_instance = RetrospectiveGenerator(
        archive_root=archive_root,
        summarization_service=summarization_adapter,
        source_registry=source_registry,
        cost_tracker=cost_tracker,
        api_key_resolver=api_key_resolver,
        stored_summary_repository=stored_summary_repo,
        summary_job_repository=job_repo,
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


def create_whatsapp_message_fetcher(archive_root: Path, group_id: str):
    """
    Create a message fetcher callback for WhatsApp sources.

    This fetches messages from imported WhatsApp chat files.
    """
    from src.archive.importers.whatsapp import WhatsAppImporter

    importer = WhatsAppImporter(archive_root)

    async def fetch_messages(source, start_time, end_time):
        """Fetch messages for a period from imported WhatsApp data."""
        messages = await importer.get_messages_for_period(
            group_id=group_id,
            start=start_time,
            end=end_time,
        )

        logger.info(
            f"Fetched {len(messages)} WhatsApp messages for {group_id} "
            f"from {start_time.isoformat()} to {end_time.isoformat()}"
        )

        return messages

    return fetch_messages


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


def create_slack_message_fetcher(workspace_id: str, channel_ids: Optional[List[str]] = None):
    """
    Create a message fetcher callback for Slack workspaces.

    This fetches messages from Slack using the Slack API and converts
    them to the dictionary format expected by the archive generator.
    """
    from src.slack.client import SlackClient
    from src.data.repositories import get_slack_repository

    async def fetch_messages(source, start_time, end_time):
        """Fetch messages for a period from Slack."""
        # Get the Slack workspace from database
        slack_repo = await get_slack_repository()
        workspace = await slack_repo.get_workspace(workspace_id)

        if not workspace:
            logger.error(f"Slack workspace not found: {workspace_id}")
            return []

        if not workspace.enabled:
            logger.warning(f"Slack workspace is disabled: {workspace_id}")
            return []

        client = SlackClient(workspace)
        all_messages = []

        logger.info(
            f"Fetching Slack messages for {source.source_key} from "
            f"{start_time.isoformat()} to {end_time.isoformat()}"
        )

        try:
            # Determine which channels to fetch from
            if channel_ids:
                # Specific channels requested
                target_channels = channel_ids
            else:
                # Get all public channels
                channels = await client.get_all_channels(include_private=False)
                target_channels = [ch.channel_id for ch in channels if not ch.is_archived]

            # Convert datetime to Slack timestamp format (Unix seconds)
            oldest = str(start_time.timestamp())
            latest = str(end_time.timestamp())

            # Build a user cache for name resolution
            users = await client.get_all_users()
            users_by_id = {u.user_id: u for u in users}

            for channel_id in target_channels:
                try:
                    # Fetch all messages with pagination
                    cursor = None
                    channel_name = channel_id  # Default to ID

                    while True:
                        data = await client.get_channel_history(
                            channel_id=channel_id,
                            oldest=oldest,
                            latest=latest,
                            limit=200,
                            cursor=cursor,
                        )

                        for msg in data.get("messages", []):
                            # Skip system messages
                            subtype = msg.get("subtype")
                            if subtype in ("channel_join", "channel_leave", "channel_topic",
                                           "channel_purpose", "channel_name", "channel_archive"):
                                continue

                            # Get user info
                            user_id = msg.get("user", msg.get("bot_id", ""))
                            user = users_by_id.get(user_id)
                            author_name = user.display_name if user else user_id

                            # Convert Slack timestamp to ISO format
                            ts = float(msg["ts"])
                            timestamp = datetime.fromtimestamp(ts).isoformat()

                            all_messages.append({
                                "id": msg["ts"],
                                "author_id": user_id,
                                "author_name": author_name,
                                "content": msg.get("text", ""),
                                "timestamp": timestamp,
                                "channel_id": channel_id,
                                "channel_name": channel_name,
                                "attachments": [
                                    {"filename": f.get("name", ""), "url": f.get("url_private", "")}
                                    for f in msg.get("files", [])
                                ],
                                "embeds": len(msg.get("attachments", [])),
                                "is_bot": user.is_bot if user else msg.get("bot_id") is not None,
                                "thread_ts": msg.get("thread_ts"),
                                "reactions": msg.get("reactions", []),
                            })

                        # Handle pagination
                        cursor = data.get("response_metadata", {}).get("next_cursor")
                        if not cursor:
                            break

                except Exception as e:
                    logger.warning(f"Failed to fetch from Slack channel {channel_id}: {e}")
                    continue

            # Sort by timestamp
            all_messages.sort(key=lambda m: m["timestamp"])

            if not all_messages:
                logger.warning(
                    f"No Slack messages found for {source.source_key} in period "
                    f"{start_time.isoformat()} to {end_time.isoformat()}. "
                    f"Checked {len(target_channels)} channel(s)."
                )
            else:
                logger.info(
                    f"Found {len(all_messages)} Slack messages for {source.source_key} "
                    f"from {len(target_channels)} channel(s)"
                )

        finally:
            await client.close()

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
    from src.archive.models import SourceType, ArchiveSource, ArchiveScopeType
    from ..utils.scope_resolver import resolve_channels_for_scope

    logger.info(
        f"Generate request: date_range.start={request.date_range.start} "
        f"(type={type(request.date_range.start).__name__}), "
        f"date_range.end={request.date_range.end} "
        f"(type={type(request.date_range.end).__name__}), "
        f"scope={request.scope}"
    )

    # Check source types
    bot = get_discord_bot()
    is_whatsapp = request.source_type == "whatsapp"
    is_slack = request.source_type == "slack"
    is_discord = request.source_type == "discord"

    # Check if Discord bot is available for Discord sources
    if not request.dry_run and is_discord:
        if not bot:
            raise HTTPException(
                503,
                "Discord bot not available. Archive generation requires the bot to fetch messages."
            )

    # ADR-011: Resolve channels based on scope
    resolved_channel_ids = request.channel_ids or []
    slack_channel_ids = []  # Slack-specific channel IDs
    slack_workspace_id = None  # For Slack message fetcher
    category_id = request.category_id
    category_name = None
    server_name = request.server_id

    if is_whatsapp:
        # For WhatsApp, get server name from source registry
        registry = get_source_registry()
        registry.discover_sources()
        source_key = f"whatsapp:{request.server_id}"
        existing_source = registry.get_source(source_key)
        if existing_source:
            server_name = existing_source.server_name

    elif is_slack:
        # For Slack, get workspace info from database
        from src.data.repositories import get_slack_repository

        slack_repo = await get_slack_repository()

        # server_id for Slack is the linked_guild_id (Discord guild ID)
        workspace = await slack_repo.get_workspace_by_guild(request.server_id)
        if not workspace:
            raise HTTPException(404, f"No Slack workspace linked to guild {request.server_id}")

        if not workspace.enabled:
            raise HTTPException(400, f"Slack workspace {workspace.workspace_name} is disabled")

        slack_workspace_id = workspace.workspace_id
        server_name = workspace.workspace_name

        # Get Slack channels from database or API
        slack_channels = await slack_repo.list_channels(
            workspace_id=workspace.workspace_id,
            include_archived=False,
            limit=1000,
        )
        if slack_channels:
            # Use channels from database
            slack_channel_ids = [ch.channel_id for ch in slack_channels]
        else:
            # Fall back to fetching from API
            from src.slack.client import SlackClient
            client = SlackClient(workspace)
            try:
                channels = await client.get_all_channels(include_private=False)
                slack_channel_ids = [ch.channel_id for ch in channels if not ch.is_archived]
                # Save channels to database for future use
                await slack_repo.save_channels_batch(channels)
            finally:
                await client.close()

        logger.info(f"Slack archive job: workspace={workspace.workspace_name}, channels={len(slack_channel_ids)}")

    elif is_discord and bot and bot.client:
        guild = bot.client.get_guild(int(request.server_id))
        if guild:
            server_name = guild.name

            # Resolve channels based on scope
            resolved = await resolve_channels_for_scope(
                guild=guild,
                scope=request.scope,
                channel_ids=request.channel_ids,
                category_id=request.category_id,
            )
            resolved_channel_ids = [str(ch.id) for ch in resolved.channels]

            if resolved.category_info:
                category_id = str(resolved.category_info.id)
                category_name = resolved.category_info.name

    # Convert scope to archive scope type
    try:
        archive_scope = ArchiveScopeType(request.scope.value)
    except (ValueError, AttributeError):
        archive_scope = ArchiveScopeType.GUILD

    # Create source with scope info (ADR-011)
    source = ArchiveSource(
        source_type=SourceType(request.source_type),
        server_id=request.server_id,
        server_name=server_name,
        scope=archive_scope,
        channel_id=resolved_channel_ids[0] if len(resolved_channel_ids) == 1 else None,
        channel_ids=resolved_channel_ids if len(resolved_channel_ids) > 1 else None,
        category_id=category_id,
        category_name=category_name,
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
        force_regenerate=request.force_regenerate or False,
        max_cost_usd=request.max_cost_usd,
        dry_run=request.dry_run or False,
        summary_type=request.summary_type or "detailed",
        perspective=request.perspective or "general",
    )

    # Start job in background if not dry run
    if not request.dry_run:
        import asyncio

        # Use appropriate message fetcher based on source type
        if is_whatsapp:
            message_fetcher = create_whatsapp_message_fetcher(
                archive_root=get_archive_root(),
                group_id=request.server_id,
            )
        elif is_slack:
            message_fetcher = create_slack_message_fetcher(
                workspace_id=slack_workspace_id,
                channel_ids=slack_channel_ids if slack_channel_ids else None,
            )
        else:
            message_fetcher = create_message_fetcher(resolved_channel_ids)

        asyncio.create_task(generator.run_job(job.job_id, message_fetcher=message_fetcher))

    return JobResponse(**job.to_dict())


@router.get("/generate/{job_id}", response_model=JobResponse)
async def get_generation_status(job_id: str):
    """Get generation job status."""
    generator = await get_generator()
    job = generator.get_job(job_id)

    if job:
        return JobResponse(**job.to_dict())

    # ADR-013: Check database for jobs from previous sessions
    db_job = await generator.get_job_from_db(job_id)
    if db_job:
        return JobResponse(**db_job)

    raise HTTPException(404, f"Job not found: {job_id}")


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
    List all generation jobs (ADR-013: from memory and database).

    Args:
        status: Filter by status (pending, running, completed, failed, cancelled)
        limit: Maximum number of jobs to return
    """
    from src.archive.generator import JobStatus
    from ...data.repositories import get_summary_job_repository

    generator = await get_generator()

    # Filter by status if provided
    status_filter = None
    if status:
        try:
            status_filter = JobStatus(status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")

    # Get in-memory jobs
    jobs = generator.list_jobs(status=status_filter)
    job_dicts = [j.to_dict() for j in jobs]
    seen_ids = {j.job_id for j in jobs}

    # ADR-013: Also get jobs from database
    try:
        job_repo = await get_summary_job_repository()
        db_jobs = await job_repo.find_by_guild(
            guild_id="",  # Empty to get all
            status=status if status else None,
            job_type="retrospective",
            limit=limit,
        )
        # Add DB jobs that aren't in memory
        for db_job in db_jobs:
            if db_job.id not in seen_ids:
                job_dicts.append(db_job.to_dict())
    except Exception as e:
        logger.warning(f"Failed to fetch jobs from database: {e}")

    # Sort by created_at descending (newest first)
    job_dicts.sort(key=lambda j: j.get("created_at", ""), reverse=True)

    # Apply limit
    job_dicts = job_dicts[:limit]

    return [JobResponse(**j) for j in job_dicts]


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
    """
    Import WhatsApp chat export.

    ADR-006: Supports both .txt and .zip file formats.
    When a .zip file is uploaded, the archive is extracted and the
    contained .txt file is processed.
    """
    from src.archive.importers.whatsapp import WhatsAppImporter
    import tempfile
    import zipfile

    archive_root = get_archive_root()
    importer = WhatsAppImporter(archive_root)

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    extracted_path = None  # Track extracted file for cleanup

    try:
        # ADR-006: Handle .zip files by extracting the .txt file inside
        file_to_process = tmp_path
        original_filename = file.filename or "upload"

        if original_filename.lower().endswith('.zip') or tmp_path.suffix.lower() == '.zip':
            logger.info(f"Processing WhatsApp .zip upload: {original_filename}")

            # Extract the zip file
            try:
                with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                    # Find .txt file(s) in the archive
                    txt_files = [f for f in zip_ref.namelist()
                                 if f.lower().endswith('.txt') and not f.startswith('__MACOSX')]

                    if not txt_files:
                        raise HTTPException(
                            400,
                            "No .txt file found in the ZIP archive. "
                            "WhatsApp exports contain a _chat.txt file."
                        )

                    # Use the first .txt file (WhatsApp typically exports as "WhatsApp Chat with X.txt")
                    txt_filename = txt_files[0]
                    logger.info(f"Found chat file in ZIP: {txt_filename}")

                    # Extract to temp directory
                    extract_dir = Path(tempfile.mkdtemp())
                    zip_ref.extract(txt_filename, extract_dir)
                    extracted_path = extract_dir / txt_filename
                    file_to_process = extracted_path

                    # Update original filename for result metadata
                    original_filename = txt_filename

            except zipfile.BadZipFile:
                raise HTTPException(
                    400,
                    "Invalid ZIP file. Please upload a valid WhatsApp export ZIP or .txt file."
                )

        # Process the file
        if format == "reader_bot":
            result = await importer.import_reader_bot_json(
                file_to_process, group_id, group_name
            )
        else:
            result = await importer.import_txt_export(
                file_to_process, group_id, group_name
            )

        return result.to_dict()

    finally:
        # Clean up temp files
        tmp_path.unlink(missing_ok=True)
        if extracted_path and extracted_path.exists():
            # Clean up extracted file and its parent temp directory
            extracted_path.unlink(missing_ok=True)
            try:
                extracted_path.parent.rmdir()
            except OSError:
                pass  # Directory not empty or already removed


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
    sort_by: str = Query("archive_period", description="Sort field (archive_period, message_count, created_at)"),
    sort_order: str = Query("desc", description="Sort direction (asc, desc)"),
):
    """
    List archive summaries for a server.

    Returns summaries from the archive that can be displayed alongside
    regular summaries in the UI.

    ADR-019: Now queries database instead of disk files.
    ADR-017: Supports sorting by message_count and other fields.
    """
    from . import get_stored_summary_repository

    repo = await get_stored_summary_repository()
    if not repo:
        logger.warning(f"Stored summary repository not available for server {server_id}")
        return ArchiveSummariesListResponse(summaries=[], total=0)

    # ADR-017: Dynamic sorting support
    valid_sort_fields = {"archive_period", "message_count", "created_at"}
    if sort_by not in valid_sort_fields:
        sort_by = "archive_period"

    # Query database for archive summaries (source="archive")
    db_summaries = await repo.find_by_guild(
        guild_id=server_id,
        source="archive",
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    # Get total count
    all_archive = await repo.find_by_guild(
        guild_id=server_id,
        source="archive",
        limit=10000,  # Get all for count
    )
    total = len(all_archive)

    summaries = []
    for summary in db_summaries:
        # Extract archive period as date
        date_str = summary.archive_period or ""

        # Build preview
        summary_text = summary.summary_result.summary_text if summary.summary_result else ""
        preview = summary_text[:200] + "..." if len(summary_text) > 200 else summary_text

        # Get channel name from context (context is inside summary_result)
        channel_name = "Unknown"
        if summary.summary_result and summary.summary_result.context:
            channel_name = summary.summary_result.context.channel_name or "Unknown"

        # Get message count
        message_count = summary.summary_result.message_count if summary.summary_result else 0
        participant_count = 0
        if summary.summary_result and summary.summary_result.participants:
            participant_count = len(summary.summary_result.participants)

        # Get summary length from metadata (metadata is inside summary_result)
        summary_length = "detailed"
        metadata = summary.summary_result.metadata if summary.summary_result else None
        if metadata:
            summary_length = metadata.get("summary_length", "detailed")

        # Build generation metadata from summary metadata
        gen_meta = None
        if metadata:
            gen_meta = ArchiveGenerationMetadata(
                model=metadata.get("model"),
                prompt_version=metadata.get("prompt_version"),
                prompt_checksum=metadata.get("prompt_checksum"),
                tokens_input=metadata.get("tokens_input", 0),
                tokens_output=metadata.get("tokens_output", 0),
                cost_usd=metadata.get("cost_usd", 0.0),
                duration_seconds=metadata.get("duration_seconds"),
                has_prompt_data=bool(metadata.get("model")),
                perspective=metadata.get("perspective", "general"),
            )

        summaries.append(ArchiveSummaryResponse(
            id=summary.id,
            # Use stored archive_source_key if available, fallback for legacy data
            source_key=summary.archive_source_key or f"discord:{server_id}",
            date=date_str,
            channel_name=channel_name,
            summary_text=summary_text,
            message_count=message_count,
            participant_count=participant_count,
            created_at=summary.created_at.isoformat() if summary.created_at else date_str,
            summary_length=summary_length,
            preview=preview,
            is_archive=True,
            generation=gen_meta,
        ))

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

    ADR-019: Now queries database instead of disk files.
    Supports both UUID format (new) and archive_{date}_{server_id} format (legacy).
    """
    from . import get_stored_summary_repository

    repo = await get_stored_summary_repository()
    if not repo:
        raise HTTPException(500, "Repository not available")

    summary = None
    date_str = None

    # Try to get by UUID first (new format)
    summary = await repo.get(summary_id)

    # If not found, try legacy format: archive_{date}_{server_id}
    if not summary and summary_id.startswith("archive_"):
        parts = summary_id.split("_")
        if len(parts) >= 3:
            date_str = parts[1]
            # Look up by archive_period
            results = await repo.find_by_guild(
                guild_id=server_id,
                source="archive",
                archive_period=date_str,
                limit=1,
            )
            if results:
                summary = results[0]

    if not summary:
        raise HTTPException(404, f"Summary not found: {summary_id}")

    # Verify it belongs to the requested server
    if summary.guild_id != server_id:
        raise HTTPException(404, f"Summary not found for server: {server_id}")

    # Extract data
    date_str = summary.archive_period or ""
    summary_text = summary.summary_result.summary_text if summary.summary_result else ""

    # Get channel name (context is inside summary_result)
    channel_name = "Unknown"
    if summary.summary_result and summary.summary_result.context:
        channel_name = summary.summary_result.context.channel_name or "Unknown"

    # Get counts
    message_count = summary.summary_result.message_count if summary.summary_result else 0
    participant_count = 0
    if summary.summary_result and summary.summary_result.participants:
        participant_count = len(summary.summary_result.participants)

    # Get summary length (metadata is inside summary_result)
    summary_length = "detailed"
    metadata = summary.summary_result.metadata if summary.summary_result else None
    if metadata:
        summary_length = metadata.get("summary_length", "detailed")

    # ADR-020: Get navigation
    navigation = None
    try:
        navigation = await repo.get_navigation(
            summary_id=summary.id,
            guild_id=server_id,
            source="archive",
        )
    except Exception as e:
        logger.warning(f"Failed to get navigation for {summary_id}: {e}")

    return {
        "id": summary.id,
        # Use stored archive_source_key if available, fallback for legacy data
        "source_key": summary.archive_source_key or f"discord:{server_id}",
        "date": date_str,
        "channel_name": channel_name,
        "summary_text": summary_text,
        "message_count": message_count,
        "participant_count": participant_count,
        "created_at": summary.created_at.isoformat() if summary.created_at else date_str,
        "summary_length": summary_length,
        "is_archive": True,
        "metadata": metadata or {},
        "navigation": navigation,
    }


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
        server_config.last_sync = utc_now_naive()
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
        configured_at=utc_now_naive(),
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


# ==================== Archive Sync ====================

class SyncResponse(BaseModel):
    """Response for archive sync operation."""
    synced: int = 0
    skipped: int = 0
    failed: int = 0
    errors: List[str] = []


@router.post("/sync-to-database/{server_id}", response_model=SyncResponse)
async def sync_archive_to_database(
    server_id: str,
    force: bool = Query(False, description="Force re-sync by deleting existing archive summaries first"),
):
    """
    Sync archive summaries from disk to database.

    Scans the archive directory for summaries and ensures they exist
    in the stored_summaries database table for calendar view and navigation.
    """
    from . import get_stored_summary_repository
    from ...models.stored_summary import StoredSummary, SummarySource
    from ...models.summary import SummaryResult

    archive_root = get_archive_root()
    stored_repo = await get_stored_summary_repository()

    if not stored_repo:
        raise HTTPException(503, "Database not available")

    synced = 0
    skipped = 0
    failed = 0
    deleted = 0
    errors = []

    # If force=True, delete existing archive summaries for this server first
    if force:
        existing = await stored_repo.find_by_guild(server_id, source="archive", limit=10000)
        for summary in existing:
            await stored_repo.delete(summary.id)
            deleted += 1
        logger.info(f"Force sync: deleted {deleted} existing archive summaries for {server_id}")

    # Scan archive directory directly for this server_id
    # Archive structure: sources/discord/{name}_{server_id}/summaries/YYYY/MM/*.meta.json
    sources_dir = archive_root / "sources" / "discord"
    if not sources_dir.exists():
        return SyncResponse(synced=0, skipped=0, failed=0, errors=["No archive sources directory"])

    # Find all source directories for this server
    for source_dir in sources_dir.iterdir():
        if not source_dir.is_dir():
            continue
        # Extract server_id from directory name (format: name_serverid)
        dir_name = source_dir.name
        if not dir_name.endswith(f"_{server_id}"):
            continue

        source_name = dir_name.rsplit("_", 1)[0] if "_" in dir_name else dir_name
        summaries_dir = source_dir / "summaries"
        if not summaries_dir.exists():
            continue

        # Scan for meta.json files
        for meta_path in summaries_dir.glob("**/*.meta.json"):
            try:
                with open(meta_path, "r") as f:
                    metadata = json.load(f)

                # Skip incomplete markers - these are placeholders for days with no messages
                # and should not be synced to the database (they would block regeneration)
                if metadata.get("status") == "incomplete":
                    skipped += 1
                    logger.debug(f"Skipping incomplete marker: {meta_path.name}")
                    continue

                summary_id = metadata.get("summary_id")
                if not summary_id:
                    # Generate from path if not in metadata
                    summary_id = f"sum_{meta_path.stem.replace('.meta', '')}"

                # Check if already in database
                existing = await stored_repo.get(summary_id)
                if existing:
                    skipped += 1
                    continue

                # Read the markdown content
                md_path = meta_path.with_suffix("").with_suffix(".md")
                content = ""
                if md_path.exists():
                    with open(md_path, "r") as f:
                        content = f.read()

                # Skip if no actual content (another way to detect incomplete summaries)
                if not content.strip():
                    skipped += 1
                    logger.debug(f"Skipping empty summary: {meta_path.name}")
                    continue

                # Parse metadata
                stats = metadata.get("statistics", {})
                generation = metadata.get("generation", {})
                period = metadata.get("period", {})

                # Parse dates
                start_time = None
                end_time = None
                archive_period = None
                if period.get("start"):
                    start_time = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
                    archive_period = start_time.strftime("%Y-%m-%d")
                if period.get("end"):
                    end_time = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))

                # Extract source info from metadata
                source_info = metadata.get("source", {})
                channel_id = source_info.get("channel_id", "")
                channel_name = source_info.get("channel_name", source_name)
                channel_ids = source_info.get("channel_ids", [])
                if not channel_ids and channel_id:
                    channel_ids = [channel_id]
                source_key = f"discord:{server_id}"

                # Create SummaryResult
                summary_result = SummaryResult(
                    id=summary_id,
                    guild_id=server_id,
                    channel_id=channel_id,
                    start_time=start_time or datetime.now(),
                    end_time=end_time or datetime.now(),
                    message_count=stats.get("message_count", 0),
                    summary_text=content,
                    key_points=[],
                    action_items=[],
                    participants=[],
                    technical_terms=[],
                    metadata={
                        "summary_type": generation.get("options", {}).get("summary_type", "detailed"),
                        "perspective": generation.get("options", {}).get("perspective", "general"),
                        "model": generation.get("model"),
                        "tokens_input": generation.get("tokens_input", 0),
                        "tokens_output": generation.get("tokens_output", 0),
                        "cost_usd": generation.get("cost_usd", 0),
                    },
                )

                # Create StoredSummary with created_at set to the archive period
                # so it appears on the correct date in the calendar
                stored = StoredSummary(
                    id=summary_id,
                    guild_id=server_id,
                    source_channel_ids=channel_ids,
                    summary_result=summary_result,
                    title=f"{channel_name} - {archive_period or 'Unknown'}",
                    source=SummarySource.ARCHIVE,
                    archive_period=archive_period,
                    archive_granularity=period.get("granularity", "daily"),
                    archive_source_key=source_key,
                    created_at=start_time or datetime.now(),  # Use archive date for calendar
                )

                await stored_repo.save(stored)
                synced += 1
                logger.info(f"Synced archive summary to database: {summary_id}")

            except Exception as e:
                failed += 1
                errors.append(f"{meta_path.name}: {str(e)}")
                logger.warning(f"Failed to sync {meta_path}: {e}")

    return SyncResponse(
        synced=synced,
        skipped=skipped,
        failed=failed,
        errors=errors[:10],  # Limit error messages
    )


# ==================== ADR-026: Source Migration ====================


class MigrateSourceRequest(BaseModel):
    """Request to migrate a source to a different guild."""
    source_key: str  # e.g., "whatsapp:ai-code"
    target_guild_id: str  # Discord guild ID to migrate to


class MigrateSourceResponse(BaseModel):
    """Response from source migration."""
    migrated: int
    source_key: str
    old_guild_id: str
    new_guild_id: str


@router.post("/migrate-source", response_model=MigrateSourceResponse)
async def migrate_source_to_guild(request: MigrateSourceRequest):
    """
    ADR-026: Migrate all summaries from a source to a different guild.

    This is used to link WhatsApp/Slack sources to a Discord guild so
    their summaries appear alongside Discord summaries in the UI.

    Example:
        POST /archive/migrate-source
        {"source_key": "whatsapp:ai-code", "target_guild_id": "1283874310720716890"}
    """
    from . import get_stored_summary_repository

    repo = await get_stored_summary_repository()
    if not repo:
        raise HTTPException(503, "Database not available")

    # Parse source key to get the old guild_id
    parts = request.source_key.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(400, f"Invalid source_key format: {request.source_key}")

    source_type, old_guild_id = parts

    # Find all summaries with this source_key
    # We search by the old guild_id (which equals the source's server_id for non-Discord)
    summaries = await repo.find_by_guild(
        guild_id=old_guild_id,
        source="archive",
        limit=10000,
    )

    # Filter to only those matching this specific source_key
    matching = [s for s in summaries if s.archive_source_key == request.source_key]

    if not matching:
        raise HTTPException(404, f"No summaries found for source: {request.source_key}")

    migrated = 0
    for summary in matching:
        # Update guild_id to the target
        summary.guild_id = request.target_guild_id
        if summary.summary_result:
            summary.summary_result.guild_id = request.target_guild_id
        await repo.save(summary)
        migrated += 1
        logger.info(f"Migrated {summary.id} from {old_guild_id} to {request.target_guild_id}")

    return MigrateSourceResponse(
        migrated=migrated,
        source_key=request.source_key,
        old_guild_id=old_guild_id,
        new_guild_id=request.target_guild_id,
    )
