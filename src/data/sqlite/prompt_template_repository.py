"""
SQLite implementation of prompt template repository (ADR-034).
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from ..base import PromptTemplateRepository
from ...models.prompt_template import GuildPromptTemplate
from ...models.base import generate_id
from src.utils.time import utc_now_naive
from .connection import SQLiteConnection

logger = logging.getLogger(__name__)


class SQLitePromptTemplateRepository(PromptTemplateRepository):
    """SQLite implementation of prompt template repository."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    async def save_template(self, template: GuildPromptTemplate) -> GuildPromptTemplate:
        """Save or update a prompt template."""
        query = """
        INSERT OR REPLACE INTO guild_prompt_templates (
            id, guild_id, name, description, content,
            based_on_default, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            template.id,
            template.guild_id,
            template.name,
            template.description,
            template.content,
            template.based_on_default,
            template.created_by,
            template.created_at.isoformat(),
            template.updated_at.isoformat(),
        )

        await self.connection.execute(query, params)
        return template

    async def get_template(self, template_id: str) -> Optional[GuildPromptTemplate]:
        """Retrieve a template by its ID."""
        query = "SELECT * FROM guild_prompt_templates WHERE id = ?"
        row = await self.connection.fetch_one(query, (template_id,))

        if not row:
            return None

        return self._row_to_template(row)

    async def get_templates_by_guild(self, guild_id: str) -> List[GuildPromptTemplate]:
        """Retrieve all templates for a guild."""
        query = """
        SELECT * FROM guild_prompt_templates
        WHERE guild_id = ?
        ORDER BY name
        """
        rows = await self.connection.fetch_all(query, (guild_id,))
        return [self._row_to_template(row) for row in rows]

    async def delete_template(self, template_id: str) -> bool:
        """Delete a template by its ID."""
        query = "DELETE FROM guild_prompt_templates WHERE id = ?"
        result = await self.connection.execute(query, (template_id,))
        return result.rowcount > 0 if hasattr(result, 'rowcount') else True

    async def get_template_usage(self, template_id: str) -> List[Dict[str, str]]:
        """Get schedules using this template.

        Returns:
            List of dicts with schedule_id and schedule_name
        """
        query = """
        SELECT id, name FROM scheduled_tasks
        WHERE prompt_template_id = ?
        """
        rows = await self.connection.fetch_all(query, (template_id,))
        return [{"schedule_id": row['id'], "schedule_name": row['name']} for row in rows]

    async def get_usage_count(self, template_id: str) -> int:
        """Get count of schedules using this template."""
        query = """
        SELECT COUNT(*) as count FROM scheduled_tasks
        WHERE prompt_template_id = ?
        """
        row = await self.connection.fetch_one(query, (template_id,))
        return row['count'] if row else 0

    async def duplicate_template(
        self,
        template_id: str,
        new_name: str,
        user_id: str
    ) -> Optional[GuildPromptTemplate]:
        """Duplicate a template with a new name."""
        original = await self.get_template(template_id)
        if not original:
            return None

        now = utc_now_naive()
        duplicate = GuildPromptTemplate(
            id=generate_id(),
            guild_id=original.guild_id,
            name=new_name,
            description=original.description,
            content=original.content,
            based_on_default=original.based_on_default,
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )

        return await self.save_template(duplicate)

    async def template_name_exists(self, guild_id: str, name: str, exclude_id: Optional[str] = None) -> bool:
        """Check if a template name already exists in a guild."""
        if exclude_id:
            query = """
            SELECT 1 FROM guild_prompt_templates
            WHERE guild_id = ? AND name = ? AND id != ?
            LIMIT 1
            """
            row = await self.connection.fetch_one(query, (guild_id, name, exclude_id))
        else:
            query = """
            SELECT 1 FROM guild_prompt_templates
            WHERE guild_id = ? AND name = ?
            LIMIT 1
            """
            row = await self.connection.fetch_one(query, (guild_id, name))

        return row is not None

    def _row_to_template(self, row) -> GuildPromptTemplate:
        """Convert a database row to a GuildPromptTemplate."""
        created_at = row['created_at']
        updated_at = row['updated_at']

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return GuildPromptTemplate(
            id=row['id'],
            guild_id=row['guild_id'],
            name=row['name'],
            description=row['description'],
            content=row['content'],
            based_on_default=row['based_on_default'],
            created_by=row['created_by'],
            created_at=created_at,
            updated_at=updated_at,
        )
