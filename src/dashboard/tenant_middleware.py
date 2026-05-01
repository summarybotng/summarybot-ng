"""
ADR-079: Tenant Middleware for subdomain multi-tenancy.

Resolves tenant context from request hostname and injects into request state.
"""

import logging
import re
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..models.tenant import Tenant

logger = logging.getLogger(__name__)

# Patterns for extracting subdomain
# Match *.summarybot.app or *.localhost (for local development)
SUBDOMAIN_PATTERNS = [
    re.compile(r"^([a-z0-9-]+)\.summarybot\.app$", re.IGNORECASE),
    re.compile(r"^([a-z0-9-]+)\.localhost(:\d+)?$", re.IGNORECASE),
    re.compile(r"^([a-z0-9-]+)\.127\.0\.0\.1(:\d+)?$", re.IGNORECASE),
]

# Main app domains (no tenant context)
MAIN_DOMAINS = [
    "summarybot.app",
    "www.summarybot.app",
    "app.summarybot.app",
    "localhost",
    "127.0.0.1",
]


def extract_subdomain(host: str) -> Optional[str]:
    """Extract subdomain from hostname.

    Args:
        host: Hostname (e.g., "acme.summarybot.app", "acme.localhost:5000")

    Returns:
        Subdomain if found, None otherwise
    """
    # Strip port if present
    hostname = host.split(":")[0].lower()

    # Check if this is a main domain (no tenant)
    for main_domain in MAIN_DOMAINS:
        if hostname == main_domain or hostname == f"www.{main_domain}":
            return None

    # Try to extract subdomain
    for pattern in SUBDOMAIN_PATTERNS:
        match = pattern.match(host.lower())
        if match:
            subdomain = match.group(1)
            # Don't treat 'www', 'app', 'api' as tenant subdomains
            if subdomain not in ("www", "app", "api"):
                return subdomain

    return None


class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware to resolve tenant context from hostname.

    Injects tenant into request.state for route handlers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get hostname from request
        host = request.headers.get("host", "localhost")

        # Initialize tenant state as None
        request.state.tenant = None
        request.state.tenant_id = None

        # Try to resolve tenant
        tenant = await self._resolve_tenant(host)

        if tenant:
            request.state.tenant = tenant
            request.state.tenant_id = tenant.id
            logger.debug(f"Resolved tenant '{tenant.slug}' for host '{host}'")

        return await call_next(request)

    async def _resolve_tenant(self, host: str) -> Optional[Tenant]:
        """Resolve tenant from hostname.

        Resolution order:
        1. Custom domain (most specific)
        2. Subdomain on *.summarybot.app or *.localhost

        Args:
            host: Request hostname

        Returns:
            Tenant if found, None otherwise
        """
        from ..data.repositories import get_tenant_repository

        try:
            repo = await get_tenant_repository()

            # Strip port for domain comparison
            hostname = host.split(":")[0].lower()

            # 1. Check custom domain first (most specific)
            if "." in hostname and not any(
                hostname.endswith(d) for d in ["summarybot.app", "localhost", "127.0.0.1"]
            ):
                tenant = await repo.get_tenant_by_custom_domain(hostname)
                if tenant:
                    return tenant

            # 2. Check subdomain
            subdomain = extract_subdomain(host)
            if subdomain:
                tenant = await repo.get_tenant_by_subdomain(subdomain)
                if tenant:
                    return tenant

            return None

        except RuntimeError:
            # Repositories not initialized yet
            return None
        except Exception as e:
            logger.warning(f"Error resolving tenant for host '{host}': {e}")
            return None


def get_current_tenant(request: Request) -> Optional[Tenant]:
    """Get the current tenant from request state.

    Helper for route handlers.

    Args:
        request: FastAPI request

    Returns:
        Tenant if resolved, None otherwise
    """
    return getattr(request.state, "tenant", None)


def get_current_tenant_id(request: Request) -> Optional[str]:
    """Get the current tenant ID from request state.

    Helper for route handlers.

    Args:
        request: FastAPI request

    Returns:
        Tenant ID if resolved, None otherwise
    """
    return getattr(request.state, "tenant_id", None)


def setup_tenant_middleware(app):
    """Add tenant middleware to FastAPI app.

    Args:
        app: FastAPI application instance
    """
    app.add_middleware(TenantMiddleware)
    logger.info("ADR-079: Tenant middleware configured")
