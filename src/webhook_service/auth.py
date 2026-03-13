"""
Authentication middleware for webhook service.
"""

import logging
import hashlib
import hmac
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from ..exceptions.webhook import WebhookAuthError
from ..config.settings import BotConfig
from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# JWT configuration (will be overridden by config)
# SEC-001: Default is None - MUST be set via config before use
JWT_SECRET: str | None = None
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60

# Known insecure default values that must not be used in production
_INSECURE_SECRETS = {
    "your-secret-key-change-in-production",
    "change-this-in-production",
    "change-in-production",
    "secret",
    "changeme",
}

# Rate limiting storage (in-memory for now)
_rate_limit_store: Dict[str, list] = {}

# Global config reference (will be set by server)
_config: Optional[BotConfig] = None


def set_config(config: BotConfig) -> None:
    """Set global configuration for auth module.

    Args:
        config: Bot configuration

    Raises:
        ValueError: If JWT secret is missing or insecure in production
    """
    global _config, JWT_SECRET, JWT_EXPIRATION_MINUTES
    _config = config

    if config is None:
        JWT_SECRET = None
        JWT_EXPIRATION_MINUTES = 60
        return

    import os
    environment = os.getenv("ENVIRONMENT", "development").lower()
    testing_enabled = os.getenv("TESTING", "").lower() in ("true", "1", "yes")

    # SEC-001: Validate JWT secret is set and not an insecure default
    jwt_secret = config.webhook_config.jwt_secret
    if not jwt_secret:
        if environment == "production" and not testing_enabled:
            raise ValueError(
                "WEBHOOK_JWT_SECRET is required but not set. "
                "Please set a strong, random secret in your environment."
            )
        else:
            # Generate a temporary secret for development/testing
            import secrets as secrets_module
            jwt_secret = secrets_module.token_urlsafe(32)
            logger.warning(
                "WEBHOOK_JWT_SECRET not set - using generated temporary secret. "
                "This is acceptable for development/testing but MUST be configured for production."
            )
    elif jwt_secret.lower() in _INSECURE_SECRETS:
        if environment == "production" and not testing_enabled:
            raise ValueError(
                f"WEBHOOK_JWT_SECRET is set to an insecure default value. "
                "Please set a strong, random secret for production use."
            )
        else:
            logger.warning(
                "WEBHOOK_JWT_SECRET is using an insecure default value. "
                "This is acceptable for development but MUST be changed for production."
            )

    JWT_SECRET = jwt_secret
    JWT_EXPIRATION_MINUTES = config.webhook_config.jwt_expiration_minutes


class APIKeyAuth(BaseModel):
    """API key authentication."""
    api_key: str
    user_id: Optional[str] = None
    permissions: list = []


class JWTAuth(BaseModel):
    """JWT authentication."""
    token: str
    user_id: str
    guild_id: Optional[str] = None
    permissions: list = []
    expires_at: datetime


async def get_api_key_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
) -> APIKeyAuth:
    """Validate API key authentication.

    Args:
        x_api_key: API key from X-API-Key header
        authorization: Bearer token from Authorization header

    Returns:
        Validated API key auth

    Raises:
        HTTPException: If authentication fails
    """
    # Try X-API-Key header first
    if x_api_key:
        # Validate API key length
        if not x_api_key or len(x_api_key) < 10:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key format"
            )

        # Check against configured API keys
        user_id = None
        if _config and _config.webhook_config.api_keys:
            user_id = _config.webhook_config.api_keys.get(x_api_key)
            if not user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid API key"
                )
        else:
            # SEC-003: Fail closed - reject all requests when no API keys configured
            import os
            environment = os.getenv("ENVIRONMENT", "development").lower()
            if environment == "production":
                raise HTTPException(
                    status_code=401,
                    detail="API authentication not configured. Contact administrator."
                )
            else:
                # Allow development mode to continue with warning
                user_id = "api-user"
                logger.warning(
                    "No API keys configured - accepting any valid key format. "
                    "This is only allowed in non-production environments."
                )

        return APIKeyAuth(
            api_key=x_api_key,
            user_id=user_id,
            permissions=["read", "write", "admin"]
        )

    # Try Authorization header with Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]

        try:
            # Validate JWT
            jwt_auth = await verify_jwt_token(token)

            # Convert to APIKeyAuth for compatibility
            return APIKeyAuth(
                api_key=token,
                user_id=jwt_auth.user_id,
                permissions=jwt_auth.permissions
            )
        except JWTError as e:
            logger.warning(f"JWT validation failed: {e}")
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token"
            )

    # No authentication provided
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide X-API-Key or Authorization header."
    )


async def get_jwt_auth(
    authorization: str = Header(None)
) -> JWTAuth:
    """Validate JWT authentication.

    Args:
        authorization: Bearer token from Authorization header

    Returns:
        Validated JWT auth

    Raises:
        HTTPException: If authentication fails
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header with Bearer token required"
        )

    token = authorization[7:]

    try:
        return await verify_jwt_token(token)
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


async def verify_jwt_token(token: str) -> JWTAuth:
    """Verify and decode JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded JWT authentication

    Raises:
        JWTError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        user_id = payload.get("sub")
        if not user_id:
            raise JWTError("Token missing user ID")

        expires_at = datetime.fromtimestamp(payload.get("exp", 0))
        if expires_at < utc_now_naive():
            raise JWTError("Token expired")

        return JWTAuth(
            token=token,
            user_id=user_id,
            guild_id=payload.get("guild_id"),
            permissions=payload.get("permissions", []),
            expires_at=expires_at
        )

    except JWTError:
        raise
    except Exception as e:
        raise JWTError(f"Token validation failed: {e}")


def create_jwt_token(
    user_id: str,
    guild_id: Optional[str] = None,
    permissions: list = None,
    expires_minutes: int = JWT_EXPIRATION_MINUTES
) -> str:
    """Create a new JWT token.

    Args:
        user_id: User identifier
        guild_id: Optional guild identifier
        permissions: List of permissions
        expires_minutes: Token expiration time in minutes

    Returns:
        Encoded JWT token
    """
    now = utc_now_naive()
    expires = now + timedelta(minutes=expires_minutes)

    payload = {
        "sub": user_id,
        "iat": now.timestamp(),
        "exp": expires.timestamp(),
        "permissions": permissions or []
    }

    if guild_id:
        payload["guild_id"] = guild_id

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str
) -> bool:
    """Verify webhook signature.

    Args:
        payload: Request payload bytes
        signature: Signature from X-Signature header
        secret: Webhook secret key

    Returns:
        True if signature is valid
    """
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected_signature)


def setup_rate_limiting(app, rate_limit: int = 100):
    """Setup rate limiting middleware.

    Args:
        app: FastAPI application
        rate_limit: Maximum requests per minute
    """

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """Rate limiting middleware."""
        # Get client identifier (IP or API key)
        client_id = request.headers.get("X-API-Key") or request.client.host

        # Get current minute
        current_minute = int(time.time() / 60)

        # Initialize rate limit tracking
        if client_id not in _rate_limit_store:
            _rate_limit_store[client_id] = []

        # Clean old entries
        _rate_limit_store[client_id] = [
            t for t in _rate_limit_store[client_id]
            if t == current_minute
        ]

        # Check rate limit
        request_count = len(_rate_limit_store[client_id])

        if request_count >= rate_limit:
            # SEC-004: Return JSONResponse instead of returning HTTPException object
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit of {rate_limit} requests per minute exceeded",
                    "retry_after": 60
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(rate_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str((current_minute + 1) * 60)
                }
            )

        # Add current request
        _rate_limit_store[client_id].append(current_minute)

        # Add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_limit - request_count - 1)
        response.headers["X-RateLimit-Reset"] = str((current_minute + 1) * 60)

        return response
