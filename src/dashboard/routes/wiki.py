"""
Wiki routes for dashboard API (ADR-056, ADR-058, ADR-063).

Provides REST endpoints for:
- Browse wiki pages by category
- Full-text search with optional AI synthesis
- Navigation tree
- Recent changes
- Contradiction review queue
- Page synthesis with LLM
"""

import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request
from pydantic import BaseModel, Field

from ..auth import get_current_user
from . import get_wiki_repository, get_summarization_engine
from ...logging.audit_service import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


# -------------------------------------------------------------------------
# Response Models (ADR-058)
# -------------------------------------------------------------------------

class WikiPageSummaryResponse(BaseModel):
    """Summary view of a wiki page."""
    id: str
    path: str
    title: str
    topics: List[str] = []
    updated_at: Optional[str] = None
    inbound_links: int = 0
    confidence: int = 100
    # ADR-064: Filter fields
    created_at: Optional[str] = None
    source_count: int = 0
    has_synthesis: bool = False
    synthesis_model: Optional[str] = None
    average_rating: Optional[float] = None
    rating_count: int = 0


class WikiPageDetailResponse(BaseModel):
    """Full wiki page with content and metadata."""
    id: str
    path: str
    title: str
    content: str  # Raw updates
    topics: List[str] = []
    source_refs: List[str] = []
    inbound_links: int = 0
    outbound_links: int = 0
    confidence: int = 100
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    category: str = ""
    # ADR-063: Synthesis fields
    synthesis: Optional[str] = None
    synthesis_updated_at: Optional[str] = None
    synthesis_source_count: int = 0
    # ADR-064/065: Rating and model tracking
    synthesis_model: Optional[str] = None
    average_rating: Optional[float] = None
    rating_count: int = 0


class WikiFilterFacetsResponse(BaseModel):
    """Facet counts for wiki filtering (ADR-064)."""
    source_count: dict = {}
    rating: dict = {}
    synthesis_model: dict = {}
    has_synthesis: dict = {}


class WikiPagesResponse(BaseModel):
    """List of wiki pages."""
    total: int
    filtered: Optional[int] = None
    pages: List[WikiPageSummaryResponse]
    facets: Optional[WikiFilterFacetsResponse] = None


class WikiTreeNodeResponse(BaseModel):
    """Node in navigation tree."""
    path: str
    title: str
    children: List["WikiTreeNodeResponse"] = []
    page_count: int = 0


class WikiTreeResponse(BaseModel):
    """Navigation tree structure."""
    guild_id: str
    categories: List[WikiTreeNodeResponse]


class WikiSearchResultResponse(BaseModel):
    """Search results with optional synthesis."""
    query: str
    total: int
    pages: List[WikiPageSummaryResponse]
    synthesis: Optional[str] = None
    gaps: List[str] = []


class WikiChangeResponse(BaseModel):
    """A recent change to the wiki."""
    page_path: str
    page_title: str
    operation: str
    changed_at: str
    source_id: Optional[str] = None
    agent_id: Optional[str] = None


class WikiRecentChangesResponse(BaseModel):
    """List of recent changes."""
    changes: List[WikiChangeResponse]


class WikiContradictionResponse(BaseModel):
    """A detected contradiction."""
    id: int
    page_a: str
    page_b: str
    claim_a: str
    claim_b: str
    detected_at: str
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None


class WikiContradictionsResponse(BaseModel):
    """List of contradictions."""
    total: int
    contradictions: List[WikiContradictionResponse]


class ResolveContradictionRequest(BaseModel):
    """Request to resolve a contradiction."""
    resolution: str = Field(..., min_length=1, max_length=2000)


class ErrorResponse(BaseModel):
    """Error response."""
    code: str
    message: str


# Enable forward references
WikiTreeNodeResponse.model_rebuild()


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------

def _check_guild_access(guild_id: str, user: dict):
    """Check user has access to guild."""
    if guild_id not in user.get("guilds", []):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You don't have permission to access this guild"},
        )


def _page_to_summary_response(page) -> WikiPageSummaryResponse:
    """Convert WikiPageSummary to response model."""
    return WikiPageSummaryResponse(
        id=page.id,
        path=page.path,
        title=page.title,
        topics=page.topics,
        updated_at=page.updated_at.isoformat() if page.updated_at else None,
        inbound_links=page.inbound_links,
        confidence=page.confidence,
        # ADR-064: Filter fields
        created_at=page.created_at.isoformat() if getattr(page, 'created_at', None) else None,
        source_count=getattr(page, 'source_count', 0),
        has_synthesis=getattr(page, 'has_synthesis', False),
        synthesis_model=getattr(page, 'synthesis_model', None),
        average_rating=getattr(page, 'average_rating', None),
        rating_count=getattr(page, 'rating_count', 0),
    )


def _page_to_detail_response(page) -> WikiPageDetailResponse:
    """Convert WikiPage to response model."""
    return WikiPageDetailResponse(
        id=page.id,
        path=page.path,
        title=page.title,
        content=page.content,
        topics=page.topics,
        source_refs=page.source_refs,
        inbound_links=page.inbound_links,
        outbound_links=page.outbound_links,
        confidence=page.confidence,
        created_at=page.created_at.isoformat() if page.created_at else None,
        updated_at=page.updated_at.isoformat() if page.updated_at else None,
        category=page.category,
        # ADR-063: Synthesis fields
        synthesis=getattr(page, 'synthesis', None),
        synthesis_updated_at=page.synthesis_updated_at.isoformat() if getattr(page, 'synthesis_updated_at', None) else None,
        synthesis_source_count=getattr(page, 'synthesis_source_count', 0),
        # ADR-064/065: Rating and model tracking
        synthesis_model=getattr(page, 'synthesis_model', None),
        average_rating=page.average_rating if hasattr(page, 'average_rating') else None,
        rating_count=getattr(page, 'rating_count', 0),
    )


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------

@router.get(
    "/guilds/{guild_id}/wiki/pages",
    response_model=WikiPagesResponse,
    summary="List wiki pages",
    description="Get paginated list of wiki pages with filtering and sorting (ADR-064).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def list_pages(
    guild_id: str = Path(..., description="Guild ID"),
    category: Optional[str] = Query(None, description="Filter by category (topics, decisions, processes, experts, questions)"),
    min_sources: Optional[int] = Query(None, ge=0, description="Minimum source count"),
    max_sources: Optional[int] = Query(None, ge=0, description="Maximum source count"),
    created_after: Optional[str] = Query(None, description="Created after date (ISO format)"),
    created_before: Optional[str] = Query(None, description="Created before date (ISO format)"),
    updated_after: Optional[str] = Query(None, description="Updated after date (ISO format)"),
    updated_before: Optional[str] = Query(None, description="Updated before date (ISO format)"),
    min_rating: Optional[float] = Query(None, ge=0, le=5, description="Minimum average rating"),
    has_synthesis: Optional[bool] = Query(None, description="Filter by synthesis presence"),
    synthesis_model: Optional[str] = Query(None, description="Filter by synthesis model (comma-separated)"),
    min_confidence: Optional[int] = Query(None, ge=0, le=100, description="Minimum confidence score"),
    sort_by: str = Query("updated_at", description="Sort field: updated_at, created_at, rating, source_count, confidence, title"),
    sort_order: str = Query("desc", description="Sort order: asc, desc"),
    include_facets: bool = Query(False, description="Include facet counts"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """List wiki pages for a guild with filtering (ADR-064)."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    # Parse date filters
    created_after_dt = datetime.fromisoformat(created_after) if created_after else None
    created_before_dt = datetime.fromisoformat(created_before) if created_before else None
    updated_after_dt = datetime.fromisoformat(updated_after) if updated_after else None
    updated_before_dt = datetime.fromisoformat(updated_before) if updated_before else None

    # Parse synthesis models
    synthesis_models = synthesis_model.split(",") if synthesis_model else None

    pages = await repo.list_pages(
        guild_id,
        category=category,
        min_sources=min_sources,
        max_sources=max_sources,
        created_after=created_after_dt,
        created_before=created_before_dt,
        updated_after=updated_after_dt,
        updated_before=updated_before_dt,
        min_rating=min_rating,
        has_synthesis=has_synthesis,
        synthesis_models=synthesis_models,
        min_confidence=min_confidence,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    total = await repo.count_pages(guild_id, category=category)

    # Get facets if requested
    facets = None
    if include_facets:
        facets_data = await repo.get_filter_facets(guild_id)
        facets = WikiFilterFacetsResponse(
            source_count=facets_data.source_count,
            rating=facets_data.rating,
            synthesis_model=facets_data.synthesis_model,
            has_synthesis=facets_data.has_synthesis,
        )

    return WikiPagesResponse(
        total=total,
        filtered=len(pages),
        pages=[_page_to_summary_response(p) for p in pages],
        facets=facets,
    )


@router.get(
    "/guilds/{guild_id}/wiki/pages/{path:path}",
    response_model=WikiPageDetailResponse,
    summary="Get wiki page",
    description="Get a wiki page by path with full content and metadata.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Page not found"},
    },
)
async def get_page(
    guild_id: str = Path(..., description="Guild ID"),
    path: str = Path(..., description="Page path (e.g., topics/authentication.md)"),
    user: dict = Depends(get_current_user),
):
    """Get a wiki page by path."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    page = await repo.get_page(guild_id, path)
    if not page:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"Page not found: {path}"})

    # Audit log page view
    await audit_log(
        "access.wiki.view",
        user_id=user.get("id"),
        user_name=user.get("username"),
        guild_id=guild_id,
        resource_type="wiki_page",
        resource_id=path,
        resource_name=page.title,
        action="view",
    )

    return _page_to_detail_response(page)


@router.get(
    "/guilds/{guild_id}/wiki/search",
    response_model=WikiSearchResultResponse,
    summary="Search wiki",
    description="Full-text search across wiki pages with optional AI synthesis.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def search_wiki(
    guild_id: str = Path(..., description="Guild ID"),
    q: str = Query(..., min_length=1, description="Search query"),
    synthesize: bool = Query(False, description="Generate AI-synthesized answer"),
    limit: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """Search wiki pages with optional AI synthesis."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    pages = await repo.search_pages(guild_id, q, limit=limit)

    # TODO: Implement AI synthesis when synthesize=True
    synthesis = None
    gaps = []

    return WikiSearchResultResponse(
        query=q,
        total=len(pages),
        pages=[_page_to_summary_response(p) for p in pages],
        synthesis=synthesis,
        gaps=gaps,
    )


@router.get(
    "/guilds/{guild_id}/wiki/tree",
    response_model=WikiTreeResponse,
    summary="Get navigation tree",
    description="Get the wiki navigation tree structure.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def get_tree(
    guild_id: str = Path(..., description="Guild ID"),
    user: dict = Depends(get_current_user),
):
    """Get wiki navigation tree."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    tree = await repo.get_tree(guild_id)
    tree_dict = tree.to_dict()

    return WikiTreeResponse(
        guild_id=guild_id,
        categories=[
            WikiTreeNodeResponse(**cat)
            for cat in tree_dict["categories"]
        ],
    )


@router.get(
    "/guilds/{guild_id}/wiki/recent",
    response_model=WikiRecentChangesResponse,
    summary="Get recent changes",
    description="Get recently updated wiki pages.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def get_recent_changes(
    guild_id: str = Path(..., description="Guild ID"),
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """Get recent changes to the wiki."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    changes = await repo.get_recent_changes(guild_id, days=days, limit=limit)

    return WikiRecentChangesResponse(
        changes=[
            WikiChangeResponse(
                page_path=c.page_path,
                page_title=c.page_title,
                operation=c.operation,
                changed_at=c.changed_at.isoformat(),
                source_id=c.source_id,
                agent_id=c.agent_id,
            )
            for c in changes
        ],
    )


@router.get(
    "/guilds/{guild_id}/wiki/contradictions",
    response_model=WikiContradictionsResponse,
    summary="Get contradictions",
    description="Get unresolved contradictions for review.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def get_contradictions(
    guild_id: str = Path(..., description="Guild ID"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """Get unresolved contradictions."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    contradictions = await repo.get_unresolved_contradictions(guild_id, limit=limit)

    return WikiContradictionsResponse(
        total=len(contradictions),
        contradictions=[
            WikiContradictionResponse(
                id=c.id,
                page_a=c.page_a,
                page_b=c.page_b,
                claim_a=c.claim_a,
                claim_b=c.claim_b,
                detected_at=c.detected_at.isoformat() if c.detected_at else "",
                resolved_at=c.resolved_at.isoformat() if c.resolved_at else None,
                resolution=c.resolution,
            )
            for c in contradictions
        ],
    )


@router.post(
    "/guilds/{guild_id}/wiki/contradictions/{contradiction_id}/resolve",
    response_model=WikiContradictionResponse,
    summary="Resolve contradiction",
    description="Mark a contradiction as resolved with a resolution note.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Contradiction not found"},
    },
)
async def resolve_contradiction(
    guild_id: str = Path(..., description="Guild ID"),
    contradiction_id: int = Path(..., description="Contradiction ID"),
    request: ResolveContradictionRequest = ...,
    user: dict = Depends(get_current_user),
):
    """Resolve a contradiction."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    success = await repo.resolve_contradiction(contradiction_id, request.resolution)
    if not success:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Contradiction not found"})

    # Fetch updated contradiction
    contradictions = await repo.get_unresolved_contradictions(guild_id, limit=1000)
    # Find the resolved one (it won't be in unresolved, so we return a placeholder)
    return WikiContradictionResponse(
        id=contradiction_id,
        page_a="",
        page_b="",
        claim_a="",
        claim_b="",
        detected_at="",
        resolved_at=datetime.utcnow().isoformat(),
        resolution=request.resolution,
    )


@router.get(
    "/guilds/{guild_id}/wiki/orphans",
    response_model=WikiPagesResponse,
    summary="Get orphan pages",
    description="Get pages with no inbound links.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def get_orphan_pages(
    guild_id: str = Path(..., description="Guild ID"),
    user: dict = Depends(get_current_user),
):
    """Get orphan pages (no inbound links)."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    pages = await repo.find_orphan_pages(guild_id)

    return WikiPagesResponse(
        total=len(pages),
        pages=[_page_to_summary_response(p) for p in pages],
    )


# -------------------------------------------------------------------------
# Population Endpoints (ADR-061)
# -------------------------------------------------------------------------

class PopulateRequest(BaseModel):
    """Request to populate wiki from historical summaries."""
    days: int = Field(30, ge=1, le=365, description="Number of days to look back")


class PopulateResponse(BaseModel):
    """Response from populate operation."""
    summaries_processed: int
    pages_created: int
    pages_updated: int
    errors: List[str] = []


class WikiStatsResponse(BaseModel):
    """Wiki statistics."""
    total_pages: int
    total_sources: int
    categories: dict


class ClearWikiResponse(BaseModel):
    """Response from clear wiki operation."""
    pages_deleted: int
    sources_deleted: int


class SynthesizeResponse(BaseModel):
    """Response from synthesize operation (ADR-063)."""
    success: bool
    synthesis_length: int
    source_count: int
    conflicts_found: int
    model_used: Optional[str] = None


class SynthesizeRequest(BaseModel):
    """Request options for synthesis regeneration (ADR-065)."""
    model: str = "auto"
    temperature: float = 0.3
    max_tokens: int = 2000
    focus_areas: List[str] = []
    custom_instructions: Optional[str] = None


class RateSynthesisRequest(BaseModel):
    """Request to rate a wiki synthesis (ADR-065)."""
    rating: int = Field(..., ge=1, le=5, description="Rating from 1-5")
    feedback: Optional[str] = Field(None, max_length=2000, description="Optional feedback text")


class RateSynthesisResponse(BaseModel):
    """Response from rating a synthesis (ADR-065)."""
    success: bool
    average_rating: Optional[float] = None
    rating_count: int = 0


@router.post(
    "/guilds/{guild_id}/wiki/populate",
    response_model=PopulateResponse,
    summary="Populate wiki",
    description="Populate wiki from historical summaries (ADR-061).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def populate_wiki(
    guild_id: str = Path(..., description="Guild ID"),
    request: PopulateRequest = PopulateRequest(),
    user: dict = Depends(get_current_user),
):
    """Populate wiki from last N days of summaries."""
    _check_guild_access(guild_id, user)

    from datetime import timedelta
    from ...data.repositories import get_stored_summary_repository, get_wiki_repository
    from ...wiki.agents import WikiIngestAgent
    from ...utils.time import utc_now_naive

    wiki_repo = await get_wiki_repository()
    if not wiki_repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    stored_repo = await get_stored_summary_repository()
    if not stored_repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Summary repository unavailable"})

    # Get summaries from last N days
    cutoff = utc_now_naive() - timedelta(days=request.days)

    # Fetch summaries using find_by_guild with date filter
    summaries = await stored_repo.find_by_guild(
        guild_id=guild_id,
        created_after=cutoff,
        limit=500,  # Process up to 500 summaries
    )
    logger.info(f"Found {len(summaries)} summaries to process for wiki population")

    # Create ingest agent
    ingest_agent = WikiIngestAgent(wiki_repo)

    # Process each summary
    pages_created = 0
    pages_updated = 0
    errors = []

    for summary in summaries:
        try:
            result = await ingest_agent.ingest_summary(
                guild_id=guild_id,
                summary_id=summary.id,
                summary_text=summary.summary_result.summary_text if summary.summary_result else "",
                key_points=summary.summary_result.key_points if summary.summary_result else [],
                action_items=[a.description for a in (summary.summary_result.action_items if summary.summary_result else [])],
                participants=[p.display_name for p in (summary.summary_result.participants if summary.summary_result else [])],
                technical_terms=[t.term for t in (summary.summary_result.technical_terms if summary.summary_result else [])],
                channel_name=summary.title or "Unknown",
                timestamp=summary.created_at,
            )
            pages_created += len(result.pages_created)
            pages_updated += len(result.pages_updated)
        except Exception as e:
            logger.warning(f"Failed to ingest summary {summary.id}: {e}")
            errors.append(f"Summary {summary.id}: {str(e)}")

    logger.info(f"Wiki population complete: {pages_created} created, {pages_updated} updated, {len(errors)} errors")

    # Audit log
    await audit_log(
        "action.wiki.populate",
        user_id=user.get("id"),
        user_name=user.get("username"),
        guild_id=guild_id,
        resource_type="wiki",
        action="populate",
        details={
            "days": request.days,
            "summaries_processed": len(summaries),
            "pages_created": pages_created,
            "pages_updated": pages_updated,
            "errors": len(errors),
        },
    )

    return PopulateResponse(
        summaries_processed=len(summaries),
        pages_created=pages_created,
        pages_updated=pages_updated,
        errors=errors[:10],  # Limit error list
    )


class WikiSourceResponse(BaseModel):
    """Source document with pages that reference it."""
    source_id: str
    pages: List[WikiPageSummaryResponse]


@router.get(
    "/guilds/{guild_id}/wiki/sources/{source_id}",
    response_model=WikiSourceResponse,
    summary="Get source references",
    description="Get all wiki pages that reference a specific source.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def get_source_references(
    guild_id: str = Path(..., description="Guild ID"),
    source_id: str = Path(..., description="Source ID (e.g., summary-xxx)"),
    user: dict = Depends(get_current_user),
):
    """Get pages that reference a specific source."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    pages = await repo.find_pages_by_source(guild_id, source_id)

    return WikiSourceResponse(
        source_id=source_id,
        pages=[_page_to_summary_response(p) for p in pages],
    )


@router.delete(
    "/guilds/{guild_id}/wiki",
    response_model=ClearWikiResponse,
    summary="Clear wiki",
    description="Delete all wiki pages and sources for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def clear_wiki(
    guild_id: str = Path(..., description="Guild ID"),
    user: dict = Depends(get_current_user),
):
    """Clear all wiki data for a guild."""
    _check_guild_access(guild_id, user)

    # Check for admin role
    guild_roles = user.get("guild_roles", {})
    if guild_roles.get(guild_id) != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Admin access required to clear wiki"},
        )

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    result = await repo.clear_wiki(guild_id)
    logger.info(f"Wiki cleared for guild {guild_id}: {result}")

    # Audit log
    await audit_log(
        "admin.wiki.clear",
        user_id=user.get("id"),
        user_name=user.get("username"),
        guild_id=guild_id,
        resource_type="wiki",
        action="clear",
        details=result,
    )

    return ClearWikiResponse(**result)


@router.get(
    "/guilds/{guild_id}/wiki/stats",
    response_model=WikiStatsResponse,
    summary="Get wiki stats",
    description="Get wiki statistics.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def get_wiki_stats(
    guild_id: str = Path(..., description="Guild ID"),
    user: dict = Depends(get_current_user),
):
    """Get wiki statistics."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    # Count pages by category
    categories = {}
    for cat in ["topics", "decisions", "processes", "experts", "questions"]:
        categories[cat] = await repo.count_pages(guild_id, category=cat)

    total_pages = await repo.count_pages(guild_id)
    total_sources = await repo.count_sources(guild_id)

    return WikiStatsResponse(
        total_pages=total_pages,
        total_sources=total_sources,
        categories=categories,
    )


# -------------------------------------------------------------------------
# Synthesis (ADR-063)
# -------------------------------------------------------------------------

@router.post(
    "/guilds/{guild_id}/wiki/pages/{path:path}/synthesize",
    response_model=SynthesizeResponse,
    summary="Synthesize wiki page",
    description="Generate an AI synthesis of a wiki page's content (ADR-063/065).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Page not found"},
    },
)
async def synthesize_page(
    guild_id: str = Path(..., description="Guild ID"),
    path: str = Path(..., description="Wiki page path"),
    options: Optional[SynthesizeRequest] = None,
    user: dict = Depends(get_current_user),
):
    """Generate synthesis for a wiki page with configurable options (ADR-065)."""
    import os
    from ...wiki.synthesis import synthesize_wiki_page
    from ...wiki.models import SynthesisOptions
    from ...summarization.claude_client import ClaudeClient

    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    # Get the page
    page = await repo.get_page(guild_id, path)
    if not page:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Page not found"})

    # Get Claude client - try engine first, fall back to direct OpenRouter config
    claude_client = None
    engine = get_summarization_engine()
    if engine and hasattr(engine, 'claude_client') and engine.claude_client:
        claude_client = engine.claude_client
        logger.info("Using claude_client from summarization engine")
    else:
        # Direct OpenRouter configuration fallback
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if openrouter_key:
            claude_client = ClaudeClient(
                api_key=openrouter_key,
                base_url='https://openrouter.ai/api',
                max_retries=3,
            )
            logger.info("Created direct OpenRouter client for wiki synthesis")
        else:
            logger.warning("No OpenRouter API key configured - using heuristic synthesis")

    # Build synthesis options from request
    synthesis_options = None
    if options:
        synthesis_options = SynthesisOptions(
            model=options.model,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
            focus_areas=options.focus_areas,
            custom_instructions=options.custom_instructions,
        )

    # Generate synthesis with LLM
    result = await synthesize_wiki_page(
        page_title=page.title,
        page_content=page.content,
        source_refs=page.source_refs,
        claude_client=claude_client,
        options=synthesis_options,
    )

    # Save synthesis to database with model info
    model_used = getattr(result, 'model_used', None) or (options.model if options else None)
    await repo.save_synthesis(
        guild_id=guild_id,
        path=path,
        synthesis=result.synthesis,
        source_count=result.source_count,
        model=model_used,
    )

    # Audit log
    await audit_log(
        "action.wiki.synthesize",
        user_id=user.get("id"),
        user_name=user.get("username"),
        guild_id=guild_id,
        resource_type="wiki_page",
        resource_id=path,
        resource_name=page.title,
        action="synthesize",
        details={
            "source_count": result.source_count,
            "conflicts_found": result.conflicts_found,
            "synthesis_length": len(result.synthesis),
            "used_llm": claude_client is not None,
            "model": model_used,
        },
    )

    logger.info(f"Generated synthesis for {path}: {result.source_count} sources, {result.conflicts_found} conflicts")

    return SynthesizeResponse(
        success=True,
        synthesis_length=len(result.synthesis),
        source_count=result.source_count,
        conflicts_found=result.conflicts_found,
        model_used=model_used,
    )


# -------------------------------------------------------------------------
# Rating (ADR-065)
# -------------------------------------------------------------------------

@router.post(
    "/guilds/{guild_id}/wiki/pages/{path:path}/rate",
    response_model=RateSynthesisResponse,
    summary="Rate wiki synthesis",
    description="Rate a wiki page's synthesis quality (ADR-065).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Page not found"},
    },
)
async def rate_synthesis(
    guild_id: str = Path(..., description="Guild ID"),
    path: str = Path(..., description="Wiki page path"),
    rating_request: RateSynthesisRequest = ...,
    user: dict = Depends(get_current_user),
):
    """Rate a wiki page synthesis (ADR-065)."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    # Check page exists
    page = await repo.get_page(guild_id, path)
    if not page:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Page not found"})

    # Submit rating
    result = await repo.rate_synthesis(
        guild_id=guild_id,
        page_path=path,
        user_id=user.get("id"),
        rating=rating_request.rating,
        feedback=rating_request.feedback,
    )

    # Audit log
    await audit_log(
        "action.wiki.rate",
        user_id=user.get("id"),
        user_name=user.get("username"),
        guild_id=guild_id,
        resource_type="wiki_page",
        resource_id=path,
        resource_name=page.title,
        action="rate",
        details={
            "rating": rating_request.rating,
            "has_feedback": rating_request.feedback is not None,
        },
    )

    return RateSynthesisResponse(
        success=True,
        average_rating=result.get("average_rating"),
        rating_count=result.get("rating_count", 0),
    )


@router.get(
    "/guilds/{guild_id}/wiki/facets",
    response_model=WikiFilterFacetsResponse,
    summary="Get wiki facets",
    description="Get filter facet counts for the wiki (ADR-064).",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def get_wiki_facets(
    guild_id: str = Path(..., description="Guild ID"),
    user: dict = Depends(get_current_user),
):
    """Get wiki filter facets."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    facets = await repo.get_filter_facets(guild_id)

    return WikiFilterFacetsResponse(
        source_count=facets.source_count,
        rating=facets.rating,
        synthesis_model=facets.synthesis_model,
        has_synthesis=facets.has_synthesis,
    )
