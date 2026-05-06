"""
RuVector API routes (ADR-057 Phase 2).

Provides REST endpoints for:
- Semantic search across knowledge units
- View rendering (topic, daily, weekly)
- Knowledge graph statistics
- Edge exploration
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field

from ..auth import get_current_user
from . import get_wiki_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ruvector", tags=["ruvector"])


# -------------------------------------------------------------------------
# Response Models
# -------------------------------------------------------------------------

class KnowledgeUnitResponse(BaseModel):
    """A knowledge unit from semantic search."""
    id: str
    content: str
    unit_type: str
    score: float = 0.0
    source_id: str
    source_channel: Optional[str] = None
    source_date: Optional[str] = None


class SemanticSearchResponse(BaseModel):
    """Response from semantic search."""
    query: str
    guild_id: str
    total: int
    units: List[KnowledgeUnitResponse]
    search_time_ms: int = 0


class EdgeResponse(BaseModel):
    """A relationship edge between units."""
    from_unit_id: str
    to_unit_id: str
    edge_type: str
    weight: float


class RelatedUnitsResponse(BaseModel):
    """Related units for a given unit."""
    unit_id: str
    related: List[KnowledgeUnitResponse]
    edges: List[EdgeResponse]


class RenderedViewResponse(BaseModel):
    """A rendered wiki view."""
    title: str
    content: str
    view_type: str
    source_count: int
    generated_at: str
    cache_key: Optional[str] = None


class RuVectorStatsResponse(BaseModel):
    """Statistics for RuVector knowledge store."""
    guild_id: str
    total_units: int
    units_by_type: dict
    total_edges: int
    edges_by_type: dict
    total_signals: int
    units_with_embeddings: int


# -------------------------------------------------------------------------
# Search Endpoints
# -------------------------------------------------------------------------

@router.get(
    "/guilds/{guild_id}/search",
    response_model=SemanticSearchResponse,
    summary="Semantic search",
    description="ADR-057: Search knowledge units using semantic similarity",
)
async def semantic_search(
    guild_id: str = Path(..., description="Guild ID"),
    q: str = Query(..., description="Search query", min_length=1),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
    threshold: float = Query(0.6, ge=0.0, le=1.0, description="Minimum similarity"),
    unit_types: Optional[str] = Query(None, description="Comma-separated unit types filter"),
    channel: Optional[str] = Query(None, description="Filter by channel"),
    user: dict = Depends(get_current_user),
):
    """
    Perform semantic search across knowledge units.

    Returns units ranked by embedding similarity to the query.
    """
    import time
    start_time = time.time()

    try:
        # Get vector store
        vector_store = await _get_vector_store(guild_id)

        # Parse unit types filter
        type_filter = None
        if unit_types:
            from src.wiki.ruvector.models import KnowledgeUnitType
            type_filter = []
            for t in unit_types.split(","):
                try:
                    type_filter.append(KnowledgeUnitType(t.strip()))
                except ValueError:
                    pass

        # Perform search
        results = await vector_store.search(
            query=q,
            guild_id=guild_id,
            limit=limit,
            threshold=threshold,
            unit_types=type_filter,
            channel=channel,
        )

        search_time = int((time.time() - start_time) * 1000)

        return SemanticSearchResponse(
            query=q,
            guild_id=guild_id,
            total=len(results),
            units=[
                KnowledgeUnitResponse(
                    id=r.unit_id,
                    content=r.content,
                    unit_type=r.unit_type.value,
                    score=r.score,
                    source_id=r.source_id,
                    source_channel=r.source_channel,
                    source_date=r.source_date.isoformat() if r.source_date else None,
                )
                for r in results
            ],
            search_time_ms=search_time,
        )

    except Exception as e:
        logger.exception(f"Semantic search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/guilds/{guild_id}/units/{unit_id}/related",
    response_model=RelatedUnitsResponse,
    summary="Find related units",
    description="ADR-057: Find units related to a specific unit",
)
async def get_related_units(
    guild_id: str = Path(..., description="Guild ID"),
    unit_id: str = Path(..., description="Unit ID"),
    limit: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """
    Find knowledge units related to a given unit.

    Returns similar units and the edges connecting them.
    """
    try:
        vector_store = await _get_vector_store(guild_id)

        # Get similar units
        similar = await vector_store.find_similar(
            unit_id=unit_id,
            limit=limit,
            threshold=0.6,
        )

        # Get edges from this unit
        edges_from = await vector_store.get_edges_from(unit_id)

        return RelatedUnitsResponse(
            unit_id=unit_id,
            related=[
                KnowledgeUnitResponse(
                    id=r.unit_id,
                    content=r.content,
                    unit_type=r.unit_type.value,
                    score=r.score,
                    source_id=r.source_id,
                    source_channel=r.source_channel,
                    source_date=r.source_date.isoformat() if r.source_date else None,
                )
                for r in similar
            ],
            edges=[
                EdgeResponse(
                    from_unit_id=e.from_unit_id,
                    to_unit_id=e.to_unit_id,
                    edge_type=e.edge_type.value,
                    weight=e.weight,
                )
                for e in edges_from
            ],
        )

    except Exception as e:
        logger.exception(f"Get related units failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# View Rendering Endpoints
# -------------------------------------------------------------------------

@router.get(
    "/guilds/{guild_id}/views/topic/{topic}",
    response_model=RenderedViewResponse,
    summary="Render topic page",
    description="ADR-057/087: Generate a topic page from knowledge units",
)
async def render_topic_view(
    guild_id: str = Path(..., description="Guild ID"),
    topic: str = Path(..., description="Topic name"),
    max_units: int = Query(30, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """
    Render a topic page from semantically related knowledge units.
    """
    try:
        renderer = await _get_view_renderer(guild_id)

        view = await renderer.render_topic_page(
            guild_id=guild_id,
            topic=topic,
            max_units=max_units,
        )

        return RenderedViewResponse(
            title=view.title,
            content=view.content,
            view_type=view.view_type,
            source_count=len(view.source_units),
            generated_at=view.generated_at.isoformat(),
            cache_key=view.cache_key,
        )

    except Exception as e:
        logger.exception(f"Render topic view failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/guilds/{guild_id}/views/daily/{date}",
    response_model=RenderedViewResponse,
    summary="Render daily digest",
    description="ADR-057/087: Generate daily cross-channel digest",
)
async def render_daily_view(
    guild_id: str = Path(..., description="Guild ID"),
    date: str = Path(..., description="Date (YYYY-MM-DD)"),
    user: dict = Depends(get_current_user),
):
    """
    Render a daily cross-channel digest for a specific date.
    """
    try:
        # Parse date
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        renderer = await _get_view_renderer(guild_id)

        view = await renderer.render_daily_digest(
            guild_id=guild_id,
            date=target_date,
        )

        return RenderedViewResponse(
            title=view.title,
            content=view.content,
            view_type=view.view_type,
            source_count=len(view.source_units),
            generated_at=view.generated_at.isoformat(),
            cache_key=view.cache_key,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Render daily view failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/guilds/{guild_id}/views/weekly/{week_start}",
    response_model=RenderedViewResponse,
    summary="Render weekly rollup",
    description="ADR-057/087: Generate weekly theme rollup",
)
async def render_weekly_view(
    guild_id: str = Path(..., description="Guild ID"),
    week_start: str = Path(..., description="Week start date (YYYY-MM-DD, Monday)"),
    user: dict = Depends(get_current_user),
):
    """
    Render a weekly rollup with theme clustering.
    """
    try:
        # Parse date
        try:
            start_date = datetime.strptime(week_start, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        renderer = await _get_view_renderer(guild_id)

        view = await renderer.render_weekly_rollup(
            guild_id=guild_id,
            week_start=start_date,
        )

        return RenderedViewResponse(
            title=view.title,
            content=view.content,
            view_type=view.view_type,
            source_count=len(view.source_units),
            generated_at=view.generated_at.isoformat(),
            cache_key=view.cache_key,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Render weekly view failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/guilds/{guild_id}/views/decisions",
    response_model=RenderedViewResponse,
    summary="Render decisions log",
    description="ADR-057: Generate decisions log view",
)
async def render_decisions_view(
    guild_id: str = Path(..., description="Guild ID"),
    limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = Query(None, description="Filter by channel"),
    user: dict = Depends(get_current_user),
):
    """
    Render a log of decisions.
    """
    try:
        renderer = await _get_view_renderer(guild_id)

        view = await renderer.render_decisions_log(
            guild_id=guild_id,
            limit=limit,
            channel=channel,
        )

        return RenderedViewResponse(
            title=view.title,
            content=view.content,
            view_type=view.view_type,
            source_count=len(view.source_units),
            generated_at=view.generated_at.isoformat(),
            cache_key=view.cache_key,
        )

    except Exception as e:
        logger.exception(f"Render decisions view failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Statistics Endpoints
# -------------------------------------------------------------------------

@router.get(
    "/guilds/{guild_id}/stats",
    response_model=RuVectorStatsResponse,
    summary="Get RuVector statistics",
    description="ADR-057: Get knowledge store statistics for a guild",
)
async def get_stats(
    guild_id: str = Path(..., description="Guild ID"),
    user: dict = Depends(get_current_user),
):
    """
    Get statistics about the RuVector knowledge store.
    """
    try:
        vector_store = await _get_vector_store(guild_id)
        stats = await vector_store.get_stats(guild_id)

        return RuVectorStatsResponse(
            guild_id=guild_id,
            total_units=stats.get("total_units", 0),
            units_by_type=stats.get("units_by_type", {}),
            total_edges=stats.get("total_edges", 0),
            edges_by_type=stats.get("edges_by_type", {}),
            total_signals=stats.get("total_signals", 0),
            units_with_embeddings=stats.get("units_with_embeddings", 0),
        )

    except Exception as e:
        logger.exception(f"Get stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------

async def _get_vector_store(guild_id: str):
    """Get or create vector store for a guild."""
    from src.wiki.ruvector import VectorStore, EmbeddingService
    from src.data.sqlite.connection import SQLiteConnection

    # Get database connection
    # In production, this would be injected via dependency
    connection = SQLiteConnection.get_instance()

    embedding_service = EmbeddingService()
    return VectorStore(connection=connection, embedding_service=embedding_service)


async def _get_view_renderer(guild_id: str):
    """Get view renderer for a guild."""
    from src.wiki.ruvector import VectorStore
    from src.wiki.ruvector.view_renderer import WikiViewRenderer

    vector_store = await _get_vector_store(guild_id)
    return WikiViewRenderer(vector_store=vector_store)


# -------------------------------------------------------------------------
# Comparison Endpoints (ADR-057 Phase 4)
# -------------------------------------------------------------------------

class ComparisonViewResponse(BaseModel):
    """Comparison of RuVector vs existing wiki synthesis."""
    topic: str
    guild_id: str
    ruvector_view: Optional[RenderedViewResponse] = None
    existing_synthesis: Optional[str] = None
    existing_content: Optional[str] = None
    existing_path: Optional[str] = None
    ruvector_unit_count: int = 0
    existing_source_count: int = 0


@router.get(
    "/guilds/{guild_id}/compare/topic/{topic}",
    response_model=ComparisonViewResponse,
    summary="Compare topic renderings",
    description="ADR-057 Phase 4: Compare RuVector rendering vs existing wiki synthesis",
)
async def compare_topic_views(
    guild_id: str = Path(..., description="Guild ID"),
    topic: str = Path(..., description="Topic name"),
    user: dict = Depends(get_current_user),
):
    """
    Compare RuVector topic rendering with existing wiki synthesis.

    Useful for validating RuVector produces equivalent or better content.
    """
    from . import get_wiki_repository

    response = ComparisonViewResponse(topic=topic, guild_id=guild_id)

    # Get RuVector view
    try:
        renderer = await _get_view_renderer(guild_id)
        view = await renderer.render_topic_page(
            guild_id=guild_id,
            topic=topic,
            max_units=30,
        )
        response.ruvector_view = RenderedViewResponse(
            title=view.title,
            content=view.content,
            view_type=view.view_type,
            source_count=len(view.source_units),
            generated_at=view.generated_at.isoformat(),
            cache_key=view.cache_key,
        )
        response.ruvector_unit_count = len(view.source_units)
    except Exception as e:
        logger.warning(f"RuVector view failed: {e}")

    # Get existing wiki synthesis
    try:
        wiki_repo = await get_wiki_repository()
        if wiki_repo:
            # Try to find a matching topic page
            import re
            slug = re.sub(r'[^\w\s-]', '', topic.lower().strip())
            slug = re.sub(r'[-\s]+', '-', slug)[:50]
            path = f"topics/{slug}.md"

            page = await wiki_repo.get_page(guild_id, path)
            if page:
                response.existing_synthesis = getattr(page, 'synthesis', None)
                response.existing_content = page.content
                response.existing_path = path
                response.existing_source_count = len(page.source_refs) if page.source_refs else 0
    except Exception as e:
        logger.warning(f"Existing wiki lookup failed: {e}")

    return response


class ComparisonDailyResponse(BaseModel):
    """Comparison of daily views."""
    date: str
    guild_id: str
    ruvector_view: Optional[RenderedViewResponse] = None
    existing_summaries: List[dict] = []
    ruvector_unit_count: int = 0


@router.get(
    "/guilds/{guild_id}/compare/daily/{date}",
    response_model=ComparisonDailyResponse,
    summary="Compare daily views",
    description="ADR-057 Phase 4: Compare RuVector daily digest vs existing summaries",
)
async def compare_daily_views(
    guild_id: str = Path(..., description="Guild ID"),
    date: str = Path(..., description="Date (YYYY-MM-DD)"),
    user: dict = Depends(get_current_user),
):
    """
    Compare RuVector daily digest with existing summaries for that date.
    """
    from ...data.repositories import get_stored_summary_repository

    # Parse date
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    response = ComparisonDailyResponse(date=date, guild_id=guild_id)

    # Get RuVector view
    try:
        renderer = await _get_view_renderer(guild_id)
        view = await renderer.render_daily_digest(
            guild_id=guild_id,
            date=target_date,
        )
        response.ruvector_view = RenderedViewResponse(
            title=view.title,
            content=view.content,
            view_type=view.view_type,
            source_count=len(view.source_units),
            generated_at=view.generated_at.isoformat(),
            cache_key=view.cache_key,
        )
        response.ruvector_unit_count = len(view.source_units)
    except Exception as e:
        logger.warning(f"RuVector daily view failed: {e}")

    # Get existing summaries for that date
    try:
        stored_repo = await get_stored_summary_repository()
        if stored_repo:
            start_of_day = target_date.replace(hour=0, minute=0, second=0)
            end_of_day = target_date.replace(hour=23, minute=59, second=59)

            summaries = await stored_repo.find_by_guild(
                guild_id=guild_id,
                created_after=start_of_day,
                created_before=end_of_day,
                limit=50,
            )

            response.existing_summaries = [
                {
                    "id": s.id,
                    "title": s.title,
                    "summary_text": s.summary_result.summary_text[:500] if s.summary_result else "",
                    "channel": s.title,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in summaries
            ]
    except Exception as e:
        logger.warning(f"Existing summaries lookup failed: {e}")

    return response


# -------------------------------------------------------------------------
# Backfill Endpoints (ADR-057 Phase 3/4)
# -------------------------------------------------------------------------

class BackfillRequest(BaseModel):
    """Request to start RuVector backfill."""
    include_sources: bool = True
    include_pages: bool = True
    rebuild_edges: bool = True


class BackfillStatusResponse(BaseModel):
    """Status of RuVector data for a guild."""
    guild_id: str
    knowledge_units: int
    wiki_sources: int
    edges: int
    estimated_coverage: float


class BackfillResultResponse(BaseModel):
    """Result of backfill operation."""
    guild_id: str
    sources_processed: int
    pages_processed: int
    units_created: int
    edges_created: int
    errors: List[str]
    duration_seconds: float


@router.get(
    "/guilds/{guild_id}/backfill/status",
    response_model=BackfillStatusResponse,
    summary="Get backfill status",
    description="ADR-057 Phase 4: Get RuVector backfill status for a guild",
)
async def get_backfill_status(
    guild_id: str = Path(..., description="Guild ID"),
    user: dict = Depends(get_current_user),
):
    """
    Get current RuVector backfill status.

    Shows how much existing wiki content has been migrated.
    """
    try:
        from src.wiki.ruvector import RuVectorBackfill, VectorStore, KnowledgeExtractor, EmbeddingService
        from src.data.sqlite.connection import SQLiteConnection

        connection = SQLiteConnection.get_instance()
        embedding_service = EmbeddingService()
        vector_store = VectorStore(connection=connection, embedding_service=embedding_service)
        extractor = KnowledgeExtractor(embedding_service=embedding_service)

        backfill = RuVectorBackfill(
            wiki_connection=connection,
            vector_store=vector_store,
            knowledge_extractor=extractor,
        )

        status = await backfill.get_backfill_status(guild_id)

        return BackfillStatusResponse(**status)

    except Exception as e:
        logger.exception(f"Get backfill status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/guilds/{guild_id}/backfill",
    response_model=BackfillResultResponse,
    summary="Start backfill",
    description="ADR-057 Phase 4: Backfill existing wiki content to RuVector",
)
async def start_backfill(
    guild_id: str = Path(..., description="Guild ID"),
    request: BackfillRequest = BackfillRequest(),
    user: dict = Depends(get_current_user),
):
    """
    Backfill existing wiki content to RuVector.

    Migrates wiki_sources and wiki_pages to knowledge units.
    """
    try:
        from src.wiki.ruvector import RuVectorBackfill, VectorStore, KnowledgeExtractor, EmbeddingService, EdgeInferenceEngine
        from src.data.sqlite.connection import SQLiteConnection

        connection = SQLiteConnection.get_instance()
        embedding_service = EmbeddingService()
        vector_store = VectorStore(connection=connection, embedding_service=embedding_service)
        extractor = KnowledgeExtractor(embedding_service=embedding_service)
        edge_inference = EdgeInferenceEngine(vector_store=vector_store)

        backfill = RuVectorBackfill(
            wiki_connection=connection,
            vector_store=vector_store,
            knowledge_extractor=extractor,
            edge_inference=edge_inference,
            enable_coherence_check=False,  # Skip coherence during bulk backfill
        )

        result = await backfill.backfill_guild(
            guild_id=guild_id,
            include_sources=request.include_sources,
            include_pages=request.include_pages,
            rebuild_edges=request.rebuild_edges,
        )

        logger.info(f"RuVector backfill completed for {guild_id}: {result.units_created} units")

        return BackfillResultResponse(
            guild_id=result.guild_id,
            sources_processed=result.sources_processed,
            pages_processed=result.pages_processed,
            units_created=result.units_created,
            edges_created=result.edges_created,
            errors=result.errors[:20],  # Limit errors in response
            duration_seconds=result.duration_seconds,
        )

    except Exception as e:
        logger.exception(f"Backfill failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# SONA Learning Endpoints (ADR-057 Phase 3)
# -------------------------------------------------------------------------

class LearningStatsResponse(BaseModel):
    """SONA learning statistics."""
    guild_id: str
    signals_by_type: dict
    total_signals: int
    recent_signals_7d: int
    top_clicked_units: List[tuple]


class RecordClickRequest(BaseModel):
    """Record a search click."""
    query: str
    unit_id: str
    position: int


class RecordDwellRequest(BaseModel):
    """Record dwell time."""
    unit_id: str
    dwell_seconds: float


class RecordFeedbackRequest(BaseModel):
    """Record explicit feedback."""
    unit_id: str
    feedback_type: str = Field(..., pattern="^(helpful|not_helpful|report)$")
    comment: Optional[str] = None


@router.get(
    "/guilds/{guild_id}/learning/stats",
    response_model=LearningStatsResponse,
    summary="Get learning stats",
    description="ADR-057 Phase 3: Get SONA learning statistics",
)
async def get_learning_stats(
    guild_id: str = Path(..., description="Guild ID"),
    user: dict = Depends(get_current_user),
):
    """
    Get SONA learning statistics for a guild.
    """
    try:
        from src.wiki.ruvector import SONALearning
        vector_store = await _get_vector_store(guild_id)
        sona = SONALearning(vector_store=vector_store)

        stats = await sona.get_learning_stats(guild_id)

        return LearningStatsResponse(
            guild_id=guild_id,
            **stats,
        )

    except Exception as e:
        logger.exception(f"Get learning stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/guilds/{guild_id}/learning/click",
    summary="Record search click",
    description="ADR-057 Phase 3: Record a search result click for learning",
)
async def record_click(
    guild_id: str = Path(..., description="Guild ID"),
    request: RecordClickRequest = ...,
    user: dict = Depends(get_current_user),
):
    """
    Record that a user clicked a search result.
    """
    try:
        from src.wiki.ruvector import SONALearning
        vector_store = await _get_vector_store(guild_id)
        sona = SONALearning(vector_store=vector_store)

        await sona.on_search_click(
            guild_id=guild_id,
            query=request.query,
            unit_id=request.unit_id,
            position=request.position,
            user_id=user.get("sub"),
        )

        return {"success": True}

    except Exception as e:
        logger.exception(f"Record click failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/guilds/{guild_id}/learning/dwell",
    summary="Record dwell time",
    description="ADR-057 Phase 3: Record content view duration for learning",
)
async def record_dwell(
    guild_id: str = Path(..., description="Guild ID"),
    request: RecordDwellRequest = ...,
    user: dict = Depends(get_current_user),
):
    """
    Record time spent viewing content.
    """
    try:
        from src.wiki.ruvector import SONALearning
        vector_store = await _get_vector_store(guild_id)
        sona = SONALearning(vector_store=vector_store)

        await sona.on_dwell(
            guild_id=guild_id,
            unit_id=request.unit_id,
            dwell_seconds=request.dwell_seconds,
            user_id=user.get("sub"),
        )

        return {"success": True}

    except Exception as e:
        logger.exception(f"Record dwell failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/guilds/{guild_id}/learning/feedback",
    summary="Record feedback",
    description="ADR-057 Phase 3: Record explicit user feedback for learning",
)
async def record_feedback(
    guild_id: str = Path(..., description="Guild ID"),
    request: RecordFeedbackRequest = ...,
    user: dict = Depends(get_current_user),
):
    """
    Record explicit user feedback on content.
    """
    try:
        from src.wiki.ruvector import SONALearning
        vector_store = await _get_vector_store(guild_id)
        sona = SONALearning(vector_store=vector_store)

        await sona.on_feedback(
            guild_id=guild_id,
            unit_id=request.unit_id,
            feedback_type=request.feedback_type,
            comment=request.comment,
            user_id=user.get("sub"),
        )

        return {"success": True}

    except Exception as e:
        logger.exception(f"Record feedback failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Coherence Gate Endpoints (ADR-057 Phase 3)
# -------------------------------------------------------------------------

class CoherenceValidationResponse(BaseModel):
    """A flagged coherence validation."""
    id: int
    unit_id: str
    validation_type: str
    status: str
    details: dict
    unit_content: Optional[str] = None
    created_at: Optional[str] = None


class CoherenceValidationsResponse(BaseModel):
    """List of flagged validations."""
    guild_id: str
    total: int
    validations: List[CoherenceValidationResponse]


@router.get(
    "/guilds/{guild_id}/coherence/flagged",
    response_model=CoherenceValidationsResponse,
    summary="Get flagged validations",
    description="ADR-057 Phase 3: Get content flagged by coherence gate",
)
async def get_flagged_validations(
    guild_id: str = Path(..., description="Guild ID"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """
    Get validations flagged for human review.
    """
    try:
        from src.wiki.ruvector import CoherenceGate
        vector_store = await _get_vector_store(guild_id)
        gate = CoherenceGate(vector_store=vector_store)

        validations = await gate.get_flagged_validations(guild_id, limit=limit)

        return CoherenceValidationsResponse(
            guild_id=guild_id,
            total=len(validations),
            validations=[
                CoherenceValidationResponse(
                    id=v.get("id", 0),
                    unit_id=v.get("unit_id", ""),
                    validation_type=v.get("validation_type", ""),
                    status=v.get("status", ""),
                    details=v.get("details", {}),
                    unit_content=v.get("unit_content"),
                    created_at=v.get("created_at"),
                )
                for v in validations
            ],
        )

    except Exception as e:
        logger.exception(f"Get flagged validations failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ResolveValidationRequest(BaseModel):
    """Request to resolve a flagged validation."""
    resolution: str


@router.post(
    "/guilds/{guild_id}/coherence/resolve/{validation_id}",
    summary="Resolve flagged validation",
    description="ADR-057 Phase 3: Resolve a flagged coherence validation",
)
async def resolve_validation(
    guild_id: str = Path(..., description="Guild ID"),
    validation_id: int = Path(..., description="Validation ID"),
    request: ResolveValidationRequest = ...,
    user: dict = Depends(get_current_user),
):
    """
    Resolve a flagged validation.
    """
    try:
        from src.wiki.ruvector import CoherenceGate
        vector_store = await _get_vector_store(guild_id)
        gate = CoherenceGate(vector_store=vector_store)

        await gate.resolve_validation(
            validation_id=validation_id,
            resolution=request.resolution,
            reviewed_by=user.get("sub", "unknown"),
        )

        return {"success": True, "validation_id": validation_id}

    except Exception as e:
        logger.exception(f"Resolve validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
