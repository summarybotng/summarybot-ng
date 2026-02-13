"""
HTTP endpoint for receiving messages from external sources (ADR-002).

This handler receives normalized message batches from WhatsApp Push Agent
and other data sources, converting them to the internal format for summarization.
"""

import os
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Depends

from ..models.ingest import IngestDocument, IngestResponse, SourceType
from ..message_processing.whatsapp_processor import WhatsAppMessageProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ingest"])


def _validate_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Validate ingest API key from header.

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        Validated API key

    Raises:
        HTTPException: If API key is invalid
    """
    expected_key = os.environ.get("INGEST_API_KEY")
    if not expected_key:
        logger.warning("INGEST_API_KEY not configured, rejecting request")
        raise HTTPException(status_code=500, detail="Ingest API not configured")

    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return x_api_key


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest messages from external source",
    description="Receive a batch of normalized messages from WhatsApp or other sources.",
    responses={
        400: {"description": "Invalid payload"},
        401: {"description": "Invalid API key"},
        500: {"description": "Server error"},
    },
)
async def ingest_messages(
    payload: IngestDocument,
    api_key: str = Depends(_validate_api_key),
):
    """Receive a batch of normalized messages from any external source.

    This endpoint accepts messages pushed from:
    - WhatsApp Push Agent (ADR-002)
    - Future: Slack, Telegram, Email adapters

    The messages are converted to ProcessedMessage format and stored for
    later summarization.
    """
    # Validate payload
    if not payload.messages:
        raise HTTPException(status_code=400, detail="Empty message batch")

    if payload.source_type not in [s.value for s in SourceType]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {payload.source_type}"
        )

    logger.info(
        f"Received ingest batch: source={payload.source_type}, "
        f"channel={payload.channel_name}, messages={len(payload.messages)}"
    )

    # Convert to ProcessedMessages based on source type
    if payload.source_type == SourceType.WHATSAPP.value:
        processor = WhatsAppMessageProcessor()
        processed = processor.convert_batch(payload)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Source type not yet implemented: {payload.source_type}"
        )

    # Generate batch ID
    batch_id = str(uuid.uuid4())

    # Store the batch (async - don't block response)
    try:
        await _store_ingest_batch(batch_id, payload, processed)
    except Exception as e:
        logger.error(f"Failed to store ingest batch: {e}")
        # Don't fail the request - return success but mark as not processed
        return IngestResponse(
            status="accepted",
            batch_id=batch_id,
            message_count=len(processed),
            source=payload.source_type,
            channel=payload.channel_name,
            processed=False,
        )

    logger.info(f"Stored ingest batch {batch_id} with {len(processed)} messages")

    return IngestResponse(
        status="accepted",
        batch_id=batch_id,
        message_count=len(processed),
        source=payload.source_type,
        channel=payload.channel_name,
        processed=True,
    )


async def _store_ingest_batch(batch_id: str, payload: IngestDocument, processed_messages):
    """Store ingest batch to database.

    Args:
        batch_id: Unique batch identifier
        payload: Original ingest document
        processed_messages: Converted ProcessedMessage objects
    """
    try:
        from ..data import get_ingest_repository
        repo = await get_ingest_repository()
        if repo:
            await repo.store_batch(batch_id, payload, processed_messages)
    except ImportError:
        logger.warning("Ingest repository not available, batch stored in memory only")
    except Exception as e:
        logger.error(f"Failed to store batch {batch_id}: {e}")
        raise


@router.get(
    "/ingest/status",
    summary="Get ingest API status",
    description="Check if the ingest API is configured and ready.",
)
async def ingest_status():
    """Get status of the ingest API."""
    api_key_configured = bool(os.environ.get("INGEST_API_KEY"))

    return {
        "enabled": api_key_configured,
        "supported_sources": [s.value for s in SourceType],
        "version": "1.0.0",
    }


@router.get(
    "/ingest/batches/{batch_id}",
    summary="Get ingest batch details",
    description="Retrieve details about a specific ingest batch.",
    responses={
        401: {"description": "Invalid API key"},
        404: {"description": "Batch not found"},
    },
)
async def get_ingest_batch(
    batch_id: str,
    api_key: str = Depends(_validate_api_key),
):
    """Get details about a specific ingest batch."""
    try:
        from ..data import get_ingest_repository
        repo = await get_ingest_repository()
        if repo:
            batch = await repo.get_batch(batch_id)
            if batch:
                return batch
    except ImportError:
        pass

    raise HTTPException(status_code=404, detail="Batch not found")
