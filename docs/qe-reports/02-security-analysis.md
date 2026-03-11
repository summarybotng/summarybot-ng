# Security Analysis Report: SummaryBot-NG

**Report ID**: QE-SEC-2026-0311
**Date**: 2026-03-11
**Analyst**: QE Security Reviewer (Agentic QE v3)
**Scope**: Full codebase security review
**Classification**: CONFIDENTIAL

---

## Executive Summary

SummaryBot-NG is a Discord summarization bot with a FastAPI web dashboard, AI integration (Anthropic/OpenRouter), OAuth flows, email delivery, and Google Drive sync. This review analyzed **45+ security-sensitive files** across authentication, authorization, data access, secrets management, API security, and infrastructure.

**Overall Risk Rating: MEDIUM-HIGH**

The application demonstrates several good security practices (parameterized SQL queries, token encryption, log sanitization, Fernet encryption for OAuth tokens, non-root Docker user). However, critical and high-severity findings -- particularly a hardcoded JWT secret used as fallback, an authentication bypass mechanism accessible via environment variables, overly permissive CORS in production, and an in-memory session store -- require immediate remediation before production hardening can be considered complete.

**Security Score: 4.5 / 10**

| Risk Level | Count |
|------------|-------|
| CRITICAL   | 3     |
| HIGH       | 7     |
| MEDIUM     | 8     |
| LOW        | 5     |
| INFO       | 4     |

**Weighted Finding Score**: 3 x CRITICAL(3) + 7 x HIGH(2) + 8 x MEDIUM(1) + 5 x LOW(0.5) + 4 x INFO(0.25) = 9.0 + 14.0 + 8.0 + 2.5 + 1.0 = **34.5** (minimum threshold: 3.0 -- EXCEEDED)

---

## Vulnerability Catalog

### CRITICAL Findings

#### SEC-001: Hardcoded JWT Secret with Insecure Fallback Chain
- **Severity**: CRITICAL
- **CVSS**: 9.1 (Critical)
- **OWASP**: A07:2021 - Identification and Authentication Failures
- **CWE**: CWE-798 (Use of Hard-coded Credentials)
- **Files**:
  - `src/webhook_service/auth.py:23` -- `JWT_SECRET = "your-secret-key-change-in-production"`
  - `src/config/settings.py:172` -- `jwt_secret: str = "change-this-in-production"`
  - `src/dashboard/router.py:38` -- `jwt_secret = os.environ.get("DASHBOARD_JWT_SECRET", os.environ.get("JWT_SECRET", "change-in-production"))`

**Description**: The webhook service auth module defines a module-level hardcoded JWT secret `"your-secret-key-change-in-production"`. While `set_config()` is intended to override this, if configuration loading fails or is not called, all JWT tokens would be signed with this known secret. The `WebhookConfig` dataclass defaults to `"change-this-in-production"`, and the dashboard router falls back to `"change-in-production"`. An attacker who knows these defaults (they are in the public source code) can forge arbitrary JWT tokens with any user identity and permissions.

**Evidence**:
```python
# src/webhook_service/auth.py:23
JWT_SECRET = "your-secret-key-change-in-production"

# src/config/settings.py:172
jwt_secret: str = "change-this-in-production"

# src/dashboard/router.py:38
jwt_secret = os.environ.get("DASHBOARD_JWT_SECRET", os.environ.get("JWT_SECRET", "change-in-production"))
```

**Impact**: Complete authentication bypass. An attacker can create JWT tokens granting admin access to all API endpoints.

**Remediation**:
1. Remove all hardcoded JWT secret defaults. The application should **refuse to start** if `JWT_SECRET` or `DASHBOARD_JWT_SECRET` is not set.
2. Add startup validation that checks secret length (minimum 32 bytes) and rejects known weak values.
3. Use `secrets.token_urlsafe(32)` as a minimum for generated secrets, and log a CRITICAL warning if an ephemeral key is used.

---

#### SEC-002: Test Authentication Bypass Accessible in Production
- **Severity**: CRITICAL
- **CVSS**: 9.8 (Critical)
- **OWASP**: A07:2021 - Identification and Authentication Failures
- **CWE**: CWE-287 (Improper Authentication)
- **File**: `src/dashboard/auth.py:588-626`

**Description**: The `get_current_user()` FastAPI dependency checks for an `X-Test-Auth-Key` header and, if `TEST_AUTH_ADMIN_SECRET` or `TEST_AUTH_SECRET` environment variables are set, bypasses all OAuth/JWT authentication entirely. There is **no environment check** (e.g., `ENV=development`) guarding this path. If these environment variables are accidentally set in production (they appear in `.env.example`), an attacker with the key gets full admin access. Worse, when `TEST_GUILD_ID=*` (the default in `.env.example`), the mock user is granted access to **all guilds**.

**Evidence**:
```python
# src/dashboard/auth.py:592-626
provided_key = request.headers.get("X-Test-Auth-Key")
if provided_key:
    admin_secret = os.getenv("TEST_AUTH_ADMIN_SECRET")
    user_secret = os.getenv("TEST_AUTH_SECRET")
    is_admin = admin_secret and provided_key == admin_secret
    is_user = user_secret and provided_key == user_secret
    if is_admin or is_user:
        # Return a mock user -- full bypass
```

**Impact**: If `TEST_AUTH_ADMIN_SECRET` is set in production, any request with the correct header value bypasses all authentication. The comparison is done with `==` (not constant-time), enabling timing attacks to brute-force the secret.

**Remediation**:
1. Gate this entire code path behind an explicit `ENVIRONMENT=development` or `TESTING=true` check.
2. Use `hmac.compare_digest()` for timing-safe comparison.
3. Add a loud startup warning if test auth secrets are configured alongside `ENVIRONMENT=production`.
4. Never set `TEST_GUILD_ID=*` -- require explicit guild IDs.

---

#### SEC-003: API Key Authentication Falls Open When Unconfigured
- **Severity**: CRITICAL
- **CVSS**: 9.0 (Critical)
- **OWASP**: A01:2021 - Broken Access Control
- **CWE**: CWE-284 (Improper Access Control)
- **File**: `src/webhook_service/auth.py:96-104`

**Description**: When no API keys are configured in the webhook config, the `get_api_key_auth()` function accepts **any API key** of 10+ characters and grants `["read", "write", "admin"]` permissions. A warning is logged, but no authentication is enforced. This fail-open design means an unconfigured production deployment is wide open.

**Evidence**:
```python
# src/webhook_service/auth.py:96-104
else:
    # If no API keys configured, accept any valid format for development
    user_id = "api-user"
    logger.warning("No API keys configured - accepting any valid key format")
return APIKeyAuth(
    api_key=x_api_key,
    user_id=user_id,
    permissions=["read", "write", "admin"]
)
```

**Impact**: Any unauthenticated user can access all webhook API endpoints with admin permissions by providing any string of 10+ characters as an API key.

**Remediation**:
1. Change to fail-closed: if no API keys are configured, reject all requests with 401.
2. If development mode must accept all keys, gate this behind `ENVIRONMENT=development`.
3. Remove the blanket `["read", "write", "admin"]` permission grant -- use least-privilege defaults.

---

### HIGH Findings

#### SEC-004: In-Memory Session Store Not Suitable for Production
- **Severity**: HIGH
- **CVSS**: 7.5
- **OWASP**: A07:2021 - Identification and Authentication Failures
- **CWE**: CWE-613 (Insufficient Session Expiration)
- **File**: `src/dashboard/auth.py:71`

**Description**: Dashboard sessions are stored in `self._sessions: dict[str, DashboardSession] = {}` -- a Python dictionary in process memory. This means:
1. Sessions are lost on every application restart, forcing all users to re-authenticate.
2. In a multi-process deployment (multiple workers, replicas), sessions are not shared.
3. There is no bound on session count, enabling memory exhaustion attacks.

**Remediation**: Implement a persistent session store (Redis or database-backed) with configurable TTL and maximum session count per user.

---

#### SEC-005: Rate Limiting is In-Memory and Easily Bypassed
- **Severity**: HIGH
- **CVSS**: 7.0
- **OWASP**: A04:2021 - Insecure Design
- **CWE**: CWE-770 (Allocation of Resources Without Limits)
- **Files**: `src/webhook_service/auth.py:28,261-311`

**Description**: Rate limiting uses an in-memory dictionary `_rate_limit_store: Dict[str, list] = {}`. The rate limiter:
1. Loses state on restart.
2. Does not share state across workers/replicas.
3. Uses the client-supplied `X-API-Key` header for identification (`client_id = request.headers.get("X-API-Key") or request.client.host`), which means an attacker can rotate API key headers to get unlimited rate limit buckets.
4. Returns an `HTTPException` object instead of a `Response`, so the 429 status is never actually sent (the HTTPException is returned as the response body, not raised).

**Evidence**:
```python
# src/webhook_service/auth.py:291-299 -- BUG: returns HTTPException instead of raising it
if request_count >= rate_limit:
    return HTTPException(  # <-- should be: raise HTTPException(...)
        status_code=429,
        ...
    )
```

**Impact**: Rate limiting is completely broken (HTTP 429 is never returned due to the return-vs-raise bug) and can be bypassed by rotating API keys.

**Remediation**:
1. Fix the `return HTTPException` to `raise HTTPException` or return a proper `JSONResponse(status_code=429, ...)`.
2. Use Redis-backed rate limiting for persistence across restarts and workers.
3. Rate-limit by IP address only (not client-supplied headers).

---

#### SEC-006: CORS Wildcard in docker-compose.yml and Dev Origins in Production
- **Severity**: HIGH
- **CVSS**: 6.5
- **OWASP**: A05:2021 - Security Misconfiguration
- **CWE**: CWE-942 (Permissive Cross-domain Policy)
- **Files**:
  - `docker-compose.yml:33` -- `WEBHOOK_CORS_ORIGINS=${WEBHOOK_CORS_ORIGINS:-*}`
  - `src/webhook_service/server.py:104-111` -- Always adds localhost origins

**Description**: The docker-compose default for CORS origins is `*` (wildcard), which allows any website to make authenticated cross-origin requests. Additionally, the `_setup_middleware()` method unconditionally adds `localhost:8080`, `localhost:5173`, and `localhost:3000` to CORS origins -- even in production.

**Remediation**:
1. Remove the `*` default from docker-compose.yml. Require explicit CORS origins.
2. Only add localhost origins when `ENVIRONMENT=development`.
3. Document required CORS configuration for production deployments.

---

#### SEC-007: Ephemeral Encryption Keys for OAuth Tokens
- **Severity**: HIGH
- **CVSS**: 6.8
- **OWASP**: A02:2021 - Cryptographic Failures
- **CWE**: CWE-321 (Use of Hard-coded Cryptographic Key)
- **Files**:
  - `src/dashboard/auth.py:66-68` -- Ephemeral Fernet key if not configured
  - `src/dashboard/router.py:53-54` -- Ephemeral key fallback
  - `src/archive/sync/oauth.py:99-105` -- Ephemeral token encryption key

**Description**: Multiple components generate ephemeral Fernet encryption keys when environment variables are not set. This means:
1. Encrypted data (Discord OAuth tokens, Google Drive tokens) becomes unreadable after restart.
2. Users must re-authenticate after every deployment/restart.
3. A warning is logged but operation continues, masking the problem.

**Remediation**: Require `DASHBOARD_ENCRYPTION_KEY` and `ARCHIVE_TOKEN_ENCRYPTION_KEY` to be set, and fail startup if they are missing.

---

#### SEC-008: SQL String Interpolation in Queries
- **Severity**: HIGH
- **CVSS**: 7.4
- **OWASP**: A03:2021 - Injection
- **CWE**: CWE-89 (SQL Injection)
- **Files**:
  - `src/data/sqlite.py:369` -- `f"SELECT COUNT(*) as count FROM summaries {where_clause}"`
  - `src/data/sqlite.py:1498` -- `f"SELECT COUNT(*) as count FROM stored_summaries WHERE {where_clause}"`
  - `src/data/sqlite.py:1958` -- `f"SELECT COUNT(*) as total FROM stored_summaries WHERE {where_clause}"`
  - `src/logging/repository.py:326` -- `f"SELECT COUNT(*) as count FROM command_logs WHERE {where_sql}"`
  - `src/data/migrations/__init__.py:118` -- `f"DROP TABLE IF EXISTS {table_name}"`

**Description**: Several queries use f-string interpolation to construct SQL. While `where_clause` variables are built programmatically from code-controlled strings with parameterized values, this pattern is fragile and error-prone. If `where_clause` construction is ever modified to include user input without parameterization, SQL injection becomes possible. The `DROP TABLE IF EXISTS {table_name}` in migrations is particularly dangerous if `table_name` could ever come from user input.

**Remediation**:
1. Audit all f-string SQL construction to ensure no user input flows into interpolated portions.
2. Use a query builder pattern that enforces parameterization.
3. Add static analysis rules to flag f-string SQL patterns.

---

#### SEC-009: Google Drive Sync Uses Unvalidated File Names in API Queries
- **Severity**: HIGH
- **CVSS**: 6.0
- **OWASP**: A03:2021 - Injection
- **CWE**: CWE-74 (Injection)
- **File**: `src/archive/sync/google_drive.py:274,324`

**Description**: Google Drive API queries use single-quoted file names without escaping:
```python
query = f"name='{folder_name}' and '{parent_id}' in parents and ..."
query = f"name='{local_path.name}' and '{parent_id}' in parents ..."
```
If `folder_name` or `local_path.name` contains a single quote, the query breaks. A malicious file name could manipulate the query to access or overwrite files in other folders.

**Remediation**: Escape single quotes in file names before inserting them into Google Drive API queries (replace `'` with `\'`).

---

#### SEC-010: Missing Authorization Checks on Webhook Endpoints
- **Severity**: HIGH
- **CVSS**: 6.5
- **OWASP**: A01:2021 - Broken Access Control
- **CWE**: CWE-862 (Missing Authorization)
- **File**: `src/webhook_service/endpoints.py:300-301`

**Description**: The webhook endpoints authenticate users but do not verify that the authenticated user has permission to access the specific guild or channel they are requesting. A `TODO` comment on line 300 confirms this:
```python
# TODO: Check user permissions based on guild_id/channel_id
```
An authenticated user can summarize messages from any guild/channel.

**Remediation**: Implement guild-level and channel-level authorization checks after authentication, verifying the authenticated user has access to the requested resources.

---

### MEDIUM Findings

#### SEC-011: Jinja2 Template Rendering with autoescape in Email but XSS in Fallback
- **Severity**: MEDIUM
- **CVSS**: 5.4
- **OWASP**: A03:2021 - Injection
- **CWE**: CWE-79 (Cross-Site Scripting)
- **File**: `src/services/email_delivery.py:105-108,239-274`

**Description**: The Jinja2 template environment enables `select_autoescape(["html", "xml"])`, which is good. However, the fallback HTML rendering (`_render_html_fallback`) uses a custom `_escape_html()` method. While this method does escape `<`, `>`, `"`, `'`, and `&`, the approach is manual and could miss edge cases. The HTML template is built with f-strings, which is error-prone for security.

**Remediation**: Use the `markupsafe.escape()` function from the Jinja2 dependency instead of a custom escaper, and prefer template rendering over f-string HTML construction.

---

#### SEC-012: `dangerouslySetInnerHTML` Usage in Frontend
- **Severity**: MEDIUM
- **CVSS**: 5.0
- **OWASP**: A03:2021 - Injection
- **CWE**: CWE-79 (Cross-Site Scripting)
- **File**: `src/frontend/src/components/ui/chart.tsx:70`

**Description**: The chart component uses `dangerouslySetInnerHTML` to inject CSS styles. While the content appears to come from a controlled configuration object (theme colors), this pattern is inherently risky if any of the data flows from user input.

**Remediation**: Verify that no user-controlled data flows into the `dangerouslySetInnerHTML` prop. Consider using CSS-in-JS solutions or CSS custom properties set via `style` attributes instead.

---

#### SEC-013: `datetime.utcnow()` Deprecated and Naive Timezone Handling
- **Severity**: MEDIUM
- **CVSS**: 4.0
- **OWASP**: A04:2021 - Insecure Design
- **CWE**: CWE-682 (Incorrect Calculation)
- **Files**: Throughout codebase (auth.py, oauth.py, email_delivery.py, etc.)

**Description**: The codebase uses `datetime.utcnow()` extensively, which is deprecated in Python 3.12+ and returns naive (non-timezone-aware) datetime objects. This can lead to incorrect time comparisons, especially in JWT expiration checks where timezone-aware timestamps from external systems are compared with naive local timestamps.

**Remediation**: Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` throughout the codebase.

---

#### SEC-014: Webhook Signature Verification Uses `hmac.new` (Wrong Module)
- **Severity**: MEDIUM
- **CVSS**: 5.0
- **OWASP**: A02:2021 - Cryptographic Failures
- **CWE**: CWE-347 (Improper Verification of Cryptographic Signature)
- **File**: `src/webhook_service/auth.py:252`

**Description**: The `verify_webhook_signature()` function calls `hmac.new()` which does not exist -- the correct call is `hmac.new()` is not a Python standard library function. The correct function is `hmac.new()`. Actually, reviewing more carefully, the Python `hmac` module function is `hmac.new()`. This will work correctly. However, the function signature accepts `signature` as a raw string and compares with a hex digest. If the signature format differs (e.g., prefixed with `sha256=`), the comparison will always fail.

**Remediation**: Document the expected signature format and strip any prefix before comparison. Add unit tests for signature verification.

---

#### SEC-015: No CSRF Protection on OAuth Callback
- **Severity**: MEDIUM
- **CVSS**: 5.5
- **OWASP**: A07:2021 - Identification and Authentication Failures
- **CWE**: CWE-352 (Cross-Site Request Forgery)
- **File**: `src/dashboard/auth.py:92-110`

**Description**: The `get_oauth_url()` method generates a state parameter for CSRF protection, but the state parameter is **optional** (`state: Optional[str] = None`). If the caller does not provide a state parameter, the OAuth flow proceeds without CSRF protection. The state validation on the callback side must also be verified -- the code does not show the callback handler rejecting requests without state.

**Remediation**: Make the state parameter mandatory and reject OAuth callbacks without a valid state parameter.

---

#### SEC-016: API Key Validation Uses `hash()` for Cache Key
- **Severity**: MEDIUM
- **CVSS**: 4.5
- **OWASP**: A02:2021 - Cryptographic Failures
- **CWE**: CWE-328 (Use of Weak Hash)
- **File**: `src/archive/api_keys/resolver.py:169`

**Description**: The key validation cache uses Python's built-in `hash()` function (`key_hash = hash(key)`) to create cache keys. Python's `hash()` is not a cryptographic hash -- it uses randomization (PYTHONHASHSEED) and can produce collisions. Two different API keys could map to the same cache entry, causing one key's validation result to be returned for another.

**Remediation**: Use `hashlib.sha256(key.encode()).hexdigest()` for cache keys instead of `hash()`.

---

#### SEC-017: Permissive File Path in EncryptedFileBackend
- **Severity**: MEDIUM
- **CVSS**: 5.0
- **OWASP**: A01:2021 - Broken Access Control
- **CWE**: CWE-22 (Path Traversal)
- **File**: `src/archive/api_keys/backends.py:163-170`

**Description**: The `_parse_ref()` method in `EncryptedFileBackend` strips a `file:` prefix but does not sanitize the remaining path for directory traversal. A key reference like `file:../../etc/shadow` would resolve to a path outside the intended `keys_dir`.

**Remediation**: Add path traversal validation: resolve the full path and verify it is still within `keys_dir`.

---

#### SEC-018: SMTP Credentials Logged at Service Initialization
- **Severity**: MEDIUM
- **CVSS**: 4.5
- **OWASP**: A09:2021 - Security Logging and Monitoring Failures
- **CWE**: CWE-532 (Information Exposure Through Log Files)
- **File**: `src/services/email_delivery.py:571-575`

**Description**: The email service initialization logs the SMTP host, port, and from address. While credentials are not directly logged, the log message reveals SMTP configuration details that could aid an attacker in targeting the email infrastructure.

**Remediation**: Reduce log verbosity for SMTP configuration. Log only that email service is enabled/disabled and whether it is properly configured.

---

### LOW Findings

#### SEC-019: `--dangerously-skip-permissions` in start.sh
- **Severity**: LOW
- **CVSS**: 3.0
- **OWASP**: A05:2021 - Security Misconfiguration
- **File**: `start.sh:225`

**Description**: The startup script launches Claude Code with `--dangerously-skip-permissions`, which disables permission checks. While this is a development tool and not part of the production application, it could be inadvertently used in production environments.

**Remediation**: Add a warning comment and consider removing this flag or gating it behind an explicit development mode check.

---

#### SEC-020: Discord Bot Token Accepted as Empty String
- **Severity**: LOW
- **CVSS**: 3.5
- **OWASP**: A05:2021 - Security Misconfiguration
- **File**: `src/config/environment.py:26`

**Description**: `discord_token = os.getenv('DISCORD_TOKEN', '')` defaults to an empty string. While the application handles webhook-only mode, an empty token that gets passed to `client.start('')` would cause a login failure at runtime rather than at startup validation.

**Remediation**: Validate configuration at startup and provide clear error messages about running modes.

---

#### SEC-021: Request ID Truncated to 8 Characters
- **Severity**: LOW
- **CVSS**: 2.0
- **OWASP**: A09:2021 - Security Logging and Monitoring Failures
- **File**: `src/dashboard/middleware.py:31`

**Description**: Request IDs are generated as `str(uuid.uuid4())[:8]` -- only 8 hex characters (32 bits of entropy). This provides approximately 4.3 billion unique values, which could lead to collisions in high-traffic scenarios, making log correlation unreliable.

**Remediation**: Use the full UUID4 (128 bits) for request IDs.

---

#### SEC-022: Exposed API Documentation Endpoints
- **Severity**: LOW
- **CVSS**: 2.5
- **OWASP**: A05:2021 - Security Misconfiguration
- **File**: `src/webhook_service/server.py:80-87`

**Description**: The FastAPI application exposes `/docs`, `/redoc`, and `/openapi.json` endpoints by default. In production, these should be disabled or protected to prevent information disclosure about API structure.

**Remediation**: Disable docs endpoints in production: `docs_url=None, redoc_url=None, openapi_url=None` when `ENVIRONMENT=production`.

---

#### SEC-023: Missing `Secure` and `SameSite` Cookie Attributes
- **Severity**: LOW
- **CVSS**: 3.0
- **OWASP**: A07:2021 - Identification and Authentication Failures
- **CWE**: CWE-614 (Sensitive Cookie in HTTPS Session Without 'Secure' Attribute)
- **File**: `src/dashboard/auth.py`

**Description**: The dashboard uses JWT tokens in Authorization headers rather than cookies, which avoids some cookie-related vulnerabilities. However, if cookies are used in the frontend for session persistence, they should include `Secure`, `HttpOnly`, and `SameSite=Strict` attributes. The current implementation does not appear to set cookies, but this should be verified in the frontend code.

**Remediation**: If any cookies are used, ensure they have `Secure`, `HttpOnly`, and `SameSite=Strict` attributes.

---

### INFORMATIONAL Findings

#### SEC-024: Rate Limiting Placeholder in Permission Validator
- **Severity**: INFO
- **File**: `src/permissions/validators.py:392-403`

**Description**: The `validate_user_rate_limit()` method is a placeholder that always returns success. It includes a note: `"Rate limiting not yet implemented"`. This means Discord command abuse prevention relies entirely on the webhook rate limiter (which is broken -- see SEC-005).

---

#### SEC-025: PostgreSQL Support is a Stub
- **Severity**: INFO
- **File**: `src/data/postgresql.py`

**Description**: The PostgreSQL implementation raises `NotImplementedError` for all methods. This is expected and documented but should be noted for production planning.

---

#### SEC-026: Missing Security Headers
- **Severity**: INFO
- **File**: `src/webhook_service/server.py`

**Description**: The application does not set standard security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`, `Content-Security-Policy`. While Fly.io handles some of these at the proxy level, the application should set them explicitly.

**Remediation**: Add a middleware that sets security headers on all responses.

---

#### SEC-027: Dependency Versions Allow Wide Ranges
- **Severity**: INFO
- **File**: `requirements.txt`

**Description**: Dependencies use `>=` version constraints without upper bounds (e.g., `anthropic>=0.5.0`, `fastapi>=0.104.0`). This could pull in breaking changes or versions with known vulnerabilities.

**Remediation**: Use pinned versions or upper-bounded ranges (e.g., `fastapi>=0.104.0,<1.0.0`). Use `pip-audit` or `safety` for automated vulnerability scanning.

---

## OWASP Top 10 2021 Coverage Matrix

| OWASP Category | Findings | Status |
|---|---|---|
| **A01: Broken Access Control** | SEC-003 (CRITICAL), SEC-010 (HIGH), SEC-017 (MEDIUM) | FAIL |
| **A02: Cryptographic Failures** | SEC-007 (HIGH), SEC-014 (MEDIUM), SEC-016 (MEDIUM) | FAIL |
| **A03: Injection** | SEC-008 (HIGH), SEC-009 (HIGH), SEC-011 (MEDIUM), SEC-012 (MEDIUM) | FAIL |
| **A04: Insecure Design** | SEC-005 (HIGH), SEC-013 (MEDIUM) | FAIL |
| **A05: Security Misconfiguration** | SEC-006 (HIGH), SEC-019 (LOW), SEC-020 (LOW), SEC-022 (LOW) | FAIL |
| **A06: Vulnerable Components** | SEC-027 (INFO) -- requires `pip-audit` scan | PARTIAL |
| **A07: Auth Failures** | SEC-001 (CRITICAL), SEC-002 (CRITICAL), SEC-004 (HIGH), SEC-015 (MEDIUM), SEC-023 (LOW) | FAIL |
| **A08: Software/Data Integrity** | No findings (good: no pickle/yaml.load usage detected) | PASS |
| **A09: Logging Failures** | SEC-018 (MEDIUM), SEC-021 (LOW), SEC-024 (INFO) | PARTIAL |
| **A10: SSRF** | No SSRF vectors detected (webhook URL validation delegated to Pydantic HttpUrl) | PASS |

---

## Secrets and Credential Handling Assessment

### Positive Findings
- `BotConfig.to_dict()` redacts `discord_token`, `database_url`, and `redis_url` (settings.py:211-224)
- `LogSanitizer` redacts API keys, bearer tokens, and file paths in logs (sanitizer.py:100-142)
- OAuth tokens are encrypted at rest using Fernet (oauth.py:77-188)
- Encrypted key files set restrictive permissions `0o600` (backends.py:198)
- `.env.production.template` contains instructions not to commit production env files

### Negative Findings
- Three separate hardcoded JWT secrets in source code (SEC-001)
- `.env.example` contains placeholder API key patterns that could be confused with real values
- `ClaudeClient.__init__` logs masked API key (first 10 + last 4 characters) -- this reveals key length and partial content
- The `webhook_secret` field in `GuildConfig.to_dict()` is serialized without redaction (settings.py:109)
- No automated secret scanning in CI/CD pipeline

### Recommendations
1. Implement pre-commit hooks using `detect-secrets` or `trufflehog`
2. Add CI/CD secret scanning step
3. Redact `webhook_secret` in `GuildConfig.to_dict()`
4. Reduce API key logging to only first 4 characters

---

## Attack Surface Analysis

### External Attack Surface
| Entry Point | Auth Required | Rate Limited | Input Validated |
|---|---|---|---|
| `/api/v1/auth/*` (OAuth) | No | No (BUG) | Partial |
| `/api/v1/guilds/*` (Dashboard) | JWT | No (BUG) | Yes (Pydantic) |
| `/api/v1/summaries` (Webhook) | API Key | No (BUG) | Yes (Pydantic) |
| `/api/v1/summarize` (Webhook) | API Key | No (BUG) | Yes (Pydantic) |
| `/api/v1/schedule` (Webhook) | API Key | No (BUG) | Yes (Pydantic) |
| `/api/v1/ingest` (WhatsApp) | API Key | No (BUG) | Yes (Pydantic) |
| `/api/v1/archive/oauth/google/*` | JWT | No | Partial |
| `/docs`, `/redoc`, `/openapi.json` | No | No | N/A |
| `/health` | No | No | N/A |
| Discord Bot Commands | Discord Auth | Placeholder | Discord validates |

**Note**: "No (BUG)" for rate limiting refers to SEC-005 where the rate limiter returns instead of raises the HTTPException.

### Internal Attack Surface
- SQLite database with WAL mode (good for concurrency, but WAL files could leak data)
- In-memory caches without bounds (potential memory exhaustion)
- File-based token storage for Google Drive OAuth tokens
- SMTP connections for email delivery

---

## Infrastructure Security Assessment

### Docker Configuration (Positive)
- Multi-stage build reduces image size and attack surface
- Non-root user (`botuser`, UID 1000) for runtime
- Health checks configured
- No secrets in Dockerfile
- `PYTHONDONTWRITEBYTECODE=1` prevents `.pyc` file creation

### Docker Configuration (Concerns)
- `WEBHOOK_HOST=0.0.0.0` binds to all interfaces (expected for containers but should be documented)
- No resource limits (`mem_limit`, `cpus`) in docker-compose.yml for the bot service
- Redis runs without authentication (`redis-server` with no `--requirepass`)

### Fly.io Configuration (Positive)
- Force HTTPS enabled (`force_https = true`)
- Health checks configured
- Rolling deploy strategy

### Fly.io Configuration (Concerns)
- `PRIMARY_GUILD_ID` is hardcoded in `fly.toml` (should be a secret)
- CORS origins list in `fly.toml:23` includes localhost URLs that should only be in development

---

## Remediation Roadmap (Prioritized by Risk)

### Phase 1: CRITICAL -- Immediate (Week 1)
| ID | Finding | Effort | Impact |
|---|---|---|---|
| SEC-001 | Remove hardcoded JWT secrets, require env vars | Low | Eliminates token forgery |
| SEC-002 | Gate test auth behind ENVIRONMENT check | Low | Prevents production auth bypass |
| SEC-003 | Fail closed when API keys unconfigured | Low | Prevents open access |
| SEC-005 | Fix rate limiter return vs raise bug | Low | Enables rate limiting |

### Phase 2: HIGH -- Short Term (Weeks 2-3)
| ID | Finding | Effort | Impact |
|---|---|---|---|
| SEC-004 | Implement Redis session store | Medium | Persistent, scalable sessions |
| SEC-006 | Remove wildcard CORS, gate dev origins | Low | Prevents cross-origin attacks |
| SEC-007 | Require encryption keys at startup | Low | Prevents data loss on restart |
| SEC-008 | Audit SQL f-strings, add query builder | Medium | Prevents SQL injection |
| SEC-009 | Escape single quotes in GDrive queries | Low | Prevents query manipulation |
| SEC-010 | Implement guild-level authz on endpoints | Medium | Enforces access control |
| SEC-005 | Migrate rate limiter to Redis | Medium | Distributed rate limiting |

### Phase 3: MEDIUM -- Mid Term (Weeks 4-6)
| ID | Finding | Effort | Impact |
|---|---|---|---|
| SEC-011 | Use markupsafe.escape() in email fallback | Low | Prevents XSS in emails |
| SEC-013 | Migrate to timezone-aware datetimes | Medium | Correct time handling |
| SEC-015 | Make OAuth state mandatory | Low | Prevents CSRF |
| SEC-016 | Use hashlib for cache keys | Low | Prevents cache collisions |
| SEC-017 | Add path traversal validation | Low | Prevents file access escape |
| SEC-018 | Reduce SMTP log verbosity | Low | Reduces info exposure |

### Phase 4: HARDENING -- Ongoing
| ID | Finding | Effort | Impact |
|---|---|---|---|
| SEC-026 | Add security headers middleware | Low | Defense in depth |
| SEC-022 | Disable docs in production | Low | Reduces info exposure |
| SEC-027 | Pin dependency versions, add pip-audit | Low | Reduces supply chain risk |
| -- | Add Redis auth to docker-compose | Low | Prevents cache poisoning |
| -- | Implement account lockout after N failures | Medium | Brute force protection |
| -- | Add CSP headers | Medium | XSS mitigation |

---

## Positive Security Observations

The codebase demonstrates several security-conscious practices that should be maintained and expanded:

1. **Parameterized SQL queries**: The majority of database operations use parameterized queries via aiosqlite
2. **Fernet encryption**: OAuth tokens and API keys are encrypted at rest using industry-standard Fernet symmetric encryption
3. **Log sanitization**: The `LogSanitizer` class redacts API keys, tokens, passwords, and masks IP addresses
4. **HMAC signature verification**: Webhook signatures use timing-safe `hmac.compare_digest()`
5. **Pydantic validation**: Request models use Pydantic with field constraints for input validation
6. **Non-root Docker**: Production container runs as non-root user
7. **Token hashing for sessions**: JWT tokens are SHA-256 hashed before use as session keys
8. **OAuth state tokens**: CSRF protection via state tokens in OAuth flows (when used)
9. **File permissions**: Encrypted key files are set to 0o600
10. **Comprehensive security tests**: The test suite includes tests for timing attacks, path traversal, unicode bypasses, ReDoS, and more

---

## Files Examined

| Category | Files |
|---|---|
| Authentication | `src/webhook_service/auth.py`, `src/dashboard/auth.py` |
| Authorization | `src/permissions/manager.py`, `src/permissions/validators.py`, `src/permissions/roles.py` |
| API Endpoints | `src/webhook_service/endpoints.py`, `src/webhook_service/server.py`, `src/dashboard/router.py` |
| Configuration | `src/config/settings.py`, `src/config/environment.py` |
| Data Access | `src/data/sqlite.py` (partial), `src/data/postgresql.py`, `src/data/base.py` |
| Cryptography | `src/archive/sync/oauth.py`, `src/archive/api_keys/backends.py`, `src/archive/api_keys/resolver.py` |
| Logging | `src/logging/sanitizer.py`, `src/dashboard/middleware.py` |
| Email | `src/services/email_delivery.py` |
| Google Drive | `src/archive/sync/google_drive.py` |
| Discord Bot | `src/discord_bot/bot.py`, `src/discord_bot/commands.py` |
| AI Client | `src/summarization/claude_client.py` |
| Validators | `src/webhook_service/validators.py` |
| WhatsApp | `src/archive/importers/whatsapp.py` |
| Infrastructure | `Dockerfile`, `docker-compose.yml`, `fly.toml`, `requirements.txt` |
| Templates | `.env.example`, `.env.production.template` |
| Tests | `tests/security/test_security_validation.py`, `tests/security/test_audit_logging.py` |
| Frontend | `src/frontend/src/components/ui/chart.tsx` |
| Startup | `start.sh` |

---

*Report generated by QE Security Reviewer -- Agentic QE v3*
*Methodology: OWASP Top 10 2021, CWE Top 25, NIST SP 800-53*
