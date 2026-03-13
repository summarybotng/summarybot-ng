"""
Utility functions for Discord bot operations.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import discord
from src.utils.time import utc_now_naive


def create_embed(
    title: str,
    description: str = None,
    color: int = 0x4A90E2,
    fields: List[Dict[str, Any]] = None,
    footer: str = None,
    timestamp: datetime = None,
    thumbnail_url: str = None,
    image_url: str = None
) -> discord.Embed:
    """
    Create a Discord embed with common formatting.

    Args:
        title: Embed title
        description: Embed description
        color: Embed color (hex value)
        fields: List of field dictionaries with 'name', 'value', and optional 'inline'
        footer: Footer text
        timestamp: Timestamp to display
        thumbnail_url: URL for thumbnail image
        image_url: URL for main image

    Returns:
        discord.Embed: Configured Discord embed
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=timestamp
    )

    if fields:
        for field in fields:
            embed.add_field(
                name=field.get('name', ''),
                value=field.get('value', ''),
                inline=field.get('inline', False)
            )

    if footer:
        embed.set_footer(text=footer)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    if image_url:
        embed.set_image(url=image_url)

    return embed


def create_error_embed(
    title: str = "Error",
    description: str = None,
    error_code: str = None,
    details: str = None
) -> discord.Embed:
    """
    Create an error embed with standard formatting.

    Args:
        title: Error title
        description: Error description
        error_code: Error code for reference
        details: Additional error details

    Returns:
        discord.Embed: Error embed
    """
    fields = []

    if error_code:
        fields.append({
            'name': 'Error Code',
            'value': f"`{error_code}`",
            'inline': True
        })

    if details:
        fields.append({
            'name': 'Details',
            'value': details,
            'inline': False
        })

    footer_text = "If this persists, please contact server administrators."
    if error_code:
        footer_text = f"Error Code: {error_code} | {footer_text}"

    return create_embed(
        title=f"❌ {title}",
        description=description,
        color=0xE74C3C,  # Red
        fields=fields if fields else None,
        footer=footer_text,
        timestamp=utc_now_naive()
    )


def create_success_embed(
    title: str = "Success",
    description: str = None,
    fields: List[Dict[str, Any]] = None
) -> discord.Embed:
    """
    Create a success embed with standard formatting.

    Args:
        title: Success title
        description: Success description
        fields: Additional fields

    Returns:
        discord.Embed: Success embed
    """
    return create_embed(
        title=f"✅ {title}",
        description=description,
        color=0x2ECC71,  # Green
        fields=fields,
        timestamp=utc_now_naive()
    )


def create_info_embed(
    title: str,
    description: str = None,
    fields: List[Dict[str, Any]] = None
) -> discord.Embed:
    """
    Create an info embed with standard formatting.

    Args:
        title: Info title
        description: Info description
        fields: Additional fields

    Returns:
        discord.Embed: Info embed
    """
    return create_embed(
        title=f"ℹ️ {title}",
        description=description,
        color=0x3498DB,  # Blue
        fields=fields,
        timestamp=utc_now_naive()
    )


def format_timestamp(dt: datetime, style: str = "f") -> str:
    """
    Format a datetime as a Discord timestamp.

    Args:
        dt: Datetime to format
        style: Discord timestamp style:
            - 't': Short time (16:20)
            - 'T': Long time (16:20:30)
            - 'd': Short date (20/04/2021)
            - 'D': Long date (20 April 2021)
            - 'f': Short date/time (20 April 2021 16:20)
            - 'F': Long date/time (Tuesday, 20 April 2021 16:20)
            - 'R': Relative time (2 months ago)

    Returns:
        str: Discord formatted timestamp
    """
    timestamp = int(dt.timestamp())
    return f"<t:{timestamp}:{style}>"


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length with a suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncated

    Returns:
        str: Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def format_code_block(code: str, language: str = "") -> str:
    """
    Format text as a Discord code block.

    Args:
        code: Code content
        language: Programming language for syntax highlighting

    Returns:
        str: Formatted code block
    """
    return f"```{language}\n{code}\n```"


def format_list(items: List[str], bullet: str = "•") -> str:
    """
    Format a list of items with bullets.

    Args:
        items: List of items
        bullet: Bullet character

    Returns:
        str: Formatted list
    """
    return "\n".join([f"{bullet} {item}" for item in items])


def parse_channel_mention(mention: str) -> Optional[int]:
    """
    Parse a channel mention to extract the channel ID.

    Args:
        mention: Channel mention string (e.g., "<#123456789>")

    Returns:
        Optional[int]: Channel ID or None if invalid
    """
    if mention.startswith("<#") and mention.endswith(">"):
        try:
            return int(mention[2:-1])
        except ValueError:
            return None
    return None


def parse_user_mention(mention: str) -> Optional[int]:
    """
    Parse a user mention to extract the user ID.

    Args:
        mention: User mention string (e.g., "<@123456789>" or "<@!123456789>")

    Returns:
        Optional[int]: User ID or None if invalid
    """
    if mention.startswith("<@") and mention.endswith(">"):
        # Remove <@, <@!, and >
        id_str = mention[2:-1].lstrip("!")
        try:
            return int(id_str)
        except ValueError:
            return None
    return None


def parse_role_mention(mention: str) -> Optional[int]:
    """
    Parse a role mention to extract the role ID.

    Args:
        mention: Role mention string (e.g., "<@&123456789>")

    Returns:
        Optional[int]: Role ID or None if invalid
    """
    if mention.startswith("<@&") and mention.endswith(">"):
        try:
            return int(mention[3:-1])
        except ValueError:
            return None
    return None


def get_permission_names(permissions: discord.Permissions) -> List[str]:
    """
    Get a list of permission names from a Permissions object.

    Args:
        permissions: Discord permissions object

    Returns:
        List[str]: List of enabled permission names
    """
    return [perm for perm, value in permissions if value]


def create_progress_bar(current: int, total: int, length: int = 10,
                       filled: str = "█", empty: str = "░") -> str:
    """
    Create a text-based progress bar.

    Args:
        current: Current progress value
        total: Total/maximum value
        length: Length of the progress bar
        filled: Character for filled portion
        empty: Character for empty portion

    Returns:
        str: Progress bar string
    """
    if total == 0:
        return empty * length

    filled_length = int(length * current / total)
    bar = filled * filled_length + empty * (length - filled_length)
    percentage = int(100 * current / total)

    return f"{bar} {percentage}%"


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        str: Formatted size (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def split_message(text: str, max_length: int = 2000) -> List[str]:
    """
    Split a long message into multiple parts respecting Discord's character limit.

    Args:
        text: Text to split
        max_length: Maximum length per message

    Returns:
        List[str]: List of message parts
    """
    if len(text) <= max_length:
        return [text]

    parts = []
    current_part = ""

    for line in text.split('\n'):
        if len(current_part) + len(line) + 1 <= max_length:
            current_part += line + '\n'
        else:
            if current_part:
                parts.append(current_part.rstrip())

            # If a single line is too long, split it
            if len(line) > max_length:
                while line:
                    parts.append(line[:max_length])
                    line = line[max_length:]
                current_part = ""
            else:
                current_part = line + '\n'

    if current_part:
        parts.append(current_part.rstrip())

    return parts
