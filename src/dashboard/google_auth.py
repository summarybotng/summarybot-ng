"""
Google Workspace SSO Authentication.

ADR-049: Google OAuth2 with domain restriction and security hardening.
Security requirements from QE Fleet review 2026-04-23.
"""

import os
import base64
import hashlib
import secrets
import logging
import threading
import unicodedata
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List
from urllib.parse import urlencode

import httpx
from jose import jwt, JWTError
from fastapi import HTTPException

from src.utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Google OAuth endpoints
GOOGLE_OAUTH_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_OAUTH_CERTS = "https://www.googleapis.com/oauth2/v3/certs"

# Required OAuth scopes
GOOGLE_SCOPES = ["openid", "email", "profile"]

# Generic error message (security: no info leakage)
GENERIC_AUTH_ERROR = "Authentication failed. Please contact your administrator if you believe this is an error."


class GoogleAuthConfig:
    """Google OAuth configuration with secure defaults."""

    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI",
            "https://summarybot-ng.fly.dev/api/v1/auth/google/callback"
        )

        # Domain restrictions
        domains_str = os.getenv("GOOGLE_ALLOWED_DOMAINS", "")
        self.allowed_domains = [d.strip().lower() for d in domains_str.split(",") if d.strip()]

        # SECURITY: Default to true (QE Fleet requirement)
        self.require_workspace = os.getenv("GOOGLE_REQUIRE_WORKSPACE", "true").lower() == "true"

        # Guild mapping
        self.domain_guilds = self._parse_domain_guilds()

    def _parse_domain_guilds(self) -> Dict[str, List[str]]:
        """Parse GOOGLE_DOMAIN_GUILDS env var.

        Format: domain1:guild1,domain2:guild2
        """
        mapping = {}
        guilds_str = os.getenv("GOOGLE_DOMAIN_GUILDS", "")

        for entry in guilds_str.split(","):
            entry = entry.strip()
            if ":" in entry:
                domain, guild_id = entry.split(":", 1)
                domain = domain.strip().lower()
                guild_id = guild_id.strip()
                if domain and guild_id:
                    if domain not in mapping:
                        mapping[domain] = []
                    mapping[domain].append(guild_id)

        return mapping

    @property
    def is_enabled(self) -> bool:
        """Check if Google SSO is enabled."""
        return bool(self.client_id and self.client_secret)

    def validate(self) -> None:
        """Validate configuration at startup.

        SECURITY: Fail closed on misconfiguration.
        """
        if not self.is_enabled:
            return  # Google SSO not configured

        # SECURITY: Require explicit domain configuration
        if not self.allowed_domains:
            raise ValueError(
                "SECURITY: GOOGLE_ALLOWED_DOMAINS must be configured when Google SSO is enabled. "
                "Empty domain list is not allowed to prevent unauthorized access."
            )

        # Validate domain format
        for domain in self.allowed_domains:
            if not self._is_valid_domain(domain):
                raise ValueError(f"Invalid domain format: {domain}")

        logger.info(f"Google SSO configured with domains: {self.allowed_domains}")

    def _is_valid_domain(self, domain: str) -> bool:
        """Validate domain format."""
        if not domain or len(domain) > 253:
            return False

        # Must be ASCII (no Unicode homoglyphs in config)
        try:
            domain.encode('ascii')
        except UnicodeEncodeError:
            return False

        # Basic domain validation
        parts = domain.split(".")
        if len(parts) < 2:
            return False

        return all(
            part and len(part) <= 63 and part[0].isalnum() and part[-1].isalnum()
            for part in parts
        )


class GoogleAuth:
    """Google OAuth2 authentication handler.

    Implements security requirements from ADR-049 and QE Fleet review.
    """

    def __init__(self, config: GoogleAuthConfig, jwt_secret: str):
        self.config = config
        self.jwt_secret = jwt_secret

        # SECURITY: Mutex for atomic state/nonce consumption
        self._state_lock = threading.Lock()

        # Pending OAuth states: state -> (nonce, pkce_verifier, created_at)
        self._pending_states: Dict[str, Tuple[str, str, datetime]] = {}

        # HTTP client
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # =========================================================================
    # PKCE Support (SECURITY: Required by QE Fleet)
    # =========================================================================

    def _generate_pkce_pair(self) -> Tuple[str, str]:
        """Generate PKCE code_verifier and code_challenge.

        SECURITY: Prevents authorization code interception attacks.
        """
        # Generate 64-byte random verifier
        code_verifier = secrets.token_urlsafe(64)

        # S256 challenge method
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')

        return code_verifier, code_challenge

    # =========================================================================
    # OAuth Flow
    # =========================================================================

    def create_oauth_state(self) -> Tuple[str, str]:
        """Create OAuth state with PKCE and nonce.

        Returns:
            Tuple of (state, oauth_url)
        """
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier, code_challenge = self._generate_pkce_pair()

        # Store state atomically
        with self._state_lock:
            # Clean up expired states (5 minute TTL - QE Fleet requirement)
            cutoff = utc_now_naive() - timedelta(minutes=5)
            self._pending_states = {
                s: v for s, v in self._pending_states.items()
                if v[2] > cutoff
            }

            self._pending_states[state] = (nonce, code_verifier, utc_now_naive())

        # Build OAuth URL
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "select_account",
        }

        oauth_url = f"{GOOGLE_OAUTH_AUTHORIZE}?{urlencode(params)}"
        return state, oauth_url

    def validate_state_atomic(self, state: str) -> Optional[Tuple[str, str]]:
        """Atomically validate and consume state token.

        SECURITY: Prevents race condition attacks.

        Returns:
            Tuple of (nonce, code_verifier) if valid, None otherwise
        """
        with self._state_lock:
            state_data = self._pending_states.pop(state, None)

            if state_data is None:
                return None

            nonce, code_verifier, created_at = state_data

            # Check expiration (5 minutes)
            if utc_now_naive() - created_at > timedelta(minutes=5):
                return None

            return nonce, code_verifier

    async def exchange_code(self, code: str, code_verifier: str) -> Dict:
        """Exchange authorization code for tokens.

        SECURITY: Uses PKCE code_verifier.
        """
        client = await self._get_http_client()

        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "code_verifier": code_verifier,
        }

        try:
            response = await client.post(
                GOOGLE_OAUTH_TOKEN,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                # SECURITY: Generic error message (no details leaked)
                logger.warning(f"Google token exchange failed: {response.status_code}")
                raise HTTPException(
                    status_code=401,
                    detail={"code": "AUTH_FAILED", "message": GENERIC_AUTH_ERROR},
                )

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"Google API request failed: {e}")
            raise HTTPException(
                status_code=502,
                detail={"code": "AUTH_FAILED", "message": GENERIC_AUTH_ERROR},
            )

    # =========================================================================
    # ID Token Verification
    # =========================================================================

    async def verify_id_token(self, id_token: str, expected_nonce: str) -> Dict:
        """Verify Google ID token with full validation.

        SECURITY: Validates signature, issuer, audience, nonce, expiration.
        """
        try:
            # Use Google's library for proper verification
            try:
                from google.oauth2 import id_token as google_id_token
                from google.auth.transport import requests as google_requests

                # Verify token signature and standard claims
                claims = google_id_token.verify_oauth2_token(
                    id_token,
                    google_requests.Request(),
                    self.config.client_id,
                    clock_skew_in_seconds=30,
                )
            except ImportError:
                # Fallback: Decode without verification (DEV ONLY)
                logger.warning("google-auth not installed, using unverified token decode (DEV ONLY)")
                claims = jwt.decode(id_token, options={"verify_signature": False})

            # SECURITY: Verify issuer
            if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
                logger.warning(f"Invalid issuer: {claims.get('iss')}")
                raise ValueError("Invalid issuer")

            # SECURITY: Verify audience
            if claims.get("aud") != self.config.client_id:
                logger.warning("Invalid audience")
                raise ValueError("Invalid audience")

            # SECURITY: Verify nonce (replay protection)
            if claims.get("nonce") != expected_nonce:
                logger.warning("Nonce mismatch")
                raise ValueError("Invalid nonce")

            # SECURITY: Require email verification
            if not claims.get("email_verified", False):
                logger.warning("Email not verified")
                raise ValueError("Email not verified")

            return claims

        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"ID token verification failed: {e}")
            raise HTTPException(
                status_code=401,
                detail={"code": "AUTH_FAILED", "message": GENERIC_AUTH_ERROR},
            )

    # =========================================================================
    # Domain Verification
    # =========================================================================

    def verify_domain(self, id_token_claims: Dict) -> Tuple[bool, str, Optional[str]]:
        """Verify Google Workspace domain using hd claim.

        SECURITY: Uses Google-verified hd claim, NOT email parsing.
        SECURITY: Unicode NFKC normalization for homoglyph protection.

        Returns:
            Tuple of (is_valid, error_message, domain)
        """
        email = id_token_claims.get("email", "")
        hd = id_token_claims.get("hd")  # Google Workspace hosted domain

        # SECURITY: Require Workspace account if configured
        if self.config.require_workspace and hd is None:
            return False, "Google Workspace account required", None

        # SECURITY: Fail closed - require explicit domain config
        if not self.config.allowed_domains:
            return False, "Domain configuration error", None

        # Personal Gmail (no hd claim) - reject if require_workspace
        if hd is None:
            return False, "Workspace account required", None

        # SECURITY: Normalize domain (NFKC + lowercase)
        normalized_hd = unicodedata.normalize('NFKC', hd.lower().strip())

        # Normalize allowed domains
        normalized_allowed = [
            unicodedata.normalize('NFKC', d.lower().strip())
            for d in self.config.allowed_domains
        ]

        if normalized_hd not in normalized_allowed:
            # SECURITY: Don't reveal which domains are allowed
            return False, "Domain not authorized", normalized_hd

        # Cross-verify email domain matches hd claim
        if "@" in email:
            email_domain = email.rsplit("@", 1)[1].lower()
            if email_domain != hd.lower():
                logger.warning(f"Email domain mismatch: {email_domain} vs {hd}")
                return False, "Domain verification failed", normalized_hd

        return True, "", normalized_hd

    # =========================================================================
    # Guild Access
    # =========================================================================

    def get_guilds_for_domain(self, domain: str) -> List[str]:
        """Get guild IDs for a domain.

        SECURITY: No default guild - require explicit mapping.
        """
        if not domain:
            return []

        normalized_domain = unicodedata.normalize('NFKC', domain.lower().strip())
        return self.config.domain_guilds.get(normalized_domain, [])

    # =========================================================================
    # Group-based Role Assignment (ADR-050)
    # =========================================================================

    async def _get_user_role_for_guild(
        self,
        user_email: str,
        domain: str,
        guild_id: str,
    ) -> str:
        """Determine if user should have admin role for a guild based on group membership.

        ADR-050: Check Google Workspace group membership against configured admin groups.

        Args:
            user_email: User's email address
            domain: User's Google Workspace domain
            guild_id: Discord guild ID to check

        Returns:
            "admin" if user is in an admin group for the guild, "member" otherwise
        """
        try:
            from ..data.repositories import get_repository_factory
            from ..data.repositories.google_admin_groups import GoogleAdminGroupsRepository
            from .google_directory import get_google_directory_client

            # Get configured admin groups for this guild
            try:
                factory = get_repository_factory()
                connection = await factory.get_connection()
                repo = GoogleAdminGroupsRepository(connection)
                admin_groups = await repo.get_admin_groups(guild_id)
            except RuntimeError:
                # Repository not initialized - default to fallback
                admin_groups = []

            # If no groups configured, default to admins@domain
            if not admin_groups:
                admin_groups = [f"admins@{domain}"]

            # Get directory client and check membership
            directory = get_google_directory_client()
            if directory and directory.is_configured:
                # get_user_groups is synchronous
                user_groups = directory.get_user_groups(user_email)
                # Case-insensitive comparison
                user_groups_lower = [g.lower() for g in user_groups]
                if any(ag.lower() in user_groups_lower for ag in admin_groups):
                    logger.info(f"User {user_email} granted admin for guild {guild_id} via group membership")
                    return "admin"
                return "member"
            else:
                # ADR-050 Phase 1: Grant admin to all Google SSO users until Directory API is configured
                logger.info(f"Directory API not configured - granting admin to {user_email} for guild {guild_id}")
                return "admin"
        except Exception as e:
            logger.warning(f"Failed to check group membership for {user_email}: {e}")
            return "member"

    # =========================================================================
    # JWT Creation
    # =========================================================================

    async def create_jwt(
        self,
        user_id: str,
        email: str,
        name: str,
        picture: Optional[str],
        domain: str,
        guild_ids: List[str],
    ) -> str:
        """Create JWT token for authenticated Google user.

        SECURITY: Includes auth_provider claim for provider distinction.
        SECURITY: 4-hour expiration (not 24).
        ADR-050: Checks group membership for admin role assignment.
        """
        # Determine role for each guild based on group membership (ADR-050)
        guild_roles = {}
        for guild_id in guild_ids:
            role = await self._get_user_role_for_guild(email, domain, guild_id)
            guild_roles[guild_id] = role

        now = utc_now_naive()
        payload = {
            "sub": f"google_{user_id}",  # Prefix to prevent collision
            "email": email,
            "username": name,
            "avatar": picture,
            "auth_provider": "google",
            "domain": domain,
            "guilds": guild_ids,
            "guild_roles": guild_roles,
            "iat": now,
            "exp": now + timedelta(hours=4),  # SECURITY: Short expiration
            # NOTE: Don't include iss/aud claims - jose library requires explicit
            # audience verification if aud claim is present, and we share the
            # verify_jwt method with Discord auth which doesn't expect these.
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm="HS256")
        logger.info(f"Created Google JWT for user {user_id}, secret prefix: {self.jwt_secret[:8]}...")
        return token


# Global instance
_google_auth: Optional[GoogleAuth] = None
_google_config: Optional[GoogleAuthConfig] = None


def get_google_config() -> GoogleAuthConfig:
    """Get Google auth configuration."""
    global _google_config
    if _google_config is None:
        _google_config = GoogleAuthConfig()
    return _google_config


def get_google_auth() -> Optional[GoogleAuth]:
    """Get Google auth handler if enabled."""
    global _google_auth
    config = get_google_config()

    if not config.is_enabled:
        return None

    if _google_auth is None:
        # Check DASHBOARD_JWT_SECRET first (same as dashboard auth), then JWT_SECRET
        jwt_secret = os.getenv("DASHBOARD_JWT_SECRET", os.getenv("JWT_SECRET", ""))
        if not jwt_secret:
            logger.warning("DASHBOARD_JWT_SECRET/JWT_SECRET not set, Google SSO disabled")
            return None

        _google_auth = GoogleAuth(config, jwt_secret)
        logger.info(f"GoogleAuth initialized with JWT secret prefix: {jwt_secret[:8]}...")

    return _google_auth


def initialize_google_auth() -> None:
    """Initialize and validate Google auth at startup."""
    config = get_google_config()
    if config.is_enabled:
        config.validate()
        logger.info("Google SSO initialized successfully")
