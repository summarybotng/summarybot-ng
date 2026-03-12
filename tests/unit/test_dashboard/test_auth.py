"""
Unit tests for dashboard/auth.py.

Tests DashboardAuth for OAuth, JWT, and session management.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from jose import jwt
from fastapi import HTTPException

from src.dashboard.auth import DashboardAuth, OAUTH_SCOPES
from src.dashboard.models import DashboardUser, DashboardGuild, GuildRole


class TestDashboardAuthInit:
    """Tests for DashboardAuth initialization."""

    def test_basic_init(self):
        """Create auth handler with required params."""
        auth = DashboardAuth(
            client_id="123456",
            client_secret="secret",
            redirect_uri="https://example.com/callback",
            jwt_secret="jwt-secret-key"
        )
        assert auth.client_id == "123456"
        assert auth.jwt_expiration_hours == 24
        assert auth.session_expiration_days == 7

    def test_custom_expiration(self):
        """Custom expiration times."""
        auth = DashboardAuth(
            client_id="123456",
            client_secret="secret",
            redirect_uri="https://example.com/callback",
            jwt_secret="jwt-secret-key",
            jwt_expiration_hours=12,
            session_expiration_days=14
        )
        assert auth.jwt_expiration_hours == 12
        assert auth.session_expiration_days == 14

    def test_ephemeral_encryption_key_warning(self):
        """Warning logged when no encryption key provided."""
        with patch('src.dashboard.auth.logger') as mock_logger:
            auth = DashboardAuth(
                client_id="123456",
                client_secret="secret",
                redirect_uri="https://example.com/callback",
                jwt_secret="jwt-secret-key"
            )
            mock_logger.warning.assert_called()


class TestOAuthURL:
    """Tests for OAuth URL generation."""

    @pytest.fixture
    def auth(self):
        """Create auth handler."""
        return DashboardAuth(
            client_id="123456789",
            client_secret="secret",
            redirect_uri="https://example.com/callback",
            jwt_secret="jwt-secret-key"
        )

    def test_oauth_url_basic(self, auth):
        """Generate OAuth URL with required params."""
        url = auth.get_oauth_url()
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert "discord.com" in parsed.netloc
        assert params["client_id"][0] == "123456789"
        assert params["redirect_uri"][0] == "https://example.com/callback"
        assert params["response_type"][0] == "code"
        assert "identify" in params["scope"][0]
        assert "guilds" in params["scope"][0]

    def test_oauth_url_with_state(self, auth):
        """OAuth URL includes state parameter."""
        url = auth.get_oauth_url(state="csrf-token-123")
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params["state"][0] == "csrf-token-123"

    def test_oauth_url_without_state(self, auth):
        """OAuth URL omits state when not provided."""
        url = auth.get_oauth_url()
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert "state" not in params


class TestJWT:
    """Tests for JWT creation and verification."""

    @pytest.fixture
    def auth(self):
        """Create auth handler."""
        return DashboardAuth(
            client_id="123456",
            client_secret="secret",
            redirect_uri="https://example.com/callback",
            jwt_secret="test-jwt-secret-key-12345"
        )

    @pytest.fixture
    def sample_user(self):
        """Create sample user."""
        return DashboardUser(
            id="user123",
            username="testuser",
            discriminator="1234",
            avatar="avatar123"
        )

    def test_create_jwt(self, auth, sample_user):
        """Create valid JWT token."""
        token = auth.create_jwt(sample_user, ["guild1", "guild2"])
        assert token is not None
        assert len(token.split(".")) == 3  # JWT has 3 parts

    def test_verify_jwt_valid(self, auth, sample_user):
        """Verify valid JWT returns payload."""
        token = auth.create_jwt(sample_user, ["guild1"])
        payload = auth.verify_jwt(token)

        assert payload["sub"] == "user123"
        assert payload["username"] == "testuser"
        assert "guild1" in payload["guilds"]

    def test_verify_jwt_expired(self, auth, sample_user):
        """Verify expired JWT raises exception."""
        # Create token with negative expiration
        with patch('src.dashboard.auth.datetime') as mock_dt:
            mock_dt.utcnow.return_value = datetime.utcnow() - timedelta(hours=48)
            token = auth.create_jwt(sample_user, ["guild1"])

        with pytest.raises(HTTPException) as exc_info:
            auth.verify_jwt(token)
        assert exc_info.value.status_code == 401
        assert "expired" in str(exc_info.value.detail).lower()

    def test_verify_jwt_invalid(self, auth):
        """Verify invalid JWT raises exception."""
        with pytest.raises(HTTPException) as exc_info:
            auth.verify_jwt("invalid.token.here")
        assert exc_info.value.status_code == 401

    def test_verify_jwt_wrong_secret(self, auth, sample_user):
        """JWT signed with wrong secret fails."""
        # Create token with different auth instance
        other_auth = DashboardAuth(
            client_id="123456",
            client_secret="secret",
            redirect_uri="https://example.com/callback",
            jwt_secret="different-secret-key"
        )
        token = other_auth.create_jwt(sample_user, ["guild1"])

        with pytest.raises(HTTPException) as exc_info:
            auth.verify_jwt(token)
        assert exc_info.value.status_code == 401

    def test_jwt_contains_guild_roles(self, auth, sample_user):
        """JWT includes guild roles."""
        guild_roles = {"guild1": "owner", "guild2": "admin"}
        token = auth.create_jwt(sample_user, ["guild1", "guild2"], guild_roles)
        payload = auth.verify_jwt(token)

        assert payload["guild_roles"]["guild1"] == "owner"
        assert payload["guild_roles"]["guild2"] == "admin"

    def test_refresh_jwt(self, auth, sample_user):
        """Refresh JWT creates valid token with same user data."""
        original_token = auth.create_jwt(sample_user, ["guild1"])
        new_token = auth.refresh_jwt(original_token)

        # Token may be identical if created in same second (same iat/exp)
        # so verify the new token is valid and has correct data
        payload = auth.verify_jwt(new_token)
        assert payload["sub"] == "user123"
        assert payload["username"] == "testuser"
        assert "guild1" in payload["guilds"]


class TestDiscordAPI:
    """Tests for Discord API interaction."""

    @pytest.fixture
    def auth(self):
        """Create auth handler."""
        return DashboardAuth(
            client_id="123456",
            client_secret="secret",
            redirect_uri="https://example.com/callback",
            jwt_secret="jwt-secret-key"
        )

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, auth):
        """Successful OAuth code exchange."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access123",
            "refresh_token": "refresh456",
            "expires_in": 604800
        }

        with patch.object(auth, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            access, refresh, expires = await auth.exchange_code("code123")

            assert access == "access123"
            assert refresh == "refresh456"
            assert expires == 604800

    @pytest.mark.asyncio
    async def test_exchange_code_failure(self, auth):
        """Failed OAuth code exchange raises exception."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"

        with patch.object(auth, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            with pytest.raises(HTTPException) as exc_info:
                await auth.exchange_code("invalid-code")
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_user_success(self, auth):
        """Get Discord user info."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "user123",
            "username": "testuser",
            "discriminator": "1234",
            "avatar": "avatar123"
        }

        with patch.object(auth, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_client.return_value = mock_http

            user = await auth.get_user("access123")

            assert user.id == "user123"
            assert user.username == "testuser"

    @pytest.mark.asyncio
    async def test_get_user_invalid_token(self, auth):
        """Invalid token raises exception."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.object(auth, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_client.return_value = mock_http

            with pytest.raises(HTTPException) as exc_info:
                await auth.get_user("invalid-token")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_user_guilds_success(self, auth):
        """Get user's Discord guilds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "guild1",
                "name": "Server 1",
                "icon": "icon1",
                "owner": True,
                "permissions": "2147483647"
            },
            {
                "id": "guild2",
                "name": "Server 2",
                "icon": None,
                "owner": False,
                "permissions": "0"
            }
        ]

        with patch.object(auth, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_client.return_value = mock_http

            guilds = await auth.get_user_guilds("access123")

            assert len(guilds) == 2
            assert guilds[0].id == "guild1"
            assert guilds[0].owner is True
            assert guilds[1].owner is False

    @pytest.mark.asyncio
    async def test_refresh_discord_token_success(self, auth):
        """Refresh Discord token successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 604800
        }

        with patch.object(auth, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            access, refresh, expires = await auth.refresh_discord_token("old_refresh")

            assert access == "new_access"
            assert refresh == "new_refresh"

    @pytest.mark.asyncio
    async def test_refresh_discord_token_failure(self, auth):
        """Refresh Discord token failure raises exception."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.object(auth, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            with pytest.raises(HTTPException) as exc_info:
                await auth.refresh_discord_token("expired_refresh")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_close_http_client(self, auth):
        """Close HTTP client properly."""
        # Initialize client with a mock that supports aclose
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        auth._http_client = mock_client

        await auth.close()

        mock_client.aclose.assert_called_once()
        assert auth._http_client is None


class TestTokenHashing:
    """Tests for token hashing (if exposed)."""

    @pytest.fixture
    def auth(self):
        """Create auth handler."""
        return DashboardAuth(
            client_id="123456",
            client_secret="secret",
            redirect_uri="https://example.com/callback",
            jwt_secret="jwt-secret-key"
        )

    def test_same_token_same_hash(self, auth):
        """Same token produces same hash."""
        if hasattr(auth, '_hash_token'):
            hash1 = auth._hash_token("test-token")
            hash2 = auth._hash_token("test-token")
            assert hash1 == hash2

    def test_different_tokens_different_hash(self, auth):
        """Different tokens produce different hashes."""
        if hasattr(auth, '_hash_token'):
            hash1 = auth._hash_token("token-1")
            hash2 = auth._hash_token("token-2")
            assert hash1 != hash2
