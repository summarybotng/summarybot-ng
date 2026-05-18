"""
Wiki agents for Compounding Wiki (ADR-056).

Agents responsible for:
- Ingest: Processing new sources and updating wiki pages
- Query: Answering questions with wiki knowledge
- Maintenance: Lint operations for wiki hygiene
"""

import logging
from typing import Optional, Any

from .ingest_agent import WikiIngestAgent
from .query_agent import WikiQueryAgent
from .maintenance_agent import WikiMaintenanceAgent

logger = logging.getLogger(__name__)

__all__ = [
    "WikiIngestAgent",
    "WikiQueryAgent",
    "WikiMaintenanceAgent",
    "create_ingest_agent",
]


async def create_ingest_agent(
    repository: Any,
    llm_client: Optional[Any] = None,
    enable_ruvector: bool = True,
) -> WikiIngestAgent:
    """
    Create a WikiIngestAgent with optional RuVector integration.

    ADR-057 Phase 4: Factory function that sets up dual-write to RuVector
    when available and enabled.

    Args:
        repository: Wiki repository for data access
        llm_client: Optional LLM client for semantic analysis
        enable_ruvector: Whether to enable RuVector dual-write (default True)

    Returns:
        WikiIngestAgent configured with or without RuVector hook
    """
    ruvector_hook = None

    if enable_ruvector:
        try:
            from ..ruvector import (
                RuVectorIngestHook,
                RuVectorIngestIntegration,
                EmbeddingService,
            )

            # Get database connection from repository
            connection = repository.connection

            # Initialize RuVector integration with correct parameters
            embedding_service = EmbeddingService()
            integration = RuVectorIngestIntegration(
                connection=connection,
                claude_client=llm_client,
                embedding_service=embedding_service,
                enable_edge_inference=True,
            )

            # Create hook
            ruvector_hook = RuVectorIngestHook(integration=integration)

            logger.info("RuVector dual-write enabled for wiki ingest")

        except ImportError as e:
            logger.debug(f"RuVector not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to initialize RuVector: {e}", exc_info=True)

    return WikiIngestAgent(
        repository=repository,
        llm_client=llm_client,
        ruvector_hook=ruvector_hook,
    )
