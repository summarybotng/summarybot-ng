"""
Discord DM delivery strategy (ADR-047).

Delivers summaries directly to a Discord user via Direct Message.
"""

import logging
from typing import Any

import discord

from .base import DeliveryStrategy, DeliveryResult, DeliveryContext
from ...models.summary import SummaryResult
from ...models.task import Destination

logger = logging.getLogger(__name__)


class DiscordDMDeliveryStrategy(DeliveryStrategy):
    """Strategy for delivering summaries via Discord Direct Message.

    The target should be a Discord user ID. The bot will attempt to send
    a DM to that user with the summary.

    Formats supported:
    - embed: Discord rich embed (default)
    - markdown: Plain markdown text
    """

    @property
    def destination_type(self) -> str:
        return "discord_dm"

    async def deliver(
        self,
        summary: SummaryResult,
        destination: Destination,
        context: DeliveryContext,
    ) -> DeliveryResult:
        """Deliver summary via Discord DM to a user.

        Args:
            summary: Summary to deliver
            destination: DM destination with user ID as target
            context: Delivery context

        Returns:
            Delivery result
        """
        user_id = destination.target
        format_type = destination.format

        if not context.discord_client:
            return DeliveryResult(
                destination_type=self.destination_type,
                target=user_id,
                success=False,
                error="Discord client not available",
            )

        try:
            # Fetch the user
            user = context.discord_client.get_user(int(user_id))
            if not user:
                user = await context.discord_client.fetch_user(int(user_id))

            if not user:
                return DeliveryResult(
                    destination_type=self.destination_type,
                    target=user_id,
                    success=False,
                    error=f"User {user_id} not found",
                )

            # Create DM channel if needed
            dm_channel = user.dm_channel
            if not dm_channel:
                dm_channel = await user.create_dm()

            # Deliver based on format
            if format_type == "embed":
                embed_dict = summary.to_embed_dict()
                embed = discord.Embed.from_dict(embed_dict)
                message = await dm_channel.send(embed=embed)

            elif format_type == "markdown":
                markdown = summary.to_markdown()
                # Split if too long
                if len(markdown) > 2000:
                    chunks = [markdown[i:i+2000] for i in range(0, len(markdown), 2000)]
                    for chunk in chunks:
                        message = await dm_channel.send(chunk)
                else:
                    message = await dm_channel.send(markdown)

            else:
                # Default to simple text
                message = await dm_channel.send(f"Summary generated: {summary.summary_text[:1900]}...")

            logger.info(f"Delivered summary via DM to user {user_id}")

            return DeliveryResult(
                destination_type=self.destination_type,
                target=user_id,
                success=True,
                message_id=str(message.id),
                details={"message": "Delivered via DM successfully", "user_name": str(user)},
            )

        except discord.Forbidden as e:
            # User has DMs disabled or bot is blocked
            logger.warning(f"Cannot send DM to user {user_id}: {e}")
            return DeliveryResult(
                destination_type=self.destination_type,
                target=user_id,
                success=False,
                error="User has DMs disabled or has blocked the bot",
            )

        except discord.NotFound:
            logger.warning(f"User {user_id} not found")
            return DeliveryResult(
                destination_type=self.destination_type,
                target=user_id,
                success=False,
                error=f"User {user_id} not found",
            )

        except Exception as e:
            logger.exception(f"Failed to deliver DM to user {user_id}: {e}")
            return DeliveryResult(
                destination_type=self.destination_type,
                target=user_id,
                success=False,
                error=str(e),
            )
