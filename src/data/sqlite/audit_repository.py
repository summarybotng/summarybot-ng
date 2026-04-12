"""
SQLite implementation of audit log repository.

ADR-045: Audit Logging System
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from ...models.audit_log import AuditLog, AuditEventCategory, AuditSeverity, AuditSummary
from .connection import SQLiteConnection
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class SQLiteAuditRepository:
    """SQLite implementation of audit log repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save(self, entry: AuditLog) -> str:
        """Save a single audit log entry."""
        query = """
        INSERT INTO audit_logs (
            id, event_type, category, severity,
            user_id, user_name, session_id,
            guild_id, guild_name, ip_address, user_agent,
            resource_type, resource_id, resource_name,
            action, details, changes,
            success, error_message,
            timestamp, request_id, duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            entry.id,
            entry.event_type,
            entry.category.value if isinstance(entry.category, AuditEventCategory) else entry.category,
            entry.severity.value if isinstance(entry.severity, AuditSeverity) else entry.severity,
            entry.user_id,
            entry.user_name,
            entry.session_id,
            entry.guild_id,
            entry.guild_name,
            entry.ip_address,
            entry.user_agent[:500] if entry.user_agent else None,
            entry.resource_type,
            entry.resource_id,
            entry.resource_name,
            entry.action,
            json.dumps(entry.details) if entry.details else None,
            json.dumps(entry.changes) if entry.changes else None,
            1 if entry.success else 0,
            entry.error_message[:500] if entry.error_message else None,
            entry.timestamp.isoformat() if entry.timestamp else utc_now_naive().isoformat(),
            entry.request_id,
            entry.duration_ms,
        )

        await self.connection.execute(query, params)
        return entry.id

    async def save_batch(self, entries: List[AuditLog]) -> int:
        """Save multiple audit log entries efficiently."""
        if not entries:
            return 0

        query = """
        INSERT INTO audit_logs (
            id, event_type, category, severity,
            user_id, user_name, session_id,
            guild_id, guild_name, ip_address, user_agent,
            resource_type, resource_id, resource_name,
            action, details, changes,
            success, error_message,
            timestamp, request_id, duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params_list = []
        for entry in entries:
            params_list.append((
                entry.id,
                entry.event_type,
                entry.category.value if isinstance(entry.category, AuditEventCategory) else entry.category,
                entry.severity.value if isinstance(entry.severity, AuditSeverity) else entry.severity,
                entry.user_id,
                entry.user_name,
                entry.session_id,
                entry.guild_id,
                entry.guild_name,
                entry.ip_address,
                entry.user_agent[:500] if entry.user_agent else None,
                entry.resource_type,
                entry.resource_id,
                entry.resource_name,
                entry.action,
                json.dumps(entry.details) if entry.details else None,
                json.dumps(entry.changes) if entry.changes else None,
                1 if entry.success else 0,
                entry.error_message[:500] if entry.error_message else None,
                entry.timestamp.isoformat() if entry.timestamp else utc_now_naive().isoformat(),
                entry.request_id,
                entry.duration_ms,
            ))

        await self.connection.executemany(query, params_list)
        return len(entries)

    async def get(self, entry_id: str) -> Optional[AuditLog]:
        """Retrieve an audit log entry by ID."""
        query = "SELECT * FROM audit_logs WHERE id = ?"
        row = await self.connection.fetch_one(query, (entry_id,))

        if not row:
            return None

        return self._row_to_entry(row)

    async def find(
        self,
        *,
        user_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        event_type: Optional[str] = None,
        category: Optional[AuditEventCategory] = None,
        severity: Optional[AuditSeverity] = None,
        success: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AuditLog]:
        """Find audit logs with filtering."""
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params: List[Any] = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if guild_id:
            query += " AND guild_id = ?"
            params.append(guild_id)

        if event_type:
            if event_type.endswith("*"):
                query += " AND event_type LIKE ?"
                params.append(event_type[:-1] + "%")
            else:
                query += " AND event_type = ?"
                params.append(event_type)

        if category:
            query += " AND category = ?"
            params.append(category.value if isinstance(category, AuditEventCategory) else category)

        if severity:
            query += " AND severity = ?"
            params.append(severity.value if isinstance(severity, AuditSeverity) else severity)

        if success is not None:
            query += " AND success = ?"
            params.append(1 if success else 0)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        if resource_type:
            query += " AND resource_type = ?"
            params.append(resource_type)

        if resource_id:
            query += " AND resource_id = ?"
            params.append(resource_id)

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = await self.connection.fetch_all(query, tuple(params))
        return [self._row_to_entry(row) for row in rows]

    async def count(
        self,
        *,
        user_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        event_type: Optional[str] = None,
        category: Optional[AuditEventCategory] = None,
        severity: Optional[AuditSeverity] = None,
        success: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """Count audit logs matching criteria."""
        query = "SELECT COUNT(*) as cnt FROM audit_logs WHERE 1=1"
        params: List[Any] = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if guild_id:
            query += " AND guild_id = ?"
            params.append(guild_id)

        if event_type:
            if event_type.endswith("*"):
                query += " AND event_type LIKE ?"
                params.append(event_type[:-1] + "%")
            else:
                query += " AND event_type = ?"
                params.append(event_type)

        if category:
            query += " AND category = ?"
            params.append(category.value if isinstance(category, AuditEventCategory) else category)

        if severity:
            query += " AND severity = ?"
            params.append(severity.value if isinstance(severity, AuditSeverity) else severity)

        if success is not None:
            query += " AND success = ?"
            params.append(1 if success else 0)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        result = await self.connection.fetch_one(query, tuple(params))
        return result["cnt"] if result else 0

    async def get_summary(
        self,
        *,
        guild_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> AuditSummary:
        """Get aggregated audit statistics."""
        base_query = "FROM audit_logs WHERE 1=1"
        params: List[Any] = []

        if guild_id:
            base_query += " AND guild_id = ?"
            params.append(guild_id)

        if start_date:
            base_query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            base_query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        # Total count
        total_result = await self.connection.fetch_one(
            f"SELECT COUNT(*) as cnt {base_query}", tuple(params)
        )
        total_count = total_result["cnt"] if total_result else 0

        # By category
        cat_query = f"SELECT category, COUNT(*) as cnt {base_query} GROUP BY category"
        cat_rows = await self.connection.fetch_all(cat_query, tuple(params))
        by_category = {row["category"]: row["cnt"] for row in cat_rows}

        # By severity
        sev_query = f"SELECT severity, COUNT(*) as cnt {base_query} GROUP BY severity"
        sev_rows = await self.connection.fetch_all(sev_query, tuple(params))
        by_severity = {row["severity"]: row["cnt"] for row in sev_rows}

        # By event type (top 20)
        evt_query = f"SELECT event_type, COUNT(*) as cnt {base_query} GROUP BY event_type ORDER BY cnt DESC LIMIT 20"
        evt_rows = await self.connection.fetch_all(evt_query, tuple(params))
        by_event_type = {row["event_type"]: row["cnt"] for row in evt_rows}

        # By user (top 20)
        user_query = f"SELECT user_id, COUNT(*) as cnt {base_query} AND user_id IS NOT NULL GROUP BY user_id ORDER BY cnt DESC LIMIT 20"
        user_rows = await self.connection.fetch_all(user_query, tuple(params))
        by_user = {row["user_id"]: row["cnt"] for row in user_rows}

        # By guild (top 20) - only if not filtered by guild
        by_guild = {}
        if not guild_id:
            guild_query = f"SELECT guild_id, COUNT(*) as cnt {base_query} AND guild_id IS NOT NULL GROUP BY guild_id ORDER BY cnt DESC LIMIT 20"
            guild_rows = await self.connection.fetch_all(guild_query, tuple(params))
            by_guild = {row["guild_id"]: row["cnt"] for row in guild_rows}

        # Failed count
        failed_result = await self.connection.fetch_one(
            f"SELECT COUNT(*) as cnt {base_query} AND success = 0", tuple(params)
        )
        failed_count = failed_result["cnt"] if failed_result else 0

        # Alert count
        alert_result = await self.connection.fetch_one(
            f"SELECT COUNT(*) as cnt {base_query} AND severity IN ('warning', 'alert')", tuple(params)
        )
        alert_count = alert_result["cnt"] if alert_result else 0

        return AuditSummary(
            total_count=total_count,
            by_category=by_category,
            by_severity=by_severity,
            by_event_type=by_event_type,
            by_user=by_user,
            by_guild=by_guild,
            failed_count=failed_count,
            alert_count=alert_count,
        )

    async def delete_before(
        self,
        category: AuditEventCategory,
        before: datetime,
    ) -> int:
        """Delete audit logs older than specified date for a category."""
        query = "DELETE FROM audit_logs WHERE category = ? AND timestamp < ?"
        params = (
            category.value if isinstance(category, AuditEventCategory) else category,
            before.isoformat(),
        )

        result = await self.connection.execute(query, params)
        return result  # Returns rows affected

    async def anonymize_ips_before(self, before: datetime) -> int:
        """Anonymize IP addresses older than specified date."""
        query = """
        UPDATE audit_logs
        SET ip_address = CASE
            WHEN ip_address IS NOT NULL THEN 'anonymized'
            ELSE NULL
        END
        WHERE timestamp < ? AND ip_address IS NOT NULL AND ip_address != 'anonymized'
        """

        result = await self.connection.execute(query, (before.isoformat(),))
        return result

    def _row_to_entry(self, row: Dict[str, Any]) -> AuditLog:
        """Convert database row to AuditLog instance."""
        data = dict(row)

        # Handle success as boolean
        data["success"] = bool(data.get("success", 1))

        # Parse JSON fields
        if data.get("details"):
            try:
                data["details"] = json.loads(data["details"])
            except (json.JSONDecodeError, TypeError):
                data["details"] = {}

        if data.get("changes"):
            try:
                data["changes"] = json.loads(data["changes"])
            except (json.JSONDecodeError, TypeError):
                data["changes"] = None

        return AuditLog.from_dict(data)
