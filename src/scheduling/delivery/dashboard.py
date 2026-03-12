"""
Dashboard delivery strategy (CS-008, ADR-005).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import DeliveryStrategy, DeliveryResult, DeliveryContext
from ...models.summary import SummaryResult
from ...models.stored_summary import StoredSummary, SummarySource
from ...models.task import Destination
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


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

            # Create stored summary with SCHEDULED source
            stored_summary = StoredSummary(
                guild_id=context.guild_id,
                source_channel_ids=scope_channel_ids,  # Store full scope for reference
                schedule_id=context.scheduled_task.id if context.scheduled_task else None,
                summary_result=summary,
                title=title,
                source=SummarySource.SCHEDULED,
            )

            # Persist to database
            stored_summary_repo = await get_stored_summary_repository()
            await stored_summary_repo.save(stored_summary)

            logger.info(f"Stored summary {stored_summary.id} in dashboard for guild {context.guild_id}")

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

        if scope_type == "guild" or len(scope_channel_ids) > 10:
            # Server-wide summary - use count instead of listing all
            if len(channel_names) > 3:
                title = f"Server Summary ({len(channel_names)} channels) — {timestamp}"
            elif channel_names:
                title = f"{', '.join(channel_names)} — {timestamp}"
            else:
                title = f"Server Summary — {timestamp}"

        elif scope_type == "category":
            # Category summary
            category_name = None
            if context.scheduled_task:
                category_name = getattr(context.scheduled_task, 'category_name', None)

            if category_name:
                title = f"📁 {category_name} ({len(channel_names)} channels) — {timestamp}"
            elif len(channel_names) > 3:
                title = f"Category Summary ({len(channel_names)} channels) — {timestamp}"
            else:
                title = f"{', '.join(channel_names)} — {timestamp}"

        else:
            # Channel-specific summary
            if len(channel_names) > 5:
                title = f"{', '.join(channel_names[:3])} +{len(channel_names)-3} more — {timestamp}"
            elif channel_names:
                title = f"{', '.join(channel_names)} — {timestamp}"
            else:
                title = f"Summary — {timestamp}"

        return title
