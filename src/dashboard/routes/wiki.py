"""
Wiki routes for dashboard API (ADR-056, ADR-058).

Provides REST endpoints for:
- Browse wiki pages by category
- Full-text search with optional AI synthesis
- Navigation tree
- Recent changes
- Contradiction review queue
"""

import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field

from ..auth import get_current_user
from . import get_wiki_repository

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


class WikiPageDetailResponse(BaseModel):
    """Full wiki page with content and metadata."""
    id: str
    path: str
    title: str
    content: str
    topics: List[str] = []
    source_refs: List[str] = []
    inbound_links: int = 0
    outbound_links: int = 0
    confidence: int = 100
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    category: str = ""


class WikiPagesResponse(BaseModel):
    """List of wiki pages."""
    total: int
    pages: List[WikiPageSummaryResponse]


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
    )


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------

@router.get(
    "/guilds/{guild_id}/wiki/pages",
    response_model=WikiPagesResponse,
    summary="List wiki pages",
    description="Get paginated list of wiki pages, optionally filtered by category.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
    },
)
async def list_pages(
    guild_id: str = Path(..., description="Guild ID"),
    category: Optional[str] = Query(None, description="Filter by category (topics, decisions, processes, experts, questions)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """List wiki pages for a guild."""
    _check_guild_access(guild_id, user)

    repo = await get_wiki_repository()
    if not repo:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE", "message": "Wiki service unavailable"})

    pages = await repo.list_pages(guild_id, category=category, limit=limit, offset=offset)
    total = await repo.count_pages(guild_id, category=category)

    return WikiPagesResponse(
        total=total,
        pages=[_page_to_summary_response(p) for p in pages],
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

    # Fetch summaries - use search with date filter
    from ...data.base import SearchCriteria
    criteria = SearchCriteria(
        guild_id=guild_id,
        start_time=cutoff,
        limit=500,  # Process up to 500 summaries
    )

    summaries = await stored_repo.search(criteria)
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
                summary_text=summary.summary_result.content if summary.summary_result else "",
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

    return PopulateResponse(
        summaries_processed=len(summaries),
        pages_created=pages_created,
        pages_updated=pages_updated,
        errors=errors[:10],  # Limit error list
    )


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
