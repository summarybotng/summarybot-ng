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

            # Convert summary to Confluence content
            content = self._format_for_confluence(summary)

            # Get parent page from settings
            parent_page_id = None
            try:
                repo = await get_confluence_repository()
                if repo:
                    settings = await repo.get_settings(context.guild_id)
                    if settings:
                        parent_page_id = settings.parent_page_id
            except Exception as e:
                logger.warning(f"Could not get Confluence settings: {e}")

            # Publish to Confluence
            result = await confluence_service.publish_summary(
                title=title,
                content=content,
                summary_id=summary.id,
                parent_page_id=parent_page_id,
            )

            if not result.get("success"):
                return DeliveryResult(
                    destination_type=self.destination_type,
                    target="confluence",
                    success=False,
                    error=result.get("error", "Unknown error"),
                )

            # Store publication record
            confluence_repo = await get_confluence_repository()
            if confluence_repo:
                publication = ConfluencePublication(
                    guild_id=context.guild_id,
                    summary_id=summary.id,
                    page_id=result["page_id"],
                    page_url=result["page_url"],
                    page_version=result.get("version", 1),
                    published_at=utc_now_naive(),
                )
                await confluence_repo.save(publication)

            logger.info(
                f"Published summary {summary.id} to Confluence: {result['page_url']}"
            )

            return DeliveryResult(
                destination_type=self.destination_type,
                target=result["page_url"],
                success=True,
                details={
                    "message": "Published to Confluence",
                    "page_id": result["page_id"],
                    "page_url": result["page_url"],
                    "version": result.get("version", 1),
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

    def _format_for_confluence(self, summary: SummaryResult) -> str:
        """Format summary content for Confluence (ADF/wiki markup).

        Returns HTML-like content that Confluence can render.
        """
        parts = []

        # Summary text
        if summary.summary_text:
            parts.append(f"<h2>Summary</h2>\n{summary.summary_text}")

        # Key points
        if summary.key_points:
            points_html = "\n".join(f"<li>{point}</li>" for point in summary.key_points)
            parts.append(f"<h2>Key Points</h2>\n<ul>{points_html}</ul>")

        # Action items
        if summary.action_items:
            items_html = "\n".join(
                f"<li><strong>{item.assignee or 'Unassigned'}</strong>: {item.description}</li>"
                for item in summary.action_items
            )
            parts.append(f"<h2>Action Items</h2>\n<ul>{items_html}</ul>")

        # Participants
        if summary.participants:
            participants_list = ", ".join(p.display_name for p in summary.participants)
            parts.append(f"<h2>Participants</h2>\n<p>{participants_list}</p>")

        # Technical terms
        if summary.technical_terms:
            terms_html = "\n".join(
                f"<li><strong>{term.term}</strong>: {term.definition or 'No definition'}</li>"
                for term in summary.technical_terms
            )
            parts.append(f"<h2>Technical Terms</h2>\n<ul>{terms_html}</ul>")

        return "\n\n".join(parts) if parts else "<p>No content available.</p>"
