"""
Content Coverage API Routes (ADR-072)

Endpoints for viewing coverage and managing backfill.
"""

import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Path, Query
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..services.coverage_service import get_coverage_service, CoverageReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guilds/{guild_id}/coverage", tags=["coverage"])


# =============================================================================
# Pydantic Models
# =============================================================================

class ChannelCoverageResponse(BaseModel):
    """Coverage for a single channel."""
    channel_id: str
    channel_name: Optional[str]
    content_start: Optional[str]
    content_end: Optional[str]
    covered_start: Optional[str]
    covered_end: Optional[str]
    summary_count: int
    coverage_percent: float
    gap_count: int
    covered_days: int
    total_days: int


class CoverageReportResponse(BaseModel):
    """Full coverage report."""
    guild_id: str
    platform: str
    total_coverage_percent: float
    total_gaps: int
    total_channels: int
    covered_channels: int
    total_summaries: int
    earliest_content: Optional[str]
    latest_content: Optional[str]
    computed_at: str
    channels: List[ChannelCoverageResponse]


class CoverageGapResponse(BaseModel):
    """A coverage gap."""
    id: str
    channel_id: str
    channel_name: Optional[str]
    gap_start: str
    gap_end: str
    gap_days: int
    status: str
    priority: int
    summary_id: Optional[str]
    error_message: Optional[str]


class GapsListResponse(BaseModel):
    """List of coverage gaps."""
    gaps: List[CoverageGapResponse]
    total: int


class BackfillRequest(BaseModel):
    """Request to start backfill."""
    channels: Optional[List[str]] = Field(None, description="Channel IDs to backfill, null for all")
    priority_mode: str = Field("oldest_first", description="oldest_first, newest_first, largest_gaps")
    rate_limit: int = Field(10, ge=1, le=100, description="Summaries per hour")


class BackfillStatusResponse(BaseModel):
    """Backfill status."""
    enabled: bool
    paused: bool
    priority_mode: str
    rate_limit: int
    total_gaps: int
    completed_gaps: int
    failed_gaps: int
    progress_percent: float
    last_run_at: Optional[str]
    next_run_at: Optional[str]


class CoverageSummaryResponse(BaseModel):
    """Quick coverage summary."""
    total_coverage_percent: float
    total_gaps: int
    total_channels: int
    covered_channels: int
    has_backfill: bool
    backfill_progress: Optional[float]


# =============================================================================
# Helper Functions
# =============================================================================

def _check_guild_access(guild_id: str, user: dict) -> None:
    """Check if user has access to guild."""
    guilds = user.get("guilds", [])
    if guild_id not in guilds:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You don't have access to this guild"},
        )


def _format_datetime(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


def _report_to_response(report: CoverageReport) -> CoverageReportResponse:
    """Convert internal report to API response."""
    return CoverageReportResponse(
        guild_id=report.guild_id,
        platform=report.platform,
        total_coverage_percent=report.total_coverage_percent,
        total_gaps=report.total_gaps,
        total_channels=report.total_channels,
        covered_channels=report.covered_channels,
        total_summaries=report.total_summaries,
        earliest_content=_format_datetime(report.earliest_content),
        latest_content=_format_datetime(report.latest_content),
        computed_at=_format_datetime(report.computed_at) or datetime.utcnow().isoformat(),
        channels=[
            ChannelCoverageResponse(
                channel_id=c.channel_id,
                channel_name=c.channel_name,
                content_start=_format_datetime(c.content_start),
                content_end=_format_datetime(c.content_end),
                covered_start=_format_datetime(c.covered_start),
                covered_end=_format_datetime(c.covered_end),
                summary_count=c.summary_count,
                coverage_percent=c.coverage_percent,
                gap_count=c.gap_count,
                covered_days=c.covered_days,
                total_days=c.total_days,
            )
            for c in report.channels
        ],
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=CoverageReportResponse)
async def get_coverage(
    guild_id: str = Path(..., description="Guild ID"),
    platform: str = Query("discord", description="Platform"),
    user: dict = Depends(get_current_user),
):
    """Get coverage report for a guild."""
    _check_guild_access(guild_id, user)

    service = get_coverage_service()
    report = await service.get_coverage_report(guild_id, platform)

    if not report:
        # Return empty report
        return CoverageReportResponse(
            guild_id=guild_id,
            platform=platform,
            total_coverage_percent=0,
            total_gaps=0,
            total_channels=0,
            covered_channels=0,
            total_summaries=0,
            earliest_content=None,
            latest_content=None,
            computed_at=datetime.utcnow().isoformat(),
            channels=[],
        )

    return _report_to_response(report)


@router.get("/summary", response_model=CoverageSummaryResponse)
async def get_coverage_summary(
    guild_id: str = Path(..., description="Guild ID"),
    platform: str = Query("discord", description="Platform"),
    user: dict = Depends(get_current_user),
):
    """Get quick coverage summary."""
    _check_guild_access(guild_id, user)

    service = get_coverage_service()
    report = await service.get_coverage_report(guild_id, platform)
    backfill = await service.get_backfill_status(guild_id, platform)

    if not report:
        return CoverageSummaryResponse(
            total_coverage_percent=0,
            total_gaps=0,
            total_channels=0,
            covered_channels=0,
            has_backfill=False,
            backfill_progress=None,
        )

    backfill_progress = None
    if backfill and backfill.total_gaps > 0:
        backfill_progress = round(backfill.completed_gaps / backfill.total_gaps * 100, 1)

    return CoverageSummaryResponse(
        total_coverage_percent=report.total_coverage_percent,
        total_gaps=report.total_gaps,
        total_channels=report.total_channels,
        covered_channels=report.covered_channels,
        has_backfill=backfill is not None and backfill.enabled,
        backfill_progress=backfill_progress,
    )


@router.post("/refresh", response_model=CoverageReportResponse)
async def refresh_coverage(
    guild_id: str = Path(..., description="Guild ID"),
    platform: str = Query("discord", description="Platform"),
    include_inventory: bool = Query(False, description="Fetch fresh inventory from platform"),
    user: dict = Depends(get_current_user),
):
    """Recompute coverage from current summaries."""
    _check_guild_access(guild_id, user)

    service = get_coverage_service()

    inventory = None
    if include_inventory and platform == "discord":
        # Get Discord bot for inventory
        from . import get_discord_bot
        bot = get_discord_bot()
        if bot and bot.client:
            inventory = await service.get_discord_inventory(guild_id, bot.client)

    report = await service.compute_coverage(guild_id, platform, inventory)
    return _report_to_response(report)


@router.get("/gaps", response_model=GapsListResponse)
async def get_gaps(
    guild_id: str = Path(..., description="Guild ID"),
    platform: str = Query("discord", description="Platform"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """Get coverage gaps."""
    _check_guild_access(guild_id, user)

    service = get_coverage_service()
    gaps, total = await service.get_gaps(guild_id, platform, status=status, limit=limit, offset=offset)

    return GapsListResponse(
        gaps=[
            CoverageGapResponse(
                id=g.id,
                channel_id=g.channel_id,
                channel_name=g.channel_name,
                gap_start=g.gap_start.isoformat(),
                gap_end=g.gap_end.isoformat(),
                gap_days=g.gap_days,
                status=g.status,
                priority=g.priority,
                summary_id=g.summary_id,
                error_message=g.error_message,
            )
            for g in gaps
        ],
        total=total,
    )


@router.post("/backfill", response_model=BackfillStatusResponse)
async def start_backfill(
    guild_id: str = Path(..., description="Guild ID"),
    body: BackfillRequest = BackfillRequest(),
    platform: str = Query("discord", description="Platform"),
    user: dict = Depends(get_current_user),
):
    """Start or update backfill schedule."""
    _check_guild_access(guild_id, user)

    service = get_coverage_service()

    # First ensure coverage is computed
    report = await service.get_coverage_report(guild_id, platform)
    if not report or report.total_gaps == 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "NO_GAPS", "message": "No coverage gaps to backfill. Run /refresh first."},
        )

    schedule = await service.start_backfill(
        guild_id=guild_id,
        platform=platform,
        channels=body.channels,
        priority_mode=body.priority_mode,
        rate_limit=body.rate_limit,
    )

    progress = round(schedule.completed_gaps / schedule.total_gaps * 100, 1) if schedule.total_gaps > 0 else 0

    return BackfillStatusResponse(
        enabled=schedule.enabled,
        paused=schedule.paused,
        priority_mode=schedule.priority_mode,
        rate_limit=schedule.rate_limit,
        total_gaps=schedule.total_gaps,
        completed_gaps=schedule.completed_gaps,
        failed_gaps=schedule.failed_gaps,
        progress_percent=progress,
        last_run_at=_format_datetime(schedule.last_run_at),
        next_run_at=_format_datetime(schedule.next_run_at),
    )


@router.get("/backfill", response_model=BackfillStatusResponse)
async def get_backfill_status(
    guild_id: str = Path(..., description="Guild ID"),
    platform: str = Query("discord", description="Platform"),
    user: dict = Depends(get_current_user),
):
    """Get backfill status."""
    _check_guild_access(guild_id, user)

    service = get_coverage_service()
    schedule = await service.get_backfill_status(guild_id, platform)

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "No backfill schedule found"},
        )

    progress = round(schedule.completed_gaps / schedule.total_gaps * 100, 1) if schedule.total_gaps > 0 else 0

    return BackfillStatusResponse(
        enabled=schedule.enabled,
        paused=schedule.paused,
        priority_mode=schedule.priority_mode,
        rate_limit=schedule.rate_limit,
        total_gaps=schedule.total_gaps,
        completed_gaps=schedule.completed_gaps,
        failed_gaps=schedule.failed_gaps,
        progress_percent=progress,
        last_run_at=_format_datetime(schedule.last_run_at),
        next_run_at=_format_datetime(schedule.next_run_at),
    )


@router.post("/backfill/pause")
async def pause_backfill(
    guild_id: str = Path(..., description="Guild ID"),
    platform: str = Query("discord", description="Platform"),
    user: dict = Depends(get_current_user),
):
    """Pause backfill."""
    _check_guild_access(guild_id, user)

    service = get_coverage_service()
    await service.pause_backfill(guild_id, platform)

    return {"success": True, "message": "Backfill paused"}


@router.post("/backfill/resume")
async def resume_backfill(
    guild_id: str = Path(..., description="Guild ID"),
    platform: str = Query("discord", description="Platform"),
    user: dict = Depends(get_current_user),
):
    """Resume backfill."""
    _check_guild_access(guild_id, user)

    service = get_coverage_service()
    await service.resume_backfill(guild_id, platform)

    return {"success": True, "message": "Backfill resumed"}


@router.delete("/backfill")
async def cancel_backfill(
    guild_id: str = Path(..., description="Guild ID"),
    platform: str = Query("discord", description="Platform"),
    user: dict = Depends(get_current_user),
):
    """Cancel backfill."""
    _check_guild_access(guild_id, user)

    service = get_coverage_service()
    await service.cancel_backfill(guild_id, platform)

    return {"success": True, "message": "Backfill cancelled"}
