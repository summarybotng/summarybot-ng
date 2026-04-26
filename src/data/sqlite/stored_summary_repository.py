"""
SQLite implementation of stored summary repository (ADR-005).
"""

import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from ..base import StoredSummaryRepository
from src.utils.time import utc_now_naive
from ...models.summary import (
    SummaryResult,
    ActionItem,
    TechnicalTerm,
    Participant,
    SummarizationContext,
    SummaryWarning
)
from ...models.stored_summary import StoredSummary, PushDelivery, SummarySource
from .connection import SQLiteConnection
from .filters import StoredSummaryFilter

logger = logging.getLogger(__name__)


class SQLiteStoredSummaryRepository(StoredSummaryRepository):
    """SQLite implementation of stored summary repository (ADR-005)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save(self, summary: StoredSummary) -> str:
        """Save a stored summary to the database."""
        # ADR-016: Validate regeneration capability and log warnings
        regen_status = summary.validate_regeneration()
        if not regen_status["can_regenerate"]:
            logger.warning(
                f"Storing summary {summary.id} without regeneration capability: "
                f"{', '.join(regen_status['issues'])}"
            )
        elif regen_status["issues"]:
            logger.info(
                f"Summary {summary.id} can regenerate via {regen_status['method']}, "
                f"but has issues: {', '.join(regen_status['issues'])}"
            )

        # ADR-017: Extract message_count from summary_result for sortable column
        message_count = 0
        participant_count = 0
        if summary.summary_result:
            message_count = summary.summary_result.message_count or 0
            participant_count = len(summary.summary_result.participants) if summary.summary_result.participants else 0

        query = """
        INSERT OR REPLACE INTO stored_summaries (
            id, guild_id, source_channel_ids, schedule_id,
            summary_json, created_at, viewed_at, pushed_at,
            push_deliveries, title, is_pinned, is_archived, tags,
            source, archive_period, archive_granularity, archive_source_key,
            message_count, participant_count,
            wiki_ingested, wiki_ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            summary.id,
            summary.guild_id,
            json.dumps(summary.source_channel_ids),
            summary.schedule_id,
            json.dumps(summary.summary_result.to_dict() if summary.summary_result else {}),
            summary.created_at.isoformat(),
            summary.viewed_at.isoformat() if summary.viewed_at else None,
            summary.pushed_at.isoformat() if summary.pushed_at else None,
            json.dumps([d.to_dict() for d in summary.push_deliveries]),
            summary.title,
            summary.is_pinned,
            summary.is_archived,
            json.dumps(summary.tags),
            # ADR-008: Source tracking
            summary.source.value,
            summary.archive_period,
            summary.archive_granularity,
            summary.archive_source_key,
            # ADR-017: Sortable columns
            message_count,
            participant_count,
            # ADR-067: Wiki ingestion tracking
            summary.wiki_ingested,
            summary.wiki_ingested_at.isoformat() if summary.wiki_ingested_at else None,
        )

        await self.connection.execute(query, params)

        # ADR-020: Populate FTS table for search
        await self._update_fts(summary)

        return summary.id

    async def _update_fts(self, summary: StoredSummary) -> None:
        """Update FTS index for a summary (ADR-020)."""
        try:
            # Delete existing FTS entry
            await self.connection.execute(
                "DELETE FROM summary_fts WHERE summary_id = ?",
                (summary.id,)
            )

            # Extract searchable content
            sr = summary.summary_result
            if not sr:
                return

            summary_text = sr.summary_text or ""
            key_points = " ".join(sr.key_points) if sr.key_points else ""
            action_items = " ".join(
                item.description for item in sr.action_items
            ) if sr.action_items else ""
            participants = " ".join(
                f"{p.display_name} {p.user_id}" for p in sr.participants
            ) if sr.participants else ""
            technical_terms = " ".join(
                term.term for term in sr.technical_terms
            ) if sr.technical_terms else ""

            # Insert into FTS
            await self.connection.execute(
                """INSERT INTO summary_fts
                   (summary_id, guild_id, summary_text, key_points, action_items, participants, technical_terms)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (summary.id, summary.guild_id, summary_text, key_points, action_items, participants, technical_terms)
            )
        except Exception as e:
            # FTS is optional - don't fail the save if FTS update fails
            logger.warning(f"Failed to update FTS for summary {summary.id}: {e}")

    async def get(self, summary_id: str) -> Optional[StoredSummary]:
        """Retrieve a stored summary by its ID."""
        query = "SELECT * FROM stored_summaries WHERE id = ?"
        row = await self.connection.fetch_one(query, (summary_id,))

        if not row:
            return None

        return self._row_to_stored_summary(row)

    def _build_filter_clause(self, filter: StoredSummaryFilter) -> Tuple[str, List[Any]]:
        """Build WHERE clause and params from filter.

        CS-002: Shared filter logic for find_by_guild and count_by_guild.

        Args:
            filter: StoredSummaryFilter with all filter parameters

        Returns:
            Tuple of (where_clause, params_list)
        """
        conditions = ["guild_id = ?"]
        params: List[Any] = [filter.guild_id]

        if filter.pinned_only:
            conditions.append("is_pinned = 1")

        if not filter.include_archived:
            conditions.append("is_archived = 0")

        # ADR-008: Source filtering
        if filter.source and filter.source != "all":
            conditions.append("source = ?")
            params.append(filter.source)

        # ADR-017: Date range filtering
        if filter.created_after:
            conditions.append("created_at >= ?")
            params.append(filter.created_after.isoformat())

        if filter.created_before:
            conditions.append("created_at <= ?")
            params.append(filter.created_before.isoformat())

        # ADR-017: Archive period filtering
        if filter.archive_period:
            conditions.append("archive_period = ?")
            params.append(filter.archive_period)

        # ADR-017: Channel mode filtering (single vs multi-channel)
        if filter.channel_mode == "single":
            conditions.append("json_array_length(source_channel_ids) = 1")
        elif filter.channel_mode == "multi":
            conditions.append("json_array_length(source_channel_ids) > 1")

        # ADR-017: Grounding filter
        if filter.has_grounding is True:
            conditions.append("json_array_length(json_extract(summary_json, '$.reference_index')) > 0")
        elif filter.has_grounding is False:
            conditions.append("(json_extract(summary_json, '$.reference_index') IS NULL OR json_array_length(json_extract(summary_json, '$.reference_index')) = 0)")

        # ADR-018: Content-based filters
        if filter.has_key_points is True:
            conditions.append("json_array_length(json_extract(summary_json, '$.key_points')) > 0")
        elif filter.has_key_points is False:
            conditions.append("(json_extract(summary_json, '$.key_points') IS NULL OR json_array_length(json_extract(summary_json, '$.key_points')) = 0)")

        if filter.has_action_items is True:
            conditions.append("json_array_length(json_extract(summary_json, '$.action_items')) > 0")
        elif filter.has_action_items is False:
            conditions.append("(json_extract(summary_json, '$.action_items') IS NULL OR json_array_length(json_extract(summary_json, '$.action_items')) = 0)")

        if filter.has_participants is True:
            conditions.append("json_array_length(json_extract(summary_json, '$.participants')) > 0")
        elif filter.has_participants is False:
            conditions.append("(json_extract(summary_json, '$.participants') IS NULL OR json_array_length(json_extract(summary_json, '$.participants')) = 0)")

        if filter.min_message_count is not None:
            conditions.append("message_count >= ?")
            params.append(filter.min_message_count)

        if filter.max_message_count is not None:
            conditions.append("message_count <= ?")
            params.append(filter.max_message_count)

        # ADR-021: Content count filters
        if filter.min_key_points is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.key_points')), 0) >= ?")
            params.append(filter.min_key_points)

        if filter.max_key_points is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.key_points')), 0) <= ?")
            params.append(filter.max_key_points)

        if filter.min_action_items is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.action_items')), 0) >= ?")
            params.append(filter.min_action_items)

        if filter.max_action_items is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.action_items')), 0) <= ?")
            params.append(filter.max_action_items)

        if filter.min_participants is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.participants')), 0) >= ?")
            params.append(filter.min_participants)

        if filter.max_participants is not None:
            conditions.append("COALESCE(json_array_length(json_extract(summary_json, '$.participants')), 0) <= ?")
            params.append(filter.max_participants)

        # ADR-026: Platform filter (filters by archive_source_key prefix)
        if filter.platform and filter.platform != "all":
            conditions.append("archive_source_key LIKE ?")
            params.append(f"{filter.platform}:%")

        # ADR-035: Generation settings filters (stored in summary_json.metadata)
        if filter.summary_length:
            conditions.append("json_extract(summary_json, '$.metadata.summary_length') = ?")
            params.append(filter.summary_length)

        if filter.perspective:
            # Case-insensitive match for perspective
            conditions.append("LOWER(json_extract(summary_json, '$.metadata.perspective')) = LOWER(?)")
            params.append(filter.perspective)

        # ADR-041: Access issues filter (partial coverage detection)
        if filter.has_access_issues is True:
            conditions.append("json_extract(summary_json, '$.metadata.has_access_issues') = 1")
        elif filter.has_access_issues is False:
            conditions.append("(json_extract(summary_json, '$.metadata.has_access_issues') IS NULL OR json_extract(summary_json, '$.metadata.has_access_issues') = 0)")

        where_clause = " AND ".join(conditions)
        return where_clause, params

    async def find_by_guild(
        self,
        guild_id: str,
        limit: int = 20,
        offset: int = 0,
        pinned_only: bool = False,
        include_archived: bool = False,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,  # ADR-008: Filter by source
        # ADR-017: Enhanced filtering
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        archive_period: Optional[str] = None,
        channel_mode: Optional[str] = None,  # "single" or "multi"
        has_grounding: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        # ADR-018: Content-based filters
        has_key_points: Optional[bool] = None,
        has_action_items: Optional[bool] = None,
        has_participants: Optional[bool] = None,
        min_message_count: Optional[int] = None,
        max_message_count: Optional[int] = None,
        # ADR-021: Content count filters
        min_key_points: Optional[int] = None,
        max_key_points: Optional[int] = None,
        min_action_items: Optional[int] = None,
        max_action_items: Optional[int] = None,
        min_participants: Optional[int] = None,
        max_participants: Optional[int] = None,
        # ADR-026: Platform filter (discord, whatsapp, etc.)
        platform: Optional[str] = None,
        # ADR-035: Generation settings filters
        summary_length: Optional[str] = None,
        perspective: Optional[str] = None,
        # ADR-041: Access issues filter
        has_access_issues: Optional[bool] = None,
    ) -> List[StoredSummary]:
        """Find stored summaries for a guild.

        Args:
            guild_id: Discord guild/server ID
            limit: Maximum number of results
            offset: Pagination offset
            pinned_only: Only return pinned summaries
            include_archived: Include archived summaries
            tags: Filter by any of these tags
            source: ADR-008 - Filter by source type (realtime, archive, etc.)
                    Use "all" or None for no filtering
            created_after: ADR-017 - Filter by creation date (after)
            created_before: ADR-017 - Filter by creation date (before)
            archive_period: ADR-017 - Filter by archive period (e.g., "2026-01-15")
            channel_mode: ADR-017 - "single" for single-channel, "multi" for multi-channel
            has_grounding: ADR-017 - Filter by grounding status
            sort_by: ADR-017 - Sort field (created_at, message_count)
            sort_order: ADR-017 - Sort direction (asc, desc)

        Returns:
            List of matching StoredSummary objects
        """
        # CS-002: Use shared filter builder
        filter_obj = StoredSummaryFilter(
            guild_id=guild_id,
            pinned_only=pinned_only,
            include_archived=include_archived,
            tags=tags,
            source=source,
            created_after=created_after,
            created_before=created_before,
            archive_period=archive_period,
            channel_mode=channel_mode,
            has_grounding=has_grounding,
            has_key_points=has_key_points,
            has_action_items=has_action_items,
            has_participants=has_participants,
            min_message_count=min_message_count,
            max_message_count=max_message_count,
            min_key_points=min_key_points,
            max_key_points=max_key_points,
            min_action_items=min_action_items,
            max_action_items=max_action_items,
            min_participants=min_participants,
            max_participants=max_participants,
            platform=platform,
            summary_length=summary_length,
            perspective=perspective,
            has_access_issues=has_access_issues,
        )
        where_clause, params = self._build_filter_clause(filter_obj)

        # ADR-017: Dynamic sorting
        valid_sort_fields = {"created_at", "message_count", "archive_period"}
        if sort_by not in valid_sort_fields:
            sort_by = "created_at"
        sort_direction = "ASC" if sort_order.lower() == "asc" else "DESC"

        # Handle NULL values for sorting - use COALESCE for message_count
        if sort_by == "message_count":
            sort_field = f"COALESCE({sort_by}, 0)"
        else:
            sort_field = sort_by

        # Always sort pinned first, then by the selected field
        order_clause = f"is_pinned DESC, {sort_field} {sort_direction}"

        query = f"""
        SELECT * FROM stored_summaries
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        summaries = [self._row_to_stored_summary(row) for row in rows]

        # Filter by tags in Python (SQLite JSON support is limited)
        if tags:
            summaries = [
                s for s in summaries
                if any(tag in s.tags for tag in tags)
            ]

        return summaries

    async def count_by_guild(
        self,
        guild_id: str,
        include_archived: bool = False,
        source: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        archive_period: Optional[str] = None,
        channel_mode: Optional[str] = None,
        has_grounding: Optional[bool] = None,
        # ADR-018: Content-based filters
        has_key_points: Optional[bool] = None,
        has_action_items: Optional[bool] = None,
        has_participants: Optional[bool] = None,
        min_message_count: Optional[int] = None,
        max_message_count: Optional[int] = None,
        # ADR-021: Content count filters
        min_key_points: Optional[int] = None,
        max_key_points: Optional[int] = None,
        min_action_items: Optional[int] = None,
        max_action_items: Optional[int] = None,
        min_participants: Optional[int] = None,
        max_participants: Optional[int] = None,
        # ADR-026: Platform filter
        platform: Optional[str] = None,
        # ADR-035: Generation settings filters
        summary_length: Optional[str] = None,
        perspective: Optional[str] = None,
        # ADR-041: Access issues filter
        has_access_issues: Optional[bool] = None,
    ) -> int:
        """Count stored summaries for a guild with optional filters (ADR-017, ADR-018, ADR-021, ADR-026, ADR-035, ADR-041)."""
        # CS-002: Use shared filter builder
        filter_obj = StoredSummaryFilter(
            guild_id=guild_id,
            include_archived=include_archived,
            source=source,
            created_after=created_after,
            created_before=created_before,
            archive_period=archive_period,
            channel_mode=channel_mode,
            has_grounding=has_grounding,
            has_key_points=has_key_points,
            has_action_items=has_action_items,
            has_participants=has_participants,
            min_message_count=min_message_count,
            max_message_count=max_message_count,
            min_key_points=min_key_points,
            max_key_points=max_key_points,
            min_action_items=min_action_items,
            max_action_items=max_action_items,
            min_participants=min_participants,
            max_participants=max_participants,
            platform=platform,
            summary_length=summary_length,
            perspective=perspective,
            has_access_issues=has_access_issues,
        )
        where_clause, params = self._build_filter_clause(filter_obj)

        query = f"SELECT COUNT(*) as count FROM stored_summaries WHERE {where_clause}"

        row = await self.connection.fetch_one(query, tuple(params))
        return row['count'] if row else 0

    async def get_calendar_data(
        self,
        guild_id: str,
        year: int,
        month: int,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get summary counts grouped by day for calendar view (ADR-017).

        Returns list of dicts with: date, count, sources, has_incomplete.
        Uses archive_period for archive summaries, created_at for others.
        """
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        if not include_archived:
            conditions.append("is_archived = 0")

        # Use archive_period for archive summaries, created_at for others
        # This ensures archive summaries appear on their content date, not generation date
        date_expr = "COALESCE(archive_period, DATE(created_at))"

        # Filter by year and month using the effective date
        conditions.append(f"strftime('%Y', {date_expr}) = ?")
        conditions.append(f"strftime('%m', {date_expr}) = ?")
        params.extend([str(year), f"{month:02d}"])

        where_clause = " AND ".join(conditions)

        query = f"""
        SELECT
            {date_expr} as date,
            COUNT(*) as count,
            GROUP_CONCAT(DISTINCT source) as sources,
            SUM(CASE WHEN source_channel_ids = '[]' OR source_channel_ids IS NULL THEN 1 ELSE 0 END) as incomplete_count
        FROM stored_summaries
        WHERE {where_clause}
        GROUP BY {date_expr}
        ORDER BY date
        """

        rows = await self.connection.fetch_all(query, tuple(params))
        return [
            {
                "date": row["date"],
                "count": row["count"],
                "sources": row["sources"].split(",") if row["sources"] else [],
                "has_incomplete": row["incomplete_count"] > 0,
            }
            for row in rows
        ]

    async def update(self, summary: StoredSummary) -> bool:
        """Update a stored summary.

        Note: This also updates summary_json to support regeneration where
        the summary_result is replaced with new content.
        """
        query = """
        UPDATE stored_summaries SET
            summary_json = ?,
            viewed_at = ?,
            pushed_at = ?,
            push_deliveries = ?,
            title = ?,
            is_pinned = ?,
            is_archived = ?,
            tags = ?
        WHERE id = ?
        """

        params = (
            json.dumps(summary.summary_result.to_dict() if summary.summary_result else {}),
            summary.viewed_at.isoformat() if summary.viewed_at else None,
            summary.pushed_at.isoformat() if summary.pushed_at else None,
            json.dumps([d.to_dict() for d in summary.push_deliveries]),
            summary.title,
            summary.is_pinned,
            summary.is_archived,
            json.dumps(summary.tags),
            summary.id,
        )

        cursor = await self.connection.execute(query, params)

        # ADR-020: Update FTS index
        if cursor.rowcount > 0:
            await self._update_fts(summary)

        return cursor.rowcount > 0

    async def delete(self, summary_id: str) -> bool:
        """Delete a stored summary."""
        # ADR-020: Delete from FTS first
        try:
            await self.connection.execute(
                "DELETE FROM summary_fts WHERE summary_id = ?",
                (summary_id,)
            )
        except Exception:
            pass  # FTS table might not exist yet

        query = "DELETE FROM stored_summaries WHERE id = ?"
        cursor = await self.connection.execute(query, (summary_id,))
        return cursor.rowcount > 0

    async def bulk_delete(self, summary_ids: List[str], guild_id: str) -> Dict[str, Any]:
        """Delete multiple stored summaries (ADR-018).

        Args:
            summary_ids: List of summary IDs to delete
            guild_id: Guild ID for access control

        Returns:
            Dict with deleted_count, failed_ids, errors
        """
        if not summary_ids:
            return {"deleted_count": 0, "failed_ids": [], "errors": []}

        deleted_count = 0
        failed_ids = []
        errors = []

        # Delete in batches to avoid SQL parameter limits
        batch_size = 100
        for i in range(0, len(summary_ids), batch_size):
            batch = summary_ids[i:i + batch_size]
            placeholders = ",".join(["?" for _ in batch])

            # Only delete summaries belonging to this guild
            query = f"""
            DELETE FROM stored_summaries
            WHERE id IN ({placeholders}) AND guild_id = ?
            """

            try:
                cursor = await self.connection.execute(query, tuple(batch) + (guild_id,))
                deleted_count += cursor.rowcount
            except Exception as e:
                logger.error(f"Bulk delete batch failed: {e}")
                failed_ids.extend(batch)
                errors.append(str(e))

        return {
            "deleted_count": deleted_count,
            "failed_ids": failed_ids,
            "errors": errors,
        }

    async def find_by_schedule(
        self,
        schedule_id: str,
        limit: int = 10,
    ) -> List[StoredSummary]:
        """Find stored summaries created by a specific schedule."""
        query = """
        SELECT * FROM stored_summaries
        WHERE schedule_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """

        rows = await self.connection.fetch_all(query, (schedule_id, limit))
        return [self._row_to_stored_summary(row) for row in rows]

    def _row_to_stored_summary(self, row: Dict[str, Any]) -> StoredSummary:
        """Convert database row to StoredSummary object."""
        # Parse summary_result JSON back to SummaryResult
        summary_data = json.loads(row['summary_json'])
        summary_result = None
        if summary_data:
            # Reconstruct SummaryResult from dict
            summary_result = self._dict_to_summary_result(summary_data)

        # Parse push deliveries
        push_deliveries_data = json.loads(row.get('push_deliveries') or '[]')
        push_deliveries = [PushDelivery.from_dict(d) for d in push_deliveries_data]

        # ADR-008: Parse source enum
        source_str = row.get('source', 'realtime')
        try:
            source = SummarySource(source_str)
        except ValueError:
            source = SummarySource.REALTIME

        return StoredSummary(
            id=row['id'],
            guild_id=row['guild_id'],
            source_channel_ids=json.loads(row['source_channel_ids']),
            schedule_id=row['schedule_id'],
            summary_result=summary_result,
            created_at=datetime.fromisoformat(row['created_at']),
            viewed_at=datetime.fromisoformat(row['viewed_at']) if row['viewed_at'] else None,
            pushed_at=datetime.fromisoformat(row['pushed_at']) if row['pushed_at'] else None,
            push_deliveries=push_deliveries,
            title=row['title'],
            is_pinned=bool(row['is_pinned']),
            is_archived=bool(row['is_archived']),
            tags=json.loads(row.get('tags') or '[]'),
            # ADR-008: Source tracking
            source=source,
            archive_period=row.get('archive_period'),
            archive_granularity=row.get('archive_granularity'),
            archive_source_key=row.get('archive_source_key'),
            # ADR-067: Wiki ingestion tracking
            wiki_ingested=bool(row.get('wiki_ingested', False)),
            wiki_ingested_at=datetime.fromisoformat(row['wiki_ingested_at']) if row.get('wiki_ingested_at') else None,
        )

    def _dict_to_summary_result(self, data: Dict[str, Any]) -> SummaryResult:
        """Convert dictionary to SummaryResult object."""
        # Handle nested objects
        # ActionItem expects 'description' but JSON may have 'text'
        action_items = []
        for item in data.get('action_items', []):
            if 'text' in item and 'description' not in item:
                item = {**item, 'description': item.pop('text')}
            action_items.append(ActionItem(**item))
        technical_terms = [TechnicalTerm(**term) for term in data.get('technical_terms', [])]
        participants = [Participant(**p) for p in data.get('participants', [])]

        context = None
        if data.get('context'):
            context = SummarizationContext(**data['context'])

        # Parse warnings
        warnings = []
        if data.get('warnings'):
            warnings = [SummaryWarning(**w) for w in data['warnings']]

        return SummaryResult(
            id=data.get('id', ''),
            channel_id=data.get('channel_id', ''),
            guild_id=data.get('guild_id', ''),
            start_time=datetime.fromisoformat(data['start_time']) if data.get('start_time') else utc_now_naive(),
            end_time=datetime.fromisoformat(data['end_time']) if data.get('end_time') else utc_now_naive(),
            message_count=data.get('message_count', 0),
            key_points=data.get('key_points', []),
            action_items=action_items,
            technical_terms=technical_terms,
            participants=participants,
            summary_text=data.get('summary_text', ''),
            metadata=data.get('metadata', {}),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else utc_now_naive(),
            context=context,
            prompt_system=data.get('prompt_system'),
            prompt_user=data.get('prompt_user'),
            prompt_template_id=data.get('prompt_template_id'),
            source_content=data.get('source_content'),
            warnings=warnings,
            referenced_key_points=data.get('referenced_key_points', []),
            referenced_action_items=data.get('referenced_action_items', []),
            referenced_decisions=data.get('referenced_decisions', []),
            reference_index=data.get('reference_index', []),
        )

    # ADR-020: Navigation and Search

    async def get_navigation(
        self,
        summary_id: str,
        guild_id: str,
        source: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """Get previous/next summary IDs for navigation."""
        # First, get the current summary's created_at
        current_query = "SELECT created_at FROM stored_summaries WHERE id = ? AND guild_id = ?"
        current_row = await self.connection.fetch_one(current_query, (summary_id, guild_id))

        if not current_row:
            return {"previous_id": None, "previous_date": None, "next_id": None, "next_date": None}

        current_time = current_row["created_at"]

        # Build conditions
        base_conditions = ["guild_id = ?"]
        params_base: List[Any] = [guild_id]

        if source and source != "all":
            base_conditions.append("source = ?")
            params_base.append(source)

        base_where = " AND ".join(base_conditions)

        # Get previous (older) summary
        prev_query = f"""
        SELECT id, archive_period, created_at
        FROM stored_summaries
        WHERE {base_where} AND created_at < ?
        ORDER BY created_at DESC
        LIMIT 1
        """
        prev_row = await self.connection.fetch_one(
            prev_query, tuple(params_base) + (current_time,)
        )

        # Get next (newer) summary
        next_query = f"""
        SELECT id, archive_period, created_at
        FROM stored_summaries
        WHERE {base_where} AND created_at > ?
        ORDER BY created_at ASC
        LIMIT 1
        """
        next_row = await self.connection.fetch_one(
            next_query, tuple(params_base) + (current_time,)
        )

        return {
            "previous_id": prev_row["id"] if prev_row else None,
            "previous_date": prev_row["archive_period"] or prev_row["created_at"][:10] if prev_row else None,
            "next_id": next_row["id"] if next_row else None,
            "next_date": next_row["archive_period"] or next_row["created_at"][:10] if next_row else None,
        }

    async def search(
        self,
        guild_id: str,
        query: str,
        fields: Optional[List[str]] = None,
        source: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Full-text search across summary content using FTS5."""
        # Build the FTS query with optional field restrictions
        if fields:
            # Search specific fields: {field1 field2}: query
            field_spec = " ".join(fields)
            fts_match = f"{{summary_text key_points action_items participants technical_terms}}: {query}"
            if all(f in ["summary_text", "key_points", "action_items", "participants", "technical_terms"] for f in fields):
                fts_match = f"{{{field_spec}}}: {query}"
        else:
            fts_match = query

        # Build the main query with joins
        conditions = ["fts.guild_id = ?"]
        params: List[Any] = [guild_id]

        if source and source != "all":
            conditions.append("s.source = ?")
            params.append(source)

        if date_from:
            conditions.append("s.created_at >= ?")
            params.append(date_from.isoformat())

        if date_to:
            conditions.append("s.created_at <= ?")
            params.append(date_to.isoformat())

        where_clause = " AND ".join(conditions)

        # Count total matches
        count_query = f"""
        SELECT COUNT(*) as total
        FROM summary_fts fts
        JOIN stored_summaries s ON fts.summary_id = s.id
        WHERE fts MATCH ? AND {where_clause}
        """
        count_row = await self.connection.fetch_one(count_query, (fts_match,) + tuple(params))
        total = count_row["total"] if count_row else 0

        # Get matching results with snippets
        search_query = f"""
        SELECT
            s.id,
            s.title,
            s.archive_period,
            s.created_at,
            s.source,
            bm25(fts) as relevance_score,
            snippet(fts, 1, '<mark>', '</mark>', '...', 32) as summary_snippet,
            snippet(fts, 2, '<mark>', '</mark>', '...', 32) as key_points_snippet,
            snippet(fts, 3, '<mark>', '</mark>', '...', 32) as action_items_snippet
        FROM summary_fts fts
        JOIN stored_summaries s ON fts.summary_id = s.id
        WHERE fts MATCH ? AND {where_clause}
        ORDER BY relevance_score
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = await self.connection.fetch_all(search_query, (fts_match,) + tuple(params))

        items = []
        for row in rows:
            highlights = []
            if row["summary_snippet"] and "<mark>" in row["summary_snippet"]:
                highlights.append({"field": "summary_text", "snippet": row["summary_snippet"]})
            if row["key_points_snippet"] and "<mark>" in row["key_points_snippet"]:
                highlights.append({"field": "key_points", "snippet": row["key_points_snippet"]})
            if row["action_items_snippet"] and "<mark>" in row["action_items_snippet"]:
                highlights.append({"field": "action_items", "snippet": row["action_items_snippet"]})

            items.append({
                "id": row["id"],
                "title": row["title"],
                "archive_period": row["archive_period"],
                "created_at": row["created_at"],
                "source": row["source"],
                "relevance_score": abs(row["relevance_score"]),  # bm25 returns negative values
                "highlights": highlights,
            })

        return {
            "query": query,
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }

    async def search_by_participant(
        self,
        guild_id: str,
        user_id: Optional[str] = None,
        display_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Find summaries by participant."""
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        # Build participant search condition
        participant_conditions = []
        if user_id:
            participant_conditions.append(
                "EXISTS (SELECT 1 FROM json_each(json_extract(summary_json, '$.participants')) "
                "WHERE json_extract(value, '$.user_id') = ?)"
            )
            params.append(user_id)

        if display_name:
            participant_conditions.append(
                "EXISTS (SELECT 1 FROM json_each(json_extract(summary_json, '$.participants')) "
                "WHERE json_extract(value, '$.display_name') LIKE ?)"
            )
            params.append(f"%{display_name}%")

        if participant_conditions:
            conditions.append(f"({' OR '.join(participant_conditions)})")

        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from.isoformat())

        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to.isoformat())

        where_clause = " AND ".join(conditions)

        # Count total
        count_query = f"SELECT COUNT(*) as total FROM stored_summaries WHERE {where_clause}"
        count_row = await self.connection.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        # Get matching summaries
        search_query = f"""
        SELECT id, title, archive_period, created_at, source,
               json_extract(summary_json, '$.participants') as participants,
               json_extract(summary_json, '$.message_count') as message_count
        FROM stored_summaries
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = await self.connection.fetch_all(search_query, tuple(params))

        # Build participant info from first result if searching by user_id
        participant_info = None
        if user_id and rows:
            # Aggregate participant stats across all matching summaries
            total_messages = 0
            found_name = None
            for row in rows:
                participants = json.loads(row["participants"] or "[]")
                for p in participants:
                    if p.get("user_id") == user_id:
                        found_name = found_name or p.get("display_name")
                        total_messages += p.get("message_count", 0)

            participant_info = {
                "user_id": user_id,
                "display_name": found_name or display_name or "Unknown",
                "total_summaries": total,
                "total_messages": total_messages,
            }

        items = []
        for row in rows:
            participants = json.loads(row["participants"] or "[]")

            # Find key contributions from matching participant
            contributions = []
            for p in participants:
                if (user_id and p.get("user_id") == user_id) or \
                   (display_name and display_name.lower() in (p.get("display_name") or "").lower()):
                    contributions = p.get("contributions", [])[:3] if p.get("contributions") else []
                    break

            items.append({
                "id": row["id"],
                "title": row["title"],
                "archive_period": row["archive_period"],
                "created_at": row["created_at"],
                "source": row["source"],
                "message_count": row["message_count"] or 0,
                "key_contributions": contributions,
            })

        return {
            "participant": participant_info,
            "total": total,
            "limit": limit,
            "offset": offset,
            "summaries": items,
        }

    # ADR-067: Wiki ingestion tracking

    async def mark_wiki_ingested(self, summary_id: str) -> bool:
        """Mark a summary as ingested into wiki."""
        query = """
        UPDATE stored_summaries
        SET wiki_ingested = 1, wiki_ingested_at = ?
        WHERE id = ?
        """
        cursor = await self.connection.execute(
            query, (utc_now_naive().isoformat(), summary_id)
        )
        return cursor.rowcount > 0

    async def find_not_wiki_ingested(
        self,
        guild_id: str,
        limit: int = 50,
    ) -> List[StoredSummary]:
        """Find summaries that haven't been ingested into wiki."""
        query = """
        SELECT * FROM stored_summaries
        WHERE guild_id = ? AND (wiki_ingested = 0 OR wiki_ingested IS NULL)
        ORDER BY created_at DESC
        LIMIT ?
        """
        rows = await self.connection.fetch_all(query, (guild_id, limit))
        return [self._row_to_stored_summary(row) for row in rows]
