"""
Filter dataclasses for SQLite queries.

CS-002: Shared filter logic to eliminate duplication.
"""

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class StoredSummaryFilter:
    """Filter parameters for stored summary queries.

    Used by find_by_guild and count_by_guild to avoid duplicating filter logic.
    """
    guild_id: str
    pinned_only: bool = False
    include_archived: bool = False
    tags: Optional[List[str]] = None
    source: Optional[str] = None  # ADR-008: Filter by source
    # ADR-017: Enhanced filtering
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    archive_period: Optional[str] = None
    channel_mode: Optional[str] = None  # "single" or "multi"
    has_grounding: Optional[bool] = None
    # ADR-018: Content-based filters
    has_key_points: Optional[bool] = None
    has_action_items: Optional[bool] = None
    has_participants: Optional[bool] = None
    min_message_count: Optional[int] = None
    max_message_count: Optional[int] = None
    # ADR-021: Content count filters
    min_key_points: Optional[int] = None
    max_key_points: Optional[int] = None
    min_action_items: Optional[int] = None
    max_action_items: Optional[int] = None
    min_participants: Optional[int] = None
    max_participants: Optional[int] = None
    # ADR-026: Platform filter
    platform: Optional[str] = None
    # ADR-035: Generation settings filters
    summary_length: Optional[str] = None  # 'brief' | 'detailed' | 'comprehensive'
    perspective: Optional[str] = None  # 'general' | 'developer' | etc.
    exclude_custom_perspectives: Optional[bool] = None  # True = exclude summaries with custom prompt templates
    # ADR-041: Access issues filter
    has_access_issues: Optional[bool] = None  # True = partial access, False = full access
