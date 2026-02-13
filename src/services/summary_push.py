"""
Summary Push Service for ADR-005: Summary Delivery Destinations.

This service handles pushing stored summaries to Discord channels on demand.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

import discord

from ..models.stored_summary import StoredSummary
from ..models.summary import SummaryResult
from ..models.error_log import ErrorType, ErrorSeverity
from ..data.repositories import get_stored_summary_repository, get_summary_repository
from ..logging.error_tracker import get_error_tracker

logger = logging.getLogger(__name__)


@dataclass
class PushResult:
    """Result of a single channel push."""
    channel_id: str
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "channel_id": self.channel_id,
            "success": self.success,
            "message_id": self.message_id,
            "error": self.error
        }


@dataclass
class PushToChannelsResult:
    """Result of pushing a summary to multiple channels."""
    summary_id: str
    success: bool
    total_channels: int
    successful_channels: int
    deliveries: List[PushResult]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "summary_id": self.summary_id,
            "success": self.success,
            "total_channels": self.total_channels,
            "successful_channels": self.successful_channels,
            "deliveries": [d.to_dict() for d in self.deliveries]
        }


class SummaryPushService:
    """Service for pushing stored summaries to Discord channels.

    ADR-005: Summary Delivery Destinations

    This service allows users to push summaries that were stored in the
    dashboard to Discord channels on demand. It handles:
    - Channel permission verification
    - Multiple format support (embed, markdown, plain)
    - Delivery tracking in the stored summary
    - Rate limiting (future)
    """

    def __init__(self, discord_client: Optional[discord.Client] = None):
        """Initialize the push service.

        Args:
            discord_client: Discord client for sending messages
        """
        self.discord_client = discord_client

    async def push_to_channels(
        self,
        summary_id: str,
        channel_ids: List[str],
        format: str = "embed",
        include_references: bool = True,
        custom_message: Optional[str] = None,
        user_id: Optional[str] = None,
        include_key_points: bool = True,
        include_action_items: bool = True,
        include_participants: bool = True,
        include_technical_terms: bool = True,
    ) -> PushToChannelsResult:
        """Push a stored summary to one or more Discord channels.

        Args:
            summary_id: ID of the stored summary to push
            channel_ids: List of Discord channel IDs to push to
            format: Output format ("embed", "markdown", "plain")
            include_references: Include ADR-004 source references
            custom_message: Optional custom intro message
            user_id: ID of user performing the push (for audit)
            include_key_points: Include key points section
            include_action_items: Include action items section
            include_participants: Include participants section
            include_technical_terms: Include technical terms section

        Returns:
            Result of the push operation

        Raises:
            ValueError: If summary not found
        """
        # Load stored summary
        stored_summary_repo = await get_stored_summary_repository()
        stored_summary = await stored_summary_repo.get(summary_id)

        if not stored_summary:
            raise ValueError(f"Stored summary {summary_id} not found")

        if not stored_summary.summary_result:
            raise ValueError(f"Stored summary {summary_id} has no summary content")

        # Build section options dict
        section_options = {
            "include_key_points": include_key_points,
            "include_action_items": include_action_items,
            "include_participants": include_participants,
            "include_technical_terms": include_technical_terms,
        }

        # Push to each channel
        deliveries = []
        successful_count = 0

        for channel_id in channel_ids:
            result = await self._push_to_channel(
                stored_summary=stored_summary,
                channel_id=channel_id,
                format=format,
                include_references=include_references,
                custom_message=custom_message,
                section_options=section_options,
            )
            deliveries.append(result)

            # Track delivery in stored summary
            stored_summary.add_push_delivery(
                channel_id=channel_id,
                message_id=result.message_id,
                success=result.success,
                error=result.error
            )

            if result.success:
                successful_count += 1
            else:
                # Track error in error log
                await self._track_push_error(
                    guild_id=stored_summary.guild_id,
                    channel_id=channel_id,
                    summary_id=summary_id,
                    error_message=result.error or "Unknown error",
                    user_id=user_id,
                )

        # Update stored summary with delivery info
        await stored_summary_repo.update(stored_summary)

        logger.info(
            f"Pushed summary {summary_id} to {successful_count}/{len(channel_ids)} channels"
            f" by user {user_id}"
        )

        return PushToChannelsResult(
            summary_id=summary_id,
            success=successful_count > 0,
            total_channels=len(channel_ids),
            successful_channels=successful_count,
            deliveries=deliveries
        )

    async def _push_to_channel(
        self,
        stored_summary: StoredSummary,
        channel_id: str,
        format: str,
        include_references: bool,
        custom_message: Optional[str],
        section_options: Optional[Dict[str, bool]] = None,
    ) -> PushResult:
        """Push summary to a single channel.

        Args:
            stored_summary: Stored summary to push
            channel_id: Discord channel ID
            format: Output format
            include_references: Include source references
            custom_message: Optional intro message
            section_options: Dict of section toggles (include_key_points, etc.)

        Returns:
            Push result
        """
        if not self.discord_client:
            return PushResult(
                channel_id=channel_id,
                success=False,
                error="Discord client not available"
            )

        # Default section options if not provided
        if section_options is None:
            section_options = {
                "include_key_points": True,
                "include_action_items": True,
                "include_participants": True,
                "include_technical_terms": True,
            }

        try:
            # Get channel
            channel = self.discord_client.get_channel(int(channel_id))
            if not channel:
                try:
                    channel = await self.discord_client.fetch_channel(int(channel_id))
                except discord.NotFound:
                    return PushResult(
                        channel_id=channel_id,
                        success=False,
                        error="Channel not found"
                    )

            # Check if we can send messages
            if not hasattr(channel, 'send'):
                return PushResult(
                    channel_id=channel_id,
                    success=False,
                    error="Cannot send messages to this channel type"
                )

            summary = stored_summary.summary_result
            message_id = None

            # Send custom intro message if provided
            if custom_message:
                await channel.send(custom_message)

            # Send summary in requested format
            if format == "embed":
                message_id = await self._send_embed(channel, summary, section_options)
            elif format == "markdown":
                message_id = await self._send_markdown(channel, summary, include_references, section_options)
            else:  # plain
                message_id = await self._send_plain(channel, summary)

            return PushResult(
                channel_id=channel_id,
                success=True,
                message_id=message_id
            )

        except discord.Forbidden:
            return PushResult(
                channel_id=channel_id,
                success=False,
                error="Missing permission to send messages"
            )
        except Exception as e:
            logger.exception(f"Failed to push to channel {channel_id}: {e}")
            return PushResult(
                channel_id=channel_id,
                success=False,
                error=str(e)
            )

    async def _send_embed(
        self,
        channel,
        summary,
        section_options: Optional[Dict[str, bool]] = None,
    ) -> Optional[str]:
        """Send summary as Discord embed.

        Args:
            channel: Discord channel
            summary: SummaryResult
            section_options: Dict of section toggles

        Returns:
            Message ID if successful
        """
        embed_dict = summary.to_embed_dict()

        # Filter fields based on section_options
        if section_options:
            filtered_fields = []
            for field in embed_dict.get("fields", []):
                name = field.get("name", "").lower()
                # Map field names to section options
                if "key point" in name and not section_options.get("include_key_points", True):
                    continue
                if "action" in name and not section_options.get("include_action_items", True):
                    continue
                if "participant" in name and not section_options.get("include_participants", True):
                    continue
                if "technical" in name and not section_options.get("include_technical_terms", True):
                    continue
                filtered_fields.append(field)
            embed_dict["fields"] = filtered_fields

        embed = discord.Embed.from_dict(embed_dict)
        message = await channel.send(embed=embed)
        return str(message.id)

    async def _send_markdown(
        self,
        channel,
        summary,
        include_references: bool,
        section_options: Optional[Dict[str, bool]] = None,
    ) -> Optional[str]:
        """Send summary as markdown.

        Args:
            channel: Discord channel
            summary: SummaryResult
            include_references: Include source references
            section_options: Dict of section toggles

        Returns:
            Message ID of first message
        """
        markdown = summary.to_markdown(include_citations=include_references)

        # Filter sections based on section_options
        if section_options:
            lines = markdown.split('\n')
            filtered_lines = []
            skip_section = False
            skip_headers = []

            if not section_options.get("include_key_points", True):
                skip_headers.append("## 🎯 key point")
            if not section_options.get("include_action_items", True):
                skip_headers.append("## ✅ action")
            if not section_options.get("include_participants", True):
                skip_headers.append("## 👥 participant")
            if not section_options.get("include_technical_terms", True):
                skip_headers.append("## 📚 technical")

            for line in lines:
                line_lower = line.lower()
                # Check if this is a section header we should skip
                if line.startswith("## "):
                    skip_section = any(skip in line_lower for skip in skip_headers)
                    if skip_section:
                        continue
                # Skip lines in a section we're filtering out
                if skip_section and not line.startswith("## "):
                    continue
                filtered_lines.append(line)

            markdown = '\n'.join(filtered_lines)

        # Discord has 2000 char limit, split if needed
        if len(markdown) > 2000:
            chunks = []
            current_chunk = ""

            for line in markdown.split('\n'):
                if len(current_chunk) + len(line) + 1 > 1990:
                    chunks.append(current_chunk)
                    current_chunk = line
                else:
                    current_chunk += '\n' + line if current_chunk else line

            if current_chunk:
                chunks.append(current_chunk)

            first_message = None
            for chunk in chunks:
                msg = await channel.send(chunk)
                if first_message is None:
                    first_message = msg

            return str(first_message.id) if first_message else None
        else:
            message = await channel.send(markdown)
            return str(message.id)

    async def _send_plain(self, channel, summary) -> Optional[str]:
        """Send summary as plain text.

        Args:
            channel: Discord channel
            summary: SummaryResult

        Returns:
            Message ID
        """
        text = summary.summary_text
        if len(text) > 2000:
            text = text[:1997] + "..."

        message = await channel.send(text)
        return str(message.id)

    async def push_summary_to_channels(
        self,
        summary_id: str,
        channel_ids: List[str],
        format: str = "embed",
        include_references: bool = True,
        custom_message: Optional[str] = None,
        user_id: Optional[str] = None,
        include_key_points: bool = True,
        include_action_items: bool = True,
        include_participants: bool = True,
        include_technical_terms: bool = True,
    ) -> PushToChannelsResult:
        """Push a regular summary (from History) to one or more Discord channels.

        This is for manual/on-demand summaries, not stored summaries.

        Args:
            summary_id: ID of the summary to push
            channel_ids: List of Discord channel IDs to push to
            format: Output format ("embed", "markdown", "plain")
            include_references: Include ADR-004 source references
            custom_message: Optional custom intro message
            user_id: ID of user performing the push (for audit)
            include_key_points: Include key points section
            include_action_items: Include action items section
            include_participants: Include participants section
            include_technical_terms: Include technical terms section

        Returns:
            Result of the push operation

        Raises:
            ValueError: If summary not found
        """
        # Load summary from regular repository
        summary_repo = await get_summary_repository()
        summary = await summary_repo.get_summary(summary_id)

        if not summary:
            raise ValueError(f"Summary {summary_id} not found")

        if not summary.summary_text:
            raise ValueError(f"Summary {summary_id} has no summary content")

        # Build section options dict
        section_options = {
            "include_key_points": include_key_points,
            "include_action_items": include_action_items,
            "include_participants": include_participants,
            "include_technical_terms": include_technical_terms,
        }

        # Push to each channel
        deliveries = []
        successful_count = 0

        for channel_id in channel_ids:
            result = await self._push_result_to_channel(
                summary_result=summary,
                channel_id=channel_id,
                format=format,
                include_references=include_references,
                custom_message=custom_message,
                section_options=section_options,
            )
            deliveries.append(result)

            if result.success:
                successful_count += 1
            else:
                logger.warning(f"Failed to push to channel {channel_id}: {result.error}")
                # Track error in error log
                await self._track_push_error(
                    guild_id=summary.guild_id,
                    channel_id=channel_id,
                    summary_id=summary_id,
                    error_message=result.error or "Unknown error",
                    user_id=user_id,
                )

        logger.info(
            f"Pushed summary {summary_id} to {successful_count}/{len(channel_ids)} channels"
            f" by user {user_id}"
        )

        return PushToChannelsResult(
            summary_id=summary_id,
            success=successful_count > 0,
            total_channels=len(channel_ids),
            successful_channels=successful_count,
            deliveries=deliveries
        )

    async def _push_result_to_channel(
        self,
        summary_result: SummaryResult,
        channel_id: str,
        format: str,
        include_references: bool,
        custom_message: Optional[str],
        section_options: Optional[Dict[str, bool]] = None,
    ) -> PushResult:
        """Push a SummaryResult to a single channel.

        Args:
            summary_result: SummaryResult to push
            channel_id: Discord channel ID
            format: Output format
            include_references: Include source references
            custom_message: Optional intro message
            section_options: Dict of section toggles (include_key_points, etc.)

        Returns:
            Push result
        """
        if not self.discord_client:
            return PushResult(
                channel_id=channel_id,
                success=False,
                error="Discord client not available"
            )

        # Default section options if not provided
        if section_options is None:
            section_options = {
                "include_key_points": True,
                "include_action_items": True,
                "include_participants": True,
                "include_technical_terms": True,
            }

        try:
            # Get channel
            channel = self.discord_client.get_channel(int(channel_id))
            if not channel:
                try:
                    channel = await self.discord_client.fetch_channel(int(channel_id))
                except discord.NotFound:
                    return PushResult(
                        channel_id=channel_id,
                        success=False,
                        error="Channel not found"
                    )

            # Check if we can send messages
            if not hasattr(channel, 'send'):
                return PushResult(
                    channel_id=channel_id,
                    success=False,
                    error="Cannot send messages to this channel type"
                )

            message_id = None

            # Send custom intro message if provided
            if custom_message:
                await channel.send(custom_message)

            # Send summary in requested format
            if format == "embed":
                message_id = await self._send_embed(channel, summary_result, section_options)
            elif format == "markdown":
                message_id = await self._send_markdown(channel, summary_result, include_references, section_options)
            else:  # plain
                message_id = await self._send_plain(channel, summary_result)

            return PushResult(
                channel_id=channel_id,
                success=True,
                message_id=message_id
            )

        except discord.Forbidden:
            return PushResult(
                channel_id=channel_id,
                success=False,
                error="Missing permission to send messages"
            )
        except Exception as e:
            logger.exception(f"Failed to push to channel {channel_id}: {e}")
            return PushResult(
                channel_id=channel_id,
                success=False,
                error=str(e)
            )

    async def verify_channel_permission(
        self,
        user_id: str,
        channel_id: str,
        guild_id: str
    ) -> bool:
        """Verify user has permission to push to a channel.

        Args:
            user_id: Discord user ID
            channel_id: Discord channel ID
            guild_id: Discord guild ID

        Returns:
            True if user can push to the channel
        """
        if not self.discord_client:
            return False

        try:
            channel = self.discord_client.get_channel(int(channel_id))
            if not channel:
                return False

            # Check if it's in the correct guild
            if hasattr(channel, 'guild') and str(channel.guild.id) != guild_id:
                return False

            # Get member
            if hasattr(channel, 'guild'):
                member = channel.guild.get_member(int(user_id))
                if not member:
                    return False

                # Check for send messages permission
                permissions = channel.permissions_for(member)
                return permissions.send_messages

            return False

        except Exception as e:
            logger.warning(f"Failed to verify channel permission: {e}")
            return False

    async def _track_push_error(
        self,
        guild_id: str,
        channel_id: str,
        summary_id: str,
        error_message: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Track a push failure in the error log.

        Args:
            guild_id: Discord guild ID
            channel_id: Discord channel ID
            summary_id: Summary ID that failed to push
            error_message: Error message
            user_id: User who initiated the push
        """
        try:
            tracker = get_error_tracker()
            if not tracker:
                return

            # Determine error type based on message
            if "permission" in error_message.lower():
                error_type = ErrorType.DISCORD_PERMISSION
            elif "not found" in error_message.lower():
                error_type = ErrorType.DISCORD_NOT_FOUND
            else:
                error_type = ErrorType.UNKNOWN

            await tracker.capture_error(
                error=Exception(error_message),
                error_type=error_type,
                severity=ErrorSeverity.WARNING,
                guild_id=guild_id,
                channel_id=channel_id,
                operation="push_summary_to_channel",
                user_id=user_id,
                details={
                    "summary_id": summary_id,
                    "error_message": error_message,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to track push error: {e}")
