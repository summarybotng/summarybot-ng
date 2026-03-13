"""
API endpoint handlers for webhook service.
"""

import logging
from typing import Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse

from ..config.settings import BotConfig
from ..config.constants import DEFAULT_SUMMARIZATION_MODEL
from ..summarization.engine import SummarizationEngine
from ..models.summary import SummaryOptions, SummaryLength
from src.utils.time import utc_now_naive
from ..exceptions import (
    SummarizationError,
    InsufficientContentError,
    WebhookAuthError,
    create_error_context
)
from .auth import APIKeyAuth, JWTAuth, get_api_key_auth, get_jwt_auth
from .validators import (
    SummaryRequestModel,
    SummaryResponseModel,
    ScheduleRequestModel,
    ScheduleResponseModel,
    ErrorResponseModel
)
from .formatters import ResponseFormatter

logger = logging.getLogger(__name__)


def create_summary_router(
    summarization_engine: SummarizationEngine,
    config: BotConfig
) -> APIRouter:
    """Create router for summary endpoints.

    Args:
        summarization_engine: Summarization engine instance
        config: Bot configuration

    Returns:
        Configured API router
    """
    router = APIRouter()

    @router.post(
        "/summaries",
        response_model=SummaryResponseModel,
        responses={
            201: {"description": "Summary created successfully"},
            200: {"description": "Summary created successfully"},
            400: {"model": ErrorResponseModel},
            401: {"model": ErrorResponseModel},
            429: {"model": ErrorResponseModel},
            500: {"model": ErrorResponseModel}
        },
        summary="Create a summary from messages",
        description="Generate a summary from provided Discord messages"
    )
    async def create_summary_from_messages(
        request: Dict[str, Any],
        auth: APIKeyAuth = Depends(get_api_key_auth),
        x_request_id: str = Header(None, alias="X-Request-ID")
    ) -> SummaryResponseModel:
        """Create a new summary from provided messages.

        Args:
            request: Summary request with messages array
            auth: Authentication credentials
            x_request_id: Optional request ID for tracking

        Returns:
            Summary response with generated content

        Raises:
            HTTPException: On validation or processing errors
        """
        request_id = x_request_id or f"req-{utc_now_naive().timestamp()}"

        try:
            logger.info(f"Processing summary request {request_id}")

            # Handle Zapier's payload wrapping - Zapier sends JSON as a string in a "payload" key
            import json
            if "payload" in request and isinstance(request.get("payload"), str):
                logger.info("Unwrapping Zapier payload string")
                try:
                    request = json.loads(request["payload"])
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse Zapier payload: {e}")
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "INVALID_REQUEST",
                            "message": "Invalid JSON in payload field",
                            "request_id": request_id
                        }
                    )

            # Extract request parameters
            messages = request.get("messages", [])
            channel_id = request.get("channel_id")
            guild_id = request.get("guild_id")
            options_dict = request.get("options", {})

            # Zapier may send messages/options as JSON strings - parse them
            if isinstance(messages, str):
                logger.info(f"Parsing messages from JSON string. First 200 chars: {messages[:200]}")
                try:
                    messages = json.loads(messages)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse messages JSON: {e}")
                    logger.error(f"Malformed messages string: {messages}")
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "INVALID_REQUEST",
                            "message": "Invalid JSON in messages field",
                            "request_id": request_id
                        }
                    )

            if isinstance(options_dict, str):
                logger.info("Parsing options from JSON string")
                try:
                    options_dict = json.loads(options_dict)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse options JSON: {e}")
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "INVALID_REQUEST",
                            "message": "Invalid JSON in options field",
                            "request_id": request_id
                        }
                    )

            if not messages:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "INVALID_REQUEST",
                        "message": "No messages provided",
                        "request_id": request_id
                    }
                )

            # Convert to ProcessedMessage objects
            from ..models.message import ProcessedMessage
            processed_messages = []
            for msg in messages:
                processed_messages.append(ProcessedMessage(
                    id=msg.get("id", ""),
                    author_name=msg.get("author_name", "Unknown"),
                    author_id=msg.get("author_id", ""),
                    content=msg.get("content", ""),
                    timestamp=datetime.fromisoformat(msg.get("timestamp", utc_now_naive().isoformat())),
                    attachments=msg.get("attachments", []),
                    references=msg.get("references", []),
                    mentions=msg.get("mentions", [])
                ))

            # Build options
            summary_length = options_dict.get("summary_length", "detailed")
            options = SummaryOptions(
                summary_length=SummaryLength(summary_length),
                include_bots=options_dict.get("include_bots", False),
                min_messages=options_dict.get("min_messages", 5)
            )

            # Build context
            from ..models.summary import SummarizationContext

            # Calculate time span
            if processed_messages:
                time_span = (processed_messages[-1].timestamp - processed_messages[0].timestamp).total_seconds() / 3600
                unique_authors = len(set(msg.author_id for msg in processed_messages))
            else:
                time_span = 0.0
                unique_authors = 0

            context = SummarizationContext(
                channel_name=f"channel-{channel_id}",
                guild_name=f"guild-{guild_id}" if guild_id else "unknown",
                total_participants=unique_authors,
                time_span_hours=time_span
            )

            # Generate summary
            summary_result = await summarization_engine.summarize_messages(
                messages=processed_messages,
                options=options,
                context=context,
                channel_id=channel_id or "unknown",
                guild_id=guild_id or "unknown"
            )

            # Build response
            response = SummaryResponseModel(
                id=f"sum_{int(utc_now_naive().timestamp())}",
                channel_id=channel_id or "unknown",
                guild_id=guild_id,
                summary_text=summary_result.summary_text,
                key_points=summary_result.key_points,
                action_items=[],
                technical_terms=[],
                participants=[],
                message_count=len(messages),
                start_time=processed_messages[0].timestamp if processed_messages else utc_now_naive(),
                end_time=processed_messages[-1].timestamp if processed_messages else utc_now_naive(),
                created_at=utc_now_naive(),
                metadata={
                    "input_tokens": summary_result.metadata.get("input_tokens", 0),
                    "output_tokens": summary_result.metadata.get("output_tokens", 0),
                    "total_tokens": summary_result.metadata.get("total_tokens", 0),
                    "model": summary_result.metadata.get("model", "unknown")
                }
            )

            return response

        except InsufficientContentError as e:
            logger.warning(f"Insufficient content for summary: {e}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "INSUFFICIENT_CONTENT",
                    "message": str(e),
                    "request_id": request_id
                }
            )

        except SummarizationError as e:
            logger.error(f"Summarization failed: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": e.error_code,
                    "message": str(e),
                    "request_id": request_id
                }
            )

        except HTTPException:
            # Re-raise HTTPException without modification
            raise

        except Exception as e:
            logger.error(f"Unexpected error in create_summary: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "INTERNAL_ERROR",
                    "message": str(e),
                    "request_id": request_id
                }
            )

    @router.post(
        "/summarize",
        response_model=SummaryResponseModel,
        responses={
            201: {"description": "Summary created successfully"},
            400: {"model": ErrorResponseModel},
            401: {"model": ErrorResponseModel},
            429: {"model": ErrorResponseModel},
            500: {"model": ErrorResponseModel}
        },
        summary="Create a summary",
        description="Generate a summary from Discord messages or documents"
    )
    async def create_summary(
        request: SummaryRequestModel,
        auth: APIKeyAuth = Depends(get_api_key_auth),
        x_request_id: str = Header(None, alias="X-Request-ID")
    ) -> SummaryResponseModel:
        """Create a new summary from messages.

        Args:
            request: Summary request parameters
            auth: Authentication credentials
            x_request_id: Optional request ID for tracking

        Returns:
            Summary response with generated content

        Raises:
            HTTPException: On validation or processing errors
        """
        request_id = x_request_id or f"req-{utc_now_naive().timestamp()}"

        try:
            logger.info(f"Processing summary request {request_id}")

            # Validate authentication (already done by dependency)
            # TODO: Check user permissions based on guild_id/channel_id

            # Convert request to internal models
            options = SummaryOptions(
                summary_length=SummaryLength(request.summary_type),
                summarization_model=request.model or DEFAULT_SUMMARIZATION_MODEL,
                temperature=request.temperature,
                max_tokens=request.max_length,
                include_bots=not request.exclude_bots,
                extract_action_items=request.include_action_items,
                extract_technical_terms=request.include_technical_terms
            )

            # TODO: Fetch messages from Discord based on request parameters
            # For now, return a mock response structure

            # This is a placeholder - actual implementation would:
            # 1. Fetch messages from Discord API
            # 2. Process messages
            # 3. Call summarization engine
            # 4. Format response

            raise HTTPException(
                status_code=501,
                detail="Summary creation not yet implemented - requires Discord client integration"
            )

        except InsufficientContentError as e:
            logger.warning(f"Insufficient content for summary: {e}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "INSUFFICIENT_CONTENT",
                    "message": str(e),
                    "request_id": request_id
                }
            )

        except SummarizationError as e:
            logger.error(f"Summarization failed: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": e.error_code,
                    "message": str(e),
                    "request_id": request_id
                }
            )

        except HTTPException:
            # Re-raise HTTPException without modification
            raise

        except Exception as e:
            logger.error(f"Unexpected error in create_summary: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "request_id": request_id
                }
            )

    @router.get(
        "/summary/{summary_id}",
        response_model=SummaryResponseModel,
        responses={
            200: {"description": "Summary retrieved successfully"},
            404: {"model": ErrorResponseModel},
            401: {"model": ErrorResponseModel}
        },
        summary="Get summary by ID",
        description="Retrieve a previously generated summary"
    )
    async def get_summary(
        summary_id: str,
        auth: APIKeyAuth = Depends(get_api_key_auth)
    ) -> SummaryResponseModel:
        """Get an existing summary by ID.

        Args:
            summary_id: Summary identifier
            auth: Authentication credentials

        Returns:
            Summary response

        Raises:
            HTTPException: If summary not found
        """
        try:
            logger.info(f"Fetching summary {summary_id}")

            # TODO: Implement summary retrieval from database
            # For now, return 404

            raise HTTPException(
                status_code=404,
                detail={
                    "error": "SUMMARY_NOT_FOUND",
                    "message": f"Summary {summary_id} not found",
                    "summary_id": summary_id
                }
            )

        except HTTPException:
            raise

        except Exception as e:
            logger.error(f"Error retrieving summary: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "INTERNAL_ERROR",
                    "message": "Failed to retrieve summary"
                }
            )

    @router.post(
        "/schedule",
        response_model=ScheduleResponseModel,
        responses={
            201: {"description": "Summary scheduled successfully"},
            400: {"model": ErrorResponseModel},
            401: {"model": ErrorResponseModel}
        },
        summary="Schedule a summary",
        description="Schedule automatic summary generation"
    )
    async def schedule_summary(
        request: ScheduleRequestModel,
        auth: APIKeyAuth = Depends(get_api_key_auth),
        x_request_id: str = Header(None, alias="X-Request-ID")
    ) -> ScheduleResponseModel:
        """Schedule automatic summary generation.

        Args:
            request: Schedule request parameters
            auth: Authentication credentials
            x_request_id: Optional request ID

        Returns:
            Schedule confirmation

        Raises:
            HTTPException: On validation or scheduling errors
        """
        request_id = x_request_id or f"req-{utc_now_naive().timestamp()}"

        try:
            logger.info(f"Processing schedule request {request_id}")

            # TODO: Implement scheduling logic
            # This would integrate with the scheduling service

            raise HTTPException(
                status_code=501,
                detail={
                    "error": "NOT_IMPLEMENTED",
                    "message": "Scheduling not yet implemented - requires scheduler integration",
                    "request_id": request_id
                }
            )

        except HTTPException:
            # Re-raise HTTPException without modification
            raise

        except Exception as e:
            logger.error(f"Error scheduling summary: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "INTERNAL_ERROR",
                    "message": "Failed to schedule summary",
                    "request_id": request_id
                }
            )

    @router.delete(
        "/schedule/{schedule_id}",
        responses={
            204: {"description": "Schedule cancelled successfully"},
            404: {"model": ErrorResponseModel},
            401: {"model": ErrorResponseModel}
        },
        summary="Cancel scheduled summary",
        description="Cancel a previously scheduled summary"
    )
    async def cancel_schedule(
        schedule_id: str,
        auth: APIKeyAuth = Depends(get_api_key_auth)
    ):
        """Cancel a scheduled summary.

        Args:
            schedule_id: Schedule identifier
            auth: Authentication credentials

        Raises:
            HTTPException: If schedule not found
        """
        try:
            logger.info(f"Cancelling schedule {schedule_id}")

            # TODO: Implement schedule cancellation

            raise HTTPException(
                status_code=404,
                detail={
                    "error": "SCHEDULE_NOT_FOUND",
                    "message": f"Schedule {schedule_id} not found"
                }
            )

        except HTTPException:
            raise

        except Exception as e:
            logger.error(f"Error cancelling schedule: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "INTERNAL_ERROR",
                    "message": "Failed to cancel schedule"
                }
            )

    return router
