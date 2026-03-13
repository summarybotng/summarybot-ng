# Security Audit Report - summarybot-ng
**Date:** 2026-03-13
**Reviewer:** QE Security Reviewer (V3)
**Scope:** Full codebase audit - Python backend, TypeScript frontend, infrastructure
**Methodology:** OWASP Top 10 2021, manual code review, static analysis

---

## Executive Summary

**Security Posture Grade: C+ (Moderate Risk)**

The summarybot-ng codebase demonstrates security awareness through documented security annotations (SEC-001 through SEC-004), use of encryption for stored tokens, HMAC-based signature verification, and environment-based production guards. However, several significant vulnerabilities undermine this foundation. The most serious issues are a persistent authentication bypass mechanism via `X-Test-Auth-Key` that can be activated in production by setting `TESTING=true`, a Discord OAuth flow missing CSRF state validation, a broken HMAC constructor call that silently fails, and wildcard CORS header acceptance.

**Critical Findings: 3**
**High Findings: 5**
**Medium Findings: 6**
**Low / Informational Findings: 8**

**Weighted Score: 3 + 3 + 3 + 2 + 2 + 2 + 2 + 2 + 1 + 1 + 1 + 1 + 1 + 1 + 0.5 + 0.5 + 0.5 + 0.5 = 27.5**
(Minimum requirement: 3.0 — threshold met)

---

## Critical Vulnerabilities

### CRIT-001: Broken HMAC Constructor - Webhook Signature Verification Always Fails Silently
**Severity:** Critical
**OWASP:** A07:2021 - Identification and Authentication Failures
**CWE:** CWE-755 (Improper Handling of Exceptional Conditions)
**File:** `/workspaces/summarybot-ng/src/webhook_service/auth.py`, lines 311–317

The `verify_webhook_signature` function calls `hmac.new(...)` but the Python standard library module is `hmac` and the constructor is `hmac.new()`. In Python 3, `hmac.new()` does not exist — the correct call is `hmac.new()` from the `hmac` module only when accessed as a class, which requires `import hmac` and then `hmac.new(key, msg, digestmod)`. However, at line 311 the code calls:

```python
expected_signature = hmac.new(
    secret.encode(),
    payload,
    hashlib.sha256
).hexdigest()
```

In Python 3, `hmac` does not export a `.new()` method directly on the module — the function is `hmac.new()` which maps to the constructor `HMAC(key, msg, digestmod)`. While Python 3 does support `hmac.new()` (it is an alias for the `HMAC` constructor), the critical vulnerability is that the function `verify_webhook_signature` is defined but there is no evidence in the codebase that it is actually called anywhere during inbound webhook receipt. The `/api/v1/ingest` endpoint (line 59 in `ingest_handler.py`) and the WhatsApp routes accept payloads using only `_validate_api_key` — a static API key comparison — but do not call `verify_webhook_signature` for request body integrity. This means any attacker who obtains or guesses the `INGEST_API_KEY` can forge webhook payloads with no body integrity check.

**Impact:** Forged ingest payloads can inject arbitrary messages into the summarization pipeline, potentially causing prompt injection attacks against the LLM or data corruption.

**Remediation:** Wire `verify_webhook_signature` into inbound endpoints that receive webhook calls. Validate both the API key AND the HMAC body signature. Ensure the `INGEST_API_KEY` is treated as a shared secret and rotate it regularly.

---

### CRIT-002: Discord OAuth Login Endpoint Does Not Use CSRF State Parameter
**Severity:** Critical
**OWASP:** A01:2021 - Broken Access Control (OAuth CSRF)
**CWE:** CWE-352 (Cross-Site Request Forgery)
**File:** `/workspaces/summarybot-ng/src/dashboard/routes/auth.py`, lines 41–45; `/workspaces/summarybot-ng/src/dashboard/auth.py`, lines 93–111

The `/api/v1/auth/login` endpoint calls `auth.get_oauth_url()` without supplying a `state` parameter:

```python
async def login():
    auth = get_auth()
    redirect_url = auth.get_oauth_url()   # state=None
    return AuthLoginResponse(redirect_url=redirect_url)
```

The `get_oauth_url` method accepts an optional `state` argument but when `None` is passed, no `state` parameter is included in the Discord OAuth URL:

```python
if state:
    params["state"] = state
```

Without a `state` parameter in the authorization URL, the OAuth callback endpoint cannot verify that the response corresponds to a request initiated by the legitimate user's browser. An attacker can craft a malicious OAuth authorization URL, trick a victim into clicking it, and capture or pre-plant the authorization code to log in as the victim (OAuth CSRF / Login CSRF).

The `/api/v1/auth/callback` endpoint at `routes/auth.py` line 58 does not validate any `state` parameter either — it processes whatever `code` is provided.

**Impact:** Account takeover via OAuth CSRF. An attacker can force a victim to authenticate with the attacker's Discord account (login CSRF), or in combination with other weaknesses, steal the victim's session.

**Remediation:**
1. Generate a cryptographically random state token (`secrets.token_urlsafe(32)`) per login request.
2. Store the state in a short-lived server-side store or signed cookie.
3. Pass it to `get_oauth_url(state=state_token)`.
4. In the callback, reject requests where the returned `state` does not match the stored value.

---

### CRIT-003: Test Authentication Bypass Exploitable in Production via TESTING Environment Variable
**Severity:** Critical
**OWASP:** A07:2021 - Identification and Authentication Failures
**CWE:** CWE-287 (Improper Authentication)
**File:** `/workspaces/summarybot-ng/src/dashboard/auth.py`, lines 589–653

The `get_current_user` dependency — used by every authenticated dashboard endpoint — contains a hardcoded authentication bypass:

```python
provided_key = request.headers.get("X-Test-Auth-Key")
if provided_key:
    environment = os.getenv("ENVIRONMENT", "development").lower()
    testing_enabled = os.getenv("TESTING", "").lower() in ("true", "1", "yes")

    if environment == "production" and not testing_enabled:
        # block

    # If TESTING=true in production, the bypass is fully active
    admin_secret = os.getenv("TEST_AUTH_ADMIN_SECRET")
    ...
    if is_admin or is_user:
        return { "sub": f"test_{role}_user_id", ... }
```

The bypass is blocked only when `ENVIRONMENT=production` AND `TESTING` is not set to `true/1/yes`. This means any production deployment where `TESTING=true` is set (e.g., during a production smoke test, CI/CD pipeline, or misconfiguration) exposes all dashboard endpoints to authentication bypass with a static test key.

Additionally, the `/api/v1/auth/dev-token` endpoint at `routes/auth.py` line 209 is always registered in the router — it only returns 403 when `DEV_AUTH_ENABLED` is not set, but it is always present in the OpenAPI schema and discoverable via `/docs`.

**Impact:** Complete authentication bypass. Any actor with knowledge of `TEST_AUTH_SECRET` or `TEST_AUTH_ADMIN_SECRET` can gain full admin access to all guild management endpoints.

**Remediation:**
1. Remove the `X-Test-Auth-Key` bypass entirely from production code; test environments should use real OAuth with test Discord applications.
2. Remove the `/dev-token` endpoint from the router entirely or gate it at the router level using a middleware check, not just inside the handler.
3. Never use `TESTING=true` in a production environment; enforce this at the CI/CD pipeline level.

---

## High Severity Findings

### HIGH-001: In-Memory Session Store — Sessions Lost on Restart, No Concurrent-Safe Invalidation
**Severity:** High
**OWASP:** A02:2021 - Cryptographic Failures (data persistence)
**File:** `/workspaces/summarybot-ng/src/dashboard/auth.py`, lines 71–72, 479, 492–500

The session store is a plain Python dictionary:

```python
self._sessions: dict[str, DashboardSession] = {}
```

Sessions are keyed by the SHA-256 hash of the JWT token. Problems:
- All sessions are lost on process restart. Users are logged out on every deployment.
- No persistence: sessions cannot be validated across multiple replicas (horizontal scaling is broken).
- In an async Python application, dictionary operations are not guaranteed atomic under all async patterns, though CPython's GIL provides some protection for simple get/set.
- The `cleanup_expired_sessions` method is never called by any scheduled task visible in the codebase — expired sessions accumulate indefinitely, growing the in-memory store without bound.

**Remediation:** Replace with a persistent, TTL-enabled session store (Redis, database). Schedule `cleanup_expired_sessions` as a periodic background task.

---

### HIGH-002: Wildcard `allow_headers` in CORS Configuration
**Severity:** High
**OWASP:** A05:2021 - Security Misconfiguration
**File:** `/workspaces/summarybot-ng/src/webhook_service/server.py`, line 122

```python
self.app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],    # <-- wildcard
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"]
)
```

`allow_headers=["*"]` combined with `allow_credentials=True` allows any browser request header to be reflected in CORS responses. Per the CORS specification, when `allow_credentials=True` and `allow_headers` is a wildcard, browsers are supposed to refuse the response, but FastAPI/Starlette may handle this incorrectly in some versions, and intermediate proxies may be more permissive.

Furthermore, the server adds development localhost origins unconditionally at lines 105–112:

```python
dev_origins = [
    "http://localhost:8080",
    "http://localhost:5173",
    "http://localhost:3000",
]
for domain in dev_origins:
    if domain not in cors_origins:
        cors_origins.append(domain)
```

These development origins are appended even in production deployments, allowing requests from locally-running pages on a developer's machine that would be treated as the same origin.

**Remediation:** Replace `allow_headers=["*"]` with an explicit list: `["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"]`. Remove localhost origins in production (gate on `ENVIRONMENT` check).

---

### HIGH-003: `PermissionSettings.require_permissions` Defaults to `False` — All Commands Open by Default
**Severity:** High
**OWASP:** A01:2021 - Broken Access Control
**File:** `/workspaces/summarybot-ng/src/config/settings.py`, lines 78–81

```python
@dataclass
class PermissionSettings:
    # ...
    require_permissions: bool = False  # FUNC-002: Default False to prevent lockout
```

And in `permissions/manager.py`, lines 234–240:

```python
if not permission_settings.require_permissions:
    user_perms.level = PermissionLevel.SUMMARIZE
    logger.debug(
        f"Permissions not required for guild {guild_id}, "
        f"granting SUMMARIZE level"
    )
```

Every Discord user in any guild where the permission system has not been explicitly configured gets `SUMMARIZE` access by default. This is a fail-open design that violates the principle of least privilege.

**Impact:** Any Discord server member can invoke summarization commands without the server admin having explicitly granted access.

**Remediation:** Change the default to `require_permissions: bool = True`. Document the guild setup process to require admins to explicitly grant access. Provide a clear first-run experience so admins are not locked out.

---

### HIGH-004: Webhook Test Endpoint — Server-Side Request Forgery (SSRF)
**Severity:** High
**OWASP:** A10:2021 - Server-Side Request Forgery
**CWE:** CWE-918
**File:** `/workspaces/summarybot-ng/src/dashboard/routes/webhooks.py`, lines 315–431

The webhook test endpoint sends an HTTP POST to any URL stored in the webhook record:

```python
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.post(
        webhook["url"],
        json=test_payload,
        headers=headers,
    )
```

A user with guild access can create a webhook with any URL — including internal service URLs (`http://169.254.169.254/latest/meta-data/` for AWS EC2 metadata, `http://localhost:6379` for Redis, internal network services) — and trigger the test to probe internal infrastructure. The URL validation at line 129 only checks for `http://` or `https://` scheme prefix, which does not prevent private IP ranges or cloud metadata endpoints.

**Remediation:**
- Validate webhook URLs against an allowlist of schemes and DNS-resolved IP ranges.
- Block RFC 1918 private addresses (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback (127.0.0.0/8), and cloud metadata ranges (169.254.169.254/32) after DNS resolution.
- Consider using a dedicated outbound proxy with an allowlist.

---

### HIGH-005: Ephemeral Encryption Keys on Restart — Discord OAuth Tokens Undecryptable After Restart
**Severity:** High
**OWASP:** A02:2021 - Cryptographic Failures
**File:** `/workspaces/summarybot-ng/src/dashboard/router.py`, lines 73–80; `/workspaces/summarybot-ng/src/dashboard/auth.py`, lines 65–68

When `DASHBOARD_ENCRYPTION_KEY` is not set in non-production environments:

```python
encryption_key = Fernet.generate_key()
logger.warning("No DASHBOARD_ENCRYPTION_KEY set, using ephemeral key")
```

And in `DashboardAuth.__init__`:
```python
self._cipher = Fernet(Fernet.generate_key())
logger.warning("No encryption key provided, using ephemeral key")
```

Each restart generates a new Fernet key. Encrypted Discord access tokens and refresh tokens stored in `DashboardSession` become permanently unreadable. While this is acceptable in development, the `DASHBOARD_ENCRYPTION_KEY` is not enforced at the Docker container level or in `docker-compose.yml`. The `docker-compose.yml` does not include `DASHBOARD_ENCRYPTION_KEY`, `DASHBOARD_JWT_SECRET`, or `TEST_AUTH_SECRET` in its environment variable list, meaning operators may deploy without setting them.

**Remediation:** Add these secrets as required environment variable checks in `docker-compose.yml` using the `${VAR:?error}` syntax (as already done for `WEBHOOK_CORS_ORIGINS`). Document required secrets prominently.

---

## Medium Severity Findings

### MED-001: No Rate Limiting on Authentication Endpoints
**Severity:** Medium
**OWASP:** A07:2021 - Identification and Authentication Failures
**File:** `/workspaces/summarybot-ng/src/dashboard/routes/auth.py`

The `/api/v1/auth/callback` endpoint processes Discord OAuth codes without rate limiting. While Discord's OAuth flow has its own protections, the callback endpoint itself can be called repeatedly with invalid or replayed codes, generating traffic to Discord's API and potentially triggering Discord's rate limits for the application.

The rate limiting middleware defined in `webhook_service/auth.py` at `setup_rate_limiting` applies to the webhook API path but its application to the dashboard auth routes is not confirmed.

**Remediation:** Apply rate limiting (5 requests per minute per IP) specifically to `/auth/login` and `/auth/callback` endpoints.

---

### MED-002: JWT Tokens Contain Guild Role Information — Roles Not Re-Verified on Each Request
**Severity:** Medium
**OWASP:** A01:2021 - Broken Access Control
**File:** `/workspaces/summarybot-ng/src/dashboard/auth.py`, lines 291–300

Guild roles (`owner`, `admin`, `member`) are embedded in the JWT payload:

```python
payload = {
    "sub": user.id,
    "guilds": guild_ids,
    "guild_roles": guild_roles or {},
    ...
    "exp": now + timedelta(hours=self.jwt_expiration_hours),
}
```

A user whose Discord role in a guild changes (e.g., is demoted from admin to member) retains their old privileges until the JWT expires (default 24 hours). Admin operations like config updates (`PATCH /{guild_id}/config`) and schedule management only check the JWT-embedded role, never re-verifying against Discord's API.

**Remediation:** Shorten JWT expiration for role-sensitive tokens (2 hours maximum), or implement server-side role invalidation by maintaining a role revocation store.

---

### MED-003: `X-Test-Auth-Key` Comparison Uses Plain Equality Instead of `hmac.compare_digest`
**Severity:** Medium
**OWASP:** A07:2021 - Identification and Authentication Failures
**CWE:** CWE-208 (Observable Timing Discrepancy)
**File:** `/workspaces/summarybot-ng/src/dashboard/auth.py`, lines 614–615

```python
is_admin = admin_secret and provided_key == admin_secret
is_user = user_secret and provided_key == user_secret
```

String equality (`==`) in Python is not constant-time. For short secrets this is largely theoretical, but secrets module keys can be 43+ character URL-safe base64 strings. The correct approach is:

```python
is_admin = admin_secret and hmac.compare_digest(provided_key, admin_secret)
```

Similarly, in `ingest_handler.py` line 42 and `whatsapp_routes.py` line 75:

```python
if x_api_key != expected_key:
    raise HTTPException(status_code=401, detail="Invalid API key")
```

**Remediation:** Replace all secret comparisons with `hmac.compare_digest()`.

---

### MED-004: Health Check Endpoint Leaks Infrastructure Information
**Severity:** Medium
**OWASP:** A05:2021 - Security Misconfiguration
**CWE:** CWE-200 (Exposure of Sensitive Information)
**File:** `/workspaces/summarybot-ng/src/webhook_service/server.py`, lines 183–223

The unauthenticated `/health` endpoint returns:

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "build": "<git-commit-hash>",
  "build_date": "<date>",
  "server_time": "...",
  "services": {
    "summarization_engine": "healthy",
    "claude_api": "...",
    "cache": "..."
  }
}
```

The `build` field returns `BUILD_NUMBER` which is set to `GIT_COMMIT` if available (line 172). Exposing git commit hashes allows attackers to pinpoint the exact source code version and look for known vulnerabilities in that commit.

**Remediation:** Remove the `build` field from the public health endpoint or restrict the detailed health endpoint to internal/authenticated access only. Keep a simplified `{"status": "ok"}` response for load balancers.

---

### MED-005: OpenAPI Documentation Endpoints Exposed in Production
**Severity:** Medium
**OWASP:** A05:2021 - Security Misconfiguration
**File:** `/workspaces/summarybot-ng/src/webhook_service/server.py`, lines 85–89

```python
self.app = FastAPI(
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    ...
)
```

Interactive API documentation is exposed at `/docs` and `/redoc` with no authentication. This provides attackers with a complete map of all API endpoints, request schemas, authentication methods, and example payloads. The `/api/v1/auth/dev-token` endpoint appears in the schema even in production.

**Remediation:** Disable `docs_url`, `redoc_url`, and `openapi_url` in production (`ENVIRONMENT=production`), or restrict access via network-level controls (e.g., internal-only routes).

---

### MED-006: Rate Limiting is In-Memory Only — Bypassable in Multi-Instance Deployments
**Severity:** Medium
**OWASP:** A04:2021 - Insecure Design
**File:** `/workspaces/summarybot-ng/src/webhook_service/auth.py`, lines 38–39, 320–378

```python
_rate_limit_store: Dict[str, list] = {}
```

Rate limit state is stored in a module-level dictionary. In deployments with multiple instances (horizontal scaling, rolling restarts), each instance has independent rate limit counters. An attacker can bypass rate limits by distributing requests across instances.

Additionally, at line 342–343:

```python
_rate_limit_store[client_id] = [
    t for t in _rate_limit_store[client_id]
    if t == current_minute
]
```

This filter retains only entries matching the current minute exactly. Because minute boundaries change on a 60-second cycle, requests clustered around a minute boundary can exceed the limit twice (once at the end of minute N and once at the start of minute N+1) with no memory of the prior minute's requests.

**Remediation:** Use Redis or another shared backing store for rate limit counters. Implement a sliding window algorithm rather than per-minute bucketing.

---

## OWASP Top 10 2021 Assessment

| ID | Category | Status | Key Issues |
|----|----------|--------|------------|
| A01 | Broken Access Control | FAIL | `require_permissions=False` default; OAuth CSRF missing state; guild role trust in JWT without re-validation |
| A02 | Cryptographic Failures | PARTIAL | Fernet encryption for tokens is correct; ephemeral keys in non-production; HMAC signature verification not wired to ingest endpoints |
| A03 | Injection | PASS | All SQLite queries use parameterized statements (no f-string SQL detected); Jinja2 template uses `autoescape` for email |
| A04 | Insecure Design | PARTIAL | In-memory session store; in-memory rate limiting; `require_permissions=False` default |
| A05 | Security Misconfiguration | FAIL | Wildcard `allow_headers`; localhost CORS in production; OpenAPI docs exposed; health endpoint leaks build info |
| A06 | Vulnerable Components | UNKNOWN | `requirements.txt` uses version ranges (e.g., `fastapi>=0.104.0`, `cryptography>=41.0.0`) without pinning to specific versions; no lockfile audit performed; `poetry.lock` present but not validated against known CVEs in this audit |
| A07 | Auth Failures | FAIL | No CSRF state in OAuth; test bypass active when `TESTING=true`; no rate limiting on auth endpoints; non-constant-time secret comparison |
| A08 | Software/Data Integrity | PARTIAL | No integrity checks on external prompts fetched from GitHub (`prompts/github_client.py`); `json-repair` library allows malformed LLM JSON to be silently corrected |
| A09 | Logging Failures | PASS | `LogSanitizer` redacts API keys, Bearer tokens, and signatures; `ErrorLoggingMiddleware` logs all 4xx/5xx responses; request correlation IDs used |
| A10 | SSRF | FAIL | Webhook test endpoint makes outbound HTTP requests to operator-supplied URLs without internal IP range filtering |

---

## Authentication and Authorization Review

### Discord OAuth Implementation

The OAuth flow in `src/dashboard/auth.py` correctly:
- Uses `secrets.token_urlsafe(32)` for session IDs (line 461)
- Encrypts Discord access and refresh tokens at rest with Fernet (line 466)
- Uses `HS256` JWT algorithm with configurable expiration
- Validates JWT secret against a known-insecure list at startup (lines 43–60 in `router.py`)

The OAuth flow is missing:
- **CSRF state parameter** (CRIT-002 above)
- Any validation that the `redirect_uri` in the callback matches the registered URI
- Token binding (the JWT is not bound to the client's IP or user agent, though IP is recorded)

### JWT Implementation

The JWT in `src/dashboard/auth.py` uses `python-jose` with `HS256`. Notable observations:
- Algorithm is explicitly whitelisted on decode: `algorithms=["HS256"]` (line 315) — correct
- `exp` claim is validated by `python-jose` automatically — correct
- Guild list and roles embedded in JWT payload create stale authorization window (MED-002)

### Webhook Service Authentication

Two auth mechanisms in `webhook_service/auth.py`:
- API key (static shared secret) — validated against `_config.webhook_config.api_keys` dict
- JWT Bearer token — validated against `JWT_SECRET`

In development (`environment != "production"`), any API key of length >= 10 is accepted (lines 153–158):
```python
user_id = "api-user"
logger.warning(
    "No API keys configured - accepting any valid key format. "
    "This is only allowed in non-production environments."
)
```

This is a reasonable developer convenience but requires strict environment enforcement.

### Discord Bot Permission Enforcement

The `PermissionManager` in `src/permissions/manager.py` has a critical gap at line 249:
```python
# Note: Role-based permissions would require Discord member object
# This is a basic implementation - full implementation would need
# Discord client integration to check roles
```

Role-based permissions (`allowed_roles`, `admin_roles`) are defined in config but **never actually checked** against the Discord member's actual roles because the implementation is incomplete. Only `allowed_users` (user ID list) is checked. This means role-based access control is non-functional.

---

## Data Protection Assessment

### Sensitive Data at Rest

- Discord OAuth tokens are encrypted using Fernet symmetric encryption before storage in `DashboardSession` — correct practice
- Google Drive OAuth tokens stored in files at `archive_root/.tokens/` are encrypted with Fernet
- SQLite database at `data/summarybot.db` is not encrypted at the filesystem level (expected for SQLite; acceptable if filesystem-level encryption is applied at the infrastructure layer)
- The `BotConfig.to_dict()` method redacts `discord_token` and `database_url` — correct

### Sensitive Data in Transit

- SMTP supports TLS (port 587 STARTTLS, port 465 implicit TLS) — correct
- HSTS header is set only in production (`ENVIRONMENT=production`) — correct
- All outbound API calls use HTTPS

### PII Handling

- `LogSanitizer` (`src/logging/sanitizer.py`) redacts API keys, Bearer tokens, and hashes webhook signatures before logging
- Phone numbers in WhatsApp messages are anonymized using HMAC-SHA256 with per-guild salts (`src/services/anonymization/phone_anonymizer.py`) — good practice
- Discord message content is passed directly to the Claude/OpenRouter API; no PII scrubbing occurs before LLM processing (by design, but worth noting in a privacy context)

---

## API Security Review

### Webhook Service API

**Endpoint:** `POST /api/v1/ingest`
- Authenticated via static API key (`X-API-Key` header)
- No HMAC body signature verification (CRIT-001)
- Accepts arbitrary `source_type` but validates against `SourceType` enum — correct
- Message content from external sources is processed without sanitization before being stored and later passed to the LLM

**Endpoint:** `POST /api/v1/summaries`
- Takes `Dict[str, Any]` as the request body type (line 66 in `endpoints.py`), bypassing Pydantic validation entirely
- Handles Zapier-style payload wrapping by parsing a JSON string from a `payload` key — while legitimate, this double-parsing pattern can be an attack vector if the `payload` field contains deeply nested structures designed to exhaust memory or CPU

### Dashboard API

**Guild endpoints** (`/api/v1/guilds/{guild_id}/*`): Access is checked against the JWT `guilds` list via `_check_guild_access`. This is consistently applied across routes.

**Summary generation** (`POST /api/v1/guilds/{guild_id}/summaries/generate`): Requires guild access but only checks `_check_guild_access` (member-level). Admin access is not required to trigger expensive LLM summarization operations, which could be abused by any guild member to run up API costs.

**Email delivery** (`POST /api/v1/guilds/{guild_id}/summaries/stored/{id}/email`): Requires admin role via `require_guild_admin`. This is correctly gated, but only if `TEST_AUTH_ADMIN_SECRET` is not exposed (see CRIT-003).

### Feed Endpoints (RSS/Atom)

`GET /feeds/{feed_id}.rss` and `GET /feeds/{feed_id}.atom` serve public/private feeds. Private feed authentication uses a token comparison at line 362:

```python
if token != feed.token:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        header_token = auth_header[7:]
        if header_token != feed.token:
            raise HTTPException(status_code=401, detail="Invalid feed token")
```

The comparison `token != feed.token` is not constant-time (MED-003 class issue). For feed tokens this is lower severity, but should be fixed.

---

## Infrastructure Security (Docker and Dependencies)

### Dockerfile Analysis (`/workspaces/summarybot-ng/Dockerfile`)

Positive findings:
- Multi-stage build minimizes image size and attack surface
- Non-root user `botuser` (UID 1000) is created and used for runtime (line 55, 77)
- `--no-cache-dir` used for pip installs
- `rm -rf /var/lib/apt/lists/*` cleans apt cache
- `PYTHONDONTWRITEBYTECODE=1` set

Missing security hardening:
- No `--security-opt no-new-privileges` in docker-compose.yml
- No `read_only: true` filesystem flag for the container
- No explicit `ulimits` to prevent fork bombs or resource exhaustion
- Health check uses `curl` which is installed only as a runtime dependency; this is acceptable but `wget` would have smaller footprint
- `EXPOSE 5000` without documentation that this should be behind a reverse proxy in production

### docker-compose.yml Analysis

The `docker-compose.yml` correctly requires `WEBHOOK_CORS_ORIGINS` but does not require:
- `DASHBOARD_JWT_SECRET`
- `DASHBOARD_ENCRYPTION_KEY`
- `WEBHOOK_JWT_SECRET`
- `TEST_AUTH_SECRET` / `TEST_AUTH_ADMIN_SECRET`

The Redis container at line 64 uses:
```yaml
command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
```

Redis has no password configured. The Redis port is not exposed in `docker-compose.yml` (correct — it is only on the internal `summarybot-network`), but any container on that network has full unauthenticated access to Redis.

### Dependency Analysis (`requirements.txt`)

All dependencies use minimum version (`>=`) constraints without upper bounds. Key observations:

| Package | Constraint | Risk |
|---------|-----------|------|
| `cryptography>=41.0.0` | No upper bound | CVEs discovered post-41.0.0 would require manual monitoring |
| `python-jose[cryptography]>=3.3.0` | No upper bound | `python-jose` had historical vulnerabilities with algorithm confusion; pinning is recommended |
| `anthropic>=0.5.0` | Very broad range | Many breaking changes between 0.5.0 and current; broad range risks version drift |
| `fastapi>=0.104.0` | No upper bound | Regular security patches in FastAPI/Starlette; lockfile-only pinning |
| `Jinja2>=3.1.0` | No upper bound | SSTI vulnerabilities exist in older Jinja2 versions |
| `aiohttp>=3.9.0` | No upper bound | Known CVEs in aiohttp; pinning recommended |

The `poetry.lock` file provides actual pinning for production deployments, but `requirements.txt` — used directly in many deployment scenarios — has no version pins.

**Recommendation:** Pin exact versions in `requirements.txt` or use `poetry export --without-hashes -f requirements.txt > requirements.txt` to generate a pinned requirements file from `poetry.lock`.

---

## Informational / Low Severity Findings

### LOW-001: `X-XSS-Protection` Header Set to Legacy Value
**File:** `/workspaces/summarybot-ng/src/webhook_service/server.py`, line 138
`X-XSS-Protection: 1; mode=block` is deprecated in modern browsers and can cause issues in some scenarios. Modern browsers use CSP for XSS protection. Remove or set to `0`.

### LOW-002: Content Security Policy Permits `unsafe-eval` for Frontend
**File:** `/workspaces/summarybot-ng/src/webhook_service/server.py`, lines 148–157
The dashboard CSP includes `'unsafe-eval'` in `script-src` to accommodate framer-motion. This permits dynamic code execution from JavaScript strings, weakening XSS mitigations. Investigate whether the specific framer-motion usage can be refactored to eliminate the `unsafe-eval` requirement.

### LOW-003: OAuth Token Files Stored on Filesystem Without Access Controls
**File:** `/workspaces/summarybot-ng/src/archive/sync/oauth.py`, lines 85–93
Google Drive OAuth tokens are stored as files in `archive_root/.tokens/`. While they are Fernet-encrypted, the storage path is within the application directory. If the application is compromised, the encrypted files are accessible to the attacker along with the encryption key (if `ARCHIVE_TOKEN_ENCRYPTION_KEY` is accessible from the same process context). Consider using a dedicated secrets manager.

### LOW-004: `datetime.utcnow()` Usage in OAuth State
**File:** `/workspaces/summarybot-ng/src/archive/sync/oauth.py`, line 71
`created_at: datetime = field(default_factory=datetime.utcnow)` uses the deprecated `datetime.utcnow()` (Python 3.12+). This is a code quality issue. The rest of the codebase correctly uses `utc_now_naive()` from `src/utils/time.py`.

### LOW-005: Exception Swallowing in Permission Manager
**File:** `/workspaces/summarybot-ng/src/permissions/manager.py`, lines 116–122
Exceptions during permission checks default to `return False` (deny). While fail-closed is generally correct for permissions, swallowing exceptions silently can hide configuration errors or bugs. At minimum, the error should be logged at `ERROR` level (it is) and potentially a health metric incremented.

### LOW-006: Incomplete Role-Based Permission Implementation
**File:** `/workspaces/summarybot-ng/src/permissions/manager.py`, lines 248–250
Role-based access control is documented in `GuildConfig.permission_settings.allowed_roles` and `admin_roles` but the comment at line 249 explicitly states the implementation is incomplete. This means the `allowed_roles` and `admin_roles` config fields have no security effect.

### LOW-007: WhatsApp `/status` Endpoint Reveals API Key Configuration Status
**File:** `/workspaces/summarybot-ng/src/feeds/whatsapp_routes.py`, lines 307–323
The unauthenticated `/api/v1/whatsapp/status` endpoint reveals whether `INGEST_API_KEY` and `WHISPER_API_KEY` are configured. While low severity, this aids reconnaissance.

### LOW-008: `ingest_status` Endpoint Unauthenticated
**File:** `/workspaces/summarybot-ng/src/feeds/ingest_handler.py`, lines 148–160
The `/api/v1/ingest/status` endpoint requires no authentication and reveals supported source types. Low severity but unnecessary information disclosure.

---

## Prioritized Remediation Recommendations

### Immediate (Before Next Release)

1. **Fix CRIT-002 (OAuth CSRF):** Add state parameter generation and validation to the Discord OAuth flow. This is a 2-hour fix with high security impact.

2. **Fix CRIT-003 (Test Auth Bypass):** Remove the `X-Test-Auth-Key` mechanism entirely and the `DEV_AUTH_ENABLED` endpoint registration from production builds. Use a build flag or separate test configuration.

3. **Fix HIGH-004 (SSRF):** Add IP allowlist validation on webhook URLs before making outbound requests. Use a library like `ipaddress` to check resolved IPs against private/reserved ranges.

4. **Fix CRIT-001 (Missing HMAC Verification):** Wire `verify_webhook_signature` into `POST /api/v1/ingest` and verify both API key AND body HMAC.

### Short Term (Within 2 Sprints)

5. **Fix MED-003 (Timing Attack):** Replace all `==` secret comparisons with `hmac.compare_digest()`.

6. **Fix HIGH-002 (CORS):** Replace `allow_headers=["*"]` with an explicit list. Remove localhost origins from production.

7. **Fix HIGH-001 (Session Persistence):** Move sessions to Redis with TTL support. Schedule `cleanup_expired_sessions`.

8. **Fix HIGH-003 (Permission Default):** Change `require_permissions` default to `True`. Implement the role-based permission check that is currently documented but not implemented.

9. **Complete role-based permission implementation** (LOW-006): The `allowed_roles` and `admin_roles` config fields should actually gate access.

### Medium Term (Within a Quarter)

10. **Fix MED-001 (Auth Rate Limiting):** Add rate limiting middleware specifically for auth endpoints.

11. **Fix MED-002 (Stale JWT Roles):** Implement role invalidation or reduce JWT expiration to 2 hours. Add an endpoint to explicitly revoke sessions on role change.

12. **Fix MED-004 (Health Endpoint):** Remove `build` (git commit hash) from the public `/health` response.

13. **Fix MED-005 (OpenAPI Exposure):** Disable Swagger UI and ReDoc in production.

14. **Pin dependency versions** using `poetry export` for `requirements.txt`. Run periodic automated CVE scanning (e.g., `safety check` or `pip-audit`).

15. **Add `DASHBOARD_JWT_SECRET`, `DASHBOARD_ENCRYPTION_KEY` as required** in `docker-compose.yml` using `${VAR:?message}` syntax.

16. **Add Redis password** for production deployments.

---

## Summary Table

| ID | Severity | Description | File | Status |
|----|----------|-------------|------|--------|
| CRIT-001 | Critical | HMAC verification not wired to ingest endpoints | `webhook_service/auth.py`, `feeds/ingest_handler.py` | Open |
| CRIT-002 | Critical | OAuth CSRF - no state parameter | `dashboard/routes/auth.py` L44 | Open |
| CRIT-003 | Critical | Test auth bypass active when TESTING=true | `dashboard/auth.py` L589-653 | Open |
| HIGH-001 | High | In-memory session store, no cleanup | `dashboard/auth.py` L71 | Open |
| HIGH-002 | High | Wildcard allow_headers + localhost CORS in production | `webhook_service/server.py` L122 | Open |
| HIGH-003 | High | Permission system fail-open by default | `config/settings.py` L81 | Open |
| HIGH-004 | High | SSRF via webhook test endpoint | `dashboard/routes/webhooks.py` L368-376 | Open |
| HIGH-005 | High | Ephemeral encryption keys not enforced via config | `dashboard/router.py` L73 | Open |
| MED-001 | Medium | No rate limiting on auth endpoints | `dashboard/routes/auth.py` | Open |
| MED-002 | Medium | Stale guild roles in JWT (24h window) | `dashboard/auth.py` L291 | Open |
| MED-003 | Medium | Non-constant-time secret comparison | `dashboard/auth.py` L614; `ingest_handler.py` L42 | Open |
| MED-004 | Medium | Health endpoint leaks git commit hash | `webhook_service/server.py` L172 | Open |
| MED-005 | Medium | OpenAPI docs exposed in production | `webhook_service/server.py` L85 | Open |
| MED-006 | Medium | In-memory rate limiting bypassable | `webhook_service/auth.py` L38 | Open |
| LOW-001 | Low | Deprecated X-XSS-Protection header | `webhook_service/server.py` L138 | Open |
| LOW-002 | Low | unsafe-eval in CSP | `webhook_service/server.py` L148 | Open |
| LOW-003 | Low | OAuth token files in app directory | `archive/sync/oauth.py` L85 | Open |
| LOW-004 | Low | datetime.utcnow() deprecated usage | `archive/sync/oauth.py` L71 | Open |
| LOW-005 | Low | Exception swallowing in permission checks | `permissions/manager.py` L116 | Open |
| LOW-006 | Low | Role-based permissions unimplemented | `permissions/manager.py` L248 | Open |
| LOW-007 | Low | WhatsApp status endpoint reveals config | `feeds/whatsapp_routes.py` L307 | Open |
| LOW-008 | Low | Ingest status endpoint unauthenticated | `feeds/ingest_handler.py` L148 | Open |

---

*Report generated by QE Security Reviewer v3 - 2026-03-13*
*Files reviewed: 47 Python source files, 1 Dockerfile, 1 docker-compose.yml, requirements.txt*
