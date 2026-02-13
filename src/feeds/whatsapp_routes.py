"""
WhatsApp-specific API routes for summarization (ADR-002).

These endpoints mirror the Discord summarization API but work with
WhatsApp chat data ingested via the ingest handler.
"""

import os
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Header, Depends, Query, Path
from pydantic import BaseModel, Field

from ..models.summary import SummaryOptions, SummaryLength

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])


# Request/Response models

class WhatsAppSummarizeRequest(BaseModel):
    """Request to summarize a WhatsApp chat."""
    time_from: Optional[datetime] = None
    time_to: Optional[datetime] = None
    max_messages: int = Field(default=1000, le=5000)
    summary_type: str = "comprehensive"  # brief, detailed, comprehensive
    output_format: str = "markdown"  # markdown, json, plain
    custom_prompt: Optional[str] = None
    include_voice_transcripts: bool = True
    include_forwarded: bool = True
    filter_participants: Optional[List[str]] = None  # Only include messages from these JIDs


class WhatsAppSummarizeResponse(BaseModel):
    """Response from WhatsApp summarization."""
    summary_id: str
    summary_text: str
    key_points: List[str]
    action_items: List[dict]
    participants: List[dict]
    technical_terms: List[dict]
    message_count: int
    time_range_start: datetime
    time_range_end: datetime
    metadata: dict


class WhatsAppChatInfo(BaseModel):
    """Information about a WhatsApp chat."""
    chat_id: str  # JID
    chat_name: str
    chat_type: str  # individual, group
    message_count: int
    first_message_at: Optional[datetime]
    last_message_at: Optional[datetime]
    participant_count: int


class WhatsAppChatsResponse(BaseModel):
    """Response listing WhatsApp chats."""
    chats: List[WhatsAppChatInfo]
    total: int


def _validate_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Validate ingest API key from header."""
    expected_key = os.environ.get("INGEST_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="WhatsApp API not configured")

    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return x_api_key


def _map_summary_type(summary_type: str) -> SummaryLength:
    """Map string summary type to SummaryLength enum."""
    mapping = {
        "brief": SummaryLength.BRIEF,
        "detailed": SummaryLength.DETAILED,
        "comprehensive": SummaryLength.COMPREHENSIVE,
    }
    return mapping.get(summary_type.lower(), SummaryLength.COMPREHENSIVE)


@router.get(
    "/chats",
    response_model=WhatsAppChatsResponse,
    summary="List WhatsApp chats",
    description="List all WhatsApp chats with ingested messages.",
    responses={
        401: {"description": "Invalid API key"},
    },
)
async def list_whatsapp_chats(
    limit: int = Query(50, ge=1, le=100, description="Maximum chats to return"),
    offset: int = Query(0, ge=0, description="Number of chats to skip"),
    api_key: str = Depends(_validate_api_key),
):
    """List all WhatsApp chats that have ingested messages."""
    try:
        from ..data import get_ingest_repository
        repo = await get_ingest_repository()
        if repo:
            chats = await repo.list_channels("whatsapp", limit=limit, offset=offset)
            total = await repo.count_channels("whatsapp")
            return WhatsAppChatsResponse(
                chats=[WhatsAppChatInfo(**c) for c in chats],
                total=total,
            )
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"Failed to list WhatsApp chats: {e}")

    return WhatsAppChatsResponse(chats=[], total=0)


@router.get(
    "/chats/{chat_jid}",
    response_model=WhatsAppChatInfo,
    summary="Get WhatsApp chat details",
    description="Get details about a specific WhatsApp chat.",
    responses={
        401: {"description": "Invalid API key"},
        404: {"description": "Chat not found"},
    },
)
async def get_whatsapp_chat(
    chat_jid: str = Path(..., description="WhatsApp chat JID"),
    api_key: str = Depends(_validate_api_key),
):
    """Get details about a specific WhatsApp chat."""
    try:
        from ..data import get_ingest_repository
        repo = await get_ingest_repository()
        if repo:
            chat = await repo.get_channel_stats("whatsapp", chat_jid)
            if chat:
                return WhatsAppChatInfo(**chat)
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"Failed to get WhatsApp chat {chat_jid}: {e}")

    raise HTTPException(status_code=404, detail="Chat not found")


@router.post(
    "/chats/{chat_jid}/summarize",
    response_model=WhatsAppSummarizeResponse,
    summary="Summarize WhatsApp chat",
    description="Generate a summary of a WhatsApp chat. Equivalent to Discord channel summarization.",
    responses={
        401: {"description": "Invalid API key"},
        404: {"description": "No messages found"},
    },
)
async def summarize_whatsapp_chat(
    chat_jid: str = Path(..., description="WhatsApp chat JID"),
    request: WhatsAppSummarizeRequest = None,
    api_key: str = Depends(_validate_api_key),
):
    """Summarize a WhatsApp chat by its JID.

    This endpoint mirrors: POST /discord/channels/{channel_id}/summarize
    """
    if request is None:
        request = WhatsAppSummarizeRequest()

    # Get messages from ingest repository
    try:
        from ..data import get_ingest_repository
        repo = await get_ingest_repository()
        if not repo:
            raise HTTPException(status_code=503, detail="Repository not available")

        messages = await repo.get_messages(
            source_type="whatsapp",
            channel_id=chat_jid,
            time_from=request.time_from,
            time_to=request.time_to,
            limit=request.max_messages,
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Repository not available")

    if not messages:
        raise HTTPException(
            status_code=404,
            detail="No messages found for this chat in the given time range"
        )

    # Build summary options
    options = SummaryOptions(
        summary_length=_map_summary_type(request.summary_type),
        source_type="whatsapp",
        include_voice_transcripts=request.include_voice_transcripts,
        include_forwarded=request.include_forwarded,
    )

    # Run summarization
    try:
        from ..summarization import SummarizationEngine
        from ..summarization.prompt_builder import PromptBuilder

        # Get summarization engine (would be injected in real app)
        prompt_builder = PromptBuilder()
        # Note: In production, get engine from dependency injection
        # For now, this is a placeholder showing the intended flow

        # Build context
        context = {
            "channel_name": messages[0].channel_name if messages else chat_jid,
            "source_type": "whatsapp",
            "total_participants": len(set(m.author_id for m in messages)),
        }

        # Build prompt
        prompt = prompt_builder.build_summarization_prompt(
            messages=messages,
            options=options,
            context=context,
            custom_system_prompt=request.custom_prompt,
        )

        # For now, return a placeholder response
        # In production, this would call the actual summarization engine
        import uuid
        return WhatsAppSummarizeResponse(
            summary_id=str(uuid.uuid4()),
            summary_text="[WhatsApp summarization pending engine integration]",
            key_points=[],
            action_items=[],
            participants=[],
            technical_terms=[],
            message_count=len(messages),
            time_range_start=min(m.timestamp for m in messages),
            time_range_end=max(m.timestamp for m in messages),
            metadata={
                "source_type": "whatsapp",
                "summary_type": request.summary_type,
            },
        )

    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")


@router.get(
    "/chats/{chat_jid}/messages",
    summary="Get WhatsApp messages",
    description="Get paginated message history for a WhatsApp chat.",
    responses={
        401: {"description": "Invalid API key"},
    },
)
async def get_whatsapp_messages(
    chat_jid: str = Path(..., description="WhatsApp chat JID"),
    limit: int = Query(100, ge=1, le=500, description="Maximum messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    time_from: Optional[datetime] = Query(None, description="Filter from date"),
    time_to: Optional[datetime] = Query(None, description="Filter to date"),
    api_key: str = Depends(_validate_api_key),
):
    """Get paginated message history for a WhatsApp chat."""
    try:
        from ..data import get_ingest_repository
        repo = await get_ingest_repository()
        if repo:
            messages = await repo.get_messages(
                source_type="whatsapp",
                channel_id=chat_jid,
                time_from=time_from,
                time_to=time_to,
                limit=limit,
                offset=offset,
            )
            return {
                "messages": [
                    {
                        "id": m.id,
                        "sender": m.author_name,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat(),
                        "has_attachments": bool(m.attachments),
                        "is_forwarded": m.is_forwarded,
                    }
                    for m in messages
                ],
                "count": len(messages),
            }
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"Failed to get messages for {chat_jid}: {e}")

    return {"messages": [], "count": 0}


@router.get(
    "/status",
    summary="WhatsApp integration status",
    description="Check WhatsApp integration status and configuration.",
)
async def whatsapp_status():
    """Get WhatsApp integration status."""
    api_key_configured = bool(os.environ.get("INGEST_API_KEY"))

    return {
        "enabled": api_key_configured,
        "features": {
            "ingest": api_key_configured,
            "summarization": True,
            "voice_transcription": bool(os.environ.get("WHISPER_API_KEY")),
        },
        "version": "1.0.0",
    }
