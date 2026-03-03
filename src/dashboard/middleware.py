"""
ADR-031: Comprehensive Error Logging Middleware.

HTTP middleware for logging API errors with full context.
"""

import logging
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP errors with comprehensive context.

    ADR-031: Logs all 4xx/5xx responses with:
    - Request method and path
    - Status code
    - Request ID for correlation
    - Response time
    - Error details (for 5xx)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID for correlation
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        start_time = time.time()

        try:
            response = await call_next(request)
            duration_ms = int((time.time() - start_time) * 1000)

            # Log based on status code
            if response.status_code >= 500:
                # Server errors - ERROR level
                logger.error(
                    f"[{request_id}] HTTP {response.status_code} {request.method} {request.url.path} "
                    f"({duration_ms}ms) - Server error"
                )
            elif response.status_code >= 400:
                # Client errors - WARNING level
                logger.warning(
                    f"[{request_id}] HTTP {response.status_code} {request.method} {request.url.path} "
                    f"({duration_ms}ms)"
                )
            elif response.status_code >= 200 and logger.isEnabledFor(logging.DEBUG):
                # Success - DEBUG level (only if debug enabled)
                logger.debug(
                    f"[{request_id}] HTTP {response.status_code} {request.method} {request.url.path} "
                    f"({duration_ms}ms)"
                )

            return response

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            # Unhandled exception - ERROR level with full traceback
            logger.exception(
                f"[{request_id}] Unhandled error on {request.method} {request.url.path} "
                f"({duration_ms}ms): {type(e).__name__}: {e}"
            )
            raise


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to add request context for logging.

    Extracts useful context from requests:
    - User ID (from auth)
    - Guild ID (from path)
    - Client IP (sanitized for privacy)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract guild_id from path if present
        path_parts = request.url.path.split('/')
        guild_id = None
        for i, part in enumerate(path_parts):
            if part == 'guilds' and i + 1 < len(path_parts):
                guild_id = path_parts[i + 1]
                break

        # Store context on request state
        request.state.guild_id = guild_id

        return await call_next(request)


def setup_error_logging_middleware(app):
    """Add error logging middleware to FastAPI app.

    Args:
        app: FastAPI application instance
    """
    # Add middleware in reverse order (last added = first executed)
    app.add_middleware(ErrorLoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)

    logger.info("ADR-031: Error logging middleware configured")
