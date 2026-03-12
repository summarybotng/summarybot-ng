"""
SQLite implementation of error log repository.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from ..base import ErrorRepository
from ...models.error_log import ErrorLog, ErrorType, ErrorSeverity
from .connection import SQLiteConnection
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class SQLiteErrorRepository(ErrorRepository):
    """SQLite implementation of error log repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_error(self, error: ErrorLog) -> str:
        """Save an error log entry."""
        query = """
        INSERT OR REPLACE INTO error_logs (
            id, guild_id, channel_id, error_type, severity, error_code,
            message, details, operation, user_id, stack_trace,
            created_at, resolved_at, resolution_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            error.id,
            error.guild_id,
            error.channel_id,
            error.error_type.value if isinstance(error.error_type, ErrorType) else error.error_type,
            error.severity.value if isinstance(error.severity, ErrorSeverity) else error.severity,
            error.error_code,
            error.message,
            json.dumps(error.details),
            error.operation,
            error.user_id,
            error.stack_trace,
            error.created_at.isoformat(),
            error.resolved_at.isoformat() if error.resolved_at else None,
            error.resolution_notes,
        )

        await self.connection.execute(query, params)
        return error.id

    async def get_error(self, error_id: str) -> Optional[ErrorLog]:
        """Retrieve an error by its ID."""
        query = "SELECT * FROM error_logs WHERE id = ?"
        row = await self.connection.fetch_one(query, (error_id,))

        if not row:
            return None

        return self._row_to_error(row)

    async def get_errors_by_guild(
        self,
        guild_id: str,
        limit: int = 50,
        error_type: Optional[ErrorType] = None,
        severity: Optional[ErrorSeverity] = None,
        include_resolved: bool = False,
    ) -> List[ErrorLog]:
        """Get errors for a specific guild."""
        query = "SELECT * FROM error_logs WHERE guild_id = ?"
        params = [guild_id]

        if error_type:
            query += " AND error_type = ?"
            params.append(error_type.value if isinstance(error_type, ErrorType) else error_type)

        if severity:
            query += " AND severity = ?"
            params.append(severity.value if isinstance(severity, ErrorSeverity) else severity)

        if not include_resolved:
            query += " AND resolved_at IS NULL"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_error(row) for row in rows]

    async def get_recent_errors(
        self,
        limit: int = 100,
        error_type: Optional[ErrorType] = None,
        severity: Optional[ErrorSeverity] = None,
    ) -> List[ErrorLog]:
        """Get recent errors across all guilds."""
        query = "SELECT * FROM error_logs WHERE 1=1"
        params = []

        if error_type:
            query += " AND error_type = ?"
            params.append(error_type.value if isinstance(error_type, ErrorType) else error_type)

        if severity:
            query += " AND severity = ?"
            params.append(severity.value if isinstance(severity, ErrorSeverity) else severity)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_error(row) for row in rows]

    async def resolve_error(
        self,
        error_id: str,
        notes: Optional[str] = None,
    ) -> bool:
        """Mark an error as resolved."""
        query = """
        UPDATE error_logs
        SET resolved_at = ?, resolution_notes = ?
        WHERE id = ?
        """
        cursor = await self.connection.execute(
            query,
            (utc_now_naive().isoformat(), notes, error_id)
        )
        return cursor.rowcount > 0

    async def delete_old_errors(self, days: int = 7) -> int:
        """Delete errors older than specified days."""
        cutoff = (utc_now_naive() - timedelta(days=days)).isoformat()

        query = "DELETE FROM error_logs WHERE created_at < ?"
        cursor = await self.connection.execute(query, (cutoff,))
        return cursor.rowcount

    async def get_error_counts(
        self,
        guild_id: Optional[str] = None,
        hours: int = 24,
    ) -> Dict[str, int]:
        """Get error counts grouped by type."""
        cutoff = (utc_now_naive() - timedelta(hours=hours)).isoformat()

        if guild_id:
            query = """
            SELECT error_type, COUNT(*) as count
            FROM error_logs
            WHERE guild_id = ? AND created_at >= ?
            GROUP BY error_type
            """
            rows = await self.connection.fetch_all(query, (guild_id, cutoff))
        else:
            query = """
            SELECT error_type, COUNT(*) as count
            FROM error_logs
            WHERE created_at >= ?
            GROUP BY error_type
            """
            rows = await self.connection.fetch_all(query, (cutoff,))

        return {row['error_type']: row['count'] for row in rows}

    async def bulk_resolve_by_type(
        self,
        guild_id: str,
        error_type: ErrorType,
        notes: Optional[str] = None,
    ) -> int:
        """Resolve all unresolved errors of a specific type for a guild."""
        query = """
        UPDATE error_logs
        SET resolved_at = ?, resolution_notes = ?
        WHERE guild_id = ? AND error_type = ? AND resolved_at IS NULL
        """
        error_type_value = error_type.value if isinstance(error_type, ErrorType) else error_type
        cursor = await self.connection.execute(
            query,
            (utc_now_naive().isoformat(), notes, guild_id, error_type_value)
        )
        return cursor.rowcount

    def _row_to_error(self, row: Dict[str, Any]) -> ErrorLog:
        """Convert database row to ErrorLog object."""
        return ErrorLog(
            id=row['id'],
            guild_id=row['guild_id'],
            channel_id=row['channel_id'],
            error_type=ErrorType(row['error_type']),
            severity=ErrorSeverity(row['severity']),
            error_code=row['error_code'],
            message=row['message'],
            details=json.loads(row['details']) if row['details'] else {},
            operation=row['operation'],
            user_id=row['user_id'],
            stack_trace=row['stack_trace'],
            created_at=datetime.fromisoformat(row['created_at']),
            resolved_at=datetime.fromisoformat(row['resolved_at']) if row['resolved_at'] else None,
            resolution_notes=row['resolution_notes'],
        )
