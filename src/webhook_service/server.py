"""
FastAPI webhook server for Summary Bot NG.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from ..config.settings import BotConfig
from ..summarization.engine import SummarizationEngine
from ..exceptions.webhook import WebhookError
from .endpoints import create_summary_router
from .auth import setup_rate_limiting, set_config

logger = logging.getLogger(__name__)


class WebhookServer:
    """FastAPI server for webhook endpoints."""

    def __init__(self,
                 config: BotConfig,
                 summarization_engine: SummarizationEngine,
                 discord_bot=None,
                 task_scheduler=None,
                 config_manager=None):
        """Initialize webhook server.

        Args:
            config: Bot configuration
            summarization_engine: Summarization engine instance
            discord_bot: Discord bot instance for dashboard API
            task_scheduler: Task scheduler for dashboard API
            config_manager: Configuration manager for dashboard API
        """
        self.config = config
        self.summarization_engine = summarization_engine
        self.discord_bot = discord_bot
        self.task_scheduler = task_scheduler
        self.config_manager = config_manager
        self.server: Optional[uvicorn.Server] = None
        self._server_task: Optional[asyncio.Task] = None

        # Initialize auth configuration
        set_config(config)

        # Create FastAPI app with lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info("Webhook server starting up")

            # Initialize error tracker
            try:
                from ..logging.error_tracker import initialize_error_tracker
                await initialize_error_tracker()
                logger.info("Error tracker initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize error tracker: {e}")

            # Start error cleanup task
            cleanup_task = asyncio.create_task(self._run_error_cleanup())

            yield

            # Shutdown
            cleanup_task.cancel()
            logger.info("Webhook server shutting down")

        self.app = FastAPI(
            title="Summary Bot NG API",
            description="HTTP API for Discord summarization and webhook integration",
            version="2.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
            openapi_url="/openapi.json",
            lifespan=lifespan
        )

        # Configure middleware
        self._setup_middleware()

        # Configure routes
        self._setup_routes()

        # Configure error handlers
        self._setup_error_handlers()

    def _setup_middleware(self) -> None:
        """Configure FastAPI middleware."""
        cors_origins = self.config.webhook_config.cors_origins or []

        # Add localhost for development if not already present
        dev_origins = [
            "http://localhost:8080",
            "http://localhost:5173",
            "http://localhost:3000",
        ]
        for domain in dev_origins:
            if domain not in cors_origins:
                cors_origins.append(domain)

        # Log configured origins for debugging
        logger.info(f"CORS allowed origins: {cors_origins}")

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"]
        )

        # GZip compression
        self.app.add_middleware(GZipMiddleware, minimum_size=1000)

        # Rate limiting middleware
        setup_rate_limiting(
            self.app,
            rate_limit=self.config.webhook_config.rate_limit
        )

    def _setup_routes(self) -> None:
        """Configure API routes."""
        # Get build info from environment
        build_number = os.environ.get("BUILD_NUMBER", os.environ.get("GIT_COMMIT", "dev"))
        build_date = os.environ.get("BUILD_DATE", "")

        # Check if frontend dist exists (used for root route and SPA serving)
        frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
        has_frontend = frontend_dist.is_dir()

        # Health check endpoint
        @self.app.get("/health", tags=["Health"])
        async def health_check():
            """Check API health status."""
            try:
                # Check if summarization engine is available
                # We don't need Claude API to be healthy for the webhook service to be operational
                engine_health = await self.summarization_engine.health_check()

                # Always return 200 if the service itself is running
                # Degraded state means some features may not work but service is operational
                status = engine_health.get("status", "healthy")

                from datetime import datetime
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": status,
                        "version": "2.0.0",
                        "build": build_number,
                        "build_date": build_date,
                        "server_time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "services": {
                            "summarization_engine": engine_health.get("status"),
                            "claude_api": engine_health.get("claude_api"),
                            "cache": engine_health.get("cache")
                        }
                    }
                )
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                # Even on error, return 200 with unhealthy status
                # This allows load balancers to distinguish between service down vs degraded
                from datetime import datetime
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "degraded",
                        "version": "2.0.0",
                        "build": build_number,
                        "build_date": build_date,
                        "server_time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "error": str(e)
                    }
                )

        # Root endpoint (only JSON info when no frontend is bundled)
        if not has_frontend:
            @self.app.get("/", tags=["Info"])
            async def root():
                """API information."""
                return {
                    "name": "Summary Bot NG API",
                    "version": "2.0.0",
                    "build": build_number,
                    "build_date": build_date,
                    "docs": "/docs",
                    "health": "/health"
                }

        # Include summary endpoints
        summary_router = create_summary_router(
            summarization_engine=self.summarization_engine,
            config=self.config
        )
        self.app.include_router(summary_router, prefix="/api/v1", tags=["Summaries"])

        # Include dashboard API endpoints (if Discord bot is available)
        if self.discord_bot is not None:
            try:
                from ..dashboard import create_dashboard_router
                dashboard_router = create_dashboard_router(
                    discord_bot=self.discord_bot,
                    summarization_engine=self.summarization_engine,
                    task_scheduler=self.task_scheduler,
                    config_manager=self.config_manager,
                )
                self.app.include_router(dashboard_router)
                logger.info("Dashboard API routes enabled")
            except ImportError as e:
                logger.warning(f"Dashboard module not available: {e}")
            except Exception as e:
                logger.error(f"Failed to initialize dashboard API: {e}")

        # ADR-002: Include WhatsApp ingest and summarization routes
        try:
            from ..feeds import ingest_router, whatsapp_router
            self.app.include_router(ingest_router, tags=["Ingest"])
            self.app.include_router(whatsapp_router, tags=["WhatsApp"])
            logger.info("WhatsApp/Ingest API routes enabled (ADR-002)")
        except ImportError as e:
            logger.warning(f"WhatsApp/Ingest module not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize WhatsApp/Ingest API: {e}")

        # Public feed serving routes at root level (clean URLs for RSS readers)
        # These must be registered BEFORE the SPA catch-all route
        self._setup_public_feed_routes()

        # Serve frontend static files in production (if dist/ exists)
        if has_frontend:
            assets_dir = frontend_dist / "assets"
            if assets_dir.is_dir():
                self.app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

            index_html = frontend_dist / "index.html"

            @self.app.get("/", include_in_schema=False)
            async def serve_spa_root():
                return FileResponse(str(index_html))

            @self.app.get("/{path:path}", include_in_schema=False)
            async def serve_spa(request: Request, path: str):
                """Serve frontend SPA -- skip API and known backend paths."""
                if path.startswith(("api/", "health", "docs", "redoc", "openapi.json")):
                    return JSONResponse(status_code=404, content={"error": "NOT_FOUND"})

                # Serve actual static files from dist/ (e.g. favicon.ico, robots.txt)
                static_file = frontend_dist / path
                if path and static_file.is_file():
                    return FileResponse(str(static_file))

                # Everything else gets index.html for SPA client-side routing
                return FileResponse(str(index_html))

            logger.info(f"Frontend SPA serving enabled from {frontend_dist}")
        else:
            logger.info("Frontend dist/ not found, SPA serving disabled")

    def _setup_public_feed_routes(self) -> None:
        """Configure public feed serving routes at root level.

        These routes serve RSS/Atom feeds without the /api/v1 prefix for cleaner URLs
        that work well with RSS readers.
        """
        from fastapi import Path, Query
        from fastapi.responses import Response

        @self.app.get("/feeds/{feed_id}.rss", tags=["Feeds"], include_in_schema=True)
        async def get_public_rss_feed(
            request: Request,
            feed_id: str = Path(..., description="Feed ID"),
            token: Optional[str] = Query(None, description="Feed authentication token"),
        ):
            """Serve RSS 2.0 feed at root URL for RSS readers."""
            return await self._serve_public_feed(request, feed_id, token, "rss")

        @self.app.get("/feeds/{feed_id}.atom", tags=["Feeds"], include_in_schema=True)
        async def get_public_atom_feed(
            request: Request,
            feed_id: str = Path(..., description="Feed ID"),
            token: Optional[str] = Query(None, description="Feed authentication token"),
        ):
            """Serve Atom 1.0 feed at root URL for RSS readers."""
            return await self._serve_public_feed(request, feed_id, token, "atom")

        logger.info("Public feed routes registered at /feeds/*.rss and /feeds/*.atom")

    async def _serve_public_feed(
        self,
        request: Request,
        feed_id: str,
        token: Optional[str],
        feed_format: str,
    ):
        """Serve feed content with proper caching headers."""
        from fastapi import HTTPException
        from fastapi.responses import Response
        from ..dashboard.routes import get_feed_repository, get_summary_repository
        from ..models.feed import FeedType
        from ..feeds.generator import FeedGenerator
        from ..data.base import SearchCriteria

        feed_repo = await get_feed_repository()
        if not feed_repo:
            raise HTTPException(status_code=503, detail="Database not available")

        feed = await feed_repo.get_feed(feed_id)
        if not feed:
            raise HTTPException(status_code=404, detail="Feed not found")

        # Check authentication for private feeds
        if not feed.is_public:
            if token != feed.token:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    header_token = auth_header[7:]
                    if header_token != feed.token:
                        raise HTTPException(status_code=401, detail="Invalid feed token")
                else:
                    raise HTTPException(status_code=401, detail="Feed token required")

        # Get guild info
        if not self.discord_bot or not self.discord_bot.client:
            raise HTTPException(status_code=503, detail="Discord bot not available")

        guild = self.discord_bot.client.get_guild(int(feed.guild_id))
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")

        guild_name = guild.name
        channel_name = None
        if feed.channel_id:
            channel = guild.get_channel(int(feed.channel_id))
            channel_name = channel.name if channel else None

        # Get summaries from database
        summaries = []
        summary_repo = await get_summary_repository()
        if summary_repo:
            criteria = SearchCriteria(
                guild_id=feed.guild_id,
                channel_id=feed.channel_id,
                limit=feed.max_items,
                order_by="created_at",
                order_direction="DESC",
            )
            summaries = await summary_repo.find_summaries(criteria)

        # Generate feed content
        import os
        base_url = os.environ.get("FEED_BASE_URL", "https://summarybot-ng.fly.dev")
        dashboard_url = os.environ.get("DASHBOARD_URL", "https://summarybot-ng.fly.dev")
        generator = FeedGenerator(base_url, dashboard_url)

        # Set feed type for generation
        requested_type = FeedType.RSS if feed_format == "rss" else FeedType.ATOM
        original_type = feed.feed_type
        feed.feed_type = requested_type

        try:
            content = generator.generate(summaries, feed, guild_name, channel_name)
        finally:
            feed.feed_type = original_type

        # Update access stats
        await feed_repo.update_access_stats(feed_id)

        # Generate caching headers
        etag = FeedGenerator.generate_etag(feed_id, summaries)
        last_modified = FeedGenerator.get_last_modified(summaries)

        # Check If-None-Match header
        if_none_match = request.headers.get("If-None-Match", "").strip('"')
        if if_none_match == etag:
            return Response(status_code=304)

        # Check If-Modified-Since header
        if_modified_since = request.headers.get("If-Modified-Since")
        if if_modified_since:
            try:
                from email.utils import parsedate_to_datetime
                ims_dt = parsedate_to_datetime(if_modified_since)
                if ims_dt >= last_modified:
                    return Response(status_code=304)
            except (ValueError, TypeError):
                pass

        # Build response
        content_type = feed.get_content_type()
        headers = {
            "ETag": f'"{etag}"',
            "Last-Modified": last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "Cache-Control": "public, max-age=300",
            "Vary": "Accept-Encoding",
        }

        return Response(
            content=content,
            media_type=content_type,
            headers=headers,
        )

    def _setup_error_handlers(self) -> None:
        """Configure global error handlers."""

        @self.app.exception_handler(WebhookError)
        async def webhook_error_handler(request, exc: WebhookError):
            """Handle webhook-specific errors."""
            return JSONResponse(
                status_code=400,
                content={
                    "error": exc.error_code,
                    "message": exc.user_message or str(exc),
                    "request_id": request.headers.get("X-Request-ID")
                }
            )

        @self.app.exception_handler(Exception)
        async def general_error_handler(request, exc: Exception):
            """Handle unexpected errors."""
            logger.error(f"Unhandled error in webhook endpoint: {exc}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "request_id": request.headers.get("X-Request-ID")
                }
            )

    async def _run_error_cleanup(self) -> None:
        """Periodically cleanup old error logs."""
        import os
        cleanup_interval = int(os.environ.get("ERROR_CLEANUP_INTERVAL_HOURS", "24"))

        while True:
            try:
                await asyncio.sleep(cleanup_interval * 3600)  # Convert hours to seconds

                from ..logging.error_tracker import get_error_tracker
                tracker = get_error_tracker()
                deleted = await tracker.cleanup_old_errors()
                if deleted > 0:
                    logger.info(f"Error cleanup: removed {deleted} old errors")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error cleanup task failed: {e}")
                await asyncio.sleep(3600)  # Retry in an hour on failure

    async def start_server(self) -> None:
        """Start the webhook server.

        Starts the server in the background without blocking.
        """
        if self._server_task is not None:
            logger.warning("Webhook server already running")
            return

        host = self.config.webhook_config.host
        port = self.config.webhook_config.port

        logger.info(f"Starting webhook server on {host}:{port}")

        # Create server config
        server_config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
            loop="asyncio"
        )

        self.server = uvicorn.Server(server_config)

        # Start server in background task
        self._server_task = asyncio.create_task(self.server.serve())

        logger.info(f"Webhook server started on http://{host}:{port}")
        logger.info(f"API docs available at http://{host}:{port}/docs")

    async def stop_server(self) -> None:
        """Stop the webhook server gracefully."""
        if self.server is None:
            logger.warning("Webhook server not running")
            return

        logger.info("Stopping webhook server...")

        # Shutdown server
        if self.server:
            self.server.should_exit = True

        # Wait for server task to complete
        if self._server_task:
            try:
                await asyncio.wait_for(self._server_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Server shutdown timed out, cancelling task")
                self._server_task.cancel()
                try:
                    await self._server_task
                except asyncio.CancelledError:
                    pass

        self.server = None
        self._server_task = None

        logger.info("Webhook server stopped")

    def get_app(self) -> FastAPI:
        """Get the FastAPI application instance.

        Returns:
            FastAPI application
        """
        return self.app
