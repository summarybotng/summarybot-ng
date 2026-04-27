"""
Main dashboard API router.
"""

import os
import logging
from typing import Optional
from fastapi import APIRouter, FastAPI
from cryptography.fernet import Fernet

from .auth import DashboardAuth, set_auth_instance
from .routes import auth_router, guilds_router, summaries_router, schedules_router, webhooks_router, events_router, feeds_router, errors_router, archive_router, prompts_router, push_templates_router, health_router, prompt_templates_router, audit_router, google_auth_router, google_admin_groups_router, slack_router, wiki_router, issues_router, coverage_router

logger = logging.getLogger(__name__)


def create_dashboard_router(
    discord_bot=None,
    summarization_engine=None,
    task_scheduler=None,
    config_manager=None,
) -> APIRouter:
    """Create the dashboard API router.

    Args:
        discord_bot: Discord bot instance for guild/channel info
        summarization_engine: Summarization engine for generating summaries
        task_scheduler: Task scheduler for scheduled summaries
        config_manager: Configuration manager

    Returns:
        FastAPI router with all dashboard endpoints
    """
    # Get configuration from environment
    client_id = os.environ.get("DISCORD_CLIENT_ID")
    client_secret = os.environ.get("DISCORD_CLIENT_SECRET")
    redirect_uri = os.environ.get("DISCORD_REDIRECT_URI", "http://localhost:3000/callback")
    jwt_secret = os.environ.get("DASHBOARD_JWT_SECRET", os.environ.get("JWT_SECRET", ""))
    encryption_key = os.environ.get("DASHBOARD_ENCRYPTION_KEY")

    # SEC-001: Validate JWT secret
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    insecure_secrets = {
        "change-in-production", "change-this-in-production",
        "your-secret-key-change-in-production", "secret", "changeme", ""
    }
    if jwt_secret.lower() in insecure_secrets:
        if environment == "production":
            raise RuntimeError(
                "DASHBOARD_JWT_SECRET is required in production. "
                "Please set a strong, random secret in your environment."
            )
        else:
            logger.warning(
                "DASHBOARD_JWT_SECRET not set or using insecure default. "
                "This is acceptable for development but MUST be changed for production."
            )
            # Generate a temporary secret for development
            import secrets as secrets_module
            jwt_secret = secrets_module.token_urlsafe(32)

    if not client_id or not client_secret:
        logger.warning(
            "DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET not set. "
            "Dashboard OAuth will not work."
        )
        client_id = client_id or "not-configured"
        client_secret = client_secret or "not-configured"

    # DATA-001: Validate encryption key in production
    if encryption_key:
        encryption_key = encryption_key.encode()
    else:
        if environment == "production":
            raise RuntimeError(
                "DASHBOARD_ENCRYPTION_KEY is required in production. "
                "Please set a Fernet-compatible key (44 chars, base64)."
            )
        encryption_key = Fernet.generate_key()
        logger.warning("No DASHBOARD_ENCRYPTION_KEY set, using ephemeral key")

    # Initialize auth
    auth = DashboardAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        jwt_secret=jwt_secret,
        encryption_key=encryption_key,
    )
    set_auth_instance(auth)
    logger.info(f"DashboardAuth initialized with JWT secret prefix: {jwt_secret[:8]}...")

    # Store service references for routes
    from . import routes
    routes.set_services(
        discord_bot=discord_bot,
        summarization_engine=summarization_engine,
        task_scheduler=task_scheduler,
        config_manager=config_manager,
    )

    # Create main router
    router = APIRouter(prefix="/api/v1")

    # Include sub-routers
    router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
    router.include_router(google_auth_router, prefix="/auth", tags=["Google Authentication"])  # ADR-049
    # Register errors_router before guilds_router to avoid route conflicts
    # (guilds_router's /{guild_id} pattern would otherwise match /guilds/{id}/errors/...)
    router.include_router(errors_router, tags=["Errors"])
    router.include_router(guilds_router, prefix="/guilds", tags=["Guilds"])
    router.include_router(summaries_router, tags=["Summaries"])
    router.include_router(schedules_router, tags=["Schedules"])
    router.include_router(webhooks_router, tags=["Webhooks"])
    router.include_router(events_router, tags=["Events"])
    router.include_router(feeds_router, tags=["Feeds"])
    router.include_router(archive_router, tags=["Archive"])
    router.include_router(prompts_router, tags=["Prompts"])
    router.include_router(push_templates_router, tags=["Push Templates"])
    router.include_router(prompt_templates_router, tags=["Prompt Templates"])  # ADR-034
    router.include_router(audit_router, tags=["Audit"])  # ADR-045
    router.include_router(slack_router, tags=["Slack"])  # ADR-043
    router.include_router(google_admin_groups_router, tags=["Google Admin Groups"])  # ADR-050
    router.include_router(wiki_router, tags=["Wiki"])  # ADR-056
    router.include_router(issues_router, tags=["Issues"])  # ADR-070
    router.include_router(coverage_router, tags=["Coverage"])  # ADR-072

    return router


def setup_dashboard_api(
    app: FastAPI,
    discord_bot=None,
    summarization_engine=None,
    task_scheduler=None,
    config_manager=None,
):
    """Setup dashboard API on existing FastAPI app.

    Args:
        app: FastAPI application
        discord_bot: Discord bot instance
        summarization_engine: Summarization engine
        task_scheduler: Task scheduler
        config_manager: Configuration manager
    """
    # ADR-031: Add error logging middleware
    from .middleware import setup_error_logging_middleware
    setup_error_logging_middleware(app)

    router = create_dashboard_router(
        discord_bot=discord_bot,
        summarization_engine=summarization_engine,
        task_scheduler=task_scheduler,
        config_manager=config_manager,
    )
    app.include_router(router)

    # ADR-024: Health check endpoints at root level (not under /api/v1)
    app.include_router(health_router)
    logger.info("Dashboard API routes added to application")

    # Initialize error tracker on startup
    @app.on_event("startup")
    async def init_error_tracker():
        try:
            from ..logging.error_tracker import initialize_error_tracker
            await initialize_error_tracker()
            logger.info("Error tracker initialized for dashboard")
        except Exception as e:
            logger.warning(f"Failed to initialize error tracker: {e}")

    # Initialize audit service on startup (ADR-045)
    @app.on_event("startup")
    async def init_audit_service():
        try:
            from ..logging.audit_service import get_audit_service
            await get_audit_service()
            logger.info("Audit service initialized for dashboard")
        except Exception as e:
            logger.warning(f"Failed to initialize audit service: {e}")

    # Initialize Google SSO on startup (ADR-049)
    @app.on_event("startup")
    async def init_google_auth():
        try:
            from .google_auth import initialize_google_auth
            initialize_google_auth()
        except ValueError as e:
            logger.error(f"Google SSO configuration error: {e}")
        except Exception as e:
            logger.warning(f"Google SSO initialization failed: {e}")

    # Initialize Slack OAuth on startup (ADR-043)
    @app.on_event("startup")
    async def init_slack_auth():
        try:
            from ..slack.auth import initialize_slack_auth
            slack_auth = initialize_slack_auth()
            if slack_auth:
                logger.info("Slack OAuth initialized successfully")
            else:
                logger.info("Slack OAuth not configured (missing SLACK_CLIENT_ID/SECRET/REDIRECT_URI)")
        except Exception as e:
            logger.warning(f"Slack OAuth initialization failed: {e}")

    # Stop audit service on shutdown (ADR-045)
    @app.on_event("shutdown")
    async def stop_audit_service():
        try:
            from ..logging.audit_service import _audit_service
            if _audit_service:
                await _audit_service.stop()
                logger.info("Audit service stopped")
        except Exception as e:
            logger.warning(f"Failed to stop audit service: {e}")
