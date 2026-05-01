"""
Tenant routes for dashboard API (ADR-079).

Phase 1: Foundation - Tenant CRUD, workspace linking
Phase 2: Access Control - Membership, invites, email restrictions
Phase 3: Custom Domains - Domain verification flow
Phase 4: Branding - Theme customization, white-label
"""

import dns.resolver
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..tenant_middleware import get_current_tenant
from ...models.tenant import (
    Tenant, TenantBranding, TenantWorkspace, TenantAdmin, TenantMember,
    TenantAccessMode, TenantAdminRole, TenantMemberAccessLevel, WorkspaceType,
)
from ...models.base import generate_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants")


# =============================================================================
# Request/Response Models
# =============================================================================

class TenantBrandingModel(BaseModel):
    """Branding configuration for tenant."""
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    favicon_url: Optional[str] = None
    app_name_override: Optional[str] = Field(None, max_length=64)
    show_powered_by: bool = True


class CreateTenantRequest(BaseModel):
    """Request to create a new tenant."""
    slug: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=128)
    subdomain: Optional[str] = Field(None, min_length=3, max_length=32, pattern=r"^[a-z0-9-]+$")
    branding: Optional[TenantBrandingModel] = None
    access_mode: Optional[str] = "authenticated"


class UpdateTenantRequest(BaseModel):
    """Request to update a tenant."""
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    subdomain: Optional[str] = Field(None, min_length=3, max_length=32, pattern=r"^[a-z0-9-]+$")
    custom_domain: Optional[str] = Field(None, max_length=255)
    branding: Optional[TenantBrandingModel] = None
    access_mode: Optional[str] = None
    allowed_email_domains: Optional[List[str]] = None


# =============================================================================
# Phase 2: Access Control Models
# =============================================================================

class TenantMemberResponse(BaseModel):
    """Response for a tenant member."""
    user_id: str
    email: Optional[str]
    access_level: str
    invited_at: Optional[str]
    accepted_at: Optional[str]


class TenantAdminResponse(BaseModel):
    """Response for a tenant admin."""
    user_id: str
    role: str
    added_at: Optional[str]


class InviteMemberRequest(BaseModel):
    """Request to invite a member to a tenant."""
    email: str = Field(..., pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    access_level: str = Field("viewer", pattern=r"^(viewer|contributor)$")


class UpdateMemberRequest(BaseModel):
    """Request to update a member's access level."""
    access_level: str = Field(..., pattern=r"^(viewer|contributor)$")


class AddAdminRequest(BaseModel):
    """Request to add an admin to a tenant."""
    user_id: str
    role: str = Field("admin", pattern=r"^(owner|admin|editor)$")


# =============================================================================
# Phase 3: Custom Domain Models
# =============================================================================

class DomainVerificationResponse(BaseModel):
    """Response for domain verification status."""
    custom_domain: Optional[str]
    domain_verified: bool
    verification_token: Optional[str]
    verification_record: Optional[str]  # The TXT record to add
    cname_target: Optional[str]  # Where to point CNAME


class InitiateDomainVerificationRequest(BaseModel):
    """Request to initiate domain verification."""
    custom_domain: str = Field(..., max_length=255)


# =============================================================================
# Phase 4: Branding Models
# =============================================================================

class UpdateBrandingRequest(BaseModel):
    """Request to update tenant branding."""
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    favicon_url: Optional[str] = None
    app_name_override: Optional[str] = Field(None, max_length=64)
    show_powered_by: Optional[bool] = None
    # Extended branding options
    accent_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    tagline: Optional[str] = Field(None, max_length=128)
    custom_footer_text: Optional[str] = Field(None, max_length=256)


class TenantWorkspaceResponse(BaseModel):
    """Response for a linked workspace."""
    workspace_id: str
    workspace_type: str
    display_name: Optional[str]
    display_order: int
    added_at: Optional[str]
    added_by: str


class LinkWorkspaceRequest(BaseModel):
    """Request to link a workspace to a tenant."""
    workspace_id: str
    workspace_type: str = Field(..., pattern=r"^(discord|slack|whatsapp)$")
    display_name: Optional[str] = Field(None, max_length=128)
    display_order: int = 0


class TenantResponse(BaseModel):
    """Response for tenant details."""
    id: str
    slug: str
    name: str
    subdomain: Optional[str]
    custom_domain: Optional[str]
    domain_verified: bool
    branding: TenantBrandingModel
    access_mode: str
    allowed_email_domains: List[str] = []
    created_at: Optional[str]
    updated_at: Optional[str]
    created_by: str


class TenantListResponse(BaseModel):
    """Response for tenant list."""
    tenants: List[TenantResponse]


class CurrentTenantResponse(BaseModel):
    """Response for current tenant (resolved from hostname)."""
    tenant: Optional[TenantResponse]
    workspaces: List[TenantWorkspaceResponse]


# =============================================================================
# Helper Functions
# =============================================================================

async def get_tenant_repository():
    """Get tenant repository instance."""
    try:
        from ...data.repositories import get_tenant_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Service unavailable")


def tenant_to_response(tenant: Tenant) -> TenantResponse:
    """Convert Tenant model to response."""
    return TenantResponse(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        subdomain=tenant.subdomain,
        custom_domain=tenant.custom_domain,
        domain_verified=tenant.domain_verified,
        branding=TenantBrandingModel(
            logo_url=tenant.branding.logo_url,
            primary_color=tenant.branding.primary_color,
            favicon_url=tenant.branding.favicon_url,
            app_name_override=tenant.branding.app_name_override,
            show_powered_by=tenant.branding.show_powered_by,
        ),
        access_mode=tenant.access_mode.value,
        allowed_email_domains=tenant.allowed_email_domains or [],
        created_at=tenant.created_at.isoformat() if tenant.created_at else None,
        updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
        created_by=tenant.created_by,
    )


def member_to_response(member: TenantMember) -> TenantMemberResponse:
    """Convert TenantMember model to response."""
    return TenantMemberResponse(
        user_id=member.user_id,
        email=member.email,
        access_level=member.access_level.value,
        invited_at=member.invited_at.isoformat() if member.invited_at else None,
        accepted_at=member.accepted_at.isoformat() if member.accepted_at else None,
    )


def admin_to_response(admin: TenantAdmin) -> TenantAdminResponse:
    """Convert TenantAdmin model to response."""
    return TenantAdminResponse(
        user_id=admin.user_id,
        role=admin.role.value,
        added_at=admin.added_at.isoformat() if admin.added_at else None,
    )


async def check_tenant_access(tenant: Tenant, user: Optional[dict], repo) -> bool:
    """Check if user has access to a tenant based on access mode.

    Phase 2: Access control implementation.
    """
    if tenant.access_mode == TenantAccessMode.PUBLIC:
        return True

    if not user:
        return False

    user_id = user.get("id")
    user_email = user.get("email")

    # Admins always have access
    if await repo.is_tenant_admin(tenant.id, user_id):
        return True

    if tenant.access_mode == TenantAccessMode.AUTHENTICATED:
        # Check email domain restriction if set
        if tenant.allowed_email_domains and user_email:
            user_domain = user_email.split("@")[1].lower()
            allowed = [d.lower() for d in tenant.allowed_email_domains]
            if user_domain not in allowed:
                return False
        return True

    if tenant.access_mode == TenantAccessMode.MEMBERS_ONLY:
        return await repo.is_tenant_member(tenant.id, user_id)

    if tenant.access_mode == TenantAccessMode.WORKSPACE_MEMBERS:
        # Check if user is member of any linked workspace
        # This requires integration with Discord/Slack member checking
        # For now, check tenant membership as fallback
        return await repo.is_tenant_member(tenant.id, user_id)

    return False


async def verify_dns_txt_record(domain: str, expected_token: str) -> bool:
    """Verify DNS TXT record for domain verification.

    Phase 3: Custom domain verification.
    """
    try:
        # Check for _summarybot.{domain} TXT record
        verification_domain = f"_summarybot.{domain}"
        answers = dns.resolver.resolve(verification_domain, "TXT")

        for rdata in answers:
            txt_value = rdata.to_text().strip('"')
            if txt_value == expected_token:
                return True

        return False
    except dns.resolver.NXDOMAIN:
        logger.debug(f"No DNS TXT record found for {domain}")
        return False
    except dns.resolver.NoAnswer:
        logger.debug(f"No TXT record answer for {domain}")
        return False
    except Exception as e:
        logger.warning(f"DNS verification failed for {domain}: {e}")
        return False


def workspace_to_response(workspace: TenantWorkspace) -> TenantWorkspaceResponse:
    """Convert TenantWorkspace model to response."""
    return TenantWorkspaceResponse(
        workspace_id=workspace.workspace_id,
        workspace_type=workspace.workspace_type.value,
        display_name=workspace.display_name,
        display_order=workspace.display_order,
        added_at=workspace.added_at.isoformat() if workspace.added_at else None,
        added_by=workspace.added_by,
    )


async def check_tenant_admin(repo, tenant_id: str, user_id: str, required_role: Optional[TenantAdminRole] = None):
    """Check if user is admin of tenant, raise 403 if not."""
    is_admin = await repo.is_tenant_admin(tenant_id, user_id, required_role)
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You don't have permission to manage this tenant"},
        )


# =============================================================================
# Routes
# =============================================================================

@router.get(
    "/current",
    response_model=CurrentTenantResponse,
    summary="Get current tenant",
    description="Get the tenant resolved from the current hostname.",
)
async def get_current_tenant_route(
    request_tenant: Optional[Tenant] = Depends(get_current_tenant),
):
    """Get current tenant from hostname."""
    if not request_tenant:
        return CurrentTenantResponse(tenant=None, workspaces=[])

    repo = await get_tenant_repository()
    workspaces = await repo.get_tenant_workspaces(request_tenant.id)

    return CurrentTenantResponse(
        tenant=tenant_to_response(request_tenant),
        workspaces=[workspace_to_response(w) for w in workspaces],
    )


@router.get(
    "",
    response_model=TenantListResponse,
    summary="List user's tenants",
    description="List all tenants the user can manage.",
)
async def list_tenants(
    user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List tenants user can manage."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenants = await repo.list_tenants_for_user(user_id, limit=limit, offset=offset)

    return TenantListResponse(
        tenants=[tenant_to_response(t) for t in tenants],
    )


@router.post(
    "",
    response_model=TenantResponse,
    summary="Create tenant",
    description="Create a new tenant. The user becomes the owner.",
)
async def create_tenant(
    body: CreateTenantRequest,
    user: dict = Depends(get_current_user),
):
    """Create a new tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    # Check if slug is already taken
    existing = await repo.get_tenant_by_slug(body.slug)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": f"Slug '{body.slug}' is already taken"},
        )

    # Check if subdomain is already taken
    if body.subdomain:
        existing = await repo.get_tenant_by_subdomain(body.subdomain)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"code": "CONFLICT", "message": f"Subdomain '{body.subdomain}' is already taken"},
            )

    # Create tenant
    branding = TenantBranding()
    if body.branding:
        branding = TenantBranding(
            logo_url=body.branding.logo_url,
            primary_color=body.branding.primary_color,
            favicon_url=body.branding.favicon_url,
            app_name_override=body.branding.app_name_override,
            show_powered_by=body.branding.show_powered_by,
        )

    tenant = Tenant(
        id=generate_id(),
        slug=body.slug,
        name=body.name,
        subdomain=body.subdomain,
        branding=branding,
        access_mode=TenantAccessMode(body.access_mode or "authenticated"),
        created_by=user_id,
    )

    await repo.save_tenant(tenant)

    # Make user the owner
    await repo.add_admin(tenant.id, user_id, TenantAdminRole.OWNER)

    logger.info(f"Created tenant '{tenant.slug}' by user {user_id}")

    # Fetch fresh tenant to get updated timestamps
    tenant = await repo.get_tenant(tenant.id)
    return tenant_to_response(tenant)


@router.get(
    "/{slug}",
    response_model=TenantResponse,
    summary="Get tenant details",
    description="Get detailed information about a tenant.",
)
async def get_tenant(
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """Get tenant details."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    # Check if user has access
    is_admin = await repo.is_tenant_admin(tenant.id, user_id)
    if not is_admin:
        # Check if user is a member or if tenant is public
        is_member = await repo.is_tenant_member(tenant.id, user_id)
        if not is_member and tenant.access_mode != TenantAccessMode.PUBLIC:
            raise HTTPException(
                status_code=403,
                detail={"code": "FORBIDDEN", "message": "You don't have access to this tenant"},
            )

    return tenant_to_response(tenant)


@router.put(
    "/{slug}",
    response_model=TenantResponse,
    summary="Update tenant",
    description="Update tenant settings.",
)
async def update_tenant(
    body: UpdateTenantRequest,
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """Update tenant settings."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.EDITOR)

    # Check subdomain uniqueness if changing
    if body.subdomain and body.subdomain != tenant.subdomain:
        existing = await repo.get_tenant_by_subdomain(body.subdomain)
        if existing and existing.id != tenant.id:
            raise HTTPException(
                status_code=409,
                detail={"code": "CONFLICT", "message": f"Subdomain '{body.subdomain}' is already taken"},
            )
        tenant.subdomain = body.subdomain

    # Check custom domain uniqueness if changing
    if body.custom_domain and body.custom_domain != tenant.custom_domain:
        existing = await repo.get_tenant_by_custom_domain(body.custom_domain)
        if existing and existing.id != tenant.id:
            raise HTTPException(
                status_code=409,
                detail={"code": "CONFLICT", "message": f"Domain '{body.custom_domain}' is already taken"},
            )
        tenant.custom_domain = body.custom_domain
        tenant.domain_verified = False  # Require re-verification

    if body.name:
        tenant.name = body.name

    if body.branding:
        tenant.branding = TenantBranding(
            logo_url=body.branding.logo_url,
            primary_color=body.branding.primary_color,
            favicon_url=body.branding.favicon_url,
            app_name_override=body.branding.app_name_override,
            show_powered_by=body.branding.show_powered_by,
        )

    if body.access_mode:
        tenant.access_mode = TenantAccessMode(body.access_mode)

    if body.allowed_email_domains is not None:
        tenant.allowed_email_domains = body.allowed_email_domains

    await repo.save_tenant(tenant)

    logger.info(f"Updated tenant '{tenant.slug}' by user {user_id}")

    # Fetch fresh tenant
    tenant = await repo.get_tenant(tenant.id)
    return tenant_to_response(tenant)


@router.delete(
    "/{slug}",
    summary="Delete tenant",
    description="Delete a tenant. Only owners can delete.",
)
async def delete_tenant(
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """Delete a tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    # Only owners can delete
    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.OWNER)

    await repo.delete_tenant(tenant.id)

    logger.info(f"Deleted tenant '{tenant.slug}' by user {user_id}")

    return {"success": True}


# =============================================================================
# Workspace Routes
# =============================================================================

@router.get(
    "/{slug}/workspaces",
    response_model=List[TenantWorkspaceResponse],
    summary="List tenant workspaces",
    description="List all workspaces linked to a tenant.",
)
async def list_tenant_workspaces(
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """List workspaces linked to a tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id)

    workspaces = await repo.get_tenant_workspaces(tenant.id)
    return [workspace_to_response(w) for w in workspaces]


@router.post(
    "/{slug}/workspaces",
    response_model=TenantWorkspaceResponse,
    summary="Link workspace",
    description="Link a workspace (Discord guild, Slack workspace, etc.) to a tenant.",
)
async def link_workspace(
    body: LinkWorkspaceRequest,
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """Link a workspace to a tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.ADMIN)

    # Check if workspace is already linked to another tenant
    existing_tenant = await repo.get_tenant_for_workspace(body.workspace_id)
    if existing_tenant and existing_tenant.id != tenant.id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT",
                "message": f"Workspace is already linked to tenant '{existing_tenant.slug}'",
            },
        )

    workspace_type = WorkspaceType(body.workspace_type)
    await repo.link_workspace(
        tenant_id=tenant.id,
        workspace_id=body.workspace_id,
        workspace_type=workspace_type,
        added_by=user_id,
        display_name=body.display_name,
        display_order=body.display_order,
    )

    logger.info(f"Linked workspace {body.workspace_id} to tenant '{tenant.slug}' by user {user_id}")

    # Fetch the workspace to return
    workspaces = await repo.get_tenant_workspaces(tenant.id)
    workspace = next((w for w in workspaces if w.workspace_id == body.workspace_id), None)

    if workspace:
        return workspace_to_response(workspace)

    # Shouldn't happen, but return a response anyway
    return TenantWorkspaceResponse(
        workspace_id=body.workspace_id,
        workspace_type=body.workspace_type,
        display_name=body.display_name,
        display_order=body.display_order,
        added_at=None,
        added_by=user_id,
    )


@router.delete(
    "/{slug}/workspaces/{workspace_id}",
    summary="Unlink workspace",
    description="Unlink a workspace from a tenant.",
)
async def unlink_workspace(
    slug: str = Path(..., description="Tenant slug"),
    workspace_id: str = Path(..., description="Workspace ID"),
    user: dict = Depends(get_current_user),
):
    """Unlink a workspace from a tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.ADMIN)

    deleted = await repo.unlink_workspace(tenant.id, workspace_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Workspace not linked to this tenant"},
        )

    logger.info(f"Unlinked workspace {workspace_id} from tenant '{tenant.slug}' by user {user_id}")

    return {"success": True}


# =============================================================================
# Phase 2: Access Control Routes
# =============================================================================

@router.get(
    "/{slug}/members",
    response_model=List[TenantMemberResponse],
    summary="List tenant members",
    description="List all members of a tenant.",
)
async def list_tenant_members(
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """List members of a tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id)

    members = await repo.get_tenant_members(tenant.id)
    return [member_to_response(m) for m in members]


@router.post(
    "/{slug}/members",
    response_model=TenantMemberResponse,
    summary="Invite member",
    description="Invite a member to the tenant by email.",
)
async def invite_member(
    body: InviteMemberRequest,
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """Invite a member to the tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.ADMIN)

    # Generate a placeholder user_id from email (will be resolved on accept)
    invited_user_id = f"email:{body.email}"

    access_level = TenantMemberAccessLevel(body.access_level)
    await repo.add_member(
        tenant_id=tenant.id,
        user_id=invited_user_id,
        email=body.email,
        access_level=access_level,
    )

    logger.info(f"Invited {body.email} to tenant '{tenant.slug}' by user {user_id}")

    # Return the member
    members = await repo.get_tenant_members(tenant.id)
    member = next((m for m in members if m.email == body.email), None)

    if member:
        return member_to_response(member)

    return TenantMemberResponse(
        user_id=invited_user_id,
        email=body.email,
        access_level=body.access_level,
        invited_at=datetime.utcnow().isoformat(),
        accepted_at=None,
    )


@router.put(
    "/{slug}/members/{member_id}",
    response_model=TenantMemberResponse,
    summary="Update member",
    description="Update a member's access level.",
)
async def update_member(
    body: UpdateMemberRequest,
    slug: str = Path(..., description="Tenant slug"),
    member_id: str = Path(..., description="Member user ID"),
    user: dict = Depends(get_current_user),
):
    """Update a member's access level."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.ADMIN)

    # Check member exists
    is_member = await repo.is_tenant_member(tenant.id, member_id)
    if not is_member:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Member not found"},
        )

    # Update member
    access_level = TenantMemberAccessLevel(body.access_level)
    await repo.add_member(tenant.id, member_id, access_level=access_level)

    logger.info(f"Updated member {member_id} in tenant '{tenant.slug}' by user {user_id}")

    members = await repo.get_tenant_members(tenant.id)
    member = next((m for m in members if m.user_id == member_id), None)

    if member:
        return member_to_response(member)

    return TenantMemberResponse(
        user_id=member_id,
        email=None,
        access_level=body.access_level,
        invited_at=None,
        accepted_at=None,
    )


@router.delete(
    "/{slug}/members/{member_id}",
    summary="Remove member",
    description="Remove a member from the tenant.",
)
async def remove_member(
    slug: str = Path(..., description="Tenant slug"),
    member_id: str = Path(..., description="Member user ID"),
    user: dict = Depends(get_current_user),
):
    """Remove a member from the tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.ADMIN)

    removed = await repo.remove_member(tenant.id, member_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Member not found"},
        )

    logger.info(f"Removed member {member_id} from tenant '{tenant.slug}' by user {user_id}")

    return {"success": True}


@router.get(
    "/{slug}/admins",
    response_model=List[TenantAdminResponse],
    summary="List tenant admins",
    description="List all admins of a tenant.",
)
async def list_tenant_admins(
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """List admins of a tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id)

    admins = await repo.get_tenant_admins(tenant.id)
    return [admin_to_response(a) for a in admins]


@router.post(
    "/{slug}/admins",
    response_model=TenantAdminResponse,
    summary="Add admin",
    description="Add an admin to the tenant.",
)
async def add_admin(
    body: AddAdminRequest,
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """Add an admin to the tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    # Only owners can add owners, admins can add admins/editors
    requested_role = TenantAdminRole(body.role)
    if requested_role == TenantAdminRole.OWNER:
        await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.OWNER)
    else:
        await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.ADMIN)

    await repo.add_admin(tenant.id, body.user_id, requested_role)

    logger.info(f"Added admin {body.user_id} ({body.role}) to tenant '{tenant.slug}' by user {user_id}")

    admins = await repo.get_tenant_admins(tenant.id)
    admin = next((a for a in admins if a.user_id == body.user_id), None)

    if admin:
        return admin_to_response(admin)

    return TenantAdminResponse(
        user_id=body.user_id,
        role=body.role,
        added_at=datetime.utcnow().isoformat(),
    )


@router.delete(
    "/{slug}/admins/{admin_id}",
    summary="Remove admin",
    description="Remove an admin from the tenant.",
)
async def remove_admin(
    slug: str = Path(..., description="Tenant slug"),
    admin_id: str = Path(..., description="Admin user ID"),
    user: dict = Depends(get_current_user),
):
    """Remove an admin from the tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    # Check if target is an owner - only owners can remove owners
    target_is_owner = await repo.is_tenant_admin(tenant.id, admin_id, TenantAdminRole.OWNER)
    if target_is_owner:
        await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.OWNER)
    else:
        await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.ADMIN)

    # Prevent removing yourself if you're the only owner
    if admin_id == user_id:
        admins = await repo.get_tenant_admins(tenant.id)
        owners = [a for a in admins if a.role == TenantAdminRole.OWNER]
        if len(owners) == 1 and owners[0].user_id == user_id:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "Cannot remove the only owner"},
            )

    removed = await repo.remove_admin(tenant.id, admin_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Admin not found"},
        )

    logger.info(f"Removed admin {admin_id} from tenant '{tenant.slug}' by user {user_id}")

    return {"success": True}


# =============================================================================
# Phase 3: Custom Domain Routes
# =============================================================================

@router.post(
    "/{slug}/domain/verify",
    response_model=DomainVerificationResponse,
    summary="Initiate domain verification",
    description="Start the custom domain verification process.",
)
async def initiate_domain_verification(
    body: InitiateDomainVerificationRequest,
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """Initiate custom domain verification."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.ADMIN)

    # Check domain isn't already taken
    existing = await repo.get_tenant_by_custom_domain(body.custom_domain)
    if existing and existing.id != tenant.id:
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": "Domain is already registered to another tenant"},
        )

    # Update tenant with new domain and generate verification token
    tenant.custom_domain = body.custom_domain
    tenant.domain_verified = False
    await repo.save_tenant(tenant)

    verification_token = await repo.generate_verification_token(tenant.id)

    # Determine CNAME target
    cname_target = f"{tenant.subdomain or tenant.slug}.summarybot.app"

    logger.info(f"Initiated domain verification for '{body.custom_domain}' on tenant '{tenant.slug}'")

    return DomainVerificationResponse(
        custom_domain=body.custom_domain,
        domain_verified=False,
        verification_token=verification_token,
        verification_record=f"_summarybot.{body.custom_domain} TXT \"{verification_token}\"",
        cname_target=cname_target,
    )


@router.get(
    "/{slug}/domain/status",
    response_model=DomainVerificationResponse,
    summary="Check domain verification status",
    description="Check the verification status of a custom domain.",
)
async def check_domain_verification(
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
    verify: bool = Query(False, description="Attempt to verify the domain"),
):
    """Check custom domain verification status."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id)

    if not tenant.custom_domain:
        return DomainVerificationResponse(
            custom_domain=None,
            domain_verified=False,
            verification_token=None,
            verification_record=None,
            cname_target=None,
        )

    cname_target = f"{tenant.subdomain or tenant.slug}.summarybot.app"

    # If already verified, return status
    if tenant.domain_verified:
        return DomainVerificationResponse(
            custom_domain=tenant.custom_domain,
            domain_verified=True,
            verification_token=None,
            verification_record=None,
            cname_target=cname_target,
        )

    # If verify=true, attempt DNS verification
    if verify and tenant.domain_verification_token:
        is_verified = await verify_dns_txt_record(
            tenant.custom_domain,
            tenant.domain_verification_token,
        )

        if is_verified:
            await repo.verify_domain(tenant.id)
            logger.info(f"Domain '{tenant.custom_domain}' verified for tenant '{tenant.slug}'")

            return DomainVerificationResponse(
                custom_domain=tenant.custom_domain,
                domain_verified=True,
                verification_token=None,
                verification_record=None,
                cname_target=cname_target,
            )

    return DomainVerificationResponse(
        custom_domain=tenant.custom_domain,
        domain_verified=False,
        verification_token=tenant.domain_verification_token,
        verification_record=f"_summarybot.{tenant.custom_domain} TXT \"{tenant.domain_verification_token}\"",
        cname_target=cname_target,
    )


@router.delete(
    "/{slug}/domain",
    summary="Remove custom domain",
    description="Remove the custom domain from a tenant.",
)
async def remove_custom_domain(
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """Remove custom domain from tenant."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.ADMIN)

    old_domain = tenant.custom_domain
    tenant.custom_domain = None
    tenant.domain_verified = False
    tenant.domain_verification_token = None
    await repo.save_tenant(tenant)

    logger.info(f"Removed custom domain '{old_domain}' from tenant '{tenant.slug}'")

    return {"success": True}


# =============================================================================
# Phase 4: Branding Routes
# =============================================================================

@router.put(
    "/{slug}/branding",
    response_model=TenantBrandingModel,
    summary="Update branding",
    description="Update tenant branding and theme settings.",
)
async def update_branding(
    body: UpdateBrandingRequest,
    slug: str = Path(..., description="Tenant slug"),
    user: dict = Depends(get_current_user),
):
    """Update tenant branding."""
    repo = await get_tenant_repository()
    user_id = user.get("id")

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    await check_tenant_admin(repo, tenant.id, user_id, TenantAdminRole.EDITOR)

    # Update branding fields
    if body.logo_url is not None:
        tenant.branding.logo_url = body.logo_url
    if body.primary_color is not None:
        tenant.branding.primary_color = body.primary_color
    if body.favicon_url is not None:
        tenant.branding.favicon_url = body.favicon_url
    if body.app_name_override is not None:
        tenant.branding.app_name_override = body.app_name_override
    if body.show_powered_by is not None:
        tenant.branding.show_powered_by = body.show_powered_by

    # Store extended branding in settings
    if body.accent_color is not None:
        tenant.settings["accent_color"] = body.accent_color
    if body.tagline is not None:
        tenant.settings["tagline"] = body.tagline
    if body.custom_footer_text is not None:
        tenant.settings["custom_footer_text"] = body.custom_footer_text

    await repo.save_tenant(tenant)

    logger.info(f"Updated branding for tenant '{tenant.slug}' by user {user_id}")

    return TenantBrandingModel(
        logo_url=tenant.branding.logo_url,
        primary_color=tenant.branding.primary_color,
        favicon_url=tenant.branding.favicon_url,
        app_name_override=tenant.branding.app_name_override,
        show_powered_by=tenant.branding.show_powered_by,
    )


@router.get(
    "/{slug}/branding",
    response_model=TenantBrandingModel,
    summary="Get branding",
    description="Get tenant branding settings.",
)
async def get_branding(
    slug: str = Path(..., description="Tenant slug"),
):
    """Get tenant branding (public endpoint)."""
    repo = await get_tenant_repository()

    tenant = await repo.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Tenant not found"},
        )

    return TenantBrandingModel(
        logo_url=tenant.branding.logo_url,
        primary_color=tenant.branding.primary_color,
        favicon_url=tenant.branding.favicon_url,
        app_name_override=tenant.branding.app_name_override,
        show_powered_by=tenant.branding.show_powered_by,
    )


# =============================================================================
# Tenant-Scoped Data Routes (accessed via subdomain)
# =============================================================================

@router.get(
    "/scope/workspaces",
    response_model=List[TenantWorkspaceResponse],
    summary="List current tenant's workspaces",
    description="List workspaces for the current tenant (from subdomain).",
)
async def list_scoped_workspaces(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """List workspaces for current tenant."""
    tenant = get_current_tenant(request)

    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "No tenant context"},
        )

    repo = await get_tenant_repository()

    # Check access
    has_access = await check_tenant_access(tenant, user, repo)
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Access denied"},
        )

    workspaces = await repo.get_tenant_workspaces(tenant.id)
    return [workspace_to_response(w) for w in workspaces]
