"""
Confluence delivery strategy (CS-008, ADR-099).

Automatically publishes scheduled summaries to Confluence.
"""

import logging
from typing import Any, Dict, List

from .base import DeliveryStrategy, DeliveryResult, DeliveryContext
from ...models.summary import SummaryResult
from ...models.task import Destination

logger = logging.getLogger(__name__)


class ConfluenceDeliveryStrategy(DeliveryStrategy):
    """Strategy for publishing summaries to Confluence (ADR-099).

    Publishes the summary as a Confluence page using the guild's
    configured Confluence settings.
    """

    @property
    def destination_type(self) -> str:
        return "confluence"

    async def deliver(
        self,
        summary: SummaryResult,
        destination: Destination,
        context: DeliveryContext,
    ) -> DeliveryResult:
        """Publish summary to Confluence.

        Args:
            summary: Summary result to publish
            destination: Confluence destination configuration
            context: Delivery context with task info

        Returns:
            Delivery result with page URL
        """
        try:
            from ...services.confluence import get_confluence_service_for_guild
            from ...data.repositories import get_confluence_repository
            from ...data.sqlite.confluence_repository import ConfluencePublication
            from src.utils.time import utc_now_naive

            # Get Confluence service for this guild
            confluence_service = await get_confluence_service_for_guild(context.guild_id)
            if not confluence_service.is_configured():
                logger.warning(f"Confluence not configured for guild {context.guild_id}")
                return DeliveryResult(
                    destination_type=self.destination_type,
                    target="confluence",
                    success=False,
                    error="Confluence not configured for this guild",
                )

            # Generate title from context
            title = self._generate_title(summary, context)

            # Get channel names for content and labels (ADR-100)
            channel_names = self._get_channel_names(context)

            # Get scope type and category name for labels
            scope_type = None
            category_name = None
            if context.scheduled_task:
                scope = getattr(context.scheduled_task, 'scope', None)
                if scope:
                    scope_type = scope.value if hasattr(scope, 'value') else str(scope)
                category_name = getattr(context.scheduled_task, 'category_name', None)

            # Get summary metadata from scheduled task
            summary_type = None
            perspective = None
            if context.scheduled_task:
                summary_type = getattr(context.scheduled_task, 'summary_type', None)
                perspective = getattr(context.scheduled_task, 'perspective', None)

            # ADR-102: Publish to Confluence using correct API
            # The publish_summary method takes the full SummaryResult, not formatted content
            result = await confluence_service.publish_summary(
                summary=summary,
                title=title,
                summary_id=summary.id,
                guild_id=context.guild_id,
                channel_names=channel_names,
                scope_type=scope_type,
                category_name=category_name,
                # ADR-114: Additional metadata for Page Properties
                summary_type=summary_type,
                perspective=perspective,
                source="scheduled",
            )

            # ADR-102: Handle result as ConfluencePublishResult dataclass, not dict
            if not result.success:
                error_msg = result.error or "Unknown error"
                if result.conflict:
                    error_msg = f"Conflict: {error_msg}"
                logger.warning(
                    f"ADR-102: Confluence delivery failed for summary {summary.id}: {error_msg}"
                )
                return DeliveryResult(
                    destination_type=self.destination_type,
                    target="confluence",
                    success=False,
                    error=error_msg,
                )

            # Store publication record
            confluence_repo = await get_confluence_repository()
            if confluence_repo:
                publication = ConfluencePublication(
                    guild_id=context.guild_id,
                    summary_id=summary.id,
                    page_id=result.page_id,
                    page_url=result.page_url,
                    page_version=result.page_version or 1,
                    published_at=utc_now_naive(),
                )
                await confluence_repo.save(publication)

            logger.info(
                f"Published summary {summary.id} to Confluence: {result.page_url}"
            )

            return DeliveryResult(
                destination_type=self.destination_type,
                target=result.page_url or "confluence",
                success=True,
                details={
                    "message": "Published to Confluence",
                    "page_id": result.page_id,
                    "page_url": result.page_url,
                    "version": result.page_version or 1,
                },
            )

        except ImportError as e:
            logger.error(f"Confluence module not available: {e}")
            return DeliveryResult(
                destination_type=self.destination_type,
                target="confluence",
                success=False,
                error="Confluence module not available",
            )
        except Exception as e:
            logger.exception(f"Failed to publish summary to Confluence: {e}")
            return DeliveryResult(
                destination_type=self.destination_type,
                target="confluence",
                success=False,
                error=str(e),
            )

    def _generate_title(self, summary: SummaryResult, context: DeliveryContext) -> str:
        """Generate page title for Confluence."""
        from src.utils.time import utc_now_naive
        from datetime import timedelta

        now = utc_now_naive()

        # Check for custom title template
        title_template = getattr(context.scheduled_task, 'title_template', None) if context.scheduled_task else None
        if title_template:
            schedule_name = context.scheduled_task.name if context.scheduled_task else "Summary"
            rolling_period = getattr(context.scheduled_task, 'rolling_period', None) if context.scheduled_task else None

            # Calculate period string for rolling summaries
            if rolling_period == 'weekly':
                week_start = now - timedelta(days=now.weekday())
                period_str = f"Week of {week_start.strftime('%b %d')}"
            elif rolling_period == 'biweekly':
                week_start = now - timedelta(days=now.weekday())
                period_str = f"Biweek of {week_start.strftime('%b %d')}"
            elif rolling_period == 'monthly':
                period_str = now.strftime('%B %Y')
            else:
                period_str = now.strftime('%b %d')

            # Get channel names
            channel_names = self._get_channel_names(context)
            if len(channel_names) > 5:
                channels_str = f"{', '.join(channel_names[:3])} +{len(channel_names)-3} more"
            else:
                channels_str = ', '.join(channel_names) if channel_names else "Summary"

            # Get platform
            platform = getattr(context.scheduled_task, 'platform', 'discord') if context.scheduled_task else 'discord'
            platform_display = {
                "discord": "Discord",
                "whatsapp": "WhatsApp",
                "slack": "Slack",
            }.get(platform.lower() if platform else "discord", "Discord")

            # Apply substitutions
            result = title_template
            result = result.replace('{date}', now.strftime('%b %d, %Y'))
            result = result.replace('{time}', now.strftime('%H:%M'))
            result = result.replace('{datetime}', now.strftime('%b %d, %H:%M'))
            result = result.replace('{channels}', channels_str)
            result = result.replace('{channel_count}', str(len(channel_names)))
            result = result.replace('{platform}', platform_display)
            result = result.replace('{schedule}', schedule_name)
            result = result.replace('{period}', period_str)
            result = result.replace('{weekday}', now.strftime('%A'))
            return result

        # Default title
        timestamp = now.strftime('%Y-%m-%d %H:%M')
        schedule_name = context.scheduled_task.name if context.scheduled_task else "Summary"
        return f"{schedule_name} - {timestamp}"

    def _get_channel_names(self, context: DeliveryContext) -> List[str]:
        """Get channel names from context."""
        channel_ids = context.get_all_channel_ids()
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
