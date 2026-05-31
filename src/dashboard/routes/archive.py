"""
Archive management API routes.

Phase 10: Frontend UI - Backend API
"""

import json
import logging
import os
from datetime import date, datetime, timedelta
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
        "detailed": "anthropic/claude-sonnet-4.5",  # Updated 2026-05: use current model name
        "comprehensive": "anthropic/claude-sonnet-4.5",
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
    # For weekly granularity: which days to generate (0=Sun, 6=Sat)
    schedule_days: Optional[List[int]] = None
    # Lookback hours for each summary (default 24h for daily, 168h for weekly)
    lookback_hours: Optional[int] = None
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
    # ADR-096: Per-channel mode - generate one summary per channel
    per_channel: bool = False
    min_channel_messages: int = 5  # Skip channels with fewer messages
    # ADR-111: Auto-publish to Confluence
    auto_publish_confluence: bool = False
    # ADR-116: Track job creation source
    creation_source: str = "unknown"  # wizard, archive_dialog, api


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


class SourceChannelInfo(BaseModel):
    """Channel information within a source (for Slack)."""
    channel_id: str
    channel_name: str
    summary_count: int = 0


class SourceResponse(BaseModel):
    source_key: str
    source_type: str
    server_id: str
    server_name: str
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    summary_count: int = 0
    date_range: Optional[Dict[str, str]] = None
    guild_id: Optional[str] = None  # For WhatsApp imports - the Discord guild they belong to
    linked_guilds: Optional[List[str]] = None  # For Slack - list of guild IDs with access
    channels: Optional[List[SourceChannelInfo]] = None  # For Slack - channel breakdown


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
    # ADR-111: Confluence auto-publish tracking
    confluence_published: int = 0
    confluence_errors: Dict[str, str] = {}


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


def create_whatsapp_message_fetcher(archive_root: Path, group_id: str, chat_ids: Optional[List[str]] = None):
    """
    Create a message fetcher callback for WhatsApp sources.

    This fetches messages from:
    1. File-based archive (legacy WhatsApp imports)
    2. Database imports (ADR-081 ingest_messages table)

    Args:
        archive_root: Root path for file-based archives
        group_id: Discord guild ID that owns the WhatsApp imports
        chat_ids: Optional list of specific chat IDs to filter by
    """
    from src.archive.importers.whatsapp import WhatsAppImporter

    importer = WhatsAppImporter(archive_root)

    async def fetch_messages(source, start_time, end_time):
        """Fetch messages for a period from imported WhatsApp data."""
        # Determine which chat_ids to filter by:
        # 1. If source has a specific channel_id (per-channel mode), use that
        # 2. Otherwise, use chat_ids from closure (if any)
        # 3. Otherwise, fetch all chats for the guild
        effective_chat_ids = chat_ids
        if source and hasattr(source, 'channel_id') and source.channel_id:
            # Per-channel mode: use the source's specific channel_id
            effective_chat_ids = [source.channel_id]
            logger.debug(f"WhatsApp fetch using source.channel_id: {source.channel_id}")
        elif source and hasattr(source, 'channel_ids') and source.channel_ids:
            # Multiple specific channels
            effective_chat_ids = source.channel_ids
            logger.debug(f"WhatsApp fetch using source.channel_ids: {source.channel_ids}")

        # Try file-based archive first
        messages = await importer.get_messages_for_period(
            group_id=group_id,
            start=start_time,
            end=end_time,
        )

        # ADR-081: If no messages from file archive, try database imports
        if not messages:
            logger.info(f"WhatsApp: No file archive messages, trying database for guild={group_id}")
            try:
                from ...data.repositories import get_repository_factory
                factory = get_repository_factory()
                logger.info(f"WhatsApp: Got factory={factory}")
                conn = await factory.get_connection()
                logger.info(f"WhatsApp: Got conn={conn}")
                if conn:
                    # Query ingest_messages via whatsapp_imports
                    start_iso = start_time.isoformat() if hasattr(start_time, 'isoformat') else str(start_time)
                    end_iso = end_time.isoformat() if hasattr(end_time, 'isoformat') else str(end_time)

                    # Query by guild_id, optionally filtering by specific chat_ids
                    if effective_chat_ids:
                        placeholders = ",".join("?" * len(effective_chat_ids))
                        rows = await conn.fetch_all(
                            f"""
                            SELECT
                                m.id,
                                m.sender_id,
                                m.sender_name,
                                m.timestamp,
                                m.content,
                                m.channel_id
                            FROM ingest_messages m
                            JOIN whatsapp_imports wi ON m.batch_id = wi.id
                            WHERE wi.guild_id = ?
                              AND wi.chat_id IN ({placeholders})
                              AND m.timestamp >= ?
                              AND m.timestamp <= ?
                              AND m.content IS NOT NULL
                              AND m.content != ''
                            ORDER BY m.timestamp ASC
                            """,
                            (group_id, *effective_chat_ids, start_iso, end_iso)
                        )
                        logger.debug(f"WhatsApp query with chat_ids filter: {effective_chat_ids}, got {len(rows)} rows")
                    else:
                        rows = await conn.fetch_all(
                            """
                            SELECT
                                m.id,
                                m.sender_id,
                                m.sender_name,
                                m.timestamp,
                                m.content,
                                m.channel_id
                            FROM ingest_messages m
                            JOIN whatsapp_imports wi ON m.batch_id = wi.id
                            WHERE wi.guild_id = ?
                              AND m.timestamp >= ?
                              AND m.timestamp <= ?
                              AND m.content IS NOT NULL
                              AND m.content != ''
                            ORDER BY m.timestamp ASC
                            """,
                            (group_id, start_iso, end_iso)
                        )
                        logger.info(f"WhatsApp query without chat_ids filter, got {len(rows)} rows")

                    # Convert to archive message format
                    for row in rows:
                        messages.append({
                            "id": row["id"],
                            "author": row["sender_name"] or "Unknown",
                            "author_name": row["sender_name"] or "Unknown",  # SummarizationAdapter uses this
                            "author_id": row["sender_id"] or "unknown",
                            "content": row["content"],
                            "timestamp": row["timestamp"],
                        })
            except Exception as e:
                import traceback
                logger.error(f"Failed to fetch WhatsApp messages from database: {e}\n{traceback.format_exc()}")

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

    # ADR-081: Also include WhatsApp imports from database
    # Track guild_id for each WhatsApp source
    whatsapp_guild_map: Dict[str, str] = {}  # source_key -> guild_id
    try:
        from ...data.repositories import get_whatsapp_import_repository
        whatsapp_repo = await get_whatsapp_import_repository()
        if whatsapp_repo:
            # Get all completed imports across all guilds
            all_imports = await whatsapp_repo.list_all_completed_imports()
            for imp in all_imports:
                # Create source key matching the format used in summaries
                source_key = f"whatsapp:{imp.chat_id}"
                whatsapp_guild_map[source_key] = imp.guild_id
                if source_key not in registry._sources:
                    registry.create_source_from_whatsapp(
                        group_id=imp.chat_id,
                        group_name=imp.chat_name or imp.chat_id
                    )
    except Exception as e:
        logger.warning(f"Failed to load WhatsApp imports for archive sources: {e}")

    # ADR-085: Load Slack workspaces with channels and guild links
    slack_workspace_data: Dict[str, Dict[str, Any]] = {}  # workspace_id -> {channels, linked_guilds}
    try:
        from ...data.repositories import get_slack_repository
        slack_repo = await get_slack_repository()
        if slack_repo:
            workspaces = await slack_repo.list_workspaces(enabled_only=True)
            for ws in workspaces:
                # Get channels for this workspace
                channels = await slack_repo.list_channels(ws.workspace_id, include_archived=False)
                channel_info = [
                    SourceChannelInfo(
                        channel_id=ch.channel_id,
                        channel_name=ch.channel_name,
                        summary_count=0,  # Will be populated from archive
                    )
                    for ch in channels
                ]

                # Get linked guilds
                linked_guilds = await slack_repo.get_workspace_guild_links(ws.workspace_id)

                slack_workspace_data[ws.workspace_id] = {
                    "channels": channel_info,
                    "linked_guilds": linked_guilds,
                    "workspace_name": ws.workspace_name,
                }

                # Register workspace as source if not already discovered
                source_key = f"slack:{ws.workspace_id}"
                if source_key not in registry._sources:
                    registry.create_source_from_slack(
                        workspace_id=ws.workspace_id,
                        workspace_name=ws.workspace_name,
                    )
    except Exception as e:
        logger.warning(f"Failed to load Slack workspaces for archive sources: {e}")

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

        # Get guild_id for WhatsApp sources
        guild_id = whatsapp_guild_map.get(s.source_key) if s.source_key.startswith("whatsapp:") else None

        # Get Slack-specific data (channels and linked guilds)
        linked_guilds = None
        channels = None
        if s.source_key.startswith("slack:"):
            workspace_id = s.source_key.replace("slack:", "")
            slack_data = slack_workspace_data.get(workspace_id, {})
            linked_guilds = slack_data.get("linked_guilds")
            channels = slack_data.get("channels")

        results.append(SourceResponse(
            source_key=s.source_key,
            source_type=s.source_type.value,
            server_id=s.server_id,
            server_name=s.server_name,
            channel_id=s.channel_id,
            channel_name=s.channel_name,
            summary_count=summary_count,
            date_range=date_range,
            guild_id=guild_id,
            linked_guilds=linked_guilds,
            channels=channels,
        ))

    return results


@router.delete("/sources/{source_key}")
async def delete_source(source_key: str):
    """Delete an archive source and its directory.

    Only deletes if the source has 0 summaries to prevent data loss.
    """
    import shutil

    registry = get_source_registry()
    registry.discover_sources()

    source = registry.get_source(source_key)
    if not source:
        raise HTTPException(404, f"Source not found: {source_key}")

    archive_root = get_archive_root()
    archive_path = source.get_archive_path(archive_root)

    # Count existing summaries
    summary_count = 0
    if archive_path.exists():
        md_files = list(archive_path.glob("**/*.md"))
        summary_count = len(md_files)

    if summary_count > 0:
        raise HTTPException(
            400,
            f"Cannot delete source with {summary_count} summaries. "
            "Delete the summaries first or use force=true."
        )

    # Delete the directory if it exists
    if archive_path.exists():
        try:
            shutil.rmtree(archive_path)
            logger.info(f"Deleted archive source directory: {archive_path}")
        except Exception as e:
            logger.exception(f"Failed to delete {archive_path}: {e}")
            raise HTTPException(500, f"Failed to delete source: {e}")

    # Remove from registry
    registry.unregister_source(source_key)

    return {"success": True, "message": f"Deleted source: {source_key}"}


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
        f"scope={request.scope}, "
        f"summary_type={request.summary_type}, perspective={request.perspective}"
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

    # ADR-112: Track channel_name for path construction
    channel_name = None

    if is_whatsapp:
        # For WhatsApp, get chat names from database imports
        logger.info(f"WhatsApp job: resolved_channel_ids={resolved_channel_ids}, scope={request.scope}")
        try:
            from ...data.repositories import get_whatsapp_import_repository
            whatsapp_repo = await get_whatsapp_import_repository()
            imports, _total = await whatsapp_repo.get_imports_for_guild(guild_id=request.server_id, limit=100)
            logger.info(f"WhatsApp imports found: {len(imports) if imports else 0}")
            if imports:
                # Build a map of chat_id -> chat_name for lookups
                chat_id_to_name = {imp.chat_id: imp.chat_name for imp in imports if imp.chat_id and imp.chat_name}
                logger.debug(f"WhatsApp chat_id_to_name map: {list(chat_id_to_name.keys())}")

                # If specific channel_ids are requested, resolve their names
                if resolved_channel_ids:
                    # Get name for single channel (for channel_name field)
                    if len(resolved_channel_ids) == 1:
                        channel_name = chat_id_to_name.get(resolved_channel_ids[0], resolved_channel_ids[0])
                        logger.info(f"WhatsApp single channel: id={resolved_channel_ids[0]}, name={channel_name}")

                    # Get names for server_name display
                    resolved_names = [chat_id_to_name.get(cid, cid) for cid in resolved_channel_ids]
                    if len(resolved_names) == 1:
                        server_name = resolved_names[0]
                    elif len(resolved_names) <= 3:
                        server_name = ", ".join(resolved_names)
                    else:
                        server_name = f"{resolved_names[0]} + {len(resolved_names) - 1} more"
                else:
                    # All chats - use combined names
                    chat_names = [imp.chat_name for imp in imports if imp.chat_name]
                    if len(chat_names) == 1:
                        server_name = chat_names[0]
                    elif len(chat_names) <= 3:
                        server_name = ", ".join(chat_names)
                    else:
                        server_name = f"{chat_names[0]} + {len(chat_names) - 1} more"
        except Exception as e:
            logger.warning(f"Failed to get WhatsApp chat names: {e}", exc_info=True)

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
    # ADR-116: WhatsApp uses chat_id as server_id (no separate channel concept)
    is_whatsapp = request.source_type == "whatsapp"
    if is_whatsapp and resolved_channel_ids:
        # For WhatsApp, chat_id IS the server_id (not a channel within a server)
        source = ArchiveSource(
            source_type=SourceType.WHATSAPP,
            server_id=resolved_channel_ids[0],  # chat_id
            server_name=channel_name or resolved_channel_ids[0],  # chat_name
            scope=archive_scope,
            # No channel_id for WhatsApp - the chat IS the "server"
        )
    else:
        source = ArchiveSource(
            source_type=SourceType(request.source_type),
            server_id=request.server_id,
            server_name=server_name,
            scope=archive_scope,
            channel_id=resolved_channel_ids[0] if len(resolved_channel_ids) == 1 else None,
            channel_name=channel_name,  # ADR-112: Required for path construction
            channel_ids=resolved_channel_ids if len(resolved_channel_ids) > 1 else None,
            category_id=category_id,
            category_name=category_name,
        )

    generator = await get_generator()
    logger.info(f"Creating job with per_channel={request.per_channel}, granularity={request.granularity}, auto_publish_confluence={request.auto_publish_confluence}")
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
        schedule_days=request.schedule_days,
        lookback_hours=request.lookback_hours,
        # ADR-096: Per-channel mode
        per_channel=request.per_channel or False,
        min_channel_messages=request.min_channel_messages or 5,
        # ADR-111: Auto-publish to Confluence
        auto_publish_confluence=request.auto_publish_confluence or False,
        # ADR-116: Track creation source
        creation_source=request.creation_source or "unknown",
    )

    # Start job in background if not dry run
    if not request.dry_run:
        import asyncio

        # Use appropriate message fetcher based on source type
        if is_whatsapp:
            # Pass chat_ids to filter by specific chats if selected
            message_fetcher = create_whatsapp_message_fetcher(
                archive_root=get_archive_root(),
                group_id=request.server_id,
                chat_ids=resolved_channel_ids if resolved_channel_ids else None,
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
    """Resume a paused job.

    After server restart, jobs are lost from memory but preserved in the database.
    This endpoint will restore the job from DB if needed before resuming.
    """
    import asyncio
    from src.archive.generator import JobStatus

    generator = await get_generator()

    # Try in-memory first
    job = generator.get_job(job_id)

    # If not in memory, try to restore from database (e.g., after server restart)
    if not job:
        job = await generator.restore_job_from_db(job_id)

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


def _derive_group_info_from_filename(filename: str) -> tuple[str, str]:
    """
    Derive group name and ID from a WhatsApp export filename.

    WhatsApp exports typically have filenames like:
    - "WhatsApp Chat with GroupName.txt"
    - "WhatsApp Chat with GroupName.zip"
    - "_chat.txt" (inside zip, less useful)

    Returns:
        Tuple of (group_id, group_name)
    """
    import re
    import hashlib

    # Remove file extension
    name = filename
    for ext in ['.zip', '.txt', '.json']:
        if name.lower().endswith(ext):
            name = name[:-len(ext)]

    # Try to extract group name from "WhatsApp Chat with X" pattern
    match = re.match(r'^WhatsApp Chat with (.+)$', name, re.IGNORECASE)
    if match:
        group_name = match.group(1).strip()
    else:
        # Fall back to filename (without extension) as group name
        group_name = name.strip()

    # Clean up group name - remove any trailing underscore + numbers (dedup suffixes)
    group_name = re.sub(r'_\d+$', '', group_name)

    # Generate a deterministic group_id from the name
    # This ensures same filename always gets same ID
    slug = re.sub(r'[^\w\s-]', '', group_name.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')

    # Add a short hash to ensure uniqueness for different names that might slug the same
    name_hash = hashlib.md5(group_name.encode()).hexdigest()[:6]
    group_id = f"{slug[:30]}-{name_hash}" if slug else name_hash

    return group_id, group_name


@router.post("/import/whatsapp")
async def import_whatsapp(
    file: UploadFile = File(...),
    group_id: Optional[str] = Query(None, description="Group ID (derived from filename if not provided)"),
    group_name: Optional[str] = Query(None, description="Group name (derived from filename if not provided)"),
    format: str = Query("whatsapp_txt"),  # "whatsapp_txt" or "reader_bot"
):
    """
    Import WhatsApp chat export.

    ADR-006: Supports both .txt and .zip file formats.
    ADR-078: Derives group name and ID from filename if not provided.

    When a .zip file is uploaded, the archive is extracted and the
    contained .txt file is processed. The group name is extracted from
    filenames like "WhatsApp Chat with GroupName.zip".
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
    derived_name_source = None  # Track where we derived the name from

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

                    # ADR-078: Derive group info from the inner .txt filename first (more specific)
                    # then fall back to the outer .zip filename
                    if not group_id or not group_name:
                        # Try inner filename first (e.g., "WhatsApp Chat with Family.txt")
                        inner_id, inner_name = _derive_group_info_from_filename(txt_filename)
                        # If inner filename is generic (like "_chat.txt"), use outer filename
                        if inner_name.lower() in ['_chat', 'chat', 'whatsapp chat']:
                            derived_name_source = original_filename
                        else:
                            derived_name_source = txt_filename

                    # Update original filename for result metadata
                    original_filename = txt_filename

            except zipfile.BadZipFile:
                raise HTTPException(
                    400,
                    "Invalid ZIP file. Please upload a valid WhatsApp export ZIP or .txt file."
                )
        else:
            # For .txt files, use the filename directly
            derived_name_source = original_filename

        # ADR-078: Derive group_id and group_name from filename if not provided
        if not group_id or not group_name:
            source_filename = derived_name_source or original_filename
            derived_id, derived_name = _derive_group_info_from_filename(source_filename)

            if not group_id:
                group_id = derived_id
                logger.info(f"Derived group_id from filename: {group_id}")

            if not group_name:
                group_name = derived_name
                logger.info(f"Derived group_name from filename: {group_name}")

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

        # ADR-007.1: Get tenant name for subfolder isolation
        tenant_folder_name = None
        try:
            from . import get_tenant_repository
            tenant_repo = await get_tenant_repository()
            if tenant_repo:
                tenant = await tenant_repo.get_tenant_for_workspace(server_id)
                if tenant:
                    tenant_folder_name = tenant.name
        except Exception as e:
            logger.warning(f"Failed to get tenant for server {server_id}: {e}")

        # Sync using OAuth tokens
        files_synced = 0
        files_failed = 0
        bytes_uploaded = 0
        errors = []

        try:
            async with httpx.AsyncClient() as client:
                # ADR-007.1: Create tenant subfolder if tenant exists
                target_folder_id = server_config.folder_id
                if tenant_folder_name:
                    # Check if tenant folder exists, create if not
                    sanitized_name = tenant_folder_name.replace("/", "_").replace("\\", "_")[:50]
                    params: Dict[str, Any] = {
                        "q": f"name='{sanitized_name}' and '{server_config.folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                        "fields": "files(id,name)",
                    }
                    if server_config.drive_id:
                        params["corpora"] = "drive"
                        params["driveId"] = server_config.drive_id
                        params["includeItemsFromAllDrives"] = "true"
                        params["supportsAllDrives"] = "true"

                    response = await client.get(
                        "https://www.googleapis.com/drive/v3/files",
                        headers={"Authorization": f"Bearer {tokens.access_token}"},
                        params=params,
                    )

                    if response.status_code == 200:
                        existing = response.json().get("files", [])
                        if existing:
                            target_folder_id = existing[0]["id"]
                        else:
                            # Create tenant subfolder
                            folder_metadata: Dict[str, Any] = {
                                "name": sanitized_name,
                                "mimeType": "application/vnd.google-apps.folder",
                                "parents": [server_config.folder_id],
                            }
                            create_params: Dict[str, Any] = {"supportsAllDrives": "true"} if server_config.drive_id else {}
                            create_response = await client.post(
                                "https://www.googleapis.com/drive/v3/files",
                                headers={
                                    "Authorization": f"Bearer {tokens.access_token}",
                                    "Content-Type": "application/json",
                                },
                                params=create_params,
                                json=folder_metadata,
                            )
                            if create_response.status_code in (200, 201):
                                target_folder_id = create_response.json()["id"]
                                logger.info(f"Created tenant subfolder: {sanitized_name}")

                # ADR-091: Get stored summaries from database with filtering
                from . import get_stored_summary_repository
                from src.archive.sync.exporter import export_summary, get_period_folder_name

                repo = await get_stored_summary_repository()
                if not repo:
                    raise HTTPException(500, "Summary repository not available")

                # Apply export filters from config
                filter_kwargs: Dict[str, Any] = {"limit": 10000}
                if server_config.export_filters:
                    ef = server_config.export_filters
                    if ef.get("source"):
                        filter_kwargs["source"] = ef["source"]
                    if ef.get("createdAfter"):
                        filter_kwargs["created_after"] = ef["createdAfter"]
                    if ef.get("createdBefore"):
                        filter_kwargs["created_before"] = ef["createdBefore"]

                summaries = await repo.find_by_guild(server_id, **filter_kwargs)
                logger.info(f"Found {len(summaries)} summaries to sync for {server_id}")

                # ADR-091: Create conversations/ folder structure
                conversations_folder_id = target_folder_id
                if server_config.folder_structure == "by-period":
                    # Create 'conversations' top-level folder
                    conv_params: Dict[str, Any] = {
                        "q": f"name='conversations' and '{target_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                        "fields": "files(id,name)",
                    }
                    if server_config.drive_id:
                        conv_params["corpora"] = "drive"
                        conv_params["driveId"] = server_config.drive_id
                        conv_params["includeItemsFromAllDrives"] = "true"
                        conv_params["supportsAllDrives"] = "true"

                    conv_response = await client.get(
                        "https://www.googleapis.com/drive/v3/files",
                        headers={"Authorization": f"Bearer {tokens.access_token}"},
                        params=conv_params,
                    )

                    if conv_response.status_code == 200:
                        existing = conv_response.json().get("files", [])
                        if existing:
                            conversations_folder_id = existing[0]["id"]
                        else:
                            # Create conversations folder
                            conv_metadata: Dict[str, Any] = {
                                "name": "conversations",
                                "mimeType": "application/vnd.google-apps.folder",
                                "parents": [target_folder_id],
                            }
                            create_params: Dict[str, Any] = {"supportsAllDrives": "true"} if server_config.drive_id else {}
                            create_response = await client.post(
                                "https://www.googleapis.com/drive/v3/files",
                                headers={
                                    "Authorization": f"Bearer {tokens.access_token}",
                                    "Content-Type": "application/json",
                                },
                                params=create_params,
                                json=conv_metadata,
                            )
                            if create_response.status_code in (200, 201):
                                conversations_folder_id = create_response.json()["id"]
                                logger.info("Created conversations folder")

                # Cache for period folders
                period_folder_cache: Dict[str, str] = {}

                async def get_or_create_period_folder(period_name: str) -> str:
                    """Get or create a period folder, caching results."""
                    if period_name in period_folder_cache:
                        return period_folder_cache[period_name]

                    # Check if exists
                    search_params: Dict[str, Any] = {
                        "q": f"name='{period_name}' and '{conversations_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                        "fields": "files(id,name)",
                    }
                    if server_config.drive_id:
                        search_params["corpora"] = "drive"
                        search_params["driveId"] = server_config.drive_id
                        search_params["includeItemsFromAllDrives"] = "true"
                        search_params["supportsAllDrives"] = "true"

                    response = await client.get(
                        "https://www.googleapis.com/drive/v3/files",
                        headers={"Authorization": f"Bearer {tokens.access_token}"},
                        params=search_params,
                    )

                    if response.status_code == 200:
                        existing = response.json().get("files", [])
                        if existing:
                            period_folder_cache[period_name] = existing[0]["id"]
                            return existing[0]["id"]

                    # Create folder
                    folder_metadata: Dict[str, Any] = {
                        "name": period_name,
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [conversations_folder_id],
                    }
                    create_params: Dict[str, Any] = {"supportsAllDrives": "true"} if server_config.drive_id else {}
                    create_response = await client.post(
                        "https://www.googleapis.com/drive/v3/files",
                        headers={
                            "Authorization": f"Bearer {tokens.access_token}",
                            "Content-Type": "application/json",
                        },
                        params=create_params,
                        json=folder_metadata,
                    )
                    if create_response.status_code in (200, 201):
                        folder_id = create_response.json()["id"]
                        period_folder_cache[period_name] = folder_id
                        logger.info(f"Created period folder: {period_name}")
                        return folder_id

                    return conversations_folder_id  # Fallback

                for summary in summaries:
                    try:
                        # Export to markdown (and optionally JSON)
                        base_filename, markdown_content, json_content = export_summary(summary)

                        # ADR-091: Determine target folder based on structure
                        if server_config.folder_structure == "by-period":
                            period_name = get_period_folder_name(
                                summary.created_at,
                                server_config.period_grouping
                            )
                            file_folder_id = await get_or_create_period_folder(period_name)
                        else:
                            file_folder_id = conversations_folder_id

                        # Upload markdown file
                        md_metadata = {
                            "name": f"{base_filename}.md",
                            "parents": [file_folder_id],
                        }
                        boundary = "===boundary==="
                        md_body = (
                            f"--{boundary}\r\n"
                            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                            f"{json.dumps(md_metadata)}\r\n"
                            f"--{boundary}\r\n"
                            f"Content-Type: text/markdown; charset=UTF-8\r\n\r\n"
                            f"{markdown_content}\r\n"
                            f"--{boundary}--"
                        )

                        upload_params: Dict[str, Any] = {"uploadType": "multipart"}
                        if server_config.drive_id:
                            upload_params["supportsAllDrives"] = "true"

                        md_response = await client.post(
                            "https://www.googleapis.com/upload/drive/v3/files",
                            headers={
                                "Authorization": f"Bearer {tokens.access_token}",
                                "Content-Type": f"multipart/related; boundary={boundary}",
                            },
                            params=upload_params,
                            content=md_body.encode("utf-8"),
                        )

                        if md_response.status_code in (200, 201):
                            files_synced += 1
                            bytes_uploaded += len(markdown_content.encode("utf-8"))
                        else:
                            files_failed += 1
                            errors.append(f"{base_filename}.md: {md_response.status_code}")
                            continue  # Skip JSON if markdown failed

                        # ADR-091: Only upload JSON if include_json is enabled
                        if server_config.include_json:
                            json_metadata = {
                                "name": f"{base_filename}.json",
                                "parents": [file_folder_id],
                            }
                            json_body = (
                                f"--{boundary}\r\n"
                                f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                                f"{json.dumps(json_metadata)}\r\n"
                                f"--{boundary}\r\n"
                                f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                                f"{json_content}\r\n"
                                f"--{boundary}--"
                            )

                            json_response = await client.post(
                                "https://www.googleapis.com/upload/drive/v3/files",
                                headers={
                                    "Authorization": f"Bearer {tokens.access_token}",
                                    "Content-Type": f"multipart/related; boundary={boundary}",
                                },
                                params=upload_params,
                                content=json_body.encode("utf-8"),
                            )

                            if json_response.status_code in (200, 201):
                                files_synced += 1
                                bytes_uploaded += len(json_content.encode("utf-8"))
                            else:
                                errors.append(f"{base_filename}.json: {json_response.status_code}")

                    except Exception as e:
                        files_failed += 1
                        errors.append(f"{summary.id[:8]}: {str(e)}")

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
    folder_path: Optional[str] = None  # ADR-007.1: Full path for clarity
    drive_type: Optional[str] = None  # ADR-007.1: "my_drive" | "shared"
    drive_id: Optional[str] = None  # ADR-007.1: Shared drive ID
    drive_name: Optional[str] = None  # ADR-007.1: Drive display name
    user_email: Optional[str] = None  # ADR-007.1: Connected user's email
    configured_by: Optional[str] = None
    configured_at: Optional[str] = None
    last_sync: Optional[str] = None
    using_fallback: bool = False
    # ADR-091: Export configuration
    export_filters: Optional[Dict[str, Any]] = None
    include_markdown: bool = True  # Include markdown files (default: yes)
    include_json: bool = False
    folder_structure: str = "by-period"
    period_grouping: str = "week"
    # ADR-091: Filter fields
    filter_scope: Optional[str] = None  # "channel" | "category" | "server" | None (all)
    filter_source: Optional[str] = None  # "scheduled" | "manual" | "realtime" | "archive" | None (all)
    filter_granularity: Optional[str] = None  # "daily" | "weekly" | "monthly" | None (all)


class ConfigureServerSyncRequest(BaseModel):
    """Request to configure server sync."""
    folder_id: str
    folder_name: str = ""
    folder_path: str = ""  # ADR-007.1: Full path
    drive_type: str = "my_drive"  # ADR-007.1: "my_drive" | "shared"
    drive_id: Optional[str] = None  # ADR-007.1: For shared drives
    drive_name: Optional[str] = None  # ADR-007.1: Drive display name
    sync_on_generation: bool = True
    include_metadata: bool = True
    # ADR-091: Export configuration
    export_filters: Optional[Dict[str, Any]] = None
    include_markdown: bool = True  # Include markdown files (default: yes)
    include_json: bool = False
    folder_structure: str = "by-period"
    period_grouping: str = "week"
    # ADR-091: Filter fields
    filter_scope: Optional[str] = None  # "channel" | "category" | "server" | None (all)
    filter_source: Optional[str] = None  # "scheduled" | "manual" | "realtime" | "archive" | None (all)
    filter_granularity: Optional[str] = None  # "daily" | "weekly" | "monthly" | None (all)


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
        Redirect to frontend with success/error indicator
    """
    from fastapi.responses import RedirectResponse
    import urllib.parse

    oauth = get_oauth_flow()
    base_url = os.environ.get("DASHBOARD_BASE_URL", "https://summarybot.app")

    # Validate state
    oauth_state = oauth.validate_state(state)
    if not oauth_state:
        return RedirectResponse(
            url=f"{base_url}/?oauth_error={urllib.parse.quote('Invalid or expired state token')}",
            status_code=302,
        )

    try:
        # Exchange code for tokens
        tokens = await oauth.exchange_code(code, oauth_state)

        # Redirect to frontend settings page - Google Drive sync is now in Settings (ADR-091)
        return RedirectResponse(
            url=f"{base_url}/guilds/{oauth_state.server_id}/settings?oauth=success&select_folder=true",
            status_code=302,
        )

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}", exc_info=True)
        # Use server_id from oauth_state if available, otherwise redirect to home
        if oauth_state and oauth_state.server_id:
            return RedirectResponse(
                url=f"{base_url}/guilds/{oauth_state.server_id}/settings?oauth=error&message={urllib.parse.quote(str(e))}",
                status_code=302,
            )
        else:
            return RedirectResponse(
                url=f"{base_url}/?oauth_error={urllib.parse.quote(str(e))}",
                status_code=302,
            )


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
            folder_path=config.folder_path,
            drive_type=config.drive_type,
            drive_id=config.drive_id or None,
            drive_name=config.drive_name or None,
            user_email=config.user_email or None,
            configured_by=config.configured_by,
            configured_at=config.configured_at.isoformat() if config.configured_at else None,
            last_sync=config.last_sync.isoformat() if config.last_sync else None,
            using_fallback=False,
            # ADR-091: Export configuration
            export_filters=config.export_filters,
            include_markdown=config.include_markdown,
            include_json=config.include_json,
            folder_structure=config.folder_structure,
            period_grouping=config.period_grouping,
            # ADR-091: Filter fields
            filter_scope=config.filter_scope,
            filter_source=config.filter_source,
            filter_granularity=config.filter_granularity,
        )

    # Check if using fallback
    using_fallback = service.config.is_configured()

    return ServerSyncConfigResponse(
        server_id=server_id,
        enabled=using_fallback,
        folder_id=service.config.folder_id if using_fallback else None,
        using_fallback=using_fallback,
    )


class SyncStatsResponse(BaseModel):
    """Sync statistics for a server. ADR-007.1: Now syncs database summaries as markdown + JSON."""
    summaries_available: int  # Number of stored summaries that can be synced (after filters)
    summaries_total: int = 0  # Total summaries before filters
    filter_active: bool = False  # Whether any filters are applied
    files_in_drive: int  # Number of files already in Drive folder (includes .md and .json)
    last_sync: Optional[str] = None
    summaries_query_url: str  # URL to view summaries in UI


@router.get("/sync/server/{server_id}/stats", response_model=SyncStatsResponse)
async def get_sync_stats(server_id: str):
    """
    Get sync statistics for a server.

    Returns count of stored summaries available to sync and files already in Drive.
    ADR-007.1: Sync now exports database summaries as markdown + JSON.
    """
    from . import get_stored_summary_repository

    # Count database summaries for this server (what gets synced)
    repo = await get_stored_summary_repository()
    summaries_total = 0
    summaries_available = 0
    filter_active = False

    service = get_sync_service()
    config = await service.get_server_config(server_id)

    if repo:
        summaries = await repo.find_by_guild(server_id, limit=10000)
        summaries_total = len(summaries)

        # Apply filters if configured (using inline filter logic since helper is defined later)
        filtered = summaries
        if config:
            filter_scope = getattr(config, 'filter_scope', None)
            filter_source = getattr(config, 'filter_source', None)
            filter_granularity = getattr(config, 'filter_granularity', None)
            logger.debug(f"Sync stats filters - scope={filter_scope!r}, source={filter_source!r}, gran={filter_granularity!r}")

            if filter_scope:
                before = len(filtered)
                if filter_scope == "channel":
                    filtered = [s for s in filtered if len(getattr(s, 'source_channel_ids', []) or []) == 1]
                elif filter_scope == "category":
                    filtered = [s for s in filtered if 2 <= len(getattr(s, 'source_channel_ids', []) or []) <= 10]
                elif filter_scope == "server":
                    filtered = [s for s in filtered if len(getattr(s, 'source_channel_ids', []) or []) > 10]
                logger.debug(f"Scope filter {filter_scope}: {before} -> {len(filtered)}")

            if filter_source:
                before = len(filtered)
                # Compare enum value to filter string
                filtered = [s for s in filtered if getattr(s, 'source', None) and getattr(s, 'source').value == filter_source]
                logger.debug(f"Source filter {filter_source}: {before} -> {len(filtered)}")

            if filter_granularity:
                before = len(filtered)
                def matches_gran(s):
                    start = getattr(s, 'start_time', None)
                    end = getattr(s, 'end_time', None)
                    if not start or not end:
                        return True
                    days = (end - start).days
                    if filter_granularity == "daily":
                        return days <= 1
                    elif filter_granularity == "weekly":
                        return 2 <= days <= 8
                    elif filter_granularity == "monthly":
                        return days > 20
                    return True
                filtered = [s for s in filtered if matches_gran(s)]
                logger.debug(f"Granularity filter {filter_granularity}: {before} -> {len(filtered)}")

        summaries_available = len(filtered)
        filter_active = summaries_available != summaries_total
        logger.info(f"Sync stats for {server_id}: {summaries_available}/{summaries_total} available, filter_active={filter_active}")

    # Get files in Drive folder
    files_in_drive = 0
    last_sync = None

    if config and config.enabled and config.folder_id:
        oauth = get_oauth_flow()
        token_id = f"srv_{server_id}_gdrive"
        tokens = await oauth.get_valid_tokens(token_id)

        if tokens:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    # Count files in the sync folder
                    params: Dict[str, Any] = {
                        "q": f"'{config.folder_id}' in parents and trashed=false",
                        "fields": "files(id)",
                        "pageSize": 1000,
                    }
                    if config.drive_id:
                        params["corpora"] = "drive"
                        params["driveId"] = config.drive_id
                        params["includeItemsFromAllDrives"] = "true"
                        params["supportsAllDrives"] = "true"

                    response = await client.get(
                        "https://www.googleapis.com/drive/v3/files",
                        headers={"Authorization": f"Bearer {tokens.access_token}"},
                        params=params,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        files_in_drive = len(data.get("files", []))
            except Exception as e:
                logger.warning(f"Failed to count Drive files: {e}")

        if config.last_sync:
            last_sync = config.last_sync.isoformat()

    # Build URL to view summaries (all summaries since we sync all)
    summaries_query_url = f"/guilds/{server_id}/summaries"

    return SyncStatsResponse(
        summaries_available=summaries_available,
        summaries_total=summaries_total,
        filter_active=filter_active,
        files_in_drive=files_in_drive,
        last_sync=last_sync,
        summaries_query_url=summaries_query_url,
    )


# ADR-091: Sync preview and sample sync endpoints


class SyncPreviewFile(BaseModel):
    """Preview of a file that will be synced."""
    id: str
    title: str
    channel_name: str
    created_at: str
    size_estimate: int
    period_folder: str


class SyncPreviewResponse(BaseModel):
    """Preview of files to be synced."""
    files: List[SyncPreviewFile]
    total_pending: int
    filter_active: bool = False  # Whether any filters are applied


def _apply_sync_filters(summaries: List, config) -> List:
    """
    Apply sync filters from server config (ADR-091).

    Filters:
    - scope: "channel" | "category" | "server" (based on source_channel_ids count)
    - source: "scheduled" | "manual" | "realtime" | "archive"
    - granularity: "daily" | "weekly" | "monthly"
    """
    if not config:
        return summaries

    filtered = summaries

    # Filter by scope
    filter_scope = getattr(config, 'filter_scope', None)
    if filter_scope:
        if filter_scope == "channel":
            # Single channel summaries only
            filtered = [s for s in filtered if len(getattr(s, 'source_channel_ids', []) or []) == 1]
        elif filter_scope == "category":
            # Multi-channel but not server-wide (2-10 channels)
            filtered = [s for s in filtered if 2 <= len(getattr(s, 'source_channel_ids', []) or []) <= 10]
        elif filter_scope == "server":
            # Server-wide summaries (more than 10 channels or explicitly server scope)
            filtered = [s for s in filtered if len(getattr(s, 'source_channel_ids', []) or []) > 10]

    # Filter by source (compare enum value to filter string)
    filter_source = getattr(config, 'filter_source', None)
    if filter_source:
        filtered = [s for s in filtered if getattr(s, 'source', None) and getattr(s, 'source').value == filter_source]

    # Filter by granularity (daily/weekly/monthly based on date range)
    filter_granularity = getattr(config, 'filter_granularity', None)
    if filter_granularity:
        def matches_granularity(summary):
            start = getattr(summary, 'start_time', None)
            end = getattr(summary, 'end_time', None)
            if not start or not end:
                return True  # Include if we can't determine

            duration = (end - start).days
            if filter_granularity == "daily":
                return duration <= 1
            elif filter_granularity == "weekly":
                return 2 <= duration <= 8
            elif filter_granularity == "monthly":
                return duration > 20
            return True

        filtered = [s for s in filtered if matches_granularity(s)]

    return filtered


@router.get("/sync/server/{server_id}/preview", response_model=SyncPreviewResponse)
async def get_sync_preview(server_id: str, limit: int = 3):
    """
    Preview what will be synced (ADR-091).

    Returns the N most recent summaries that would be synced,
    along with the total count of pending files.
    Applies any configured filters.
    """
    from . import get_stored_summary_repository

    try:
        repo = await get_stored_summary_repository()
        if not repo:
            return SyncPreviewResponse(files=[], total_pending=0)

        # Get server config for filters and period grouping
        config = None
        period_grouping = "week"
        try:
            service = get_sync_service()
            config = await service.get_server_config(server_id)
            if config and hasattr(config, 'period_grouping') and config.period_grouping:
                period_grouping = config.period_grouping
        except Exception as e:
            logger.warning(f"Failed to get server config for preview: {e}")

        # Get all summaries for this server
        all_summaries = await repo.find_by_guild(server_id, limit=10000)

        # Apply filters from config
        filtered_summaries = _apply_sync_filters(all_summaries, config)
        total_pending = len(filtered_summaries)
        filter_active = len(filtered_summaries) != len(all_summaries)

        # Get the most recent N for preview
        recent = filtered_summaries[:limit]

        preview_files = []
        for summary in recent:
            try:
                # Generate period folder name
                created = summary.created_at
                if period_grouping == "week":
                    week_start = created - timedelta(days=created.weekday())
                    week_end = week_start + timedelta(days=6)
                    period_folder = f"{week_start.strftime('%Y-%m-%d')}--{week_end.strftime('%Y-%m-%d')}"
                else:
                    month_start = created.replace(day=1)
                    next_month = (month_start + timedelta(days=32)).replace(day=1)
                    month_end = next_month - timedelta(days=1)
                    period_folder = f"{month_start.strftime('%Y-%m-%d')}--{month_end.strftime('%Y-%m-%d')}"

                # Generate title from summary
                channel_name = "general"
                if summary.summary_result and summary.summary_result.context:
                    channel_name = summary.summary_result.context.channel_name or "general"
                title = f"{channel_name}_{summary.id[:8]}"

                # Estimate file size (rough: 1 byte per char of summary text)
                size_estimate = 500
                if summary.summary_result and summary.summary_result.summary_text:
                    size_estimate = len(summary.summary_result.summary_text)

                preview_files.append(SyncPreviewFile(
                    id=summary.id,
                    title=title,
                    channel_name=channel_name,
                    created_at=created.isoformat(),
                    size_estimate=size_estimate,
                    period_folder=period_folder,
                ))
            except Exception as e:
                logger.warning(f"Failed to process summary {summary.id} for preview: {e}")
                continue

        return SyncPreviewResponse(files=preview_files, total_pending=total_pending, filter_active=filter_active)

    except Exception as e:
        logger.error(f"Failed to get sync preview for {server_id}: {e}")
        return SyncPreviewResponse(files=[], total_pending=0, filter_active=False)


class SampleSyncResultResponse(BaseModel):
    """Result of a sample sync operation."""
    status: str
    files_synced: int
    files_failed: int
    bytes_uploaded: int
    errors: List[str]
    files: List[SyncPreviewFile]
    drive_urls: List[str]


@router.post("/sync/sample/{source_key}", response_model=SampleSyncResultResponse)
async def trigger_sample_sync(source_key: str, sample_size: int = 3):
    """
    Sync a sample of files for preview (ADR-091).

    Syncs only the N most recent summaries so the admin can verify
    folder structure and format before syncing everything.
    """
    import httpx

    service = get_sync_service()
    oauth = get_oauth_flow()

    # Parse source key
    parts = source_key.split(":")
    if len(parts) != 2:
        raise HTTPException(400, f"Invalid source key: {source_key}")

    source_type, server_id = parts

    # Get server config
    server_config = await service.get_server_config(server_id)
    if not server_config or not server_config.enabled:
        raise HTTPException(400, "Server sync not configured")

    # Get OAuth tokens
    tokens = await oauth.get_valid_tokens(server_config.oauth_token_id)
    if not tokens:
        raise HTTPException(400, "OAuth tokens expired. Please reconnect Google Drive.")

    # Get summaries to sync
    from . import get_stored_summary_repository
    repo = await get_stored_summary_repository()
    if not repo:
        raise HTTPException(500, "Summary repository not available")

    all_summaries = await repo.find_by_guild(server_id, limit=10000)

    # Apply filters from server config
    filtered_summaries = _apply_sync_filters(all_summaries, server_config)
    sample_summaries = filtered_summaries[:sample_size]

    logger.info(f"Sample sync: Found {len(all_summaries)} summaries, {len(filtered_summaries)} after filters, syncing {len(sample_summaries)}")

    if not sample_summaries:
        return SampleSyncResultResponse(
            status="success",
            files_synced=0,
            files_failed=0,
            bytes_uploaded=0,
            errors=[],
            files=[],
            drive_urls=[],
        )

    # Sync the sample
    files_synced = 0
    files_failed = 0
    bytes_uploaded = 0
    errors = []
    synced_files = []
    drive_urls = []

    period_grouping = server_config.period_grouping or "week"

    async with httpx.AsyncClient() as client:
        for summary in sample_summaries:
            try:
                # Generate period folder name
                created = summary.created_at
                if period_grouping == "week":
                    week_start = created - timedelta(days=created.weekday())
                    week_end = week_start + timedelta(days=6)
                    period_folder = f"{week_start.strftime('%Y-%m-%d')}--{week_end.strftime('%Y-%m-%d')}"
                else:
                    month_start = created.replace(day=1)
                    next_month = (month_start + timedelta(days=32)).replace(day=1)
                    month_end = next_month - timedelta(days=1)
                    period_folder = f"{month_start.strftime('%Y-%m-%d')}--{month_end.strftime('%Y-%m-%d')}"

                # Create conversations folder if needed
                conversations_folder_id = await _ensure_folder(
                    client, tokens.access_token,
                    "conversations",
                    server_config.folder_id,
                    server_config.drive_id,
                )

                # Create period folder if needed
                period_folder_id = await _ensure_folder(
                    client, tokens.access_token,
                    period_folder,
                    conversations_folder_id,
                    server_config.drive_id,
                )

                # Generate title
                channel_name = "general"
                if summary.summary_result and summary.summary_result.context:
                    channel_name = summary.summary_result.context.channel_name or "general"
                title = f"{channel_name}_{summary.id[:8]}"

                # Get format settings (defaults: markdown=true, json=false)
                include_markdown = getattr(server_config, 'include_markdown', True)
                include_json = getattr(server_config, 'include_json', False)
                if not include_markdown and not include_json:
                    include_markdown = True

                summary_synced = False
                summary_size = 0

                # Upload markdown if enabled
                if include_markdown:
                    md_filename = f"{title}.md"
                    existing_id = await _file_exists_in_drive(
                        client, tokens.access_token,
                        md_filename, period_folder_id, server_config.drive_id
                    )
                    if existing_id:
                        drive_urls.append(f"https://drive.google.com/file/d/{existing_id}/view")
                        logger.info(f"Skipped {md_filename} - already exists")
                    else:
                        markdown_content = _generate_summary_markdown(summary)
                        file_id = await _upload_to_drive(
                            client, tokens.access_token,
                            md_filename, markdown_content,
                            period_folder_id, server_config.drive_id,
                        )
                        drive_urls.append(f"https://drive.google.com/file/d/{file_id}/view")
                        summary_synced = True
                        summary_size += len(markdown_content.encode())

                # Upload JSON if enabled
                if include_json:
                    json_filename = f"{title}.json"
                    existing_id = await _file_exists_in_drive(
                        client, tokens.access_token,
                        json_filename, period_folder_id, server_config.drive_id
                    )
                    if existing_id:
                        drive_urls.append(f"https://drive.google.com/file/d/{existing_id}/view")
                        logger.info(f"Skipped {json_filename} - already exists")
                    else:
                        from dataclasses import asdict
                        json_content = json.dumps({
                            "id": summary.id,
                            "guild_id": summary.guild_id,
                            "title": summary.title,
                            "created_at": summary.created_at.isoformat(),
                            "source": summary.source,
                            "summary_result": asdict(summary.summary_result) if summary.summary_result else None,
                            "is_pinned": summary.is_pinned,
                            "is_archived": summary.is_archived,
                        }, indent=2, default=str)
                        file_id = await _upload_to_drive_json(
                            client, tokens.access_token,
                            json_filename, json_content,
                            period_folder_id, server_config.drive_id,
                        )
                        drive_urls.append(f"https://drive.google.com/file/d/{file_id}/view")
                        summary_synced = True
                        summary_size += len(json_content.encode())

                if summary_synced:
                    files_synced += 1
                    bytes_uploaded += summary_size

                synced_files.append(SyncPreviewFile(
                    id=summary.id,
                    title=title,
                    channel_name=channel_name,
                    created_at=created.isoformat(),
                    size_estimate=summary_size,
                    period_folder=period_folder,
                ))

            except Exception as e:
                files_failed += 1
                errors.append(f"Failed to sync {summary.id}: {str(e)}")
                logger.error(f"Sample sync error for {summary.id}: {e}")

    return SampleSyncResultResponse(
        status="success" if files_failed == 0 else "partial",
        files_synced=files_synced,
        files_failed=files_failed,
        bytes_uploaded=bytes_uploaded,
        errors=errors,
        files=synced_files,
        drive_urls=drive_urls,
    )


class SingleSyncResponse(BaseModel):
    """Result of syncing a single summary to Drive."""
    success: bool
    drive_url: Optional[str] = None  # Primary URL (markdown if enabled, else json)
    drive_urls: List[str] = []  # All URLs (md and/or json)
    files_synced: int = 0
    files_skipped: int = 0  # Already existed
    error: Optional[str] = None


@router.post("/sync/summary/{summary_id}", response_model=SingleSyncResponse)
async def sync_single_summary(summary_id: str, server_id: str):
    """
    Sync a single summary to Google Drive (ADR-091).

    Push an individual summary to Drive immediately, similar to Push to Discord.
    Respects include_markdown and include_json settings.
    Skips files that already exist to avoid duplicates.
    """
    import httpx

    service = get_sync_service()
    oauth = get_oauth_flow()

    # Get server config
    server_config = await service.get_server_config(server_id)
    if not server_config or not server_config.enabled:
        return SingleSyncResponse(success=False, error="Server sync not configured")

    # Get format settings (defaults: markdown=true, json=false)
    include_markdown = getattr(server_config, 'include_markdown', True)
    include_json = getattr(server_config, 'include_json', False)

    # At least one format must be enabled
    if not include_markdown and not include_json:
        include_markdown = True  # Default to markdown

    # Get OAuth tokens
    tokens = await oauth.get_valid_tokens(server_config.oauth_token_id)
    if not tokens:
        return SingleSyncResponse(success=False, error="OAuth tokens expired. Please reconnect Google Drive.")

    # Get the summary
    from . import get_stored_summary_repository
    repo = await get_stored_summary_repository()
    if not repo:
        return SingleSyncResponse(success=False, error="Summary repository not available")

    summary = await repo.get(summary_id)
    if not summary:
        return SingleSyncResponse(success=False, error=f"Summary {summary_id} not found")

    # Verify summary belongs to this server
    if summary.guild_id != server_id:
        return SingleSyncResponse(success=False, error="Summary does not belong to this server")

    period_grouping = server_config.period_grouping or "week"

    try:
        async with httpx.AsyncClient() as client:
            # Generate period folder name
            created = summary.created_at
            if period_grouping == "week":
                week_start = created - timedelta(days=created.weekday())
                week_end = week_start + timedelta(days=6)
                period_folder = f"{week_start.strftime('%Y-%m-%d')}--{week_end.strftime('%Y-%m-%d')}"
            else:
                month_start = created.replace(day=1)
                next_month = (month_start + timedelta(days=32)).replace(day=1)
                month_end = next_month - timedelta(days=1)
                period_folder = f"{month_start.strftime('%Y-%m-%d')}--{month_end.strftime('%Y-%m-%d')}"

            # Create conversations folder if needed
            conversations_folder_id = await _ensure_folder(
                client, tokens.access_token,
                "conversations",
                server_config.folder_id,
                server_config.drive_id,
            )

            # Create period folder if needed
            period_folder_id = await _ensure_folder(
                client, tokens.access_token,
                period_folder,
                conversations_folder_id,
                server_config.drive_id,
            )

            # Generate filename base
            channel_name = "general"
            if summary.summary_result and summary.summary_result.context:
                channel_name = summary.summary_result.context.channel_name or "general"
            title = f"{channel_name}_{summary.id[:8]}"

            drive_urls = []
            files_synced = 0
            files_skipped = 0

            # Upload markdown if enabled
            if include_markdown:
                md_filename = f"{title}.md"
                existing_id = await _file_exists_in_drive(
                    client, tokens.access_token,
                    md_filename, period_folder_id, server_config.drive_id
                )
                if existing_id:
                    # File already exists, add URL but don't re-upload
                    drive_urls.append(f"https://drive.google.com/file/d/{existing_id}/view")
                    files_skipped += 1
                    logger.info(f"Skipped {md_filename} - already exists")
                else:
                    markdown_content = _generate_summary_markdown(summary)
                    file_id = await _upload_to_drive(
                        client, tokens.access_token,
                        md_filename, markdown_content,
                        period_folder_id, server_config.drive_id,
                    )
                    drive_urls.append(f"https://drive.google.com/file/d/{file_id}/view")
                    files_synced += 1

            # Upload JSON if enabled
            if include_json:
                json_filename = f"{title}.json"
                existing_id = await _file_exists_in_drive(
                    client, tokens.access_token,
                    json_filename, period_folder_id, server_config.drive_id
                )
                if existing_id:
                    drive_urls.append(f"https://drive.google.com/file/d/{existing_id}/view")
                    files_skipped += 1
                    logger.info(f"Skipped {json_filename} - already exists")
                else:
                    # Generate JSON content
                    from dataclasses import asdict
                    json_content = json.dumps({
                        "id": summary.id,
                        "guild_id": summary.guild_id,
                        "title": summary.title,
                        "created_at": summary.created_at.isoformat(),
                        "source": summary.source,
                        "summary_result": asdict(summary.summary_result) if summary.summary_result else None,
                        "is_pinned": summary.is_pinned,
                        "is_archived": summary.is_archived,
                    }, indent=2, default=str)
                    file_id = await _upload_to_drive_json(
                        client, tokens.access_token,
                        json_filename, json_content,
                        period_folder_id, server_config.drive_id,
                    )
                    drive_urls.append(f"https://drive.google.com/file/d/{file_id}/view")
                    files_synced += 1

            primary_url = drive_urls[0] if drive_urls else None
            logger.info(f"Synced summary {summary_id}: {files_synced} files synced, {files_skipped} skipped")

            return SingleSyncResponse(
                success=True,
                drive_url=primary_url,
                drive_urls=drive_urls,
                files_synced=files_synced,
                files_skipped=files_skipped,
            )

    except Exception as e:
        logger.error(f"Failed to sync summary {summary_id} to Drive: {e}")
        return SingleSyncResponse(success=False, error=str(e))


async def _ensure_folder(
    client,
    access_token: str,
    folder_name: str,
    parent_id: str,
    drive_id: Optional[str] = None,
) -> str:
    """Ensure a folder exists, create if not. Returns folder ID."""
    # Check if folder exists
    params: Dict[str, Any] = {
        "q": f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        "fields": "files(id,name)",
        "supportsAllDrives": "true",  # Always include for Shared Drives
        "includeItemsFromAllDrives": "true",
    }
    if drive_id:
        params["corpora"] = "drive"
        params["driveId"] = drive_id

    response = await client.get(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )

    if response.status_code == 200:
        data = response.json()
        files = data.get("files", [])
        if files:
            logger.info(f"Found existing folder '{folder_name}' with ID {files[0]['id']}")
            return files[0]["id"]
    else:
        logger.warning(f"Folder search failed: {response.status_code} - {response.text}")

    # Create folder
    metadata: Dict[str, Any] = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }

    create_params: Dict[str, Any] = {"supportsAllDrives": "true"}
    response = await client.post(
        "https://www.googleapis.com/drive/v3/files",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=metadata,
        params=create_params,
    )

    if response.status_code in (200, 201):
        folder_id = response.json()["id"]
        logger.info(f"Created folder '{folder_name}' with ID {folder_id}")
        return folder_id

    logger.error(f"Failed to create folder {folder_name}: {response.status_code} - {response.text}")
    raise Exception(f"Failed to create folder {folder_name}: {response.text}")


async def _file_exists_in_drive(
    client,
    access_token: str,
    filename: str,
    parent_id: str,
    drive_id: Optional[str] = None,
) -> Optional[str]:
    """Check if a file exists in Drive. Returns file ID if exists, None otherwise."""
    params: Dict[str, Any] = {
        "q": f"name='{filename}' and '{parent_id}' in parents and trashed=false",
        "fields": "files(id,name)",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    if drive_id:
        params["corpora"] = "drive"
        params["driveId"] = drive_id

    response = await client.get(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )

    if response.status_code == 200:
        data = response.json()
        files = data.get("files", [])
        if files:
            logger.info(f"File '{filename}' already exists with ID {files[0]['id']}")
            return files[0]["id"]
    return None


async def _upload_to_drive(
    client,
    access_token: str,
    filename: str,
    content: str,
    parent_id: str,
    drive_id: Optional[str] = None,
) -> str:
    """Upload a file to Google Drive. Returns file ID."""
    # Multipart upload
    boundary = "---summarybot-boundary---"
    metadata = {
        "name": filename,
        "parents": [parent_id],
        "mimeType": "text/markdown",
    }

    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/markdown\r\n\r\n"
        f"{content}\r\n"
        f"--{boundary}--"
    )

    # Always include supportsAllDrives for Shared Drive compatibility
    params: Dict[str, Any] = {
        "uploadType": "multipart",
        "supportsAllDrives": "true",
    }

    logger.info(f"Uploading file '{filename}' to parent {parent_id}")

    response = await client.post(
        "https://www.googleapis.com/upload/drive/v3/files",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        content=body.encode("utf-8"),
        params=params,
    )

    if response.status_code in (200, 201):
        file_id = response.json()["id"]
        logger.info(f"Uploaded file '{filename}' with ID {file_id}")
        return file_id

    logger.error(f"Failed to upload {filename}: {response.status_code} - {response.text}")
    raise Exception(f"Failed to upload {filename}: {response.text}")


async def _upload_to_drive_json(
    client,
    access_token: str,
    filename: str,
    content: str,
    parent_id: str,
    drive_id: Optional[str] = None,
) -> str:
    """Upload a JSON file to Google Drive. Returns file ID."""
    boundary = "---summarybot-boundary---"
    metadata = {
        "name": filename,
        "parents": [parent_id],
        "mimeType": "application/json",
    }

    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: application/json\r\n\r\n"
        f"{content}\r\n"
        f"--{boundary}--"
    )

    params: Dict[str, Any] = {
        "uploadType": "multipart",
        "supportsAllDrives": "true",
    }

    logger.info(f"Uploading JSON file '{filename}' to parent {parent_id}")

    response = await client.post(
        "https://www.googleapis.com/upload/drive/v3/files",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        content=body.encode("utf-8"),
        params=params,
    )

    if response.status_code in (200, 201):
        file_id = response.json()["id"]
        logger.info(f"Uploaded JSON file '{filename}' with ID {file_id}")
        return file_id

    logger.error(f"Failed to upload JSON {filename}: {response.status_code} - {response.text}")
    raise Exception(f"Failed to upload JSON {filename}: {response.text}")


def _generate_summary_markdown(summary) -> str:
    """Generate markdown content for a summary."""
    lines = []

    # Get channel name safely from nested structure
    channel_name = "Summary"
    if summary.summary_result and summary.summary_result.context:
        channel_name = summary.summary_result.context.channel_name or "Summary"

    # Header
    lines.append(f"# {channel_name}")
    lines.append("")
    lines.append(f"**Date:** {summary.created_at.strftime('%Y-%m-%d')}")
    lines.append(f"**Channel:** {channel_name}")
    # message_count may be in summary_result.context
    message_count = None
    if summary.summary_result and summary.summary_result.context:
        message_count = getattr(summary.summary_result.context, 'message_count', None)
    if message_count:
        lines.append(f"**Messages:** {message_count}")
    lines.append("")

    # Summary text
    if summary.summary_result:
        lines.append("## Summary")
        lines.append("")
        lines.append(summary.summary_result.summary_text or "")
        lines.append("")

        # Key points
        if summary.summary_result.key_points:
            lines.append("## Key Points")
            lines.append("")
            for point in summary.summary_result.key_points:
                lines.append(f"- {point}")
            lines.append("")

        # Action items
        if summary.summary_result.action_items:
            lines.append("## Action Items")
            lines.append("")
            for item in summary.summary_result.action_items:
                lines.append(f"- {item}")
            lines.append("")

    lines.append("---")
    lines.append(f"*Generated by SummaryBot on {utc_now_naive().strftime('%Y-%m-%d %H:%M UTC')}*")

    return "\n".join(lines)


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
    import httpx

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

    # ADR-007.1: Prevent syncing to drive root - folder selection is required
    if not request.folder_id or request.folder_id == "root":
        raise HTTPException(
            400,
            "You must select a specific folder. Syncing to the drive root is not allowed."
        )

    # ADR-007.1: Get user email for display
    user_email = ""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens.access_token}"},
            )
            if response.status_code == 200:
                user_email = response.json().get("email", "")
    except Exception as e:
        logger.warning(f"Failed to get user email: {e}")

    # Create config with ADR-007.1 and ADR-091 fields
    config = ServerSyncConfig(
        enabled=True,
        folder_id=request.folder_id,
        folder_name=request.folder_name,
        folder_path=request.folder_path,
        drive_type=request.drive_type,
        drive_id=request.drive_id or "",
        drive_name=request.drive_name or ("My Drive" if request.drive_type == "my_drive" else ""),
        user_email=user_email,
        oauth_token_id=token_id,
        configured_by=user_id,
        configured_at=utc_now_naive(),
        sync_on_generation=request.sync_on_generation,
        include_metadata=request.include_metadata,
        # ADR-091: Export configuration
        export_filters=request.export_filters,
        include_json=request.include_json,
        folder_structure=request.folder_structure,
        period_grouping=request.period_grouping,
    )

    # Save config
    success = await service.save_server_config(server_id, config)

    if not success:
        raise HTTPException(500, "Failed to save configuration")

    return {
        "success": True,
        "server_id": server_id,
        "folder_id": request.folder_id,
        "folder_name": request.folder_name,
        "drive_type": request.drive_type,
        "user_email": user_email,
        "message": "Server sync configured successfully",
    }


class UpdateExportSettingsRequest(BaseModel):
    """ADR-091: Request to update export settings only."""
    export_filters: Optional[Dict[str, Any]] = None
    include_markdown: Optional[bool] = None
    include_json: Optional[bool] = None
    folder_structure: Optional[str] = None
    period_grouping: Optional[str] = None
    # Filter settings
    filter_scope: Optional[str] = None  # "channel" | "category" | "server" | None (all)
    filter_source: Optional[str] = None  # "scheduled" | "manual" | "realtime" | "archive" | None
    filter_granularity: Optional[str] = None  # "daily" | "weekly" | "monthly" | None


@router.patch("/sync/server/{server_id}/export-settings")
async def update_export_settings(
    server_id: str,
    request: UpdateExportSettingsRequest,
):
    """
    ADR-091: Update export settings without re-configuring OAuth.

    Allows updating filters, JSON inclusion, and folder structure
    after initial setup.
    """
    service = get_sync_service()
    config = await service.get_server_config(server_id)

    if not config or not config.enabled:
        raise HTTPException(400, "Server sync not configured")

    # Update only provided fields
    if request.export_filters is not None:
        config.export_filters = request.export_filters
    if request.include_markdown is not None:
        config.include_markdown = request.include_markdown
    if request.include_json is not None:
        config.include_json = request.include_json
    if request.folder_structure is not None:
        config.folder_structure = request.folder_structure
    if request.period_grouping is not None:
        config.period_grouping = request.period_grouping
    # Filter settings - use empty string to clear (None means don't update)
    if request.filter_scope is not None:
        config.filter_scope = request.filter_scope if request.filter_scope else None
    if request.filter_source is not None:
        config.filter_source = request.filter_source if request.filter_source else None
    if request.filter_granularity is not None:
        config.filter_granularity = request.filter_granularity if request.filter_granularity else None

    # Save updated config
    success = await service.save_server_config(server_id, config)

    if not success:
        raise HTTPException(500, "Failed to save export settings")

    return {
        "success": True,
        "server_id": server_id,
        "export_filters": config.export_filters,
        "include_markdown": config.include_markdown,
        "include_json": config.include_json,
        "folder_structure": config.folder_structure,
        "period_grouping": config.period_grouping,
        "filter_scope": config.filter_scope,
        "filter_source": config.filter_source,
        "filter_granularity": config.filter_granularity,
        "message": "Export settings updated",
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
    drive_id: Optional[str] = None,  # ADR-007.1: For shared drives
):
    """
    List folders in Google Drive for folder selection.

    Args:
        server_id: Discord server ID (to get OAuth tokens)
        parent_id: Parent folder ID (default: root)
        drive_id: Shared drive ID (optional, omit for My Drive)
    """
    oauth = get_oauth_flow()
    token_id = f"srv_{server_id}_gdrive"

    tokens = await oauth.get_valid_tokens(token_id)
    if not tokens:
        raise HTTPException(400, "No valid OAuth tokens. Please connect first.")

    try:
        import httpx

        async with httpx.AsyncClient() as client:
            # Build query params - different for shared drives
            params: Dict[str, Any] = {
                "q": f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                "fields": "files(id, name, mimeType)",
                "orderBy": "name",
                "pageSize": 100,
            }

            # ADR-007.1: Support shared drives
            if drive_id:
                params["corpora"] = "drive"
                params["driveId"] = drive_id
                params["includeItemsFromAllDrives"] = "true"
                params["supportsAllDrives"] = "true"

            response = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {tokens.access_token}"},
                params=params,
            )

            if response.status_code != 200:
                error_detail = response.text[:500] if response.text else "Unknown error"
                logger.error(f"Drive API error {response.status_code}: {error_detail}")
                raise HTTPException(response.status_code, f"Drive API error: {error_detail}")

            data = response.json()
            return {
                "parent_id": parent_id,
                "drive_id": drive_id,
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


@router.get("/oauth/google/drives")
async def list_shared_drives(server_id: str):
    """
    ADR-007.1: List available shared drives (Team Drives).

    Args:
        server_id: Discord server ID (to get OAuth tokens)
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
                "https://www.googleapis.com/drive/v3/drives",
                headers={"Authorization": f"Bearer {tokens.access_token}"},
                params={
                    "fields": "drives(id, name)",
                    "pageSize": 100,
                },
            )

            if response.status_code != 200:
                error_detail = response.text[:500] if response.text else "Unknown error"
                logger.error(f"Drive API error {response.status_code}: {error_detail}")
                raise HTTPException(response.status_code, f"Drive API error: {error_detail}")

            data = response.json()
            return {
                "drives": [
                    {"id": d["id"], "name": d["name"]}
                    for d in data.get("drives", [])
                ],
            }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error listing drives: {e}")
        raise HTTPException(500, f"Drive API error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error listing drives: {e}")
        raise HTTPException(500, f"Failed to list drives: {e}")


@router.get("/oauth/google/user")
async def get_connected_user(server_id: str):
    """
    ADR-007.1: Get connected Google account user info.

    Args:
        server_id: Discord server ID (to get OAuth tokens)
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
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens.access_token}"},
            )

            if response.status_code != 200:
                error_detail = response.text[:500] if response.text else "Unknown error"
                logger.error(f"User info API error {response.status_code}: {error_detail}")
                raise HTTPException(response.status_code, f"API error: {error_detail}")

            data = response.json()
            return {
                "email": data.get("email"),
                "name": data.get("name"),
                "picture": data.get("picture"),
            }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error getting user info: {e}")
        raise HTTPException(500, f"API error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error getting user info: {e}")
        raise HTTPException(500, f"Failed to get user info: {e}")


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
