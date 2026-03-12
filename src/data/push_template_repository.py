"""
Push Template Repository for ADR-014: Discord Push Templates.

Handles storage and retrieval of guild-specific push templates.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List

from src.utils.time import utc_now_naive
from ..models.push_template import (
    PushTemplate, GuildPushTemplate, DEFAULT_PUSH_TEMPLATE,
    validate_template,
)

logger = logging.getLogger(__name__)


class PushTemplateRepository:
    """Repository for managing guild push templates."""

    def __init__(self, connection):
        """Initialize repository with database connection.

        Args:
            connection: Database connection (SQLite or PostgreSQL)
        """
        self.connection = connection

    async def get_template(self, guild_id: str) -> PushTemplate:
        """Get push template for a guild.

        Returns guild-specific template if configured, otherwise DEFAULT.

        Args:
            guild_id: Discord guild ID

        Returns:
            PushTemplate for the guild
        """
        query = "SELECT * FROM guild_push_templates WHERE guild_id = ?"
        row = await self.connection.fetch_one(query, (guild_id,))

        if not row:
            return DEFAULT_PUSH_TEMPLATE

        try:
            template_data = json.loads(row['template_json'])
            template = PushTemplate.from_dict(template_data)

            # Validate template
            errors = validate_template(template)
            if errors:
                logger.warning(
                    f"Guild {guild_id} template has validation errors: {errors}. "
                    "Using default template."
                )
                return DEFAULT_PUSH_TEMPLATE

            return template

        except Exception as e:
            logger.error(f"Failed to parse template for guild {guild_id}: {e}")
            return DEFAULT_PUSH_TEMPLATE

    async def get_guild_template(self, guild_id: str) -> Optional[GuildPushTemplate]:
        """Get full guild template record including metadata.

        Args:
            guild_id: Discord guild ID

        Returns:
            GuildPushTemplate or None if not configured
        """
        query = "SELECT * FROM guild_push_templates WHERE guild_id = ?"
        row = await self.connection.fetch_one(query, (guild_id,))

        if not row:
            return None

        try:
            template_data = json.loads(row['template_json'])
            return GuildPushTemplate(
                guild_id=row['guild_id'],
                template=PushTemplate.from_dict(template_data),
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else utc_now_naive(),
                updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else utc_now_naive(),
                created_by=row.get('created_by'),
            )
        except Exception as e:
            logger.error(f"Failed to parse guild template for {guild_id}: {e}")
            return None

    async def set_template(
        self,
        guild_id: str,
        template: PushTemplate,
        user_id: Optional[str] = None,
    ) -> bool:
        """Set or update push template for a guild.

        Args:
            guild_id: Discord guild ID
            template: PushTemplate to save
            user_id: User ID who is setting the template

        Returns:
            True if successful
        """
        # Validate template
        errors = validate_template(template)
        if errors:
            logger.error(f"Cannot save invalid template for guild {guild_id}: {errors}")
            return False

        template_json = json.dumps(template.to_dict())

        query = """
        INSERT INTO guild_push_templates (
            guild_id, schema_version, template_json, created_at, updated_at, created_by
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            schema_version = excluded.schema_version,
            template_json = excluded.template_json,
            updated_at = excluded.updated_at
        """

        now = utc_now_naive().isoformat()
        params = (
            guild_id,
            template.schema_version,
            template_json,
            now,
            now,
            user_id,
        )

        try:
            await self.connection.execute(query, params)
            logger.info(f"Saved push template for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save push template for guild {guild_id}: {e}")
            return False

    async def delete_template(self, guild_id: str) -> bool:
        """Delete guild template (reverts to default).

        Args:
            guild_id: Discord guild ID

        Returns:
            True if template was deleted
        """
        query = "DELETE FROM guild_push_templates WHERE guild_id = ?"
        try:
            cursor = await self.connection.execute(query, (guild_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted push template for guild {guild_id}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete push template for guild {guild_id}: {e}")
            return False

    async def list_configured_guilds(self) -> List[str]:
        """List all guilds with custom templates configured.

        Returns:
            List of guild IDs
        """
        query = "SELECT guild_id FROM guild_push_templates ORDER BY updated_at DESC"
        rows = await self.connection.fetch_all(query)
        return [row['guild_id'] for row in rows]


# Global instance
_push_template_repository: Optional[PushTemplateRepository] = None


async def get_push_template_repository() -> PushTemplateRepository:
    """Get the global push template repository instance."""
    global _push_template_repository
    if _push_template_repository is None:
        from .repositories import get_repository_factory
        factory = get_repository_factory()
        conn = await factory.get_connection()
        _push_template_repository = PushTemplateRepository(conn)
    return _push_template_repository
