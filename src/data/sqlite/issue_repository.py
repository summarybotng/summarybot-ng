"""
SQLite Issue Repository (ADR-070)

Local issue storage for users without GitHub accounts.
"""

import logging
import secrets
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Tuple

from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


@dataclass
class LocalIssue:
    """Local issue model."""
    id: str
    guild_id: Optional[str]
    title: str
    description: str
    issue_type: str  # bug, feature, question
    reporter_email: Optional[str]
    reporter_discord_id: Optional[str]
    page_url: Optional[str]
    browser_info: Optional[str]
    app_version: Optional[str]
    status: str  # open, triaged, replicated, closed
    github_issue_url: Optional[str]
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class SQLiteIssueRepository:
    """Repository for local issue storage."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    def _generate_id(self) -> str:
        """Generate a short random ID."""
        return secrets.token_hex(8)

    async def create_issue(
        self,
        title: str,
        description: str,
        issue_type: str,
        guild_id: Optional[str] = None,
        reporter_email: Optional[str] = None,
        reporter_discord_id: Optional[str] = None,
        page_url: Optional[str] = None,
        browser_info: Optional[str] = None,
        app_version: Optional[str] = None,
    ) -> LocalIssue:
        """Create a new local issue."""
        issue_id = self._generate_id()
        now = datetime.utcnow().isoformat()

        query = """
            INSERT INTO local_issues (
                id, guild_id, title, description, issue_type,
                reporter_email, reporter_discord_id,
                page_url, browser_info, app_version,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
        """
        params = (
            issue_id, guild_id, title, description, issue_type,
            reporter_email, reporter_discord_id,
            page_url, browser_info, app_version,
            now, now
        )

        await self.connection.execute(query, params)

        logger.info(f"Created local issue {issue_id}: {title[:50]}")

        return LocalIssue(
            id=issue_id,
            guild_id=guild_id,
            title=title,
            description=description,
            issue_type=issue_type,
            reporter_email=reporter_email,
            reporter_discord_id=reporter_discord_id,
            page_url=page_url,
            browser_info=browser_info,
            app_version=app_version,
            status="open",
            github_issue_url=None,
            admin_notes=None,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
        )

    async def get_issue(self, issue_id: str) -> Optional[LocalIssue]:
        """Get an issue by ID."""
        query = "SELECT * FROM local_issues WHERE id = ?"
        row = await self.connection.fetch_one(query, (issue_id,))
        if not row:
            return None
        return self._row_to_issue(dict(row))

    async def list_issues(
        self,
        guild_id: Optional[str] = None,
        status: Optional[str] = None,
        issue_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[LocalIssue], int]:
        """List issues with optional filters."""
        conditions = []
        params: List = []

        if guild_id is not None:
            conditions.append("guild_id = ?")
            params.append(guild_id)

        if status:
            conditions.append("status = ?")
            params.append(status)

        if issue_type:
            conditions.append("issue_type = ?")
            params.append(issue_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        count_query = f"SELECT COUNT(*) as count FROM local_issues WHERE {where_clause}"
        count_row = await self.connection.fetch_one(count_query, tuple(params))
        total = count_row["count"] if count_row else 0

        # Get paginated results
        list_query = f"""
            SELECT * FROM local_issues
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = await self.connection.fetch_all(list_query, tuple(params) + (limit, offset))

        issues = [self._row_to_issue(dict(row)) for row in rows]
        return issues, total

    async def update_issue(
        self,
        issue_id: str,
        status: Optional[str] = None,
        github_issue_url: Optional[str] = None,
        admin_notes: Optional[str] = None,
    ) -> Optional[LocalIssue]:
        """Update an issue's status or metadata."""
        updates = []
        params: List = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if github_issue_url is not None:
            updates.append("github_issue_url = ?")
            params.append(github_issue_url)

        if admin_notes is not None:
            updates.append("admin_notes = ?")
            params.append(admin_notes)

        if not updates:
            return await self.get_issue(issue_id)

        updates.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(issue_id)

        query = f"UPDATE local_issues SET {', '.join(updates)} WHERE id = ?"
        await self.connection.execute(query, tuple(params))

        return await self.get_issue(issue_id)

    async def delete_issue(self, issue_id: str) -> bool:
        """Delete an issue."""
        query = "DELETE FROM local_issues WHERE id = ?"
        await self.connection.execute(query, (issue_id,))
        return True

    def _row_to_issue(self, row: dict) -> LocalIssue:
        """Convert a database row to a LocalIssue."""
        return LocalIssue(
            id=row["id"],
            guild_id=row["guild_id"],
            title=row["title"],
            description=row["description"],
            issue_type=row["issue_type"],
            reporter_email=row["reporter_email"],
            reporter_discord_id=row["reporter_discord_id"],
            page_url=row["page_url"],
            browser_info=row["browser_info"],
            app_version=row["app_version"],
            status=row["status"],
            github_issue_url=row["github_issue_url"],
            admin_notes=row["admin_notes"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )
