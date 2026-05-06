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
