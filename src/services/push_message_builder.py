"""
Push Message Builder for ADR-014: Discord Push Templates.

This module builds structured Discord messages from summaries using templates,
with support for threads, sections, and jump links.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Union

import discord

from ..models.push_template import (
    PushTemplate, SectionConfig, DEFAULT_PUSH_TEMPLATE,
    format_scope, format_date_range,
)
from ..models.summary import SummaryResult, ActionItem
from ..models.reference import SummaryReference, ReferencedClaim
from ..models.stored_summary import StoredSummary

logger = logging.getLogger(__name__)

# Discord limits
MAX_MESSAGE_LENGTH = 2000
MAX_EMBED_DESCRIPTION = 4096
MAX_EMBED_FIELD_VALUE = 1024
MAX_THREAD_NAME_LENGTH = 100

# Rate limiting
MESSAGE_DELAY_SECONDS = 1.0


@dataclass
class PushContext:
    """Context for building push messages."""
    guild_id: str
    channel_names: List[str] = field(default_factory=list)
    category_name: Optional[str] = None
    is_server_wide: bool = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    message_count: int = 0
    participant_count: int = 0


@dataclass
class BuiltMessage:
    """A built message ready to send."""
    content: Optional[str] = None
    embed: Optional[discord.Embed] = None
    is_thread_starter: bool = False


class PushMessageBuilder:
    """Builds Discord messages from summaries using templates.

    ADR-014: Discord Push Templates with Thread Support.
    """

    def __init__(self, template: Optional[PushTemplate] = None):
        """Initialize builder with template.

        Args:
            template: Push template to use. Defaults to DEFAULT_PUSH_TEMPLATE.
        """
        self.template = template or DEFAULT_PUSH_TEMPLATE

    def build_thread_name(self, context: PushContext) -> str:
        """Build thread name from template and context.

        Args:
            context: Push context with scope and time info

        Returns:
            Thread name (truncated to 100 chars if needed)
        """
        scope = format_scope(
            channel_names=context.channel_names,
            category_name=context.category_name,
            is_server_wide=context.is_server_wide,
        )

        date_range = ""
        if context.start_time and context.end_time:
            date_range = format_date_range(context.start_time, context.end_time)

        name = self.template.thread_name_format.format(
            scope=scope,
            date_range=date_range,
        )

        # Truncate if too long
        if len(name) > MAX_THREAD_NAME_LENGTH:
            # Keep the date range, truncate scope
            suffix = f" ({date_range})" if date_range else ""
            max_scope_len = MAX_THREAD_NAME_LENGTH - len(suffix) - 3  # -3 for "..."
            truncated_scope = scope[:max_scope_len] + "..."
            name = f"Summary: {truncated_scope}{suffix}"

        return name[:MAX_THREAD_NAME_LENGTH]

    def build_header_message(
        self,
        summary: SummaryResult,
        context: PushContext,
    ) -> BuiltMessage:
        """Build the header/first message with summary overview.

        Args:
            summary: The summary result
            context: Push context

        Returns:
            Built message with header content
        """
        scope = format_scope(
            channel_names=context.channel_names,
            category_name=context.category_name,
            is_server_wide=context.is_server_wide,
        )

        lines = []

        # Header
        header = self.template.header_format.format(scope=scope)
        lines.append(header)

        # Date range
        if self.template.show_date_range and context.start_time and context.end_time:
            date_str = f"📅 {context.start_time.strftime('%b %d, %Y %I:%M %p')} - {context.end_time.strftime('%b %d, %Y %I:%M %p')} (UTC)"
            lines.append(date_str)

        # Stats
        if self.template.show_stats:
            stats = f"📊 {context.message_count} messages from {context.participant_count} participants"
            lines.append(stats)

        # Summary text
        if self.template.show_summary_text and summary.summary_text:
            lines.append("")  # Blank line
            summary_text = summary.summary_text
            # Truncate if needed (leave room for header)
            max_summary_len = MAX_MESSAGE_LENGTH - len("\n".join(lines)) - 100
            if len(summary_text) > max_summary_len:
                summary_text = summary_text[:max_summary_len - 3] + "..."
            lines.append(summary_text)

        content = "\n".join(lines)

        # Ensure we don't exceed limit
        if len(content) > MAX_MESSAGE_LENGTH:
            content = content[:MAX_MESSAGE_LENGTH - 3] + "..."

        return BuiltMessage(content=content, is_thread_starter=True)

    def build_section_message(
        self,
        section: SectionConfig,
        summary: SummaryResult,
        include_references: bool = True,
        include_jump_links: bool = True,
    ) -> List[BuiltMessage]:
        """Build message(s) for a single section.

        Args:
            section: Section configuration
            summary: The summary result
            include_references: Include [N] citation markers
            include_jump_links: Include jump links in sources

        Returns:
            List of built messages (may be multiple if section needs pagination)
        """
        if section.type == "key_points":
            return self._build_key_points_section(section, summary, include_references)
        elif section.type == "action_items":
            return self._build_action_items_section(section, summary, include_references)
        elif section.type == "decisions":
            return self._build_decisions_section(section, summary, include_references)
        elif section.type == "technical_terms":
            return self._build_technical_terms_section(section, summary)
        elif section.type == "participants":
            return self._build_participants_section(section, summary)
        elif section.type == "sources":
            return self._build_sources_section(section, summary, include_jump_links)
        else:
            logger.warning(f"Unknown section type: {section.type}")
            return []

    def _build_key_points_section(
        self,
        section: SectionConfig,
        summary: SummaryResult,
        include_references: bool,
    ) -> List[BuiltMessage]:
        """Build key points section."""
        # Use referenced key points if available
        if include_references and summary.referenced_key_points:
            items = []
            for claim in summary.referenced_key_points[:section.max_items]:
                if isinstance(claim, ReferencedClaim):
                    items.append(f"• {claim.to_markdown(include_citations=True)}")
                else:
                    items.append(f"• {claim}")
        elif summary.key_points:
            items = [f"• {point}" for point in summary.key_points[:section.max_items]]
        else:
            return []

        return self._paginate_section(section.get_title(), items)

    def _build_action_items_section(
        self,
        section: SectionConfig,
        summary: SummaryResult,
        include_references: bool,
    ) -> List[BuiltMessage]:
        """Build action items section."""
        if include_references and summary.referenced_action_items:
            items = []
            for claim in summary.referenced_action_items[:section.max_items]:
                if isinstance(claim, ReferencedClaim):
                    items.append(f"⭕ {claim.to_markdown(include_citations=True)}")
                else:
                    items.append(f"⭕ {claim}")
        elif summary.action_items:
            items = []
            for item in summary.action_items[:section.max_items]:
                if isinstance(item, ActionItem):
                    items.append(item.to_markdown())
                else:
                    items.append(f"⭕ {item}")
        else:
            return []

        return self._paginate_section(section.get_title(), items)

    def _build_decisions_section(
        self,
        section: SectionConfig,
        summary: SummaryResult,
        include_references: bool,
    ) -> List[BuiltMessage]:
        """Build decisions section."""
        if not summary.referenced_decisions:
            return []

        items = []
        for claim in summary.referenced_decisions[:section.max_items]:
            if isinstance(claim, ReferencedClaim):
                items.append(f"• {claim.to_markdown(include_citations=include_references)}")
            else:
                items.append(f"• {claim}")

        return self._paginate_section(section.get_title(), items)

    def _build_technical_terms_section(
        self,
        section: SectionConfig,
        summary: SummaryResult,
    ) -> List[BuiltMessage]:
        """Build technical terms section."""
        if not summary.technical_terms:
            return []

        items = []
        for term in summary.technical_terms[:section.max_items]:
            if hasattr(term, 'to_markdown'):
                items.append(f"• {term.to_markdown()}")
            else:
                items.append(f"• **{term.term}**: {term.definition}")

        return self._paginate_section(section.get_title(), items)

    def _build_participants_section(
        self,
        section: SectionConfig,
        summary: SummaryResult,
    ) -> List[BuiltMessage]:
        """Build participants section."""
        if not summary.participants:
            return []

        # Sort by message count
        sorted_participants = sorted(
            summary.participants,
            key=lambda p: p.message_count,
            reverse=True
        )[:section.max_items]

        items = [
            f"• **{p.display_name}** ({p.message_count} messages)"
            for p in sorted_participants
        ]

        return self._paginate_section(section.get_title(), items)

    def _build_sources_section(
        self,
        section: SectionConfig,
        summary: SummaryResult,
        include_jump_links: bool,
    ) -> List[BuiltMessage]:
        """Build sources section with optional jump links."""
        if not summary.reference_index:
            return []

        items = []
        for ref in summary.reference_index[:section.max_items]:
            if isinstance(ref, SummaryReference):
                line = ref.to_discord_source_line(include_jump_link=include_jump_links)
            elif isinstance(ref, dict):
                # Handle dict format
                ref_obj = SummaryReference.from_dict(ref)
                line = ref_obj.to_discord_source_line(include_jump_link=include_jump_links)
            else:
                continue
            items.append(line)

        if len(summary.reference_index) > section.max_items:
            items.append(f"*...and {len(summary.reference_index) - section.max_items} more sources*")

        return self._paginate_section(section.get_title(), items)

    def _paginate_section(
        self,
        title: str,
        items: List[str],
        max_length: int = MAX_MESSAGE_LENGTH - 100,
    ) -> List[BuiltMessage]:
        """Paginate a section if it exceeds max length.

        Args:
            title: Section title
            items: List of items to include
            max_length: Maximum content length per message

        Returns:
            List of built messages
        """
        if not items:
            return []

        messages = []
        current_items = []
        current_length = len(title) + 2  # +2 for newlines

        for item in items:
            item_len = len(item) + 1  # +1 for newline

            if current_length + item_len > max_length and current_items:
                # Save current page and start new one
                page_num = len(messages) + 1
                page_title = f"{title} ({page_num}/{len(items) // 10 + 1})" if len(items) > 10 else title
                content = page_title + "\n\n" + "\n".join(current_items)
                messages.append(BuiltMessage(content=content))
                current_items = []
                current_length = len(title) + 10  # Reset with page number space

            current_items.append(item)
            current_length += item_len

        # Add remaining items
        if current_items:
            if messages:
                # This is a continuation page
                page_num = len(messages) + 1
                page_title = f"{title} ({page_num}/{page_num})"
            else:
                page_title = title
            content = page_title + "\n\n" + "\n".join(current_items)
            messages.append(BuiltMessage(content=content))

        return messages

    def build_all_messages(
        self,
        summary: SummaryResult,
        context: PushContext,
    ) -> List[BuiltMessage]:
        """Build all messages for a summary push.

        Args:
            summary: The summary result
            context: Push context

        Returns:
            List of all built messages in order
        """
        messages = []

        # Header message
        header = self.build_header_message(summary, context)
        messages.append(header)

        # Section messages
        for section in self.template.get_enabled_sections():
            section_messages = self.build_section_message(
                section=section,
                summary=summary,
                include_references=self.template.include_references,
                include_jump_links=self.template.include_jump_links,
            )
            messages.extend(section_messages)

        return messages


async def check_thread_permissions(
    channel: discord.TextChannel,
    bot_member: discord.Member,
) -> Dict[str, bool]:
    """Check if bot has permissions to create/use threads.

    Args:
        channel: The target channel
        bot_member: The bot's member object

    Returns:
        Dict with permission flags
    """
    permissions = channel.permissions_for(bot_member)

    return {
        "can_create_public_threads": permissions.create_public_threads,
        "can_send_messages_in_threads": permissions.send_messages_in_threads,
        "can_send_messages": permissions.send_messages,
        "is_thread": isinstance(channel, discord.Thread),
        "is_forum": channel.type == discord.ChannelType.forum if hasattr(channel, 'type') else False,
    }


async def send_with_template(
    channel: Union[discord.TextChannel, discord.Thread],
    summary: SummaryResult,
    context: PushContext,
    template: Optional[PushTemplate] = None,
    discord_client: Optional[discord.Client] = None,
) -> Dict[str, Any]:
    """Send a summary to a channel using template-based formatting.

    Args:
        channel: Discord channel to send to
        summary: Summary to send
        context: Push context
        template: Push template (defaults to DEFAULT_PUSH_TEMPLATE)
        discord_client: Discord client for fetching bot member

    Returns:
        Dict with send results
    """
    template = template or DEFAULT_PUSH_TEMPLATE
    builder = PushMessageBuilder(template)

    result = {
        "success": False,
        "thread_created": False,
        "thread_id": None,
        "message_ids": [],
        "error": None,
    }

    try:
        # Check if we should/can create a thread
        target = channel
        if template.use_thread and discord_client and hasattr(channel, 'guild'):
            bot_member = channel.guild.get_member(discord_client.user.id)
            if bot_member:
                perms = await check_thread_permissions(channel, bot_member)

                if perms["is_thread"]:
                    # Already a thread, use directly
                    target = channel
                elif perms["is_forum"]:
                    # Forum channel - would need different handling
                    logger.warning("Forum channels not yet supported, sending to channel directly")
                    target = channel
                elif perms["can_create_public_threads"] and perms["can_send_messages_in_threads"]:
                    # Create thread
                    thread_name = builder.build_thread_name(context)
                    thread = await channel.create_thread(
                        name=thread_name,
                        auto_archive_duration=template.thread_auto_archive_minutes,
                        type=discord.ChannelType.public_thread,
                    )
                    target = thread
                    result["thread_created"] = True
                    result["thread_id"] = str(thread.id)
                    logger.info(f"Created thread: {thread_name}")

        # Build messages
        messages = builder.build_all_messages(summary, context)

        # Send messages with rate limiting
        for i, msg in enumerate(messages):
            if i > 0:
                await asyncio.sleep(MESSAGE_DELAY_SECONDS)

            if msg.content:
                sent = await target.send(msg.content)
                result["message_ids"].append(str(sent.id))
            elif msg.embed:
                sent = await target.send(embed=msg.embed)
                result["message_ids"].append(str(sent.id))

        result["success"] = True

    except discord.Forbidden as e:
        result["error"] = f"Missing permissions: {e}"
        logger.error(f"Permission error sending to channel: {e}")
    except Exception as e:
        result["error"] = str(e)
        logger.exception(f"Error sending to channel: {e}")

    return result


def extract_push_context(
    stored_summary: Optional[StoredSummary] = None,
    summary_result: Optional[SummaryResult] = None,
) -> PushContext:
    """Extract push context from a stored summary or summary result.

    Args:
        stored_summary: StoredSummary if available
        summary_result: SummaryResult if available

    Returns:
        PushContext with extracted information
    """
    context = PushContext(guild_id="")

    if stored_summary:
        context.guild_id = stored_summary.guild_id

        # ADR-026: Handle multi-platform sources (WhatsApp, etc.)
        if stored_summary.archive_source_key:
            # Parse source key like "whatsapp:ai-code-chat" or "discord:channel-name"
            parts = stored_summary.archive_source_key.split(":", 1)
            if len(parts) == 2:
                platform, source_name = parts
                # Format as friendly name: "WhatsApp: ai-code-chat"
                platform_display = platform.capitalize()
                context.channel_names = [f"{platform_display}: {source_name}"]
            else:
                context.channel_names = [stored_summary.archive_source_key]

        # Extract channel names from source_channel_ids or title
        elif stored_summary.source_channel_ids:
            # Would need to resolve channel IDs to names via Discord API
            # For now, use the stored info if available
            pass

        # Use scope info if available
        if hasattr(stored_summary, 'scope'):
            if stored_summary.scope == 'guild':
                context.is_server_wide = True
            elif stored_summary.scope == 'category' and hasattr(stored_summary, 'category_name'):
                context.category_name = stored_summary.category_name

        # ADR-026: Use archive_period for date range on archive summaries
        if stored_summary.archive_period and not context.start_time:
            from datetime import datetime
            try:
                period_date = datetime.strptime(stored_summary.archive_period, "%Y-%m-%d")
                # Set start and end to cover the full day
                context.start_time = period_date.replace(hour=0, minute=0, second=0)
                context.end_time = period_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                pass

        # Get the summary result
        summary = stored_summary.summary_result
    else:
        summary = summary_result

    if summary:
        context.guild_id = context.guild_id or summary.guild_id
        # Only use summary times if not already set from archive_period
        if not context.start_time:
            context.start_time = summary.start_time
        if not context.end_time:
            context.end_time = summary.end_time
        context.message_count = summary.message_count
        context.participant_count = len(summary.participants)

        # Try to get channel name from context (only if not already set)
        if not context.channel_names and summary.context and summary.context.channel_name:
            context.channel_names = [summary.context.channel_name]

    return context
