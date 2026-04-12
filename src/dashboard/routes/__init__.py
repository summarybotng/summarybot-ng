"""
Dashboard API route modules.
"""

from typing import Optional

# Service references (set by router.py)
_discord_bot = None
_summarization_engine = None
_task_scheduler = None
_config_manager = None


def set_services(
    discord_bot=None,
    summarization_engine=None,
    task_scheduler=None,
    config_manager=None,
):
    """Set service references for route handlers."""
    global _discord_bot, _summarization_engine, _task_scheduler, _config_manager
    _discord_bot = discord_bot
    _summarization_engine = summarization_engine
    _task_scheduler = task_scheduler
    _config_manager = config_manager


def get_discord_bot():
    """Get Discord bot instance."""
    return _discord_bot


def get_summarization_engine():
    """Get summarization engine."""
    return _summarization_engine


def get_task_scheduler():
    """Get task scheduler."""
    return _task_scheduler


def get_config_manager():
    """Get config manager."""
    return _config_manager


async def get_summary_repository():
    """Get summary repository instance."""
    try:
        from ...data import get_summary_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


async def get_stored_summary_repository():
    """Get stored summary repository instance (ADR-005)."""
    try:
        from ...data.repositories import get_stored_summary_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


async def get_task_repository():
    """Get task repository instance."""
    try:
        from ...data import get_task_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


async def get_webhook_repository():
    """Get webhook repository instance."""
    try:
        from ...data import get_webhook_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


async def get_feed_repository():
    """Get feed repository instance."""
    try:
        from ...data import get_feed_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


async def get_summary_job_repository():
    """Get summary job repository instance (ADR-013)."""
    try:
        from ...data.repositories import get_summary_job_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


async def get_config_repository():
    """Get config repository instance (database-backed)."""
    try:
        from ...data import get_config_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


async def get_audit_repository():
    """Get audit repository instance (ADR-045)."""
    try:
        from ...data import get_audit_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


# Import routers
from .auth import router as auth_router
from .guilds import router as guilds_router
from .summaries import router as summaries_router
from .schedules import router as schedules_router
from .webhooks import router as webhooks_router
from .events import router as events_router
from .feeds import router as feeds_router
from .errors import router as errors_router
from .archive import router as archive_router
from .prompts import router as prompts_router
from .push_templates import router as push_templates_router
from .health import router as health_router  # ADR-024
from .prompt_templates import router as prompt_templates_router  # ADR-034
from .audit import router as audit_router  # ADR-045

__all__ = [
    "auth_router",
    "guilds_router",
    "summaries_router",
    "schedules_router",
    "webhooks_router",
    "events_router",
    "feeds_router",
    "errors_router",
    "archive_router",
    "prompts_router",
    "push_templates_router",
    "health_router",
    "prompt_templates_router",
    "audit_router",
    "set_services",
    "get_discord_bot",
    "get_summarization_engine",
    "get_task_scheduler",
    "get_config_manager",
    "get_config_repository",
]
