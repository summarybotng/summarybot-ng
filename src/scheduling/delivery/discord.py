"""
Discord delivery strategy (CS-008, ADR-014).
"""

import logging
from typing import Any, Dict, Optional

import discord

from .base import DeliveryStrategy, DeliveryResult, DeliveryContext
from ...models.summary import SummaryResult
from ...models.task import Destination, SummaryScope

logger = logging.getLogger(__name__)


class DiscordDeliveryStrategy(DeliveryStrategy):
    """Strategy for delivering summaries to Discord channels.

    Supports multiple formats:
    - embed: Discord rich embed
    - markdown: Markdown text
    - template: ADR-014 template-based with thread support
    - thread: Alias for template
    """

    @property
    def destination_type(self) -> str:
        return "discord_channel"

    async def deliver(
        self,
        summary: SummaryResult,
        destination: Destination,
        context: DeliveryContext,
    ) -> DeliveryResult:
        """Deliver summary to Discord channel.

        Args:
            summary: Summary to deliver
            destination: Discord destination with channel ID
            context: Delivery context

        Returns:
            Delivery result
        """
        channel_id = destination.target
        format_type = destination.format

        if not context.discord_client:
            return DeliveryResult(
                destination_type=self.destination_type,
                target=channel_id,
                success=False,
                error="Discord client not available",
            )

        try:
            channel = context.discord_client.get_channel(int(channel_id))
            if not channel:
                channel = await context.discord_client.fetch_channel(int(channel_id))

            # ADR-014: Template-based delivery with thread support
            if format_type in ("template", "thread"):
                return await self._deliver_with_template(
                    summary=summary,
                    channel=channel,
                    context=context,
                )

            elif format_type == "embed":
                embed_dict = summary.to_embed_dict()
                embed = discord.Embed.from_dict(embed_dict)
                await channel.send(embed=embed)

            elif format_type == "markdown":
                markdown = summary.to_markdown()
                # Split if too long
                if len(markdown) > 2000:
                    chunks = [markdown[i:i+2000] for i in range(0, len(markdown), 2000)]
                    for chunk in chunks:
                        await channel.send(chunk)
                else:
                    await channel.send(markdown)

            else:
                await channel.send(f"Summary generated: {summary.summary_text[:500]}...")

            return DeliveryResult(
                destination_type=self.destination_type,
                target=channel_id,
                success=True,
                details={"message": "Delivered successfully"},
            )

        except Exception as e:
            logger.exception(f"Failed to deliver to Discord channel {channel_id}: {e}")
            return DeliveryResult(
                destination_type=self.destination_type,
                target=channel_id,
                success=False,
                error=str(e),
            )

    async def _deliver_with_template(
        self,
        summary: SummaryResult,
        channel: discord.TextChannel,
        context: DeliveryContext,
    ) -> DeliveryResult:
        """Deliver summary using ADR-014 template-based formatting with threads.

        Args:
            summary: Summary to deliver
            channel: Discord channel
            context: Delivery context

        Returns:
            Delivery result with thread info
        """
        from ...services.push_message_builder import send_with_template, PushContext
        from ...data.push_template_repository import get_push_template_repository

        try:
            # Get guild-specific template (or default)
            guild_id = str(channel.guild.id) if channel.guild else None
            if guild_id:
                repo = await get_push_template_repository()
                template = await repo.get_template(guild_id)
            else:
                from ...models.push_template import DEFAULT_PUSH_TEMPLATE
                template = DEFAULT_PUSH_TEMPLATE

            # Build push context from task and summary
            push_context = PushContext(
                guild_id=guild_id or "",
                start_time=summary.start_time,
                end_time=summary.end_time,
                message_count=summary.message_count,
                participant_count=len(summary.participants) if summary.participants else 0,
            )

            # Extract channel names from context
            channel_ids = context.get_all_channel_ids()
            channel_names = []
            for cid in channel_ids[:5]:  # Limit to first 5
                try:
                    ch = context.discord_client.get_channel(int(cid))
                    if ch:
                        channel_names.append(ch.name)
                except Exception:
                    pass
            push_context.channel_names = channel_names if channel_names else [channel.name]

            # Check scope for server-wide or category summaries
            if context.scheduled_task and context.scheduled_task.scope:
                scope = context.scheduled_task.scope
                if scope == SummaryScope.GUILD:
                    push_context.is_server_wide = True
                elif scope == SummaryScope.CATEGORY:
                    push_context.category_name = getattr(context.scheduled_task, 'category_name', None)

            # Send with template (handles thread creation)
            result = await send_with_template(
                channel=channel,
                summary=summary,
                context=push_context,
                template=template,
                discord_client=context.discord_client,
            )

            logger.info(
                f"Delivered summary to channel {channel.id} with template "
                f"(thread_created={result.get('thread_created', False)})"
            )

            return DeliveryResult(
                destination_type=self.destination_type,
                target=str(channel.id),
                success=result.get("success", False),
                error=None if result.get("success") else result.get("error"),
                details={
                    "message": "Delivered with template" if result.get("success") else result.get("error"),
                    "thread_created": result.get("thread_created", False),
                    "thread_id": result.get("thread_id"),
                    "message_ids": result.get("message_ids", []),
                },
            )

        except Exception as e:
            logger.exception(f"Failed to deliver with template to channel {channel.id}: {e}")
            return DeliveryResult(
                destination_type=self.destination_type,
                target=str(channel.id),
                success=False,
                error=str(e),
            )
