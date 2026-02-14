"""
Main dashboard API router.
"""

import os
import logging
from typing import Optional
from fastapi import APIRouter, FastAPI
from cryptography.fernet import Fernet

from .auth import DashboardAuth, set_auth_instance
from .routes import auth_router, guilds_router, summaries_router, schedules_router, webhooks_router, events_router, feeds_router, errors_router, archive_router

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
    jwt_secret = os.environ.get("DASHBOARD_JWT_SECRET", os.environ.get("JWT_SECRET", "change-in-production"))
    encryption_key = os.environ.get("DASHBOARD_ENCRYPTION_KEY")

    if not client_id or not client_secret:
        logger.warning(
            "DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET not set. "
            "Dashboard OAuth will not work."
        )
        client_id = client_id or "not-configured"
        client_secret = client_secret or "not-configured"

    # Create encryption key if not provided
    if encryption_key:
        encryption_key = encryption_key.encode()
    else:
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
    router = create_dashboard_router(
        discord_bot=discord_bot,
        summarization_engine=summarization_engine,
        task_scheduler=task_scheduler,
        config_manager=config_manager,
    )
    app.include_router(router)
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
