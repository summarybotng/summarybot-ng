"""
Time utilities for consistent UTC handling.

Phase 4: Replace deprecated datetime.utcnow() with timezone-aware datetime.now(timezone.utc).

The datetime.utcnow() method is deprecated in Python 3.12+ because it returns a naive
datetime object without timezone info, which can lead to subtle bugs when comparing
with timezone-aware datetimes.

Usage:
    from src.utils.time import utc_now

    # Instead of: datetime.utcnow()
    now = utc_now()
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Get current UTC time as a timezone-aware datetime.

    This replaces datetime.utcnow() which is deprecated in Python 3.12+.
    Returns a timezone-aware datetime in UTC.

    Returns:
        Current UTC time with timezone info
    """
    return datetime.now(timezone.utc)


def utc_now_naive() -> datetime:
    """Get current UTC time as a naive datetime (for backward compatibility).

    Use this only when you need a naive datetime for compatibility with
    existing code that expects naive datetimes. Prefer utc_now() for new code.

    Returns:
        Current UTC time without timezone info
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
