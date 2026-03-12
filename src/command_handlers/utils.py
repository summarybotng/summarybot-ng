"""
Utility functions for command handlers.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import discord

from ..exceptions import UserError, create_error_context
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


def format_error_response(error_message: str, error_code: str = "ERROR") -> discord.Embed:
    """
    Format an error message as a Discord embed.

    Args:
        error_message: The error message to display
        error_code: Optional error code for debugging

    Returns:
        Discord embed with error formatting
    """
    embed = discord.Embed(
        title="❌ Error",
        description=error_message,
        color=0xFF0000,  # Red
        timestamp=utc_now_naive()
    )

    embed.set_footer(text=f"Error Code: {error_code}")

    return embed


def format_success_response(title: str, description: str,
                           fields: Optional[Dict[str, str]] = None) -> discord.Embed:
    """
    Format a success message as a Discord embed.

    Args:
        title: Embed title
        description: Main description text
        fields: Optional dictionary of field name -> value pairs

    Returns:
        Discord embed with success formatting
    """
    embed = discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=0x00FF00,  # Green
        timestamp=utc_now_naive()
    )

    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=False)

    return embed


def format_info_response(title: str, description: str,
                        fields: Optional[Dict[str, str]] = None) -> discord.Embed:
    """
    Format an informational message as a Discord embed.

    Args:
        title: Embed title
        description: Main description text
        fields: Optional dictionary of field name -> value pairs

    Returns:
        Discord embed with info formatting
    """
    embed = discord.Embed(
        title=f"ℹ️ {title}",
        description=description,
        color=0x4A90E2,  # Blue
        timestamp=utc_now_naive()
    )

    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=False)

    return embed


async def check_rate_limit(user_id: str, command: str,
                          max_requests: int = 5,
                          window_seconds: int = 60) -> Tuple[bool, Optional[int]]:
    """
    Check if user is within rate limit for a command.

    Args:
        user_id: Discord user ID
        command: Command name
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds

    Returns:
        Tuple of (is_allowed, seconds_until_reset)
    """
    # This is a placeholder - in production, this would use Redis or similar
    # For now, we'll return True (allowed)
    return True, None


async def defer_if_needed(interaction: discord.Interaction,
                         expected_duration: float = 3.0) -> bool:
    """
    Defer interaction response if operation will take longer than Discord's timeout.

    Args:
        interaction: Discord interaction object
        expected_duration: Expected operation duration in seconds

    Returns:
        True if deferred, False otherwise
    """
    # Discord requires response within 3 seconds
    if expected_duration > 2.5:  # Leave some buffer
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True)
                return True
        except Exception as e:
            logger.warning(f"Failed to defer interaction: {e}")

    return False


def validate_time_range(start_time: datetime, end_time: datetime,
                       max_hours: int = 168) -> None:
    """
    Validate that a time range is reasonable.

    Args:
        start_time: Start of time range
        end_time: End of time range
        max_hours: Maximum allowed hours in range

    Raises:
        UserError: If time range is invalid
    """
    # Check that start is before end
    if start_time >= end_time:
        raise UserError(
            message=f"Invalid time range: start={start_time}, end={end_time}",
            error_code="INVALID_TIME_RANGE",
            user_message="Start time must be before end time."
        )

    # Check time range isn't too large
    duration = end_time - start_time
    max_duration = timedelta(hours=max_hours)

    if duration > max_duration:
        raise UserError(
            message=f"Time range too large: {duration.total_seconds() / 3600} hours",
            error_code="TIME_RANGE_TOO_LARGE",
            user_message=f"Time range cannot exceed {max_hours} hours. Please choose a shorter time period."
        )

    # Check that times aren't in the future
    now = utc_now_naive()
    if end_time > now:
        raise UserError(
            message=f"End time in future: {end_time}",
            error_code="FUTURE_TIME",
            user_message="Cannot summarize messages from the future."
        )


def parse_time_string(time_str: str) -> datetime:
    """
    Parse a time string into a datetime object.

    Supports formats:
    - Relative: "1h", "30m", "2d", "1w"
    - ISO format: "2024-01-15T10:30:00"
    - Human readable: "2 hours ago", "yesterday"

    Args:
        time_str: Time string to parse

    Returns:
        Parsed datetime object

    Raises:
        UserError: If time string cannot be parsed
    """
    time_str = time_str.strip().lower()
    now = utc_now_naive()

    # Relative time formats
    relative_pattern = r'^(\d+)\s*(h|hour|hours|m|min|mins|minute|minutes|d|day|days|w|week|weeks)$'
    match = re.match(relative_pattern, time_str)

    if match:
        amount = int(match.group(1))
        unit = match.group(2)

        if unit in ('h', 'hour', 'hours'):
            return now - timedelta(hours=amount)
        elif unit in ('m', 'min', 'mins', 'minute', 'minutes'):
            return now - timedelta(minutes=amount)
        elif unit in ('d', 'day', 'days'):
            return now - timedelta(days=amount)
        elif unit in ('w', 'week', 'weeks'):
            return now - timedelta(weeks=amount)

    # "X ago" format
    ago_pattern = r'^(\d+)\s*(hour|hours|minute|minutes|day|days)\s+ago$'
    match = re.match(ago_pattern, time_str)

    if match:
        amount = int(match.group(1))
        unit = match.group(2)

        if unit in ('hour', 'hours'):
            return now - timedelta(hours=amount)
        elif unit in ('minute', 'minutes'):
            return now - timedelta(minutes=amount)
        elif unit in ('day', 'days'):
            return now - timedelta(days=amount)

    # Common keywords
    if time_str in ('yesterday', 'last 24 hours', '24h'):
        return now - timedelta(days=1)
    elif time_str == 'last week':
        return now - timedelta(weeks=1)
    elif time_str == 'today':
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ISO format
    try:
        return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
    except ValueError:
        pass

    # If nothing worked, raise error
    raise UserError(
        message=f"Unable to parse time string: {time_str}",
        error_code="INVALID_TIME_FORMAT",
        user_message=f"Could not understand time format '{time_str}'. Try formats like '1h', '30m', '2 days ago', or ISO format."
    )


def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "2h 30m" or "45s"
    """
    if seconds < 60:
        return f"{int(seconds)}s"

    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)

    if minutes < 60:
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    if hours < 24:
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"

    days = hours // 24
    remaining_hours = hours % 24

    if remaining_hours > 0:
        return f"{days}d {remaining_hours}h"
    return f"{days}d"


def truncate_text(text: str, max_length: int = 1024,
                 suffix: str = "...") -> str:
    """
    Truncate text to fit within Discord's field limits.

    Args:
        text: Text to truncate
        max_length: Maximum length (default: 1024 for Discord fields)
        suffix: Suffix to add when truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def extract_channel_id(channel_mention: str) -> Optional[str]:
    """
    Extract channel ID from a mention string.

    Args:
        channel_mention: Channel mention like "<#123456789>"

    Returns:
        Channel ID or None if not a valid mention
    """
    match = re.match(r'^<#(\d+)>$', channel_mention)
    if match:
        return match.group(1)

    # Also accept plain ID
    if channel_mention.isdigit():
        return channel_mention

    return None


def create_progress_bar(current: int, total: int, length: int = 10) -> str:
    """
    Create a text-based progress bar.

    Args:
        current: Current progress
        total: Total amount
        length: Length of progress bar in characters

    Returns:
        Progress bar string like "[####------] 40%"
    """
    if total == 0:
        percentage = 0
    else:
        percentage = min(100, int((current / total) * 100))

    filled = int((percentage / 100) * length)
    bar = "█" * filled + "░" * (length - filled)

    return f"[{bar}] {percentage}%"
