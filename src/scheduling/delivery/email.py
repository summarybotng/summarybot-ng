"""
Email delivery strategy (CS-008, ADR-030).
"""

import logging
from typing import Any, Dict

from .base import DeliveryStrategy, DeliveryResult, DeliveryContext
from ...models.summary import SummaryResult
from ...models.task import Destination, SummaryScope

logger = logging.getLogger(__name__)


class EmailDeliveryStrategy(DeliveryStrategy):
    """Strategy for delivering summaries via email."""

    @property
    def destination_type(self) -> str:
        return "email"

    async def deliver(
        self,
        summary: SummaryResult,
        destination: Destination,
        context: DeliveryContext,
    ) -> DeliveryResult:
        """Deliver summary via email (ADR-030).

        Args:
            summary: Summary to deliver
            destination: Email destination with recipients
            context: Delivery context with task info

        Returns:
            Delivery result
        """
        from ...services.email_delivery import get_email_service, EmailContext

        try:
            service = get_email_service()
            if not service.is_configured():
                logger.warning("Email delivery requested but SMTP not configured")
                return DeliveryResult(
                    destination_type=self.destination_type,
                    target=destination.target,
                    success=False,
                    error="SMTP not configured. Set SMTP_ENABLED=true and configure SMTP_* env vars.",
                )

            # Parse recipients from target
            recipients = service.parse_recipients(destination.target)
            if not recipients:
                return DeliveryResult(
                    destination_type=self.destination_type,
                    target=destination.target,
                    success=False,
                    error="No valid email addresses in destination",
                )

            # Build channel names from context
            channel_names = self._get_channel_names(context)

            # Determine scope
            is_server_wide = False
            category_name = None
            if context.scheduled_task and context.scheduled_task.scope:
                scope = context.scheduled_task.scope
                if scope == SummaryScope.GUILD:
                    is_server_wide = True
                elif scope == SummaryScope.CATEGORY:
                    category_name = getattr(context.scheduled_task, 'category_name', None)

            email_context = EmailContext(
                guild_name=f"Guild {context.guild_id}",
                channel_names=channel_names,
                category_name=category_name,
                is_server_wide=is_server_wide,
                start_time=summary.start_time,
                end_time=summary.end_time,
                message_count=summary.message_count,
                participant_count=len(summary.participants) if summary.participants else 0,
                schedule_name=context.scheduled_task.name if context.scheduled_task else None,
            )

            # Send email
            result = await service.send_summary(
                summary=summary,
                recipients=recipients,
                context=email_context,
                guild_id=context.guild_id,
            )

            if result.success:
                logger.info(f"Email delivered to {len(result.recipients_sent)} recipient(s)")
                return DeliveryResult(
                    destination_type=self.destination_type,
                    target=destination.target,
                    success=True,
                    details={
                        "message": f"Sent to {len(result.recipients_sent)} recipient(s)",
                        "recipients_sent": result.recipients_sent,
                        "recipients_failed": result.recipients_failed,
                    },
                )
            else:
                return DeliveryResult(
                    destination_type=self.destination_type,
                    target=destination.target,
                    success=False,
                    error=result.error or "Unknown error",
                )

        except Exception as e:
            logger.exception(f"Failed to deliver email: {e}")
            return DeliveryResult(
                destination_type=self.destination_type,
                target=destination.target,
                success=False,
                error=str(e),
            )

    def _get_channel_names(self, context: DeliveryContext) -> list:
        """Get channel names from context."""
        channel_names = []
        if context.discord_client:
            for channel_id in context.get_all_channel_ids()[:5]:
                try:
                    channel = context.discord_client.get_channel(int(channel_id))
                    if channel:
                        channel_names.append(channel.name)
                except Exception:
                    pass
        return channel_names
