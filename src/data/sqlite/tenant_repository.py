"""
SQLite implementation of Tenant repository (ADR-079).
"""

import json
import logging
import secrets
from datetime import datetime
from typing import List, Optional, Dict, Any

from .connection import SQLiteConnection
from ...models.tenant import (
    Tenant, TenantBranding, TenantWorkspace, TenantAdmin, TenantMember,
    TenantAccessMode, TenantAdminRole, TenantMemberAccessLevel, WorkspaceType,
)

logger = logging.getLogger(__name__)


class SQLiteTenantRepository:
    """SQLite implementation of Tenant repository (ADR-079)."""

    def __init__(self, connection: SQLiteConnection):
        self.connection = connection

    # =========================================================================
    # Tenant CRUD Operations
    # =========================================================================

    async def save_tenant(self, tenant: Tenant) -> str:
        """Save or update a tenant.

        Args:
            tenant: Tenant to save

        Returns:
            Tenant ID
        """
        query = """
        INSERT INTO tenants (
            id, slug, name, subdomain, custom_domain, domain_verified,
            domain_verification_token, logo_url, primary_color, favicon_url,
            app_name_override, show_powered_by, access_mode, allowed_email_domains,
            created_at, updated_at, created_by, settings
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            slug = excluded.slug,
            name = excluded.name,
            subdomain = excluded.subdomain,
            custom_domain = excluded.custom_domain,
            domain_verified = excluded.domain_verified,
            domain_verification_token = excluded.domain_verification_token,
            logo_url = excluded.logo_url,
            primary_color = excluded.primary_color,
            favicon_url = excluded.favicon_url,
            app_name_override = excluded.app_name_override,
            show_powered_by = excluded.show_powered_by,
            access_mode = excluded.access_mode,
            allowed_email_domains = excluded.allowed_email_domains,
            updated_at = excluded.updated_at,
            settings = excluded.settings
        """

        params = (
            tenant.id,
            tenant.slug,
            tenant.name,
            tenant.subdomain,
            tenant.custom_domain,
            tenant.domain_verified,
            tenant.domain_verification_token,
            tenant.branding.logo_url,
            tenant.branding.primary_color,
            tenant.branding.favicon_url,
            tenant.branding.app_name_override,
            tenant.branding.show_powered_by,
            tenant.access_mode.value,
            json.dumps(tenant.allowed_email_domains),
            tenant.created_at.isoformat() if tenant.created_at else None,
            datetime.utcnow().isoformat(),
            tenant.created_by,
            json.dumps(tenant.settings),
        )

        await self.connection.execute(query, params)
        return tenant.id

    async def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get a tenant by ID.

        Args:
            tenant_id: Tenant ID

        Returns:
            Tenant if found, None otherwise
        """
        query = "SELECT * FROM tenants WHERE id = ?"
        row = await self.connection.fetch_one(query, (tenant_id,))

        if not row:
            return None

        return self._row_to_tenant(row)

    async def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Get a tenant by slug.

        Args:
            slug: Tenant slug

        Returns:
            Tenant if found, None otherwise
        """
        query = "SELECT * FROM tenants WHERE slug = ?"
        row = await self.connection.fetch_one(query, (slug,))

        if not row:
            return None

        return self._row_to_tenant(row)

    async def get_tenant_by_subdomain(self, subdomain: str) -> Optional[Tenant]:
        """Get a tenant by subdomain.

        Args:
            subdomain: Subdomain (e.g., "acme" for acme.summarybot.app)

        Returns:
            Tenant if found, None otherwise
        """
        query = "SELECT * FROM tenants WHERE subdomain = ?"
        row = await self.connection.fetch_one(query, (subdomain,))

        if not row:
            return None

        return self._row_to_tenant(row)

    async def get_tenant_by_custom_domain(self, domain: str) -> Optional[Tenant]:
        """Get a tenant by custom domain.

        Args:
            domain: Custom domain (e.g., "summaries.acme.com")

        Returns:
            Tenant if found, None otherwise
        """
        query = "SELECT * FROM tenants WHERE custom_domain = ? AND domain_verified = TRUE"
        row = await self.connection.fetch_one(query, (domain,))

        if not row:
            return None

        return self._row_to_tenant(row)

    async def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant (cascades to workspaces, admins, members).

        Args:
            tenant_id: Tenant ID

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM tenants WHERE id = ?"
        cursor = await self.connection.execute(query, (tenant_id,))
        return cursor.rowcount > 0

    async def list_tenants_for_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Tenant]:
        """List tenants where user is an admin.

        Args:
            user_id: User ID
            limit: Max tenants to return
            offset: Pagination offset

        Returns:
            List of Tenant objects
        """
        query = """
        SELECT t.* FROM tenants t
        INNER JOIN tenant_admins ta ON t.id = ta.tenant_id
        WHERE ta.user_id = ?
        ORDER BY t.name ASC
        LIMIT ? OFFSET ?
        """

        rows = await self.connection.fetch_all(query, (user_id, limit, offset))
        return [self._row_to_tenant(row) for row in rows]

    # =========================================================================
    # Workspace Linking
    # =========================================================================

    async def link_workspace(
        self,
        tenant_id: str,
        workspace_id: str,
        workspace_type: WorkspaceType,
        added_by: str,
        display_name: Optional[str] = None,
        display_order: int = 0,
    ) -> bool:
        """Link a workspace to a tenant.

        Args:
            tenant_id: Tenant ID
            workspace_id: Workspace ID (guild_id, slack workspace_id, etc.)
            workspace_type: Type of workspace
            added_by: User ID who added the link
            display_name: Optional display name override
            display_order: Order for display in UI

        Returns:
            True if linked successfully
        """
        query = """
        INSERT INTO tenant_workspaces (
            tenant_id, workspace_id, workspace_type, display_name, display_order,
            added_at, added_by
        ) VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
        ON CONFLICT(tenant_id, workspace_id) DO UPDATE SET
            display_name = excluded.display_name,
            display_order = excluded.display_order
        """

        await self.connection.execute(
            query,
            (tenant_id, workspace_id, workspace_type.value, display_name, display_order, added_by),
        )
        return True

    async def unlink_workspace(self, tenant_id: str, workspace_id: str) -> bool:
        """Unlink a workspace from a tenant.

        Args:
            tenant_id: Tenant ID
            workspace_id: Workspace ID

        Returns:
            True if unlinked, False if not found
        """
        query = "DELETE FROM tenant_workspaces WHERE tenant_id = ? AND workspace_id = ?"
        cursor = await self.connection.execute(query, (tenant_id, workspace_id))
        return cursor.rowcount > 0

    async def get_tenant_workspaces(self, tenant_id: str) -> List[TenantWorkspace]:
        """Get all workspaces linked to a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of TenantWorkspace objects
        """
        query = """
        SELECT * FROM tenant_workspaces
        WHERE tenant_id = ?
        ORDER BY display_order ASC, added_at ASC
        """

        rows = await self.connection.fetch_all(query, (tenant_id,))
        return [self._row_to_workspace(row) for row in rows]

    async def get_tenant_for_workspace(self, workspace_id: str) -> Optional[Tenant]:
        """Get the tenant that a workspace belongs to.

        Args:
            workspace_id: Workspace ID

        Returns:
            Tenant if found, None otherwise
        """
        query = """
        SELECT t.* FROM tenants t
        INNER JOIN tenant_workspaces tw ON t.id = tw.tenant_id
        WHERE tw.workspace_id = ?
        """

        row = await self.connection.fetch_one(query, (workspace_id,))

        if not row:
            return None

        return self._row_to_tenant(row)

    # =========================================================================
    # Admin Management
    # =========================================================================

    async def add_admin(
        self,
        tenant_id: str,
        user_id: str,
        role: TenantAdminRole = TenantAdminRole.ADMIN,
    ) -> bool:
        """Add an admin to a tenant.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            role: Admin role

        Returns:
            True if added successfully
        """
        query = """
        INSERT INTO tenant_admins (tenant_id, user_id, role, added_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(tenant_id, user_id) DO UPDATE SET
            role = excluded.role
        """

        await self.connection.execute(query, (tenant_id, user_id, role.value))
        return True

    async def remove_admin(self, tenant_id: str, user_id: str) -> bool:
        """Remove an admin from a tenant.

        Args:
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            True if removed, False if not found
        """
        query = "DELETE FROM tenant_admins WHERE tenant_id = ? AND user_id = ?"
        cursor = await self.connection.execute(query, (tenant_id, user_id))
        return cursor.rowcount > 0

    async def get_tenant_admins(self, tenant_id: str) -> List[TenantAdmin]:
        """Get all admins for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of TenantAdmin objects
        """
        query = "SELECT * FROM tenant_admins WHERE tenant_id = ? ORDER BY added_at ASC"
        rows = await self.connection.fetch_all(query, (tenant_id,))
        return [self._row_to_admin(row) for row in rows]

    async def is_tenant_admin(
        self,
        tenant_id: str,
        user_id: str,
        required_role: Optional[TenantAdminRole] = None,
    ) -> bool:
        """Check if a user is an admin of a tenant.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            required_role: If specified, check for this specific role or higher

        Returns:
            True if user is admin (with required role if specified)
        """
        query = "SELECT role FROM tenant_admins WHERE tenant_id = ? AND user_id = ?"
        row = await self.connection.fetch_one(query, (tenant_id, user_id))

        if not row:
            return False

        if required_role is None:
            return True

        # Role hierarchy: owner > admin > editor
        role = TenantAdminRole(row["role"])
        role_hierarchy = {
            TenantAdminRole.OWNER: 3,
            TenantAdminRole.ADMIN: 2,
            TenantAdminRole.EDITOR: 1,
        }

        return role_hierarchy.get(role, 0) >= role_hierarchy.get(required_role, 0)

    # =========================================================================
    # Member Management
    # =========================================================================

    async def add_member(
        self,
        tenant_id: str,
        user_id: str,
        email: Optional[str] = None,
        access_level: TenantMemberAccessLevel = TenantMemberAccessLevel.VIEWER,
    ) -> bool:
        """Add a member to a tenant.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            email: Optional email address
            access_level: Member access level

        Returns:
            True if added successfully
        """
        query = """
        INSERT INTO tenant_members (tenant_id, user_id, email, access_level, invited_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(tenant_id, user_id) DO UPDATE SET
            email = excluded.email,
            access_level = excluded.access_level
        """

        await self.connection.execute(query, (tenant_id, user_id, email, access_level.value))
        return True

    async def remove_member(self, tenant_id: str, user_id: str) -> bool:
        """Remove a member from a tenant.

        Args:
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            True if removed, False if not found
        """
        query = "DELETE FROM tenant_members WHERE tenant_id = ? AND user_id = ?"
        cursor = await self.connection.execute(query, (tenant_id, user_id))
        return cursor.rowcount > 0

    async def get_tenant_members(self, tenant_id: str) -> List[TenantMember]:
        """Get all members of a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of TenantMember objects
        """
        query = "SELECT * FROM tenant_members WHERE tenant_id = ? ORDER BY invited_at ASC"
        rows = await self.connection.fetch_all(query, (tenant_id,))
        return [self._row_to_member(row) for row in rows]

    async def is_tenant_member(self, tenant_id: str, user_id: str) -> bool:
        """Check if a user is a member of a tenant.

        Args:
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            True if user is a member
        """
        query = "SELECT 1 FROM tenant_members WHERE tenant_id = ? AND user_id = ?"
        row = await self.connection.fetch_one(query, (tenant_id, user_id))
        return row is not None

    # =========================================================================
    # Domain Verification
    # =========================================================================

    async def generate_verification_token(self, tenant_id: str) -> str:
        """Generate a domain verification token for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Verification token
        """
        token = secrets.token_urlsafe(32)

        query = """
        UPDATE tenants
        SET domain_verification_token = ?, updated_at = datetime('now')
        WHERE id = ?
        """

        await self.connection.execute(query, (token, tenant_id))
        return token

    async def verify_domain(self, tenant_id: str) -> bool:
        """Mark a tenant's custom domain as verified.

        Args:
            tenant_id: Tenant ID

        Returns:
            True if updated successfully
        """
        query = """
        UPDATE tenants
        SET domain_verified = TRUE, domain_verification_token = NULL,
            updated_at = datetime('now')
        WHERE id = ?
        """

        cursor = await self.connection.execute(query, (tenant_id,))
        return cursor.rowcount > 0

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _row_to_tenant(self, row: Dict[str, Any]) -> Tenant:
        """Convert database row to Tenant."""
        return Tenant(
            id=row["id"],
            slug=row["slug"],
            name=row["name"],
            subdomain=row.get("subdomain"),
            custom_domain=row.get("custom_domain"),
            domain_verified=bool(row.get("domain_verified")),
            domain_verification_token=row.get("domain_verification_token"),
            branding=TenantBranding(
                logo_url=row.get("logo_url"),
                primary_color=row.get("primary_color"),
                favicon_url=row.get("favicon_url"),
                app_name_override=row.get("app_name_override"),
                show_powered_by=bool(row.get("show_powered_by", True)),
            ),
            access_mode=TenantAccessMode(row.get("access_mode", "authenticated")),
            allowed_email_domains=json.loads(row.get("allowed_email_domains") or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None,
            created_by=row.get("created_by", ""),
            settings=json.loads(row.get("settings") or "{}"),
        )

    def _row_to_workspace(self, row: Dict[str, Any]) -> TenantWorkspace:
        """Convert database row to TenantWorkspace."""
        return TenantWorkspace(
            tenant_id=row["tenant_id"],
            workspace_id=row["workspace_id"],
            workspace_type=WorkspaceType(row["workspace_type"]),
            display_name=row.get("display_name"),
            display_order=row.get("display_order", 0),
            added_at=datetime.fromisoformat(row["added_at"]) if row.get("added_at") else None,
            added_by=row.get("added_by", ""),
        )

    def _row_to_admin(self, row: Dict[str, Any]) -> TenantAdmin:
        """Convert database row to TenantAdmin."""
        return TenantAdmin(
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            role=TenantAdminRole(row.get("role", "admin")),
            added_at=datetime.fromisoformat(row["added_at"]) if row.get("added_at") else None,
        )

    def _row_to_member(self, row: Dict[str, Any]) -> TenantMember:
        """Convert database row to TenantMember."""
        return TenantMember(
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            email=row.get("email"),
            access_level=TenantMemberAccessLevel(row.get("access_level", "viewer")),
            invited_at=datetime.fromisoformat(row["invited_at"]) if row.get("invited_at") else None,
            accepted_at=datetime.fromisoformat(row["accepted_at"]) if row.get("accepted_at") else None,
        )
