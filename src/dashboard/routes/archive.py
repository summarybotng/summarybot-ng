"""
Archive management API routes.

Phase 10: Frontend UI - Backend API
"""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/archive", tags=["archive"])


# Request/Response Models

class DateRangeRequest(BaseModel):
    start: date
    end: date


class GenerateRequest(BaseModel):
    source_type: str
    server_id: str
    channel_ids: Optional[List[str]] = None
    date_range: DateRangeRequest
    granularity: str = "daily"
    timezone: str = "UTC"
    skip_existing: bool = True
    regenerate_outdated: bool = False
    regenerate_failed: bool = True
    max_cost_usd: Optional[float] = None
    dry_run: bool = False
    model: str = "anthropic/claude-3-haiku"


class BackfillReportRequest(BaseModel):
    source_type: str
    server_id: str
    channel_ids: Optional[List[str]] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    include_outdated: bool = False
    current_prompt_version: Optional[str] = None


class SourceResponse(BaseModel):
    source_key: str
    source_type: str
    server_id: str
    server_name: str
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    summary_count: int = 0
    date_range: Optional[Dict[str, str]] = None


class ScanResultResponse(BaseModel):
    source_key: str
    total_days: int
    complete: int
    failed: int
    missing: int
    outdated: int
    gaps: List[Dict[str, Any]]
    date_range: Dict[str, Optional[str]]


class JobResponse(BaseModel):
    job_id: str
    source_key: str
    status: str
    progress: Dict[str, Any]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class CostEstimateResponse(BaseModel):
    periods: int
    estimated_cost_usd: float
    estimated_tokens: int
    model: str


# Placeholder for actual implementation
# These would be injected via dependency injection in real app

def get_archive_root() -> Path:
    """Get archive root path."""
    import os
    return Path(os.environ.get("ARCHIVE_ROOT", "./summarybot-archive"))


def get_generator():
    """Get retrospective generator instance."""
    from src.archive.generator import RetrospectiveGenerator
    from src.archive.cost_tracker import CostTracker

    archive_root = get_archive_root()
    cost_tracker = CostTracker(archive_root / "cost-ledger.json")

    return RetrospectiveGenerator(
        archive_root=archive_root,
        cost_tracker=cost_tracker,
    )


def get_scanner():
    """Get archive scanner instance."""
    from src.archive.scanner import ArchiveScanner
    return ArchiveScanner(get_archive_root())


def get_source_registry():
    """Get source registry instance."""
    from src.archive.sources import SourceRegistry
    return SourceRegistry(get_archive_root())


# Routes

@router.get("/sources", response_model=List[SourceResponse])
async def list_sources(
    source_type: Optional[str] = None,
):
    """List all archive sources."""
    registry = get_source_registry()
    registry.discover_sources()

    sources = registry.list_sources()
    if source_type:
        from src.archive.models import SourceType
        try:
            filter_type = SourceType(source_type)
            sources = [s for s in sources if s.source_type == filter_type]
        except ValueError:
            raise HTTPException(400, f"Invalid source type: {source_type}")

    return [
        SourceResponse(
            source_key=s.source_key,
            source_type=s.source_type.value,
            server_id=s.server_id,
            server_name=s.server_name,
            channel_id=s.channel_id,
            channel_name=s.channel_name,
        )
        for s in sources
    ]


@router.get("/sources/{source_key}/scan", response_model=ScanResultResponse)
async def scan_source(
    source_key: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    prompt_version: Optional[str] = None,
):
    """Scan a source for gaps and outdated summaries."""
    registry = get_source_registry()
    registry.discover_sources()

    source = registry.get_source(source_key)
    if not source:
        raise HTTPException(404, f"Source not found: {source_key}")

    scanner = get_scanner()
    result = scanner.scan_source(
        source,
        start_date=start_date,
        end_date=end_date,
        current_prompt_version=prompt_version,
    )

    return ScanResultResponse(**result.to_dict())


@router.post("/backfill-report")
async def get_backfill_report(request: BackfillReportRequest):
    """Analyze archive for backfill opportunities."""
    from src.archive.models import SourceType, ArchiveSource
    from src.archive.backfill import BackfillManager
    from src.archive.cost_tracker import CostTracker

    archive_root = get_archive_root()

    source = ArchiveSource(
        source_type=SourceType(request.source_type),
        server_id=request.server_id,
        server_name=request.server_id,  # Will be updated from manifest
    )

    cost_tracker = CostTracker(archive_root / "cost-ledger.json")
    manager = BackfillManager(archive_root, cost_tracker)

    report = manager.analyze_backfill(
        source,
        start_date=request.start_date,
        end_date=request.end_date,
        include_outdated=request.include_outdated,
        current_prompt_version=request.current_prompt_version,
    )

    return report.to_dict()


@router.post("/generate", response_model=JobResponse)
async def generate_retrospective(request: GenerateRequest):
    """Generate retrospective summaries."""
    from src.archive.models import SourceType, ArchiveSource
    from src.archive.generator import GenerationRequest

    source = ArchiveSource(
        source_type=SourceType(request.source_type),
        server_id=request.server_id,
        server_name=request.server_id,
    )

    gen_request = GenerationRequest(
        source=source,
        start_date=request.date_range.start,
        end_date=request.date_range.end,
        granularity=request.granularity,
        timezone=request.timezone,
        skip_existing=request.skip_existing,
        regenerate_outdated=request.regenerate_outdated,
        regenerate_failed=request.regenerate_failed,
        max_cost_usd=request.max_cost_usd,
        dry_run=request.dry_run,
        model=request.model,
    )

    generator = get_generator()
    job = await generator.create_job(gen_request)

    # Start job in background if not dry run
    if not request.dry_run:
        import asyncio
        asyncio.create_task(generator.run_job(job.job_id))

    return JobResponse(**job.to_dict())


@router.get("/generate/{job_id}", response_model=JobResponse)
async def get_generation_status(job_id: str):
    """Get generation job status."""
    generator = get_generator()
    job = generator.get_job(job_id)

    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")

    return JobResponse(**job.to_dict())


@router.post("/generate/{job_id}/cancel")
async def cancel_generation(job_id: str):
    """Cancel a running generation job."""
    generator = get_generator()

    if not generator.cancel_job(job_id):
        raise HTTPException(404, f"Job not found: {job_id}")

    return {"status": "cancelled", "job_id": job_id}


@router.post("/estimate", response_model=CostEstimateResponse)
async def estimate_generation_cost(request: GenerateRequest):
    """Estimate cost for generation request."""
    from src.archive.models import SourceType, ArchiveSource
    from src.archive.generator import GenerationRequest

    source = ArchiveSource(
        source_type=SourceType(request.source_type),
        server_id=request.server_id,
        server_name=request.server_id,
    )

    gen_request = GenerationRequest(
        source=source,
        start_date=request.date_range.start,
        end_date=request.date_range.end,
        granularity=request.granularity,
        timezone=request.timezone,
        model=request.model,
    )

    generator = get_generator()
    estimate = await generator.estimate_cost(gen_request)

    return CostEstimateResponse(**estimate)


@router.post("/import/whatsapp")
async def import_whatsapp(
    file: UploadFile = File(...),
    group_id: str = Query(...),
    group_name: str = Query(...),
    format: str = Query("whatsapp_txt"),  # "whatsapp_txt" or "reader_bot"
):
    """Import WhatsApp chat export."""
    from src.archive.importers.whatsapp import WhatsAppImporter
    import tempfile

    archive_root = get_archive_root()
    importer = WhatsAppImporter(archive_root)

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        if format == "reader_bot":
            result = await importer.import_reader_bot_json(
                tmp_path, group_id, group_name
            )
        else:
            result = await importer.import_txt_export(
                tmp_path, group_id, group_name
            )

        return result.to_dict()

    finally:
        tmp_path.unlink()


@router.get("/costs")
async def get_cost_report():
    """Get cost report for all sources."""
    from src.archive.cost_tracker import CostTracker

    archive_root = get_archive_root()
    tracker = CostTracker(archive_root / "cost-ledger.json")

    return tracker.get_cost_report()


@router.get("/costs/{source_key}")
async def get_source_costs(source_key: str):
    """Get cost details for a specific source."""
    from src.archive.cost_tracker import CostTracker

    archive_root = get_archive_root()
    tracker = CostTracker(archive_root / "cost-ledger.json")

    cost = tracker.get_source_cost(source_key)
    if not cost:
        raise HTTPException(404, f"No cost data for source: {source_key}")

    return cost.to_dict()


@router.post("/recover/{summary_id}")
async def recover_summary(summary_id: str):
    """Recover a soft-deleted summary."""
    from src.archive.retention import RetentionManager

    archive_root = get_archive_root()
    manager = RetentionManager(archive_root)

    if not manager.recover(summary_id):
        raise HTTPException(404, f"Summary not found or already recovered: {summary_id}")

    return {"status": "recovered", "summary_id": summary_id}


@router.get("/deleted")
async def list_deleted():
    """List soft-deleted summaries."""
    from src.archive.retention import RetentionManager

    archive_root = get_archive_root()
    manager = RetentionManager(archive_root)

    deleted = manager.list_deleted()
    return [d.to_dict() for d in deleted]


@router.post("/sync/{source_key}")
async def sync_source(source_key: str, provider: str = "google_drive"):
    """Sync a source to external storage."""
    from src.archive.sync.google_drive import SyncManager

    archive_root = get_archive_root()
    manager = SyncManager(archive_root)

    results = await manager.sync_source(source_key, provider)

    if not results:
        raise HTTPException(400, f"No sync configured for source: {source_key}")

    return {
        provider: result.to_dict()
        for provider, result in results.items()
    }
