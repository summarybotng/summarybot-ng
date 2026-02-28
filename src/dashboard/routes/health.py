"""
Health check endpoints for service resilience (ADR-024).

Provides:
- /health - Full health status with all checks
- /health/live - Simple liveness probe
- /health/ready - Readiness probe for load balancer
"""

import psutil
import logging
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# Track when the service started
_start_time = datetime.utcnow()


@router.get("/health")
async def health_check():
    """
    Full health check with detailed status.

    Returns 200 if healthy, 503 if degraded.
    """
    memory = psutil.virtual_memory()

    checks = {
        "memory_percent": round(memory.percent, 1),
        "memory_available_mb": memory.available // (1024 * 1024),
        "uptime_seconds": int((datetime.utcnow() - _start_time).total_seconds()),
    }

    # Check database
    try:
        from ...data.repositories import get_stored_summary_repository
        repo = await get_stored_summary_repository()
        if repo:
            # Simple query to verify DB is accessible
            await repo.find_by_guild(guild_id="test", limit=1)
            checks["database"] = "ok"
        else:
            checks["database"] = "not_initialized"
    except Exception as e:
        logger.warning(f"Health check database error: {e}")
        checks["database"] = f"error: {type(e).__name__}"

    # Check Discord bot
    try:
        from . import get_discord_bot
        bot = get_discord_bot()
        if bot and bot.is_ready():
            checks["discord"] = "connected"
            checks["discord_guilds"] = len(bot.guilds)
        elif bot:
            checks["discord"] = "connecting"
        else:
            checks["discord"] = "not_configured"
    except Exception as e:
        logger.warning(f"Health check Discord error: {e}")
        checks["discord"] = f"error: {type(e).__name__}"

    # Check summarization engine
    try:
        from . import get_summarization_engine
        engine = get_summarization_engine()
        checks["summarization_engine"] = "available" if engine else "not_configured"
    except Exception as e:
        checks["summarization_engine"] = f"error: {type(e).__name__}"

    # Determine overall health
    is_healthy = (
        checks["memory_percent"] < 90 and
        checks["database"] in ("ok", "not_initialized") and
        checks["discord"] in ("connected", "connecting", "not_configured")
    )

    status_code = 200 if is_healthy else 503
    status = "healthy" if is_healthy else "degraded"

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks,
        }
    )


@router.get("/health/live")
async def liveness():
    """
    Simple liveness probe.

    Returns 200 if the process is running.
    Used by orchestrators to detect crashed processes.
    """
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/ready")
async def readiness():
    """
    Readiness probe.

    Returns 200 if the service can handle requests.
    Returns 503 if critical dependencies are unavailable.
    """
    errors = []

    # Check database is accessible
    try:
        from ...data.repositories import get_stored_summary_repository
        repo = await get_stored_summary_repository()
        if not repo:
            errors.append("database_not_initialized")
    except Exception as e:
        errors.append(f"database_error: {type(e).__name__}")

    # Check memory isn't critically low
    memory = psutil.virtual_memory()
    if memory.percent > 95:
        errors.append(f"memory_critical: {memory.percent}%")

    if errors:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "errors": errors,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
    }
