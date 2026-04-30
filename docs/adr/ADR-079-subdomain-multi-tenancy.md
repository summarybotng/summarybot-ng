# ADR-079: Subdomain Multi-Tenancy

## Status
Proposed

## Context

SummaryBot currently operates as a single-tenant application where all users access the same domain (summarybot-ng.fly.dev). Organizations want:

1. **Branded experience** - Custom subdomains like `pulse.agentics.org` or `summaries.guelphrobotics.ca`
2. **Workspace consolidation** - Link multiple workspaces (Discord servers, Slack workspaces, WhatsApp imports) under one tenant
3. **Access control** - Restrict who can view summaries for a tenant
4. **White-label potential** - Remove SummaryBot branding for enterprise customers

### Current Limitations

- No concept of "organization" or "tenant" - users see all guilds they have access to
- No custom domain support
- No way to group related workspaces (e.g., a company's Discord + Slack together)
- Branding is hardcoded

## Decision

### 1. Tenant Model

Introduce a `Tenant` entity that owns workspaces and configuration:

```python
@dataclass
class Tenant:
    id: str  # UUID
    slug: str  # URL-safe identifier, e.g., "agentics", "guelph-robotics"
    name: str  # Display name, e.g., "Agentics", "Guelph Robotics"

    # Custom domains
    subdomain: Optional[str]  # e.g., "pulse" for pulse.agentics.org
    custom_domain: Optional[str]  # Full custom domain if not using *.summarybot.app

    # Linked workspaces
    workspace_ids: List[str]  # Guild IDs, Slack workspace IDs, WhatsApp group IDs

    # Branding
    logo_url: Optional[str]
    primary_color: Optional[str]  # Hex color for theming
    favicon_url: Optional[str]

    # Access control
    access_mode: str  # "public", "authenticated", "members_only"
    allowed_domains: List[str]  # For SSO/email domain restriction
    admin_user_ids: List[str]  # Users who can manage this tenant

    # Settings
    default_timezone: str
    features: Dict[str, bool]  # Feature flags per tenant

    created_at: datetime
    updated_at: datetime
```

### 2. URL Structure

#### Default Domain (summarybot.app)
```
https://summarybot.app/                    # Main landing
https://summarybot.app/guilds/...          # Default app (existing)

https://pulse.summarybot.app/              # Tenant: Agentics
https://guelph.summarybot.app/             # Tenant: Guelph Robotics
```

#### Custom Domains
```
https://pulse.agentics.org/                # CNAME to pulse.summarybot.app
https://summaries.guelphrobotics.ca/       # CNAME to guelph.summarybot.app
```

#### Tenant Routes
```
/                          # Tenant dashboard (shows linked workspaces)
/workspaces                # List of linked workspaces
/workspaces/:id/...        # Workspace-specific pages (same as current /guilds/:id)
/wiki                      # Cross-workspace wiki (if enabled)
/settings                  # Tenant settings (admins only)
```

### 3. Database Schema

```sql
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,

    -- Domains
    subdomain TEXT UNIQUE,
    custom_domain TEXT UNIQUE,
    domain_verified BOOLEAN DEFAULT FALSE,
    domain_verification_token TEXT,

    -- Branding
    logo_url TEXT,
    primary_color TEXT,
    favicon_url TEXT,

    -- Access
    access_mode TEXT DEFAULT 'authenticated',
    allowed_email_domains TEXT,  -- JSON array

    -- Metadata
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    created_by TEXT NOT NULL,

    settings TEXT DEFAULT '{}'  -- JSON for extensible settings
);

CREATE TABLE tenant_workspaces (
    tenant_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,  -- Guild ID, Slack workspace ID, etc.
    workspace_type TEXT NOT NULL,  -- "discord", "slack", "whatsapp"
    display_name TEXT,  -- Override workspace name within tenant
    display_order INTEGER DEFAULT 0,
    added_at TEXT DEFAULT (datetime('now')),
    added_by TEXT NOT NULL,
    PRIMARY KEY (tenant_id, workspace_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE TABLE tenant_admins (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,  -- Discord/Google user ID
    role TEXT DEFAULT 'admin',  -- "owner", "admin", "editor"
    added_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE TABLE tenant_members (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    email TEXT,  -- For email-based access
    access_level TEXT DEFAULT 'viewer',  -- "viewer", "contributor"
    invited_at TEXT DEFAULT (datetime('now')),
    accepted_at TEXT,
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- Index for domain lookups
CREATE INDEX idx_tenants_subdomain ON tenants(subdomain);
CREATE INDEX idx_tenants_custom_domain ON tenants(custom_domain);
```

### 4. Domain Resolution Flow

```
Request: https://pulse.agentics.org/workspaces/123/summaries

1. DNS: pulse.agentics.org CNAME → pulse.summarybot.app
2. Fly.io routes to summarybot-ng app
3. Middleware extracts hostname
4. Lookup tenant by custom_domain OR subdomain
5. Verify domain_verified = true
6. Inject tenant context into request
7. Route to appropriate handler with tenant context
```

```python
class TenantMiddleware:
    async def __call__(self, request: Request, call_next):
        hostname = request.headers.get("host", "").split(":")[0]

        tenant = await self.resolve_tenant(hostname)

        if tenant:
            # Inject tenant into request state
            request.state.tenant = tenant
            request.state.tenant_id = tenant.id

        response = await call_next(request)
        return response

    async def resolve_tenant(self, hostname: str) -> Optional[Tenant]:
        # Check custom domain first
        tenant = await self.repo.get_by_custom_domain(hostname)
        if tenant and tenant.domain_verified:
            return tenant

        # Check subdomain (e.g., pulse.summarybot.app)
        if hostname.endswith(".summarybot.app"):
            subdomain = hostname.replace(".summarybot.app", "")
            return await self.repo.get_by_subdomain(subdomain)

        return None
```

### 5. Access Control Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `public` | Anyone can view summaries | Open source projects, public communities |
| `authenticated` | Must be logged in (any provider) | General organizations |
| `members_only` | Must be in tenant_members table | Private teams, enterprises |
| `workspace_members` | Must be member of linked Discord/Slack | Strict workspace-based access |

```python
async def check_tenant_access(tenant: Tenant, user: User) -> bool:
    if tenant.access_mode == "public":
        return True

    if not user:
        return False

    if tenant.access_mode == "authenticated":
        # Check email domain restriction if set
        if tenant.allowed_email_domains:
            user_domain = user.email.split("@")[1]
            if user_domain not in tenant.allowed_email_domains:
                return False
        return True

    if tenant.access_mode == "members_only":
        return await is_tenant_member(tenant.id, user.id)

    if tenant.access_mode == "workspace_members":
        # Check if user is member of any linked workspace
        for ws in tenant.workspace_ids:
            if await is_workspace_member(ws, user.id):
                return True
        return False

    return False
```

### 6. Branding & Theming

```typescript
interface TenantTheme {
  name: string;
  logoUrl?: string;
  faviconUrl?: string;
  primaryColor: string;  // HSL or hex
  accentColor?: string;

  // Text overrides
  appName?: string;  // Replace "SummaryBot" in UI
  tagline?: string;

  // Footer
  showPoweredBy: boolean;  // "Powered by SummaryBot"
  customFooterText?: string;
}

// Apply theme via CSS variables
function applyTenantTheme(theme: TenantTheme) {
  const root = document.documentElement;

  if (theme.primaryColor) {
    root.style.setProperty('--primary', theme.primaryColor);
  }

  if (theme.faviconUrl) {
    document.querySelector('link[rel="icon"]')?.setAttribute('href', theme.faviconUrl);
  }

  document.title = theme.appName || 'SummaryBot';
}
```

### 7. Custom Domain Verification

To prevent domain hijacking, require DNS verification:

```
1. User requests custom domain: summaries.example.com
2. System generates verification token: sb-verify-abc123xyz
3. User adds TXT record: _summarybot.example.com TXT "sb-verify-abc123xyz"
4. System verifies TXT record exists
5. domain_verified = true
6. User adds CNAME: summaries.example.com CNAME {tenant_slug}.summarybot.app
```

### 8. API Endpoints

```
# Tenant Management (requires authentication)
GET    /api/v1/tenants                     # List user's tenants
POST   /api/v1/tenants                     # Create tenant
GET    /api/v1/tenants/:slug               # Get tenant details
PUT    /api/v1/tenants/:slug               # Update tenant
DELETE /api/v1/tenants/:slug               # Delete tenant

# Workspace Linking
POST   /api/v1/tenants/:slug/workspaces    # Link workspace
DELETE /api/v1/tenants/:slug/workspaces/:id # Unlink workspace
PUT    /api/v1/tenants/:slug/workspaces/:id # Update workspace display settings

# Domain Management
POST   /api/v1/tenants/:slug/domain/verify # Initiate domain verification
GET    /api/v1/tenants/:slug/domain/status # Check verification status

# Members
GET    /api/v1/tenants/:slug/members       # List members
POST   /api/v1/tenants/:slug/members       # Invite member
DELETE /api/v1/tenants/:slug/members/:id   # Remove member

# Tenant-Scoped Data (accessed via subdomain)
GET    /api/v1/workspaces                  # List tenant's workspaces
GET    /api/v1/summaries                   # Cross-workspace summary search
GET    /api/v1/wiki                        # Tenant-wide wiki (merged from all workspaces)
```

### 9. Fly.io Configuration

```toml
# fly.toml

[http_service]
  internal_port = 5000
  force_https = true

# Handle wildcard subdomain
[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  path = "/health"
  timeout = "5s"

# Certificate for *.summarybot.app
[[tls]]
  alpn = ["h2", "http/1.1"]

# Custom domains added via `flyctl certs add`
```

```bash
# Add wildcard cert for subdomains
flyctl certs add "*.summarybot.app" --app summarybot-ng

# Add custom domain (after DNS verification)
flyctl certs add "summaries.example.com" --app summarybot-ng
```

### 10. Frontend Routing

```typescript
// App.tsx - Tenant-aware routing
function App() {
  const tenant = useTenant();  // From context, populated by API call

  if (tenant) {
    // Tenant-scoped routes
    return (
      <Routes>
        <Route path="/" element={<TenantDashboard />} />
        <Route path="/workspaces" element={<TenantWorkspaces />} />
        <Route path="/workspaces/:id/*" element={<WorkspaceLayout />} />
        <Route path="/wiki/*" element={<TenantWiki />} />
        <Route path="/settings" element={<TenantSettings />} />
      </Routes>
    );
  }

  // Default routes (summarybot.app)
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/guilds/*" element={<GuildsRoutes />} />
      {/* ... */}
    </Routes>
  );
}
```

## Implementation Phases

### Phase 1: Foundation
- [ ] Database schema for tenants
- [ ] Tenant CRUD API
- [ ] Basic subdomain routing (*.summarybot.app)
- [ ] Workspace linking

### Phase 2: Access Control
- [ ] Tenant membership model
- [ ] Access mode enforcement
- [ ] Email domain restrictions
- [ ] Invite flow

### Phase 3: Custom Domains
- [ ] Domain verification flow
- [ ] Fly.io certificate automation
- [ ] Custom domain routing

### Phase 4: Branding
- [ ] Theme customization UI
- [ ] Logo/favicon upload
- [ ] CSS variable theming
- [ ] White-label mode

### Phase 5: Cross-Workspace Features
- [ ] Unified search across workspaces
- [ ] Tenant-wide wiki (merged from all workspaces)
- [ ] Cross-workspace analytics

## Consequences

### Positive
- Organizations get branded, professional summary portals
- Multiple workspaces unified under one tenant
- Flexible access control for different use cases
- Foundation for enterprise/SaaS model
- Better organization for multi-platform users

### Negative
- Increased complexity in routing and access control
- DNS/certificate management overhead
- Potential for subdomain squatting (mitigate with verification)
- More infrastructure to maintain

## Security Considerations

1. **Domain verification required** - Prevent claiming domains you don't own
2. **Tenant isolation** - Ensure data from one tenant can't leak to another
3. **Admin audit logging** - Track all tenant configuration changes
4. **Rate limiting per tenant** - Prevent abuse of shared infrastructure

## Pricing Considerations (Future)

| Tier | Subdomains | Custom Domains | Workspaces | Branding |
|------|------------|----------------|------------|----------|
| Free | None | None | 1 | SummaryBot branded |
| Pro | *.summarybot.app | None | 5 | Partial |
| Enterprise | *.summarybot.app | Unlimited | Unlimited | Full white-label |

## References
- ADR-078: Platform-Agnostic UX Design
- ADR-043: Slack Workspace Integration
- [Fly.io Custom Domains](https://fly.io/docs/app-guides/custom-domains-with-fly/)
- [Multi-tenant SaaS patterns](https://docs.microsoft.com/en-us/azure/architecture/guide/multitenant/overview)
