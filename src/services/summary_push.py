"""
Summary Push Service for ADR-005: Summary Delivery Destinations.
Extended by ADR-014: Discord Push Templates with Thread Support.

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
from ..models.push_template import PushTemplate, DEFAULT_PUSH_TEMPLATE
from ..data.repositories import get_stored_summary_repository, get_summary_repository
from ..logging.error_tracker import get_error_tracker
from .push_message_builder import (
    PushMessageBuilder, PushContext, send_with_template, extract_push_context,
)

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

        CS-006: Delegates to _push_summary_to_channel to avoid code duplication.

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
        return await self._push_summary_to_channel(
            summary_result=stored_summary.summary_result,
            channel_id=channel_id,
            format=format,
            include_references=include_references,
            custom_message=custom_message,
            section_options=section_options,
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

        # Validate embed before sending
        embed_dict = self._validate_embed_dict(embed_dict)

        embed = discord.Embed.from_dict(embed_dict)
        message = await channel.send(embed=embed)
        return str(message.id)

    def _validate_embed_dict(self, embed_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and fix embed dict to comply with Discord limits.

        Discord embed limits:
        - Total: 6000 characters
        - Title: 256 characters
        - Description: 4096 characters
        - Field name: 256 characters
        - Field value: 1024 characters (non-empty)
        - Fields: max 25

        Args:
            embed_dict: Embed dictionary to validate

        Returns:
            Validated embed dictionary
        """
        # Ensure description is non-empty
        description = embed_dict.get("description", "")
        if not description or not description.strip():
            embed_dict["description"] = "*Summary generated*"
        else:
            embed_dict["description"] = description[:4096]

        # Truncate title
        if "title" in embed_dict:
            embed_dict["title"] = embed_dict["title"][:256]

        # Validate fields
        valid_fields = []
        for field in embed_dict.get("fields", [])[:25]:  # Max 25 fields
            name = field.get("name", "").strip()
            value = field.get("value", "").strip()
            # Skip fields with empty name or value
            if not name or not value:
                continue
            valid_fields.append({
                "name": name[:256],
                "value": value[:1024],
                "inline": field.get("inline", False),
            })
        embed_dict["fields"] = valid_fields

        # Truncate footer
        if "footer" in embed_dict and "text" in embed_dict["footer"]:
            embed_dict["footer"]["text"] = embed_dict["footer"]["text"][:2048]

        # Check total size (6000 char limit)
        total_size = self._calculate_embed_size(embed_dict)
        if total_size > 6000:
            # Truncate description to fit
            excess = total_size - 6000
            current_desc_len = len(embed_dict["description"])
            new_desc_len = max(100, current_desc_len - excess - 50)  # Leave buffer
            embed_dict["description"] = embed_dict["description"][:new_desc_len] + "..."
            logger.warning(f"Truncated embed description: {total_size} chars -> ~{6000 - excess} chars")

        return embed_dict

    def _calculate_embed_size(self, embed_dict: Dict[str, Any]) -> int:
        """Calculate total character count of embed."""
        total = 0
        total += len(embed_dict.get("title", ""))
        total += len(embed_dict.get("description", ""))
        for field in embed_dict.get("fields", []):
            total += len(field.get("name", ""))
            total += len(field.get("value", ""))
        if "footer" in embed_dict:
            total += len(embed_dict["footer"].get("text", ""))
        if "author" in embed_dict:
            total += len(embed_dict["author"].get("name", ""))
        return total

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
            result = await self._push_summary_to_channel(
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

    async def _push_summary_to_channel(
        self,
        summary_result: SummaryResult,
        channel_id: str,
        format: str,
        include_references: bool,
        custom_message: Optional[str],
        section_options: Optional[Dict[str, bool]] = None,
    ) -> PushResult:
        """Push a SummaryResult to a single channel.

        CS-006: Unified implementation for both StoredSummary and SummaryResult pushes.
        Called by _push_to_channel (for stored summaries) and push_result_to_channels.

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

    # =========================================================================
    # ADR-014: Template-based push with thread support
    # =========================================================================

    async def push_with_template(
        self,
        summary_id: str,
        channel_id: str,
        template: Optional[PushTemplate] = None,
        user_id: Optional[str] = None,
    ) -> PushResult:
        """Push a stored summary using template-based formatting.

        ADR-014: Discord Push Templates with Thread Support.

        This method creates a thread (if permitted) and sends structured
        messages based on the template configuration.

        Args:
            summary_id: ID of the stored summary to push
            channel_id: Discord channel ID to push to
            template: Push template (defaults to guild template or DEFAULT)
            user_id: ID of user performing the push (for audit)

        Returns:
            PushResult with success status and message IDs
        """
        if not self.discord_client:
            return PushResult(
                channel_id=channel_id,
                success=False,
                error="Discord client not available"
            )

        # Load stored summary
        stored_summary_repo = await get_stored_summary_repository()
        stored_summary = await stored_summary_repo.get(summary_id)

        if not stored_summary:
            return PushResult(
                channel_id=channel_id,
                success=False,
                error=f"Summary {summary_id} not found"
            )

        if not stored_summary.summary_result:
            return PushResult(
                channel_id=channel_id,
                success=False,
                error=f"Summary {summary_id} has no content"
            )

        # Get template (could load from guild_push_templates table in future)
        template = template or DEFAULT_PUSH_TEMPLATE

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

            # Build push context
            context = extract_push_context(
                stored_summary=stored_summary,
                summary_result=stored_summary.summary_result,
            )

            # Send using template
            result = await send_with_template(
                channel=channel,
                summary=stored_summary.summary_result,
                context=context,
                template=template,
                discord_client=self.discord_client,
            )

            if result["success"]:
                # Track delivery
                message_id = result["message_ids"][0] if result["message_ids"] else None
                stored_summary.add_push_delivery(
                    channel_id=channel_id,
                    message_id=message_id,
                    success=True,
                )
                await stored_summary_repo.update(stored_summary)

                logger.info(
                    f"Pushed summary {summary_id} to channel {channel_id} "
                    f"(thread={result['thread_created']}) by user {user_id}"
                )

                return PushResult(
                    channel_id=channel_id,
                    success=True,
                    message_id=message_id,
                )
            else:
                # Track error
                stored_summary.add_push_delivery(
                    channel_id=channel_id,
                    success=False,
                    error=result["error"],
                )
                await stored_summary_repo.update(stored_summary)

                await self._track_push_error(
                    guild_id=stored_summary.guild_id,
                    channel_id=channel_id,
                    summary_id=summary_id,
                    error_message=result["error"] or "Unknown error",
                    user_id=user_id,
                )

                return PushResult(
                    channel_id=channel_id,
                    success=False,
                    error=result["error"],
                )

        except discord.Forbidden:
            error = "Missing permission to send messages"
            await self._track_push_error(
                guild_id=stored_summary.guild_id,
                channel_id=channel_id,
                summary_id=summary_id,
                error_message=error,
                user_id=user_id,
            )
            return PushResult(
                channel_id=channel_id,
                success=False,
                error=error,
            )
        except Exception as e:
            logger.exception(f"Failed to push with template: {e}")
            await self._track_push_error(
                guild_id=stored_summary.guild_id,
                channel_id=channel_id,
                summary_id=summary_id,
                error_message=str(e),
                user_id=user_id,
            )
            return PushResult(
                channel_id=channel_id,
                success=False,
                error=str(e),
            )

    async def push_to_channels_with_template(
        self,
        summary_id: str,
        channel_ids: List[str],
        template: Optional[PushTemplate] = None,
        user_id: Optional[str] = None,
    ) -> PushToChannelsResult:
        """Push a stored summary to multiple channels using template formatting.

        ADR-014: Discord Push Templates with Thread Support.

        Args:
            summary_id: ID of the stored summary to push
            channel_ids: List of Discord channel IDs to push to
            template: Push template (defaults to guild template or DEFAULT)
            user_id: ID of user performing the push (for audit)

        Returns:
            Result of the push operation
        """
        deliveries = []
        successful_count = 0

        for channel_id in channel_ids:
            result = await self.push_with_template(
                summary_id=summary_id,
                channel_id=channel_id,
                template=template,
                user_id=user_id,
            )
            deliveries.append(result)
            if result.success:
                successful_count += 1

        return PushToChannelsResult(
            summary_id=summary_id,
            success=successful_count > 0,
            total_channels=len(channel_ids),
            successful_channels=successful_count,
            deliveries=deliveries,
        )
