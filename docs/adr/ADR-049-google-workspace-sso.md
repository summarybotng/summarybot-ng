# ADR-049: Google Workspace SSO with Domain Restriction

**Status:** Implemented
**Date:** 2026-04-22
**Implemented:** 2026-04-23
**Related:** ADR-045 (Audit Logging)

---

## 1. Context

### Current Authentication

SummaryBot currently uses Discord OAuth2 for authentication:
- Users log in with their Discord account
- Access is granted based on Discord guild membership
- Works well for Discord-native communities

### The Need

Organizations using Google Workspace want to:
1. **Single Sign-On (SSO)** - Use existing Google accounts instead of requiring Discord
2. **Domain restriction** - Only allow users from specific domains (e.g., `@agentics.org`)
3. **Per-environment configuration** - Different deployments can have different allowed domains
4. **Centralized access control** - IT admins manage access via Google Workspace

### Use Cases

1. **Corporate deployment** - Company wants employees (`@company.com`) to access summaries without Discord
2. **Partner access** - Allow specific partner domains alongside the primary domain
3. **Consultant access** - Temporary access for `@consultancy.com` domain

---

## 2. Decision

Implement Google OAuth2 SSO with configurable domain restrictions as an **additional** authentication method alongside Discord OAuth.

### 2.1 Configuration

Environment variables for Google SSO:

```bash
# Google OAuth credentials (from Google Cloud Console)
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx

# Allowed domains (comma-separated)
# Only users with emails from these domains can log in
GOOGLE_ALLOWED_DOMAINS=agentics.org,partner.com

# Optional: Require Google Workspace (reject personal @gmail.com)
GOOGLE_REQUIRE_WORKSPACE=true

# Optional: Default guild ID for Google SSO users
# (since they don't have Discord guild membership)
GOOGLE_DEFAULT_GUILD_ID=1283874310720716890
```

### 2.2 Authentication Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│  Dashboard  │────▶│   Google    │
│             │     │   /login    │     │   OAuth2    │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                    │
                           │◀───────────────────┘
                           │   id_token with email
                           ▼
                    ┌─────────────┐
                    │   Verify    │
                    │   Domain    │
                    └─────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
        ✅ Allowed                 ❌ Rejected
        Create JWT                 Show error
```

### 2.3 Domain Verification

```python
def verify_google_domain(email: str, allowed_domains: list[str]) -> bool:
    """Verify email domain is in allowed list."""
    if not allowed_domains:
        return True  # No restriction if not configured

    domain = email.split('@')[1].lower()
    return domain in [d.lower() for d in allowed_domains]
```

### 2.4 JWT Claims for Google Users

```python
# Google SSO user JWT payload
{
    "sub": "google_123456789",  # Google user ID with prefix
    "email": "user@agentics.org",
    "name": "User Name",
    "picture": "https://...",
    "auth_provider": "google",
    "domain": "agentics.org",
    "guilds": ["1283874310720716890"],  # Default guild from config
    "iat": 1234567890,
    "exp": 1234567890
}
```

### 2.5 Guild Access for Google Users

Google SSO users don't have Discord guild membership. Options:

1. **Default guild assignment** - All Google users get access to configured default guild
2. **Domain-to-guild mapping** - Map specific domains to specific guilds
3. **Manual assignment** - Admin assigns guilds to Google users via dashboard

Recommended: Start with option 1 (default guild), add option 2 later if needed.

```bash
# Simple: All Google users get this guild
GOOGLE_DEFAULT_GUILD_ID=1283874310720716890

# Future: Domain-to-guild mapping
GOOGLE_DOMAIN_GUILDS=agentics.org:1283874310720716890,partner.com:9876543210
```

---

## 3. Implementation Plan

### Phase 1: Core Google SSO

1. **Add Google OAuth routes** (`/auth/google`, `/auth/google/callback`)
2. **Domain verification middleware**
3. **JWT generation for Google users**
4. **Login page with Google option**

### Phase 2: Guild Access

1. **Default guild assignment** for Google users
2. **Google user table** for storing guild assignments
3. **Admin UI for managing Google user access**

### Phase 3: Advanced Features

1. **Domain-to-guild mapping**
2. **Google Workspace directory integration** (list users, groups)
3. **Automatic group-to-role mapping**

---

## 4. API Changes

### 4.1 New Routes

```python
# Google OAuth initiation
GET /api/v1/auth/google
# Redirects to Google OAuth consent screen

# Google OAuth callback
GET /api/v1/auth/google/callback?code=xxx
# Exchanges code for tokens, verifies domain, issues JWT

# Get current auth providers
GET /api/v1/auth/providers
# Returns: { "discord": true, "google": true }
```

### 4.2 Login Page Update

```tsx
// Login page shows available providers
<Button onClick={loginWithDiscord}>
  <DiscordIcon /> Continue with Discord
</Button>

{googleEnabled && (
  <Button onClick={loginWithGoogle}>
    <GoogleIcon /> Continue with Google
  </Button>
)}
```

---

## 5. Security Considerations

> ⚠️ **Security Review Status**: This ADR was reviewed by QE Security Fleet (2026-04-23).
> All requirements below are MANDATORY for implementation.

### 5.1 Domain Verification (CRITICAL)

- **MUST use `hd` claim** - Google's `id_token` includes `hd` (hosted domain) verified by Google
- **NEVER parse email addresses** - Email suffix can be manipulated; `hd` claim cannot
- **Unicode normalization required** - Apply NFKC normalization and Punycode to prevent homoglyph attacks
- **Fail closed** - Empty `GOOGLE_ALLOWED_DOMAINS` MUST reject all (not allow all)

```python
import unicodedata

def verify_google_domain(id_token_claims: dict, allowed_domains: list[str]) -> bool:
    """Verify domain using Google's verified hd claim.

    SECURITY: Never parse email - use hd claim only.
    """
    # CRITICAL: Fail closed - require explicit domain config
    if not allowed_domains:
        raise ValueError("GOOGLE_ALLOWED_DOMAINS must be configured")

    hd = id_token_claims.get("hd")

    # Personal Gmail has no hd claim
    if hd is None:
        return False

    # CRITICAL: Normalize to prevent Unicode homoglyph attacks
    normalized_hd = unicodedata.normalize('NFKC', hd.lower())
    normalized_allowed = [unicodedata.normalize('NFKC', d.lower()) for d in allowed_domains]

    return normalized_hd in normalized_allowed
```

### 5.2 OAuth Security (CRITICAL)

- **MUST implement PKCE** (RFC 7636) - Prevents authorization code interception
- **MUST include nonce** - Prevents ID token replay attacks
- **MUST validate nonce** - Verify nonce in ID token matches sent value
- **State token TTL**: 5 minutes maximum (not 10)
- **Atomic state consumption** - Use mutex to prevent race conditions

```python
import hashlib
import secrets
import threading

class GoogleOAuth:
    def __init__(self):
        self._state_lock = threading.Lock()
        self._pending_states = {}

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code_verifier and code_challenge."""
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip('=')
        return verifier, challenge

    def validate_state_atomic(self, state: str) -> bool:
        """Atomically validate and consume state token."""
        with self._state_lock:
            return self._pending_states.pop(state, None) is not None
```

### 5.3 Token Security (HIGH)

- **JWT algorithm restriction** - Explicitly allow only `["HS256"]`
- **Short expiration** - 1-4 hours maximum (not 24)
- **Required claims** - `exp`, `iat`, `sub`, `auth_provider`
- **Token binding** - Consider device fingerprint binding
- **Verify ID token signature** - Use `google.oauth2.id_token.verify_oauth2_token()`

### 5.4 Rate Limiting (HIGH)

```python
# REQUIRED rate limits
@limiter.limit("10/minute")  # OAuth initiation
async def google_login(): ...

@limiter.limit("5/minute")   # OAuth callback
async def google_callback(): ...
```

### 5.5 Error Handling (HIGH)

- **Generic error messages only** - Never reveal domain lists or internal state
- **Constant-time comparisons** - Prevent timing attacks
- **No PII in logs** - Hash or omit email addresses

```python
# WRONG: Reveals internal state
raise HTTPException(400, f"Domain {domain} not in {allowed_domains}")

# RIGHT: Generic message
raise HTTPException(401, detail={"code": "AUTH_FAILED", "message": "Authentication failed"})
```

### 5.6 Redirect URI Security (HIGH)

- **Exact match only** - No wildcard or partial matching
- **HTTPS required** - In production, reject HTTP
- **No fragments** - Reject URIs with `#` fragments
- **Strict whitelist** - Define in environment, validate on every request

### 5.7 Guild Access (HIGH)

- **No implicit guild access** - Don't use `GOOGLE_DEFAULT_GUILD_ID`
- **Explicit domain-to-guild mapping** - Require admin configuration
- **Default role is member** - Never auto-assign admin
- **Approval workflow** - Consider requiring admin approval for new users

---

## 6. Configuration Examples

> ⚠️ **Security Note**: `GOOGLE_REQUIRE_WORKSPACE` defaults to `true`.
> `GOOGLE_ALLOWED_DOMAINS` MUST be set - empty value rejects all.

### Example 1: Single Organization (Recommended)

```bash
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx                        # Store in secrets manager!
GOOGLE_ALLOWED_DOMAINS=agentics.org
GOOGLE_REQUIRE_WORKSPACE=true                   # Default, explicit for clarity
GOOGLE_DOMAIN_GUILDS=agentics.org:1283874310720716890
```

### Example 2: Multiple Domains

```bash
GOOGLE_ALLOWED_DOMAINS=agentics.org,partner.com
GOOGLE_DOMAIN_GUILDS=agentics.org:123,partner.com:456
```

### Example 3: ~~Any Google Account~~ (REMOVED - Security Risk)

```bash
# ⛔ NEVER USE: Empty GOOGLE_ALLOWED_DOMAINS is rejected
# GOOGLE_ALLOWED_DOMAINS=
# This configuration is explicitly blocked for security
```

### Example 4: Workspace Only (Default Behavior)

```bash
GOOGLE_ALLOWED_DOMAINS=agentics.org
# GOOGLE_REQUIRE_WORKSPACE=true is the default
```

---

## 7. Files to Create/Modify

| File | Change |
|------|--------|
| `src/dashboard/routes/auth.py` | Add Google OAuth routes |
| `src/dashboard/auth.py` | Add Google token verification |
| `src/frontend/src/pages/Login.tsx` | Add Google login button |
| `src/data/migrations/049_google_users.sql` | Google user storage |
| `.env.example` | Document Google env vars |

---

## 8. Dependencies

```toml
# pyproject.toml additions
google-auth = "^2.0"
google-auth-oauthlib = "^1.0"
```

---

## 9. Consequences

### Positive
- Organizations can use existing Google accounts
- Centralized access control via Google Workspace
- No Discord account required for dashboard access
- Per-environment domain configuration

### Negative
- Additional OAuth provider to maintain
- Google users can't interact with Discord features (reactions, mentions)
- Complexity in managing two auth systems

### Risks
- Domain misconfiguration could allow unauthorized access
- Google API rate limits (mitigated by caching)

---

## 10. Security Implementation Checklist

> Required before production deployment. From QE Security Fleet review 2026-04-23.

### P0 - Critical (Block deployment)
- [x] Use `hd` claim for domain verification (not email parsing)
- [x] Implement PKCE (RFC 7636) for OAuth flow
- [x] Add nonce to prevent ID token replay
- [x] Unicode NFKC normalization for domain comparison
- [x] Atomic state consumption with mutex
- [x] Fail closed on empty `GOOGLE_ALLOWED_DOMAINS`
- [x] Default `GOOGLE_REQUIRE_WORKSPACE=true`

### P1 - High (Before code review)
- [x] Strict redirect_uri whitelist (exact match)
- [ ] Rate limiting: 10/min login, 5/min callback (deferred - requires slowapi)
- [x] Generic error messages (no domain/state leakage)
- [x] JWT algorithm restriction to `["HS256"]`
- [x] Verify Google ID token signature via library
- [x] Explicit domain-to-guild mapping (no default guild)
- [ ] Add Referrer-Policy: no-referrer header

### P2 - Medium (Before merge)
- [x] No PII in logs (only logging domain, not email)
- [x] Session binding claims in JWT (`auth_provider`, `domain`)
- [ ] Token encryption at rest (Fernet) - tokens are short-lived
- [x] Reduce JWT expiration to 1-4 hours (set to 4 hours)
- [x] Comprehensive audit logging

---

## 11. Setup Guide

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Note the **Project ID** for later

### Step 2: Configure OAuth Consent Screen

1. Navigate to **APIs & Services** → **OAuth consent screen**
2. Select **Internal** (recommended for Workspace-only) or **External**
3. Fill in required fields:
   - **App name**: `SummaryBot Dashboard`
   - **User support email**: Your admin email
   - **Developer contact email**: Your email
4. Click **Save and Continue**
5. Add scopes:
   - `openid`
   - `email`
   - `profile`
6. Click **Save and Continue** through remaining screens

### Step 3: Create OAuth Credentials

1. Navigate to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Select **Web application**
4. Configure:
   - **Name**: `SummaryBot Dashboard`
   - **Authorized redirect URIs**:
     - `https://your-domain.fly.dev/api/v1/auth/google/callback`
     - (For local dev: `http://localhost:5000/api/v1/auth/google/callback`)
5. Click **Create**
6. Copy the **Client ID** and **Client Secret**

### Step 4: Configure Environment Variables

Add to your Fly.io secrets:

```bash
# Set Google OAuth credentials
flyctl secrets set GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
flyctl secrets set GOOGLE_CLIENT_SECRET="your-client-secret"

# Set allowed domains (comma-separated, no spaces)
flyctl secrets set GOOGLE_ALLOWED_DOMAINS="agentics.org"

# Map domains to Discord guilds
flyctl secrets set GOOGLE_DOMAIN_GUILDS="agentics.org:1283874310720716890"
```

Or for local development, add to `.env`:

```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_ALLOWED_DOMAINS=agentics.org
GOOGLE_DOMAIN_GUILDS=agentics.org:1283874310720716890
```

### Step 5: Verify Configuration

After deployment, check the available providers:

```bash
curl https://your-domain.fly.dev/api/v1/auth/google/providers
```

Expected response:
```json
{"discord": true, "google": true}
```

### Step 6: Test Login Flow

1. Visit your dashboard
2. Click "Continue with Google"
3. Sign in with a Google Workspace account from your allowed domain
4. Verify you're redirected back and logged in

### Troubleshooting

| Issue | Solution |
|-------|----------|
| `Google SSO is not configured` | Verify `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set |
| `Domain not authorized` | Check `GOOGLE_ALLOWED_DOMAINS` includes your domain |
| `Google Workspace account required` | Personal Gmail accounts are rejected by default |
| `redirect_uri_mismatch` | Ensure the redirect URI in Google Console exactly matches |
| No guilds after login | Configure `GOOGLE_DOMAIN_GUILDS` mapping |

### Security Checklist

Before going live:

- [ ] Using `Internal` OAuth consent screen (Workspace-only)
- [ ] `GOOGLE_ALLOWED_DOMAINS` is set and non-empty
- [ ] `GOOGLE_CLIENT_SECRET` is stored as a Fly.io secret (not in fly.toml)
- [ ] Redirect URI uses HTTPS
- [ ] `GOOGLE_DOMAIN_GUILDS` maps your domain to the correct guild

---

## 12. Future Considerations

1. **SAML SSO** - For enterprise customers with Okta, Azure AD, etc.
2. **Magic link auth** - Email-based passwordless login
3. **API keys** - For programmatic access without OAuth
4. **Role sync** - Sync Google Workspace groups to dashboard roles
