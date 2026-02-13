"""
RSS and Atom feed generation module for SummaryBot-NG.

Also includes multi-source ingest handlers (ADR-002).
"""

from .generator import FeedGenerator
from .ingest_handler import router as ingest_router
from .whatsapp_routes import router as whatsapp_router

__all__ = [
    'FeedGenerator',
    # ADR-002: Multi-source ingest
    'ingest_router',
    'whatsapp_router',
]
