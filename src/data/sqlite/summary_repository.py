"""
SQLite implementation of summary repository.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import SummaryRepository, SearchCriteria
from ...models.summary import (
    SummaryResult,
    ActionItem,
    TechnicalTerm,
    Participant,
    SummarizationContext,
    SummaryWarning
)
from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


class SQLiteSummaryRepository(SummaryRepository):
    """SQLite implementation of summary repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_summary(self, summary: SummaryResult) -> str:
        """Save a summary to the database."""
        query = """
        INSERT OR REPLACE INTO summaries (
            id, channel_id, guild_id, start_time, end_time,
            message_count, summary_text, key_points, action_items,
            technical_terms, participants, metadata, created_at, context,
            prompt_system, prompt_user, prompt_template_id, source_content, warnings
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Serialize warnings
        warnings_data = []
        if hasattr(summary, 'warnings') and summary.warnings:
            warnings_data = [w.to_dict() if hasattr(w, 'to_dict') else {'code': w.code, 'message': w.message, 'details': getattr(w, 'details', {})} for w in summary.warnings]

        params = (
            summary.id,
            summary.channel_id,
            summary.guild_id,
            summary.start_time.isoformat(),
            summary.end_time.isoformat(),
            summary.message_count,
            summary.summary_text,
            json.dumps(summary.key_points),
            json.dumps([item.to_dict() for item in summary.action_items]),
            json.dumps([term.to_dict() for term in summary.technical_terms]),
            json.dumps([p.to_dict() for p in summary.participants]),
            json.dumps(summary.metadata),
            summary.created_at.isoformat(),
            json.dumps(summary.context.to_dict() if summary.context else {}),
            summary.prompt_system,
            summary.prompt_user,
            summary.prompt_template_id,
            summary.source_content,
            json.dumps(warnings_data),
        )

        await self.connection.execute(query, params)
        return summary.id

    async def get_summary(self, summary_id: str) -> Optional[SummaryResult]:
        """Retrieve a summary by its ID."""
        query = "SELECT * FROM summaries WHERE id = ?"
        row = await self.connection.fetch_one(query, (summary_id,))

        if not row:
            return None

        return self._row_to_summary(row)

    async def find_summaries(self, criteria: SearchCriteria) -> List[SummaryResult]:
        """Find summaries matching the given criteria."""
        conditions = []
        params = []

        if criteria.guild_id:
            conditions.append("guild_id = ?")
            params.append(criteria.guild_id)

        if criteria.channel_id:
            conditions.append("channel_id = ?")
            params.append(criteria.channel_id)

        if criteria.start_time:
            conditions.append("created_at >= ?")
            params.append(criteria.start_time.isoformat())

        if criteria.end_time:
            conditions.append("created_at <= ?")
            params.append(criteria.end_time.isoformat())

        if criteria.perspective:
            conditions.append("json_extract(metadata, '$.perspective') = ?")
            params.append(criteria.perspective)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
        SELECT * FROM summaries
        {where_clause}
        ORDER BY {criteria.order_by} {criteria.order_direction}
        LIMIT ? OFFSET ?
        """

        params.extend([criteria.limit, criteria.offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_summary(row) for row in rows]

    async def delete_summary(self, summary_id: str) -> bool:
        """Delete a summary from the database."""
        query = "DELETE FROM summaries WHERE id = ?"
        cursor = await self.connection.execute(query, (summary_id,))
        return cursor.rowcount > 0

    async def count_summaries(self, criteria: SearchCriteria) -> int:
        """Count summaries matching the given criteria."""
        conditions = []
        params = []

        if criteria.guild_id:
            conditions.append("guild_id = ?")
            params.append(criteria.guild_id)

        if criteria.channel_id:
            conditions.append("channel_id = ?")
            params.append(criteria.channel_id)

        if criteria.start_time:
            conditions.append("created_at >= ?")
            params.append(criteria.start_time.isoformat())

        if criteria.end_time:
            conditions.append("created_at <= ?")
            params.append(criteria.end_time.isoformat())

        if criteria.perspective:
            conditions.append("json_extract(metadata, '$.perspective') = ?")
            params.append(criteria.perspective)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"SELECT COUNT(*) as count FROM summaries {where_clause}"

        row = await self.connection.fetch_one(query, tuple(params))
        return row['count'] if row else 0

    async def get_summaries_by_channel(
        self,
        channel_id: str,
        limit: int = 10
    ) -> List[SummaryResult]:
        """Get recent summaries for a specific channel."""
        criteria = SearchCriteria(
            channel_id=channel_id,
            limit=limit,
            order_by="created_at",
            order_direction="DESC"
        )
        return await self.find_summaries(criteria)

    def _row_to_summary(self, row: Dict[str, Any]) -> SummaryResult:
        """Convert database row to SummaryResult object."""
        context_data = json.loads(row['context'])
        context = SummarizationContext(**context_data) if context_data else None

        # Load warnings if present
        warnings_data = json.loads(row.get('warnings') or '[]')
        warnings = [SummaryWarning(**w) for w in warnings_data]

        return SummaryResult(
            id=row['id'],
            channel_id=row['channel_id'],
            guild_id=row['guild_id'],
            start_time=datetime.fromisoformat(row['start_time']),
            end_time=datetime.fromisoformat(row['end_time']),
            message_count=row['message_count'],
            key_points=json.loads(row['key_points']),
            action_items=[ActionItem(**item) for item in json.loads(row['action_items'])],
            technical_terms=[TechnicalTerm(**term) for term in json.loads(row['technical_terms'])],
            participants=[Participant(**p) for p in json.loads(row['participants'])],
            summary_text=row['summary_text'],
            metadata=json.loads(row['metadata']),
            created_at=datetime.fromisoformat(row['created_at']),
            context=context,
            prompt_system=row.get('prompt_system'),
            prompt_user=row.get('prompt_user'),
            prompt_template_id=row.get('prompt_template_id'),
            source_content=row.get('source_content'),
            warnings=warnings,
        )
