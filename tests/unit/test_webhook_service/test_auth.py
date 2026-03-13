"""
Unit tests for authentication (auth.py).

Tests API key validation, JWT token generation/validation,
webhook signature verification, and rate limiting.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from fastapi import HTTPException
from jose import jwt, JWTError

from src.webhook_service.auth import (
    APIKeyAuth,
    JWTAuth,
    get_api_key_auth,
    get_jwt_auth,
    verify_jwt_token,
    create_jwt_token,
    verify_webhook_signature,
    setup_rate_limiting,
    set_config,
    JWT_SECRET,
    JWT_ALGORITHM
)
from src.config.settings import BotConfig, WebhookConfig


@pytest.fixture
def webhook_config():
    """Create webhook configuration."""
    return WebhookConfig(
        enabled=True,
        host="127.0.0.1",
        port=8000,
        api_keys={
            "valid_key_123": "user_123",
            "admin_key_456": "admin_456"
        },
        jwt_secret="test_secret_key_for_jwt",
        jwt_expiration_minutes=60,
        rate_limit=100
    )


@pytest.fixture
def bot_config(webhook_config):
    """Create bot configuration."""
    config = MagicMock(spec=BotConfig)
    config.webhook_config = webhook_config
    return config


@pytest.fixture
def setup_auth_config(bot_config):
    """Setup auth configuration."""
    set_config(bot_config)
    yield
    # Cleanup
    set_config(None)


class TestAPIKeyAuth:
    """Test API key authentication."""

    @pytest.mark.asyncio
    async def test_valid_api_key(self, setup_auth_config):
        """Test authentication with valid API key."""
        auth = await get_api_key_auth(x_api_key="valid_key_123")

        assert isinstance(auth, APIKeyAuth)
        assert auth.api_key == "valid_key_123"
        assert auth.user_id == "user_123"
        assert "read" in auth.permissions
        assert "write" in auth.permissions

    @pytest.mark.asyncio
    async def test_invalid_api_key(self, setup_auth_config):
        """Test authentication with invalid API key."""
        with pytest.raises(HTTPException) as exc_info:
            await get_api_key_auth(x_api_key="invalid_key")

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_short_api_key(self, setup_auth_config):
        """Test authentication with too short API key."""
        with pytest.raises(HTTPException) as exc_info:
            await get_api_key_auth(x_api_key="short")

        assert exc_info.value.status_code == 401
        assert "Invalid API key format" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test authentication without API key."""
        with pytest.raises(HTTPException) as exc_info:
            await get_api_key_auth(x_api_key=None, authorization=None)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_no_config_accepts_any_valid_format(self):
        """Test that without config, any valid format is accepted."""
        set_config(None)

        auth = await get_api_key_auth(x_api_key="any_valid_key_1234567890")

        assert auth.user_id == "api-user"
        assert len(auth.permissions) > 0


class TestJWTAuth:
    """Test JWT token authentication."""

    @pytest.mark.asyncio
    async def test_create_jwt_token(self, setup_auth_config):
        """Test JWT token creation."""
        token = create_jwt_token(
            user_id="user_123",
            guild_id="guild_456",
            permissions=["read", "write"]
        )

        assert isinstance(token, str)
        assert len(token) > 0

        # Decode to verify structure - use module-level ref after set_config
        import src.webhook_service.auth as auth_mod
        payload = jwt.decode(token, auth_mod.JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert payload["sub"] == "user_123"
        assert payload["guild_id"] == "guild_456"
        assert payload["permissions"] == ["read", "write"]

    @pytest.mark.asyncio
    async def test_verify_valid_jwt_token(self, setup_auth_config):
        """Test verifying valid JWT token."""
        token = create_jwt_token(user_id="user_123")

        jwt_auth = await verify_jwt_token(token)

        assert isinstance(jwt_auth, JWTAuth)
        assert jwt_auth.user_id == "user_123"
        assert jwt_auth.token == token

    @pytest.mark.asyncio
    async def test_verify_expired_token(self, setup_auth_config):
        """Test verifying expired token."""
        token = create_jwt_token(user_id="user_123", expires_minutes=-10)

        with pytest.raises(JWTError) as exc_info:
            await verify_jwt_token(token)

        assert "expired" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self, setup_auth_config):
        """Test verifying invalid token."""
        with pytest.raises(JWTError):
            await verify_jwt_token("invalid.token.here")

    @pytest.mark.asyncio
    async def test_verify_token_missing_user_id(self, setup_auth_config):
        """Test token without user ID."""
        # Create token without 'sub' claim - use module-level ref after set_config
        import src.webhook_service.auth as auth_mod
        payload = {
            "iat": datetime.utcnow().timestamp(),
            "exp": (datetime.utcnow() + timedelta(hours=1)).timestamp()
        }
        token = jwt.encode(payload, auth_mod.JWT_SECRET, algorithm=JWT_ALGORITHM)

        with pytest.raises(JWTError) as exc_info:
            await verify_jwt_token(token)

        assert "missing user id" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_jwt_auth_valid(self, setup_auth_config):
        """Test get_jwt_auth with valid token."""
        token = create_jwt_token(user_id="user_123")

        jwt_auth = await get_jwt_auth(authorization=f"Bearer {token}")

        assert jwt_auth.user_id == "user_123"

    @pytest.mark.asyncio
    async def test_get_jwt_auth_missing_bearer(self):
        """Test get_jwt_auth without Bearer prefix."""
        with pytest.raises(HTTPException) as exc_info:
            await get_jwt_auth(authorization="token123")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_jwt_auth_no_header(self):
        """Test get_jwt_auth without authorization header."""
        with pytest.raises(HTTPException) as exc_info:
            await get_jwt_auth(authorization=None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_bearer_token_fallback_in_api_key_auth(self, setup_auth_config):
        """Test that get_api_key_auth accepts Bearer token."""
        token = create_jwt_token(user_id="user_from_jwt")

        auth = await get_api_key_auth(
            x_api_key=None,
            authorization=f"Bearer {token}"
        )

        assert auth.user_id == "user_from_jwt"


class TestJWTTokenExpiration:
    """Test JWT token expiration handling."""

    @pytest.mark.asyncio
    async def test_token_expiration_time(self, setup_auth_config):
        """Test token has correct expiration time."""
        expiration_minutes = 30
        token = create_jwt_token(
            user_id="user_123",
            expires_minutes=expiration_minutes
        )

        jwt_auth = await verify_jwt_token(token)

        # Check expiration is approximately correct
        time_until_expiry = (jwt_auth.expires_at - datetime.utcnow()).total_seconds()
        assert 29 * 60 < time_until_expiry < 31 * 60

    @pytest.mark.asyncio
    async def test_custom_expiration(self, setup_auth_config):
        """Test custom expiration time."""
        token = create_jwt_token(user_id="user_123", expires_minutes=120)

        jwt_auth = await verify_jwt_token(token)

        time_until_expiry = (jwt_auth.expires_at - datetime.utcnow()).total_seconds()
        assert 119 * 60 < time_until_expiry < 121 * 60


class TestWebhookSignature:
    """Test webhook signature verification."""

    def test_valid_signature(self):
        """Test verifying valid webhook signature."""
        payload = b"test payload data"
        secret = "webhook_secret_key"

        import hmac
        import hashlib
        signature = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        result = verify_webhook_signature(payload, signature, secret)

        assert result is True

    def test_invalid_signature(self):
        """Test verifying invalid signature."""
        payload = b"test payload data"
        secret = "webhook_secret_key"
        invalid_signature = "invalid_signature_here"

        result = verify_webhook_signature(payload, invalid_signature, secret)

        assert result is False

    def test_wrong_secret(self):
        """Test signature with wrong secret."""
        payload = b"test payload data"
        correct_secret = "correct_secret"
        wrong_secret = "wrong_secret"

        import hmac
        import hashlib
        signature = hmac.new(
            correct_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        result = verify_webhook_signature(payload, signature, wrong_secret)

        assert result is False

    def test_empty_payload(self):
        """Test signature verification with empty payload."""
        payload = b""
        secret = "secret"

        import hmac
        import hashlib
        signature = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        result = verify_webhook_signature(payload, signature, secret)

        assert result is True


class TestRateLimiting:
    """Test rate limiting middleware."""

    @pytest.mark.asyncio
    async def test_rate_limit_headers_added(self):
        """Test rate limit headers are added to response."""
        from fastapi import FastAPI, Request

        app = FastAPI()
        setup_rate_limiting(app, rate_limit=100)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        from fastapi.testclient import TestClient
        client = TestClient(app)

        response = client.get("/test")

        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers
        assert "x-ratelimit-reset" in response.headers
        assert response.headers["x-ratelimit-limit"] == "100"

    @pytest.mark.asyncio
    async def test_rate_limit_tracking(self):
        """Test rate limit tracks requests."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        setup_rate_limiting(app, rate_limit=5)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)

        # Make requests and check remaining count
        for i in range(3):
            response = client.get("/test", headers={"X-API-Key": "test_key"})
            remaining = int(response.headers.get("x-ratelimit-remaining", 0))
            assert remaining >= 0

    @pytest.mark.asyncio
    async def test_rate_limit_per_client(self):
        """Test rate limiting is per client."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        setup_rate_limiting(app, rate_limit=10)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)

        # Different API keys should have separate limits
        response1 = client.get("/test", headers={"X-API-Key": "key1"})
        response2 = client.get("/test", headers={"X-API-Key": "key2"})

        assert response1.status_code == 200
        assert response2.status_code == 200


class TestPermissions:
    """Test permission verification."""

    @pytest.mark.asyncio
    async def test_api_key_permissions(self, setup_auth_config):
        """Test API key includes permissions."""
        auth = await get_api_key_auth(x_api_key="valid_key_123")

        assert "read" in auth.permissions
        assert "write" in auth.permissions
        assert "admin" in auth.permissions

    @pytest.mark.asyncio
    async def test_jwt_permissions(self, setup_auth_config):
        """Test JWT token includes permissions."""
        token = create_jwt_token(
            user_id="user_123",
            permissions=["read", "write"]
        )

        jwt_auth = await verify_jwt_token(token)

        assert jwt_auth.permissions == ["read", "write"]

    @pytest.mark.asyncio
    async def test_jwt_default_permissions(self, setup_auth_config):
        """Test JWT token with default permissions."""
        token = create_jwt_token(user_id="user_123")

        jwt_auth = await verify_jwt_token(token)

        assert isinstance(jwt_auth.permissions, list)


class TestAuthModels:
    """Test authentication model classes."""

    def test_api_key_auth_model(self):
        """Test APIKeyAuth model."""
        auth = APIKeyAuth(
            api_key="test_key",
            user_id="user_123",
            permissions=["read", "write"]
        )

        assert auth.api_key == "test_key"
        assert auth.user_id == "user_123"
        assert auth.permissions == ["read", "write"]

    def test_jwt_auth_model(self):
        """Test JWTAuth model."""
        expires = datetime.utcnow() + timedelta(hours=1)
        auth = JWTAuth(
            token="jwt_token",
            user_id="user_123",
            guild_id="guild_456",
            permissions=["read"],
            expires_at=expires
        )

        assert auth.token == "jwt_token"
        assert auth.user_id == "user_123"
        assert auth.guild_id == "guild_456"
        assert auth.permissions == ["read"]
        assert auth.expires_at == expires


class TestConfigManagement:
    """Test configuration management."""

    def test_set_config(self, bot_config):
        """Test setting global configuration."""
        set_config(bot_config)

        from src.webhook_service.auth import _config, JWT_SECRET

        assert _config == bot_config
        assert JWT_SECRET == bot_config.webhook_config.jwt_secret

        # Cleanup to avoid polluting other tests
        set_config(None)

    def test_config_updates_jwt_settings(self, bot_config):
        """Test config updates JWT settings."""
        bot_config.webhook_config.jwt_expiration_minutes = 120

        set_config(bot_config)

        from src.webhook_service.auth import JWT_EXPIRATION_MINUTES

        assert JWT_EXPIRATION_MINUTES == 120

        # Cleanup to avoid polluting other tests
        set_config(None)
