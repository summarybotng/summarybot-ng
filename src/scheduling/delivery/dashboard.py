"""
Dashboard delivery strategy (CS-008, ADR-005).
Extended by ADR-067: Automatic Wiki Ingestion.
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import DeliveryStrategy, DeliveryResult, DeliveryContext
from ...models.summary import SummaryResult
from ...models.stored_summary import StoredSummary, SummarySource
from ...models.task import Destination
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# ADR-067: Retry configuration for wiki ingestion
WIKI_INGEST_MAX_RETRIES = 3
WIKI_INGEST_BASE_DELAY = 1.0  # seconds
WIKI_INGEST_MAX_DELAY = 30.0  # seconds
WIKI_INGEST_JITTER = 0.5  # randomization factor


class DashboardDeliveryStrategy(DeliveryStrategy):
    """Strategy for storing summaries in dashboard (ADR-005).

    Stores the summary in the database for viewing in the dashboard UI.
    Users can later push this summary to Discord channels on demand.
    """

    @property
    def destination_type(self) -> str:
        return "dashboard"

    async def deliver(
        self,
        summary: SummaryResult,
        destination: Destination,
        context: DeliveryContext,
    ) -> DeliveryResult:
        """Store summary in dashboard for viewing.

        Args:
            summary: Summary result to store
            destination: Dashboard destination configuration
            context: Delivery context with task info

        Returns:
            Delivery result with stored summary ID
        """
        try:
            from ...data.repositories import get_stored_summary_repository

            # Get channels that actually had content vs requested scope
            scope_channel_ids = context.get_all_channel_ids()
            channels_with_content = (
                summary.metadata.get("channels_with_content", scope_channel_ids)
                if summary.metadata else scope_channel_ids
            )

            # Build channel names from channels WITH CONTENT only
            channel_names = self._get_channel_names(context, channels_with_content)

            # Generate smart title based on scope and content
            title = self._generate_title(
                summary=summary,
                scope_channel_ids=scope_channel_ids,
                channel_names=channel_names,
                context=context,
            )

            # ADR-087: Extract continuity metadata if present
            continuity_week_number = None
            previous_summary_id = None
            archive_granularity = None
            if summary.metadata:
                continuity_week_number = summary.metadata.get("continuity_week_number")
                previous_summary_id = summary.metadata.get("previous_summary_id")
                archive_granularity = summary.metadata.get("archive_granularity")

            # Create stored summary with SCHEDULED source
            # Use the SummaryResult's ID to ensure job.summary_id matches stored summary
            stored_summary = StoredSummary(
                id=summary.id,  # Use SummaryResult ID for consistency with job tracking
                guild_id=context.guild_id,
                source_channel_ids=scope_channel_ids,  # Store full scope for reference
                schedule_id=context.scheduled_task.id if context.scheduled_task else None,
                summary_result=summary,
                title=title,
                source=SummarySource.SCHEDULED,
                # ADR-087: Weekly continuity tracking
                previous_summary_id=previous_summary_id,
                continuity_week_number=continuity_week_number,
                archive_granularity=archive_granularity,
            )

            # Persist to database
            stored_summary_repo = await get_stored_summary_repository()
            await stored_summary_repo.save(stored_summary)

            logger.info(f"Stored summary {stored_summary.id} in dashboard for guild {context.guild_id}")

            # ADR-067: Trigger wiki ingestion in background (non-blocking)
            asyncio.create_task(
                self._trigger_wiki_ingestion(stored_summary, stored_summary_repo, context)
            )

            return DeliveryResult(
                destination_type=self.destination_type,
                target="dashboard",
                success=True,
                details={
                    "message": "Stored in dashboard",
                    "summary_id": stored_summary.id,
                    "title": title,
                },
            )

        except Exception as e:
            logger.exception(f"Failed to store summary in dashboard: {e}")
            return DeliveryResult(
                destination_type=self.destination_type,
                target="dashboard",
                success=False,
                error=str(e),
            )

    def _get_channel_names(
        self,
        context: DeliveryContext,
        channel_ids: List[str],
    ) -> List[str]:
        """Get channel names from Discord client."""
        channel_names = []
        if context.discord_client:
            for channel_id in channel_ids:
                try:
                    channel = context.discord_client.get_channel(int(channel_id))
                    if channel:
                        channel_names.append(f"#{channel.name}")
                    else:
                        channel_names.append(f"Channel {channel_id}")
                except Exception:
                    channel_names.append(f"Channel {channel_id}")
        else:
            channel_names = [f"Channel {cid}" for cid in channel_ids]
        return channel_names

    async def _trigger_wiki_ingestion(
        self,
        summary: StoredSummary,
        stored_summary_repo: Any,
        context: DeliveryContext,
    ) -> None:
        """ADR-067: Trigger wiki ingestion for newly stored summary.

        Runs in background to avoid blocking summary delivery.
        Uses exponential backoff with jitter for retries.
        """
        try:
            from ...data.repositories import get_wiki_repository, get_repository_factory

            # Check wiki ingestion settings for this guild
            # ADR-090: Two separate switches for page vs vector ingestion
            auto_ingest_enabled = True  # Pages (default: enabled)
            ingest_to_vectors = False   # Vectors (default: disabled)
            try:
                factory = get_repository_factory()
                conn = await factory.get_connection()
                row = await conn.fetch_one(
                    "SELECT wiki_auto_ingest, wiki_ingest_to_vectors FROM guild_configs WHERE guild_id = ?",
                    (summary.guild_id,)
                )
                if row:
                    if row.get('wiki_auto_ingest') is not None:
                        auto_ingest_enabled = bool(row['wiki_auto_ingest'])
                    if row.get('wiki_ingest_to_vectors') is not None:
                        ingest_to_vectors = bool(row['wiki_ingest_to_vectors'])
            except Exception as e:
                # Columns may not exist yet, use defaults
                logger.debug(f"Could not check wiki ingestion settings: {e}")

            if not auto_ingest_enabled:
                logger.debug(f"Wiki auto-ingest disabled for guild {summary.guild_id}")
                return

            # ADR-080: Check perspective filtering
            allowed_perspectives = ["general"]  # Default: only general
            try:
                factory = get_repository_factory()
                conn = await factory.get_connection()
                persp_row = await conn.fetch_one(
                    "SELECT wiki_allowed_perspectives FROM guild_configs WHERE guild_id = ?",
                    (summary.guild_id,)
                )
                if persp_row and persp_row.get('wiki_allowed_perspectives'):
                    import json
                    allowed_perspectives = json.loads(persp_row['wiki_allowed_perspectives'])
            except Exception as e:
                # Column may not exist yet, default to ["general"]
                logger.debug(f"Could not check wiki_allowed_perspectives: {e}")

            # Get summary's perspective from metadata
            summary_perspective = "general"  # Default perspective
            result = summary.summary_result
            if result and result.metadata and result.metadata.get('perspective'):
                summary_perspective = result.metadata['perspective']

            # Skip if perspective not in allowed list
            if summary_perspective not in allowed_perspectives:
                logger.info(
                    f"Skipping wiki ingest for summary {summary.id}: "
                    f"perspective '{summary_perspective}' not in allowed list {allowed_perspectives}"
                )
                return

            # Get wiki repository
            wiki_repo = await get_wiki_repository()
            if not wiki_repo:
                logger.warning("Wiki repository not available, skipping ingestion")
                return

            # Get summary result
            result = summary.summary_result
            if not result:
                logger.debug(f"No summary result for {summary.id}, skipping wiki ingestion")
                return

            # ADR-057 Phase 4: Use factory to get agent with optional RuVector dual-write
            # ADR-090: Controlled by wiki_ingest_to_vectors setting
            from ...wiki.agents import create_ingest_agent

            agent = await create_ingest_agent(wiki_repo, enable_ruvector=ingest_to_vectors)

            # Get platform from context
            platform = 'discord'
            if context.scheduled_task and hasattr(context.scheduled_task, 'platform'):
                platform = context.scheduled_task.platform or 'discord'

            # Run ingestion with retry logic
            last_error = None
            for attempt in range(WIKI_INGEST_MAX_RETRIES):
                try:
                    ingest_result = await agent.ingest_summary(
                        guild_id=summary.guild_id,
                        summary_id=summary.id,
                        summary_text=result.summary_text or "",
                        key_points=result.key_points or [],
                        action_items=[a.description for a in (result.action_items or [])],
                        participants=[p.display_name for p in (result.participants or [])],
                        technical_terms=[t.term for t in (result.technical_terms or [])],
                        channel_name=summary.title or "Unknown",
                        timestamp=summary.created_at,
                        platform=platform,
                    )

                    # Mark as ingested on success
                    await stored_summary_repo.mark_wiki_ingested(summary.id)
                    logger.info(f"Wiki ingested summary {summary.id} (attempt {attempt + 1})")

                    # ADR-076: Trigger auto-synthesis if enabled
                    await self._trigger_wiki_synthesis_if_enabled(
                        guild_id=summary.guild_id,
                        ingest_result=ingest_result,
                        wiki_repo=wiki_repo,
                    )
                    return  # Success - exit retry loop

                except Exception as e:
                    last_error = e
                    if attempt < WIKI_INGEST_MAX_RETRIES - 1:
                        # Calculate delay with exponential backoff and jitter
                        delay = min(
                            WIKI_INGEST_BASE_DELAY * (2 ** attempt),
                            WIKI_INGEST_MAX_DELAY
                        )
                        jitter = delay * WIKI_INGEST_JITTER * random.random()
                        wait_time = delay + jitter

                        logger.warning(
                            f"Wiki ingestion attempt {attempt + 1} failed for {summary.id}: {e}. "
                            f"Retrying in {wait_time:.1f}s"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"Wiki ingestion failed for {summary.id} after {WIKI_INGEST_MAX_RETRIES} attempts: {e}"
                        )

        except ImportError as e:
            # Wiki module not available - that's OK
            logger.debug(f"Wiki module not available for auto-ingest: {e}")
        except Exception as e:
            # Don't fail summary delivery if wiki ingestion fails
            logger.warning(f"Wiki ingestion setup failed for {summary.id}: {e}")

    async def _trigger_wiki_synthesis_if_enabled(
        self,
        guild_id: str,
        ingest_result: Any,
        wiki_repo: Any,
    ) -> None:
        """ADR-076: Trigger wiki synthesis for updated pages if auto-synthesis is enabled."""
        try:
            from ...data.repositories import get_repository_factory

            # Check if auto-synthesis is enabled for this guild (default: enabled)
            auto_synthesis_enabled = True
            try:
                factory = get_repository_factory()
                conn = await factory.get_connection()
                row = await conn.fetch_one(
                    "SELECT wiki_auto_synthesis FROM guild_configs WHERE guild_id = ?",
                    (guild_id,)
                )
                if row and row.get('wiki_auto_synthesis') is not None:
                    auto_synthesis_enabled = bool(row['wiki_auto_synthesis'])
            except Exception as e:
                # Column may not exist yet, default to enabled
                logger.debug(f"Could not check wiki_auto_synthesis setting: {e}")

            if not auto_synthesis_enabled:
                logger.debug(f"Wiki auto-synthesis disabled for guild {guild_id}")
                return

            # Get pages that were updated/created
            affected_pages = (ingest_result.pages_updated or []) + (ingest_result.pages_created or [])
            if not affected_pages:
                return

            # Import synthesis module
            from ...wiki.synthesis import synthesize_wiki_page

            # Get Claude client for synthesis
            claude_client = None
            try:
                from ...summarization.claude_client import get_claude_client
                claude_client = await get_claude_client()
            except Exception:
                logger.debug("Claude client not available for wiki synthesis")

            # Synthesize each affected page
            for page_path in affected_pages[:5]:  # Limit to 5 pages per ingest
                try:
                    page = await wiki_repo.get_page(guild_id, page_path)
                    if not page:
                        continue

                    result = await synthesize_wiki_page(
                        page_title=page.title,
                        page_content=page.content,
                        source_refs=page.source_refs or [],
                        claude_client=claude_client,
                    )

                    # Update page with synthesis
                    page.synthesis = result.synthesis
                    page.synthesis_source_count = result.source_count
                    page.confidence = result.confidence
                    await wiki_repo.save_page(page)

                    logger.debug(f"Auto-synthesized wiki page {page_path}")

                except Exception as e:
                    logger.warning(f"Failed to auto-synthesize page {page_path}: {e}")

            logger.info(f"Auto-synthesized {len(affected_pages)} wiki pages for guild {guild_id}")

        except Exception as e:
            # Don't fail if synthesis fails
            logger.warning(f"Wiki auto-synthesis failed for guild {guild_id}: {e}")

    def _generate_title(
        self,
        summary: SummaryResult,
        scope_channel_ids: List[str],
        channel_names: List[str],
        context: DeliveryContext,
    ) -> str:
        """Generate smart title based on scope and content."""
        timestamp = utc_now_naive().strftime('%b %d, %H:%M')
        scope_type = summary.metadata.get("scope_type") if summary.metadata else None

        # Get platform for title prefix (all platforms get a prefix)
        platform = getattr(context.scheduled_task, 'platform', 'discord') if context.scheduled_task else 'discord'
        platform_display = {
            "discord": "Discord",
            "whatsapp": "WhatsApp",
            "slack": "Slack",
            "telegram": "Telegram",
        }.get(platform.lower() if platform else "discord", platform.title() if platform else "Discord")
        platform_prefix = f"{platform_display}: "

        if scope_type == "guild" or len(scope_channel_ids) > 10:
            # Server-wide summary - use count instead of listing all
            if len(channel_names) > 3:
                title = f"{platform_prefix}Server Summary ({len(channel_names)} channels) — {timestamp}"
            elif channel_names:
                title = f"{platform_prefix}{', '.join(channel_names)} — {timestamp}"
            else:
                title = f"{platform_prefix}Server Summary — {timestamp}"

        elif scope_type == "category":
            # Category summary
            category_name = None
            if context.scheduled_task:
                category_name = getattr(context.scheduled_task, 'category_name', None)

            if category_name:
                title = f"{platform_prefix}📁 {category_name} ({len(channel_names)} channels) — {timestamp}"
            elif len(channel_names) > 3:
                title = f"{platform_prefix}Category Summary ({len(channel_names)} channels) — {timestamp}"
            else:
                title = f"{platform_prefix}{', '.join(channel_names)} — {timestamp}"

        else:
            # Channel-specific summary
            if len(channel_names) > 5:
                title = f"{platform_prefix}{', '.join(channel_names[:3])} +{len(channel_names)-3} more — {timestamp}"
            elif channel_names:
                title = f"{platform_prefix}{', '.join(channel_names)} — {timestamp}"
            else:
                title = f"{platform_prefix}Summary — {timestamp}"

        return title
