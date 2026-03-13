# P0/P1 Fix Implementation Plan

**Date:** March 13, 2026
**Scope:** 8 issues (4 P0, 4 P1) from QE Swarm analysis
**Estimated effort:** 10 source files modified, 3 new utility files, ~8 test files

---

## Execution Order & Dependencies

```
P0-4 (config lock)      -> independent, smallest fix
P0-3 (test auth bypass)  -> independent, security critical
P0-1 (HMAC ingest)       -> independent
P0-2 (OAuth CSRF)        -> independent
P1-8 (encrypt secrets)   -> creates shared utility used by P1-7
P1-7 (SSRF protection)   -> can share utility pattern with P1-8
P1-5 (pool size)         -> independent
P1-6 (N+1 queries)       -> independent
```

---

## FIX 1: P0-4 -- Broken Config Lock

**Complexity: S | File: `src/config/manager.py`**

The bug: `async with asyncio.Lock():` on line 73 creates a NEW lock on every call = zero mutual exclusion.

### Changes

**`src/config/manager.py:28`** -- Add to `__init__`:
```python
self._save_lock = asyncio.Lock()
```

**`src/config/manager.py:73`** -- Replace:
```python
# BEFORE
async with asyncio.Lock():

# AFTER
async with self._save_lock:
```

### Tests
`tests/unit/test_config/test_manager.py`:
- `test_concurrent_save_config_serialized` -- `asyncio.gather` two saves, assert no file corruption

---

## FIX 2: P0-3 -- Test Auth Bypass in Production

**Complexity: S | File: `src/dashboard/auth.py`**

The bug: `TESTING=true` in production re-enables the full auth bypass.

### Changes

**`src/dashboard/auth.py:596-609`** -- Replace the guard block:

```python
# BEFORE
environment = os.getenv("ENVIRONMENT", "development").lower()
testing_enabled = os.getenv("TESTING", "").lower() in ("true", "1", "yes")
if environment == "production" and not testing_enabled:
    # ... block

# AFTER
environment = os.getenv("ENVIRONMENT", "development").lower()
# SEC-FIX: Only allow test auth in explicit dev/test environments.
# Never in production, regardless of TESTING flag.
allowed_environments = ("development", "test", "testing", "ci")
if environment not in allowed_environments:
    logger.warning(
        "Test auth bypass attempted in non-development environment. "
        f"Environment: {environment}, "
        f"Client IP: {request.client.host if request.client else 'unknown'}"
    )
    raise HTTPException(
        status_code=401,
        detail={"code": "UNAUTHORIZED", "message": "Test authentication not available"},
    )
```

### Tests
`tests/unit/test_dashboard/test_auth.py`:
- `test_test_auth_blocked_in_production_even_with_testing_flag` -- ENVIRONMENT=production, TESTING=true -> 401
- `test_test_auth_blocked_in_staging` -- ENVIRONMENT=staging -> 401
- `test_test_auth_allowed_in_development` -- ENVIRONMENT=development -> success
- `test_test_auth_allowed_in_ci` -- ENVIRONMENT=ci -> success
- `test_test_auth_default_env_is_development` -- No ENVIRONMENT set -> success

---

## FIX 3: P0-1 -- HMAC Not Wired to Ingest Endpoint

**Complexity: M | File: `src/feeds/ingest_handler.py`**

The bug: `verify_webhook_signature()` exists in `webhook_service/auth.py:296-317` but is never called by `/api/v1/ingest`.

### Changes

**`src/feeds/ingest_handler.py`** -- Add new dependency after `_validate_api_key` (line 45):

```python
async def _validate_signature(request: Request):
    """Validate HMAC signature when INGEST_WEBHOOK_SECRET is configured."""
    webhook_secret = os.environ.get("INGEST_WEBHOOK_SECRET")
    if not webhook_secret:
        return  # Backward compat: no secret = no signature check

    signature = request.headers.get("X-Signature")
    if not signature:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Signature header",
        )

    body = await request.body()  # Starlette caches this, safe to call before Pydantic

    from ..webhook_service.auth import verify_webhook_signature
    if not verify_webhook_signature(body, signature, webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
```

**Modify endpoint signature (line 59):**
```python
# BEFORE
async def ingest_messages(
    payload: IngestDocument,
    api_key: str = Depends(_validate_api_key),
):

# AFTER
async def ingest_messages(
    request: Request,
    payload: IngestDocument,
    api_key: str = Depends(_validate_api_key),
    _sig: None = Depends(_validate_signature),
):
```

### Tests
Create `tests/unit/test_feeds/test_ingest_handler.py`:
- `test_ingest_no_secret_no_signature_required` -- No env var, no header -> success
- `test_ingest_secret_configured_missing_signature_401` -- Secret set, no header -> 401
- `test_ingest_secret_configured_invalid_signature_401` -- Wrong HMAC -> 401
- `test_ingest_secret_configured_valid_signature_success` -- Correct HMAC -> accepted

---

## FIX 4: P0-2 -- OAuth CSRF Missing State Parameter

**Complexity: M | Files: 3**

The bug: `get_oauth_url()` called without `state` parameter. No CSRF protection on OAuth flow.

### Changes

**`src/dashboard/auth.py:72`** -- Add state store after `_sessions`:
```python
self._pending_states: dict[str, datetime] = {}
```

**`src/dashboard/auth.py`** -- Add methods to `DashboardAuth` (after `cleanup_expired_sessions`):
```python
def create_oauth_state(self) -> str:
    """Generate and store a CSRF state token for OAuth."""
    state = secrets.token_urlsafe(32)
    self._pending_states[state] = utc_now_naive()
    # Cleanup expired states (>10 min)
    cutoff = utc_now_naive() - timedelta(minutes=10)
    self._pending_states = {s: t for s, t in self._pending_states.items() if t > cutoff}
    return state

def validate_oauth_state(self, state: str) -> bool:
    """Validate and consume an OAuth state token."""
    created_at = self._pending_states.pop(state, None)
    if created_at is None:
        return False
    return utc_now_naive() - created_at <= timedelta(minutes=10)
```

**`src/dashboard/models.py`** -- Update models:
```python
# AuthLoginResponse: add state field
class AuthLoginResponse(BaseModel):
    redirect_url: str
    state: str

# AuthCallbackRequest: add state field
class AuthCallbackRequest(BaseModel):
    code: str
    state: str
```

**`src/dashboard/routes/auth.py:41-45`** -- Update `login()`:
```python
async def login():
    auth = get_auth()
    state = auth.create_oauth_state()
    redirect_url = auth.get_oauth_url(state=state)
    return AuthLoginResponse(redirect_url=redirect_url, state=state)
```

**`src/dashboard/routes/auth.py:58-63`** -- Update `callback()`:
```python
async def callback(request: Request, body: AuthCallbackRequest):
    auth = get_auth()
    if not auth.validate_oauth_state(body.state):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_STATE", "message": "Invalid or expired OAuth state"},
        )
    # ... rest unchanged
```

**Frontend update needed:** `src/frontend/src/stores/authStore.ts` or equivalent must:
1. Store `state` from `/login` response
2. Pass `state` back in `/callback` request body

### Tests
`tests/unit/test_dashboard/test_auth.py`:
- `test_login_returns_state_token`
- `test_callback_rejects_missing_state` (Pydantic 422)
- `test_callback_rejects_invalid_state` -> 400
- `test_callback_rejects_expired_state` -> 400 (mock time)
- `test_callback_accepts_valid_state`
- `test_state_cannot_be_reused` -> second use fails

---

## FIX 5: P1-5 -- Global Write Lock / Pool Size

**Complexity: S | File: `src/data/sqlite/connection.py`**

The bug: `pool_size=1` means all reads also serialize behind one connection, despite WAL mode.

### Changes

**`src/data/sqlite/connection.py:74`** -- Change default:
```python
# BEFORE
def __init__(self, db_path: str, pool_size: int = 1):

# AFTER
def __init__(self, db_path: str, pool_size: int = 3):
```

**Update docstring (lines 67-71):**
```python
class SQLiteConnection(DatabaseConnection):
    """SQLite database connection with connection pooling.

    Uses WAL mode for read concurrency with a global write lock to
    serialize writes (SQLite single-writer constraint). Default pool
    size of 3 allows concurrent reads while writes are serialized.
    """
```

### Tests
`tests/unit/test_data/test_sqlite.py`:
- `test_default_pool_size_is_3`
- `test_concurrent_reads_complete_without_timeout`

---

## FIX 6: P1-6 -- N+1 Query Explosion in Guild Listing

**Complexity: M | File: `src/dashboard/routes/guilds.py`**

The bug: `find_by_guild(limit=10000)` + `len()` fetches thousands of full objects just to count. Also 5 sequential queries per guild inside a loop.

### Changes

**`src/dashboard/routes/guilds.py:115-119`** -- In `list_guilds`, replace fetch-to-count:
```python
# BEFORE
all_summaries = await stored_repo.find_by_guild(guild_id=guild_id, limit=10000)
summary_count = len(all_summaries)

# AFTER
summary_count = await stored_repo.count_by_guild(guild_id=guild_id)
```

**`src/dashboard/routes/guilds.py:296-320`** -- In `get_guild`, replace all fetch-to-count patterns:
```python
# BEFORE (lines 298-320)
all_summaries = await stored_repo.find_by_guild(guild_id=guild_id, limit=10000)
total_summaries = len(all_summaries)
# ... loop over all_summaries to count by source
week_summaries = await stored_repo.find_by_guild(..., limit=10000)
summaries_this_week = len(week_summaries)

# AFTER
import asyncio
from ...models.stored_summary import SummarySource

week_ago = utc_now_naive() - timedelta(days=7)
(total_summaries, summaries_this_week,
 realtime_count, archive_count,
 scheduled_count, manual_count) = await asyncio.gather(
    stored_repo.count_by_guild(guild_id=guild_id),
    stored_repo.count_by_guild(guild_id=guild_id, created_after=week_ago),
    stored_repo.count_by_guild(guild_id=guild_id, source=SummarySource.REALTIME.value),
    stored_repo.count_by_guild(guild_id=guild_id, source=SummarySource.ARCHIVE.value),
    stored_repo.count_by_guild(guild_id=guild_id, source=SummarySource.SCHEDULED.value),
    stored_repo.count_by_guild(guild_id=guild_id, source=SummarySource.MANUAL.value),
)
```

### Tests
`tests/unit/test_dashboard/test_guilds.py`:
- `test_list_guilds_uses_count_not_find` -- assert `count_by_guild` called, `find_by_guild(limit=10000)` NOT called
- `test_get_guild_uses_parallel_count_queries`

---

## FIX 7: P1-7 -- SSRF in Webhook Test Endpoint

**Complexity: M | Files: `src/dashboard/routes/webhooks.py` + new utility**

The bug: Webhook test sends HTTP POST to any stored URL without filtering private IPs.

### New File: `src/utils/url_validation.py`

```python
"""URL validation to prevent SSRF attacks."""
import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

def validate_webhook_url(url: str) -> tuple[bool, str]:
    """Validate URL is safe (not internal/private). Returns (is_valid, error_msg)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    if parsed.scheme not in ("http", "https"):
        return False, f"Scheme must be http(s), got: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False, f"Cannot resolve hostname: {hostname}"

    for _, _, _, _, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        for blocked in _BLOCKED_RANGES:
            if ip in blocked:
                return False, f"Resolves to blocked IP range: {blocked}"

    return True, ""
```

### Changes in `src/dashboard/routes/webhooks.py`

Add validation before HTTP request in `test_webhook` (before line 365):
```python
from ...utils.url_validation import validate_webhook_url
is_valid, error_msg = validate_webhook_url(webhook["url"])
if not is_valid:
    raise HTTPException(
        status_code=400,
        detail={"code": "INVALID_URL", "message": f"Unsafe webhook URL: {error_msg}"},
    )
```

Apply same validation in `create_webhook` and `update_webhook` (replace the simple `startswith` check).

### Tests
`tests/unit/test_utils/test_url_validation.py`:
- `test_rejects_private_10x`, `test_rejects_private_172x`, `test_rejects_private_192x`
- `test_rejects_loopback`, `test_rejects_localhost`
- `test_rejects_metadata_endpoint` (169.254.169.254)
- `test_rejects_file_scheme`
- `test_accepts_public_https_url` (mock DNS)

---

## FIX 8: P1-8 -- Webhook Secrets in Plaintext

**Complexity: M | Files: `src/data/sqlite/config_repository.py` + new utility**

The bug: `webhook_secret` stored as plaintext while Discord tokens are Fernet-encrypted.

### New File: `src/utils/encryption.py`

```python
"""Shared Fernet encryption utilities."""
import os, logging
from typing import Optional
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)
_cipher: Optional[Fernet] = None

def get_cipher() -> Fernet:
    global _cipher
    if _cipher: return _cipher
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        logger.warning("ENCRYPTION_KEY not set, using ephemeral key")
        key = Fernet.generate_key().decode()
    _cipher = Fernet(key.encode() if isinstance(key, str) else key)
    return _cipher

def encrypt_value(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None: return None
    return get_cipher().encrypt(plaintext.encode()).decode()

def decrypt_value(ciphertext: Optional[str]) -> Optional[str]:
    if ciphertext is None: return None
    try:
        return get_cipher().decrypt(ciphertext.encode()).decode()
    except Exception:
        logger.warning("Decryption failed, returning as plaintext (legacy data)")
        return ciphertext  # Graceful fallback for unencrypted data
```

### Changes in `src/data/sqlite/config_repository.py`

**On save (line ~39):** `encrypt_value(config.webhook_secret)`
**On read (line ~95):** `decrypt_value(row['webhook_secret'])`

### New File: `scripts/migrate_encrypt_secrets.py`
One-time idempotent migration: read all `guild_configs` rows, detect plaintext secrets (not valid Fernet tokens), encrypt in place.

### Tests
`tests/unit/test_data/test_config_repository.py`:
- `test_webhook_secret_encrypted_on_save`
- `test_webhook_secret_decrypted_on_read`
- `test_legacy_plaintext_handled_gracefully`

---

## Summary

| # | ID | Severity | Size | Files Changed | New Files | Tests |
|---|-----|----------|------|---------------|-----------|-------|
| 1 | P0-4 | Critical | S | 1 | 0 | 1 |
| 2 | P0-3 | Critical | S | 1 | 0 | 5 |
| 3 | P0-1 | Critical | M | 1 | 0 | 4 |
| 4 | P0-2 | Critical | M | 3 | 0 | 6 |
| 5 | P1-5 | High | S | 1 | 0 | 2 |
| 6 | P1-6 | High | M | 1 | 0 | 2 |
| 7 | P1-7 | High | M | 1 | 1 | 7 |
| 8 | P1-8 | High | M | 1 | 2 | 3 |
| **Total** | | | | **10** | **3** | **30** |

---

*Generated from QE Swarm analysis -- March 13, 2026*
