# ADR-050: Google Workspace Group-Based Admin Access

## Status
Proposed

## Context

Currently, Google Workspace SSO users (ADR-049) are assigned a default "member" role for all guilds they have access to. This prevents them from performing admin actions like:
- Configuring Slack integration (ADR-043)
- Managing schedules
- Pushing summaries to channels
- Other admin-only operations

Simply giving all Google SSO users admin access is too permissive. We need a way to grant admin access based on Google Workspace group membership, allowing organizations to control who can configure integrations.

### Requirements

1. **Group-Based Admin Access**: Only Google Workspace users in specific groups should receive admin permissions
2. **Configurable Per Guild**: Each guild can specify which Google group grants admin access
3. **Sensible Defaults**: Default to Google Workspace admin groups if not configured
4. **System Admin Override**: System administrators can configure group mappings
5. **Graceful Degradation**: If group checking fails, fall back to member-only access

## Decision

### 1. Data Model

Add a new table to store guild-to-Google-group mappings:

```sql
CREATE TABLE guild_google_admin_groups (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    google_group_email TEXT NOT NULL,  -- e.g., "admins@company.com"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,  -- User ID who configured this
    UNIQUE(guild_id, google_group_email)
);
```

### 2. Google Directory API Integration

To check group membership, we need additional OAuth scopes:

```python
GOOGLE_ADMIN_SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.group.readonly",
    "https://www.googleapis.com/auth/admin.directory.group.member.readonly",
]
```

**Note**: These scopes require:
- Google Workspace admin consent (not just user consent)
- Service account with domain-wide delegation, OR
- Admin user OAuth flow

### 3. Group Membership Check Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Google SSO      │     │ Check Group      │     │ Assign Role     │
│ Callback        │────▶│ Membership       │────▶│ (admin/member)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │ guild_google_    │
                        │ admin_groups     │
                        └──────────────────┘
```

### 4. Configuration Options

#### Option A: Service Account with Domain-Wide Delegation (Recommended)

```env
GOOGLE_SERVICE_ACCOUNT_JSON={"type": "service_account", ...}
GOOGLE_ADMIN_EMAIL=admin@company.com  # For impersonation
```

Pros:
- Works without user interaction
- Can check any user's group membership
- More reliable for backend operations

Cons:
- Requires Workspace admin to set up delegation
- More complex initial setup

#### Option B: Admin OAuth Flow

Require a Workspace admin to authenticate once to grant directory access.

Pros:
- Simpler to understand
- Uses existing OAuth infrastructure

Cons:
- Token refresh complexity
- Single point of failure if admin token expires

### 5. Default Admin Groups

If no custom mapping is configured, check these groups:
1. `admins@{domain}` - Common admin group
2. Check if user has Workspace admin role (requires Directory API)

### 6. API Endpoints

```
# Admin endpoints for configuring group mappings
POST   /api/v1/guilds/{guild_id}/google-admin-groups
GET    /api/v1/guilds/{guild_id}/google-admin-groups
DELETE /api/v1/guilds/{guild_id}/google-admin-groups/{group_email}

# Request body for POST
{
    "google_group_email": "summarybot-admins@company.com"
}
```

### 7. JWT Payload Changes

Update the Google SSO JWT to include group-derived roles:

```python
payload = {
    "sub": f"google_{user_id}",
    "email": email,
    "auth_provider": "google",
    "domain": domain,
    "guilds": guild_ids,
    "guild_roles": {
        "guild_123": "admin",   # User is in admin group for this guild
        "guild_456": "member",  # User is not in admin group
    },
    "google_groups": ["admins@company.com", "engineering@company.com"],
}
```

### 8. Fallback Behavior

```python
async def get_google_user_role(user_email: str, guild_id: str) -> str:
    """Determine role for Google user in a guild."""
    try:
        # Get configured admin groups for this guild
        admin_groups = await get_guild_admin_groups(guild_id)

        if not admin_groups:
            # No groups configured - check default admin group
            admin_groups = [f"admins@{get_domain(user_email)}"]

        # Check if user is in any admin group
        user_groups = await get_user_groups(user_email)

        if any(g in admin_groups for g in user_groups):
            return "admin"

        return "member"

    except GoogleAPIError:
        # API error - fail safe to member
        logger.warning(f"Failed to check groups for {user_email}")
        return "member"
```

## Implementation Phases

### Phase 1: Basic Group Configuration (MVP)
- Add `guild_google_admin_groups` table
- Add API endpoints for CRUD operations
- UI for system admins to configure groups
- Store configured groups, but don't check membership yet
- **Temporary**: Grant admin to all Google SSO users for configured guilds

### Phase 2: Service Account Integration
- Set up service account with domain-wide delegation
- Implement Directory API client
- Check group membership on SSO callback
- Assign roles based on membership

### Phase 3: Caching and Optimization
- Cache group memberships (5-15 minute TTL)
- Background job to refresh memberships
- Handle edge cases (user removed from group)

## Alternatives Considered

### 1. Email Domain Pattern Matching
Grant admin based on email patterns like `*-admin@company.com`.

**Rejected**: Too easily spoofed, not tied to actual group membership.

### 2. Manual User Mapping
Admin manually maps Google emails to roles.

**Rejected**: Doesn't scale, out of sync with Google directory.

### 3. Require Discord OAuth for Admin Actions
Force users to also authenticate via Discord for admin permissions.

**Rejected**: Poor UX for Google-first organizations.

## Security Considerations

1. **Service Account Key Protection**: Store encrypted, rotate regularly
2. **Principle of Least Privilege**: Only request necessary scopes
3. **Audit Logging**: Log all admin group configuration changes
4. **Rate Limiting**: Respect Google API quotas
5. **Token Security**: Don't expose group membership in client-side code

## Migration

For existing Google SSO users:
1. Phase 1: Continue with current behavior (member role)
2. Phase 2: Re-authenticate to get updated role based on groups
3. Consider: Force re-auth after group checking is enabled

## References

- [Google Directory API](https://developers.google.com/admin-sdk/directory)
- [Domain-Wide Delegation](https://developers.google.com/identity/protocols/oauth2/service-account#delegatingauthority)
- ADR-049: Google Workspace SSO
- ADR-043: Slack Integration
