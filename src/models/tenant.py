"""
Tenant models for subdomain multi-tenancy (ADR-079).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from .base import BaseModel, generate_id, utc_now


class TenantAccessMode(str, Enum):
    """Access control mode for a tenant."""
    PUBLIC = "public"  # Anyone can view (read-only)
    AUTHENTICATED = "authenticated"  # Any logged-in user
    MEMBERS_ONLY = "members_only"  # Explicit tenant members
    WORKSPACE_MEMBERS = "workspace_members"  # Members of linked workspaces


class TenantAdminRole(str, Enum):
    """Admin role within a tenant."""
    OWNER = "owner"  # Full control, can delete tenant
    ADMIN = "admin"  # Can manage settings and members
    EDITOR = "editor"  # Can edit branding only


class TenantMemberAccessLevel(str, Enum):
    """Access level for tenant members."""
    VIEWER = "viewer"  # Read-only access
    CONTRIBUTOR = "contributor"  # Can create/push summaries


class WorkspaceType(str, Enum):
    """Type of workspace linked to a tenant."""
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"


@dataclass
class TenantBranding:
    """Branding configuration for a tenant."""
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    favicon_url: Optional[str] = None
    app_name_override: Optional[str] = None
    show_powered_by: bool = True


@dataclass
class TenantWorkspace(BaseModel):
    """A workspace linked to a tenant."""
    tenant_id: str
    workspace_id: str
    workspace_type: WorkspaceType
    display_name: Optional[str] = None
    display_order: int = 0
    added_at: Optional[datetime] = None
    added_by: str = ""


@dataclass
class TenantAdmin(BaseModel):
    """An administrator of a tenant."""
    tenant_id: str
    user_id: str
    role: TenantAdminRole = TenantAdminRole.ADMIN
    added_at: Optional[datetime] = None


@dataclass
class TenantMember(BaseModel):
    """A member with access to a tenant."""
    tenant_id: str
    user_id: str
    email: Optional[str] = None
    access_level: TenantMemberAccessLevel = TenantMemberAccessLevel.VIEWER
    invited_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None


@dataclass
class Tenant(BaseModel):
    """A tenant representing a subdomain/custom domain."""
    id: str = field(default_factory=generate_id)
    slug: str = ""  # URL-safe identifier, e.g., "acme-corp"
    name: str = ""  # Display name, e.g., "Acme Corporation"

    # Domain configuration
    subdomain: Optional[str] = None  # e.g., "acme" for acme.summarybot.app
    custom_domain: Optional[str] = None  # e.g., "summaries.acme.com"
    domain_verified: bool = False
    domain_verification_token: Optional[str] = None

    # Branding
    branding: TenantBranding = field(default_factory=TenantBranding)

    # Access control
    access_mode: TenantAccessMode = TenantAccessMode.AUTHENTICATED
    allowed_email_domains: List[str] = field(default_factory=list)

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: str = ""

    # Additional settings (JSON blob)
    settings: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = utc_now()
        if self.updated_at is None:
            self.updated_at = utc_now()
