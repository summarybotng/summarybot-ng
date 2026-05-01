"""
Tests for SQLiteTenantRepository (ADR-079).
"""

import pytest
import pytest_asyncio
from typing import AsyncGenerator

from src.data.sqlite import SQLiteConnection, SQLiteTenantRepository
from src.models.tenant import (
    Tenant, TenantBranding, TenantAccessMode, TenantAdminRole,
    TenantMemberAccessLevel, WorkspaceType,
)
from src.models.base import generate_id


@pytest_asyncio.fixture
async def tenant_db() -> AsyncGenerator[SQLiteConnection, None]:
    """Create an in-memory SQLite database for tenant testing."""
    conn = SQLiteConnection(":memory:", pool_size=1)
    await conn.connect()

    # Create tenants table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            subdomain TEXT UNIQUE,
            custom_domain TEXT UNIQUE,
            domain_verified BOOLEAN DEFAULT FALSE,
            domain_verification_token TEXT,
            logo_url TEXT,
            primary_color TEXT,
            favicon_url TEXT,
            app_name_override TEXT,
            show_powered_by BOOLEAN DEFAULT TRUE,
            access_mode TEXT DEFAULT 'authenticated',
            allowed_email_domains TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            created_by TEXT NOT NULL,
            settings TEXT DEFAULT '{}'
        )
    """)

    # Create tenant_workspaces table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tenant_workspaces (
            tenant_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            workspace_type TEXT NOT NULL,
            display_name TEXT,
            display_order INTEGER DEFAULT 0,
            added_at TEXT DEFAULT (datetime('now')),
            added_by TEXT NOT NULL,
            PRIMARY KEY (tenant_id, workspace_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)

    # Create tenant_admins table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tenant_admins (
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            added_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (tenant_id, user_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)

    # Create tenant_members table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tenant_members (
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            email TEXT,
            access_level TEXT DEFAULT 'viewer',
            invited_at TEXT DEFAULT (datetime('now')),
            accepted_at TEXT,
            PRIMARY KEY (tenant_id, user_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)

    yield conn
    await conn.disconnect()


@pytest_asyncio.fixture
async def repository(tenant_db: SQLiteConnection) -> SQLiteTenantRepository:
    """Create tenant repository with in-memory database."""
    return SQLiteTenantRepository(tenant_db)


class TestTenantCRUD:
    """Test tenant CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_tenant(self, repository):
        """Test creating a new tenant."""
        tenant = Tenant(
            id=generate_id(),
            slug="acme-corp",
            name="Acme Corporation",
            subdomain="acme",
            branding=TenantBranding(
                logo_url="https://example.com/logo.png",
                primary_color="#FF5733",
            ),
            access_mode=TenantAccessMode.AUTHENTICATED,
            created_by="user-123",
        )

        tenant_id = await repository.save_tenant(tenant)
        assert tenant_id == tenant.id

        # Fetch and verify
        saved = await repository.get_tenant(tenant_id)
        assert saved is not None
        assert saved.slug == "acme-corp"
        assert saved.name == "Acme Corporation"
        assert saved.subdomain == "acme"
        assert saved.branding.logo_url == "https://example.com/logo.png"
        assert saved.branding.primary_color == "#FF5733"
        assert saved.access_mode == TenantAccessMode.AUTHENTICATED

    @pytest.mark.asyncio
    async def test_get_tenant_by_slug(self, repository):
        """Test fetching tenant by slug."""
        tenant = Tenant(
            id=generate_id(),
            slug="test-tenant",
            name="Test Tenant",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)

        found = await repository.get_tenant_by_slug("test-tenant")
        assert found is not None
        assert found.id == tenant.id

        # Non-existent slug
        not_found = await repository.get_tenant_by_slug("non-existent")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_get_tenant_by_subdomain(self, repository):
        """Test fetching tenant by subdomain."""
        tenant = Tenant(
            id=generate_id(),
            slug="subdomain-test",
            name="Subdomain Test",
            subdomain="mysubdomain",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)

        found = await repository.get_tenant_by_subdomain("mysubdomain")
        assert found is not None
        assert found.id == tenant.id

    @pytest.mark.asyncio
    async def test_get_tenant_by_custom_domain(self, repository):
        """Test fetching tenant by custom domain."""
        tenant = Tenant(
            id=generate_id(),
            slug="custom-domain-test",
            name="Custom Domain Test",
            custom_domain="summaries.example.com",
            domain_verified=True,
            created_by="user-123",
        )
        await repository.save_tenant(tenant)

        found = await repository.get_tenant_by_custom_domain("summaries.example.com")
        assert found is not None
        assert found.id == tenant.id

        # Unverified domain should not be found
        unverified = Tenant(
            id=generate_id(),
            slug="unverified-test",
            name="Unverified Test",
            custom_domain="unverified.example.com",
            domain_verified=False,
            created_by="user-123",
        )
        await repository.save_tenant(unverified)

        not_found = await repository.get_tenant_by_custom_domain("unverified.example.com")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_update_tenant(self, repository):
        """Test updating tenant."""
        tenant = Tenant(
            id=generate_id(),
            slug="update-test",
            name="Original Name",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)

        # Update
        tenant.name = "Updated Name"
        tenant.subdomain = "newsubdomain"
        await repository.save_tenant(tenant)

        # Verify
        updated = await repository.get_tenant(tenant.id)
        assert updated.name == "Updated Name"
        assert updated.subdomain == "newsubdomain"

    @pytest.mark.asyncio
    async def test_delete_tenant(self, repository):
        """Test deleting tenant."""
        tenant = Tenant(
            id=generate_id(),
            slug="delete-test",
            name="Delete Test",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)

        # Delete
        deleted = await repository.delete_tenant(tenant.id)
        assert deleted is True

        # Verify deleted
        not_found = await repository.get_tenant(tenant.id)
        assert not_found is None

        # Delete non-existent
        deleted_again = await repository.delete_tenant(tenant.id)
        assert deleted_again is False


class TestWorkspaceLinking:
    """Test workspace linking operations."""

    @pytest.mark.asyncio
    async def test_link_workspace(self, repository):
        """Test linking a workspace to a tenant."""
        tenant = Tenant(
            id=generate_id(),
            slug="workspace-test",
            name="Workspace Test",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)

        # Link workspace
        success = await repository.link_workspace(
            tenant_id=tenant.id,
            workspace_id="guild-123",
            workspace_type=WorkspaceType.DISCORD,
            added_by="user-123",
            display_name="My Discord Server",
        )
        assert success is True

        # Verify
        workspaces = await repository.get_tenant_workspaces(tenant.id)
        assert len(workspaces) == 1
        assert workspaces[0].workspace_id == "guild-123"
        assert workspaces[0].workspace_type == WorkspaceType.DISCORD
        assert workspaces[0].display_name == "My Discord Server"

    @pytest.mark.asyncio
    async def test_get_tenant_for_workspace(self, repository):
        """Test reverse lookup: workspace -> tenant."""
        tenant = Tenant(
            id=generate_id(),
            slug="reverse-lookup-test",
            name="Reverse Lookup Test",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)
        await repository.link_workspace(
            tenant_id=tenant.id,
            workspace_id="slack-456",
            workspace_type=WorkspaceType.SLACK,
            added_by="user-123",
        )

        # Lookup
        found = await repository.get_tenant_for_workspace("slack-456")
        assert found is not None
        assert found.id == tenant.id

        # Non-existent workspace
        not_found = await repository.get_tenant_for_workspace("non-existent")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_unlink_workspace(self, repository):
        """Test unlinking a workspace from a tenant."""
        tenant = Tenant(
            id=generate_id(),
            slug="unlink-test",
            name="Unlink Test",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)
        await repository.link_workspace(
            tenant_id=tenant.id,
            workspace_id="guild-789",
            workspace_type=WorkspaceType.DISCORD,
            added_by="user-123",
        )

        # Unlink
        unlinked = await repository.unlink_workspace(tenant.id, "guild-789")
        assert unlinked is True

        # Verify
        workspaces = await repository.get_tenant_workspaces(tenant.id)
        assert len(workspaces) == 0


class TestAdminManagement:
    """Test tenant admin operations."""

    @pytest.mark.asyncio
    async def test_add_admin(self, repository):
        """Test adding an admin to a tenant."""
        tenant = Tenant(
            id=generate_id(),
            slug="admin-test",
            name="Admin Test",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)

        # Add admin
        success = await repository.add_admin(tenant.id, "user-456", TenantAdminRole.ADMIN)
        assert success is True

        # Verify
        admins = await repository.get_tenant_admins(tenant.id)
        assert len(admins) == 1
        assert admins[0].user_id == "user-456"
        assert admins[0].role == TenantAdminRole.ADMIN

    @pytest.mark.asyncio
    async def test_is_tenant_admin(self, repository):
        """Test checking admin status."""
        tenant = Tenant(
            id=generate_id(),
            slug="admin-check-test",
            name="Admin Check Test",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)

        await repository.add_admin(tenant.id, "owner-user", TenantAdminRole.OWNER)
        await repository.add_admin(tenant.id, "admin-user", TenantAdminRole.ADMIN)
        await repository.add_admin(tenant.id, "editor-user", TenantAdminRole.EDITOR)

        # Check basic admin status
        assert await repository.is_tenant_admin(tenant.id, "owner-user") is True
        assert await repository.is_tenant_admin(tenant.id, "admin-user") is True
        assert await repository.is_tenant_admin(tenant.id, "editor-user") is True
        assert await repository.is_tenant_admin(tenant.id, "non-admin") is False

        # Check role hierarchy
        # Owner can do everything
        assert await repository.is_tenant_admin(tenant.id, "owner-user", TenantAdminRole.OWNER) is True
        assert await repository.is_tenant_admin(tenant.id, "owner-user", TenantAdminRole.ADMIN) is True
        assert await repository.is_tenant_admin(tenant.id, "owner-user", TenantAdminRole.EDITOR) is True

        # Admin can't be owner
        assert await repository.is_tenant_admin(tenant.id, "admin-user", TenantAdminRole.OWNER) is False
        assert await repository.is_tenant_admin(tenant.id, "admin-user", TenantAdminRole.ADMIN) is True
        assert await repository.is_tenant_admin(tenant.id, "admin-user", TenantAdminRole.EDITOR) is True

        # Editor is lowest
        assert await repository.is_tenant_admin(tenant.id, "editor-user", TenantAdminRole.OWNER) is False
        assert await repository.is_tenant_admin(tenant.id, "editor-user", TenantAdminRole.ADMIN) is False
        assert await repository.is_tenant_admin(tenant.id, "editor-user", TenantAdminRole.EDITOR) is True

    @pytest.mark.asyncio
    async def test_remove_admin(self, repository):
        """Test removing an admin from a tenant."""
        tenant = Tenant(
            id=generate_id(),
            slug="remove-admin-test",
            name="Remove Admin Test",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)
        await repository.add_admin(tenant.id, "user-789", TenantAdminRole.ADMIN)

        # Remove
        removed = await repository.remove_admin(tenant.id, "user-789")
        assert removed is True

        # Verify
        assert await repository.is_tenant_admin(tenant.id, "user-789") is False


class TestListTenantsForUser:
    """Test listing tenants for a user."""

    @pytest.mark.asyncio
    async def test_list_tenants_for_user(self, repository):
        """Test listing tenants where user is admin."""
        # Create multiple tenants
        tenant1 = Tenant(id=generate_id(), slug="tenant-1", name="Tenant 1", created_by="user-123")
        tenant2 = Tenant(id=generate_id(), slug="tenant-2", name="Tenant 2", created_by="user-123")
        tenant3 = Tenant(id=generate_id(), slug="tenant-3", name="Tenant 3", created_by="other-user")

        await repository.save_tenant(tenant1)
        await repository.save_tenant(tenant2)
        await repository.save_tenant(tenant3)

        # Add user as admin to tenant1 and tenant2
        await repository.add_admin(tenant1.id, "user-123", TenantAdminRole.OWNER)
        await repository.add_admin(tenant2.id, "user-123", TenantAdminRole.ADMIN)
        await repository.add_admin(tenant3.id, "other-user", TenantAdminRole.OWNER)

        # List for user-123
        tenants = await repository.list_tenants_for_user("user-123")
        assert len(tenants) == 2
        slugs = {t.slug for t in tenants}
        assert "tenant-1" in slugs
        assert "tenant-2" in slugs
        assert "tenant-3" not in slugs


class TestDomainVerification:
    """Test domain verification operations."""

    @pytest.mark.asyncio
    async def test_generate_verification_token(self, repository):
        """Test generating a domain verification token."""
        tenant = Tenant(
            id=generate_id(),
            slug="verify-test",
            name="Verify Test",
            custom_domain="verify.example.com",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)

        # Generate token
        token = await repository.generate_verification_token(tenant.id)
        assert token is not None
        assert len(token) > 0

        # Verify stored
        updated = await repository.get_tenant(tenant.id)
        assert updated.domain_verification_token == token

    @pytest.mark.asyncio
    async def test_verify_domain(self, repository):
        """Test marking domain as verified."""
        tenant = Tenant(
            id=generate_id(),
            slug="verified-test",
            name="Verified Test",
            custom_domain="verified.example.com",
            created_by="user-123",
        )
        await repository.save_tenant(tenant)
        await repository.generate_verification_token(tenant.id)

        # Verify domain
        success = await repository.verify_domain(tenant.id)
        assert success is True

        # Check
        verified = await repository.get_tenant(tenant.id)
        assert verified.domain_verified is True
        assert verified.domain_verification_token is None
