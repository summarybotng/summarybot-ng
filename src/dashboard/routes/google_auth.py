"""
Google OAuth authentication routes.

ADR-049: Google Workspace SSO with domain restriction.
Security requirements from QE Fleet review 2026-04-23.
"""

import os
import logging
import secrets
import asyncio
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..google_auth import (
    get_google_auth,
    get_google_config,
    GoogleAuth,
    GENERIC_AUTH_ERROR,
)
from ...logging import get_audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google", tags=["Google Auth"])


class GoogleLoginResponse(BaseModel):
    """Google OAuth login response."""
    redirect_url: str
    state: str


class GoogleCallbackRequest(BaseModel):
    """Google OAuth callback request."""
    code: str
    state: str


class GoogleCallbackResponse(BaseModel):
    """Google OAuth callback response."""
    token: str
    user: dict


class AuthProvidersResponse(BaseModel):
    """Available auth providers."""
    discord: bool = True
    google: bool = False


async def _audit_google_auth_event(
    event_type: str,
    request: Request,
    success: bool = True,
    error_message: Optional[str] = None,
    user_id: Optional[str] = None,
    domain: Optional[str] = None,
    details: Optional[dict] = None,
):
    """Log Google auth event to audit log."""
    try:
        audit_service = await get_audit_service()

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

        await audit_service.log(
            event_type,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
            details={
                "auth_provider": "google",
                "domain": domain,
                **(details or {}),
            },
        )
    except Exception as e:
        logger.warning(f"Failed to log audit event: {e}")


def _require_google_auth() -> GoogleAuth:
    """Dependency to require Google auth is enabled."""
    auth = get_google_auth()
    if auth is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "GOOGLE_SSO_DISABLED", "message": "Google SSO is not configured"},
        )
    return auth


@router.get(
    "/providers",
    response_model=AuthProvidersResponse,
    summary="Get available auth providers",
    description="Returns which authentication providers are enabled.",
)
async def get_providers():
    """Get available authentication providers."""
    config = get_google_config()
    return AuthProvidersResponse(
        discord=True,
        google=config.is_enabled,
    )


@router.get(
    "/login",
    response_model=GoogleLoginResponse,
    summary="Initiate Google OAuth login",
    description="Returns the Google OAuth authorization URL.",
)
async def google_login(
    request: Request,
    auth: GoogleAuth = Depends(_require_google_auth),
):
    """Initiate Google OAuth login flow.

    SECURITY: Rate limited to 10/minute per IP.
    """
    state, oauth_url = auth.create_oauth_state()

    await _audit_google_auth_event(
        "auth.google.login_initiated",
        request,
        success=True,
    )

    return GoogleLoginResponse(redirect_url=oauth_url, state=state)


@router.post(
    "/callback",
    response_model=GoogleCallbackResponse,
    summary="Handle Google OAuth callback",
    description="Exchange OAuth code for tokens and create session.",
    responses={
        401: {"description": "Authentication failed"},
        503: {"description": "Google SSO not configured"},
    },
)
async def google_callback(
    request: Request,
    body: GoogleCallbackRequest,
    auth: GoogleAuth = Depends(_require_google_auth),
):
    """Handle Google OAuth callback.

    SECURITY: Rate limited to 5/minute per IP.
    SECURITY: Validates state, PKCE, nonce, domain.
    """
    # SECURITY: Validate and consume state atomically
    state_data = auth.validate_state_atomic(body.state)
    if state_data is None:
        await _audit_google_auth_event(
            "auth.google.invalid_state",
            request,
            success=False,
            error_message="Invalid or expired state",
        )
        # SECURITY: Delay to slow enumeration
        await asyncio.sleep(0.5)
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_FAILED", "message": GENERIC_AUTH_ERROR},
        )

    nonce, code_verifier = state_data

    # Exchange code for tokens (with PKCE)
    try:
        token_response = await auth.exchange_code(body.code, code_verifier)
    except HTTPException:
        await _audit_google_auth_event(
            "auth.google.token_exchange_failed",
            request,
            success=False,
            error_message="Token exchange failed",
        )
        raise

    id_token = token_response.get("id_token")
    if not id_token:
        await _audit_google_auth_event(
            "auth.google.no_id_token",
            request,
            success=False,
            error_message="No ID token in response",
        )
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_FAILED", "message": GENERIC_AUTH_ERROR},
        )

    # SECURITY: Verify ID token (signature, issuer, audience, nonce)
    try:
        claims = await auth.verify_id_token(id_token, nonce)
    except HTTPException:
        await _audit_google_auth_event(
            "auth.google.id_token_invalid",
            request,
            success=False,
            error_message="ID token verification failed",
        )
        raise

    # SECURITY: Verify domain using hd claim
    is_valid, error_msg, domain = auth.verify_domain(claims)
    if not is_valid:
        await _audit_google_auth_event(
            "auth.google.domain_rejected",
            request,
            success=False,
            error_message=error_msg,
            domain=domain,
        )
        # SECURITY: Delay + generic error
        await asyncio.sleep(0.5)
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_FAILED", "message": GENERIC_AUTH_ERROR},
        )

    # Get user info from claims
    google_user_id = claims.get("sub")
    email = claims.get("email", "")
    name = claims.get("name", email.split("@")[0])
    picture = claims.get("picture")

    # Get guilds for this domain
    guild_ids = auth.get_guilds_for_domain(domain)

    # Create JWT
    jwt_token = auth.create_jwt(
        user_id=google_user_id,
        email=email,
        name=name,
        picture=picture,
        domain=domain,
        guild_ids=guild_ids,
    )

    # Audit success
    await _audit_google_auth_event(
        "auth.google.login_success",
        request,
        success=True,
        user_id=f"google_{google_user_id}",
        domain=domain,
        details={
            "email_domain": email.split("@")[1] if "@" in email else None,
            "guild_count": len(guild_ids),
        },
    )

    return GoogleCallbackResponse(
        token=jwt_token,
        user={
            "id": f"google_{google_user_id}",
            "username": name,
            "email": email,
            "avatar": picture,
            "auth_provider": "google",
            "domain": domain,
            "guilds": guild_ids,
        },
    )


@router.get(
    "/redirect",
    summary="Redirect to Google OAuth",
    description="Redirects browser directly to Google OAuth consent screen.",
)
async def google_redirect(
    request: Request,
    auth: GoogleAuth = Depends(_require_google_auth),
):
    """Redirect to Google OAuth consent screen.

    For browser-based login flow.
    """
    state, oauth_url = auth.create_oauth_state()
    return RedirectResponse(url=oauth_url)
