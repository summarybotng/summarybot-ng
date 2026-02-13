"""
Main application entry point for Summary Bot NG.

This module orchestrates all components of the bot including:
- Discord bot client with slash commands
- Permission management
- Summarization engine
- Task scheduling
- Webhook API server
- Database persistence
"""
# Early debug output - before any imports that might fail
import sys
print("=== Summary Bot NG module loading ===", flush=True, file=sys.stderr)

import asyncio
import logging
import os
import signal
from typing import Optional, Tuple
from pathlib import Path

print("Standard library imports OK", flush=True, file=sys.stderr)

from .config import ConfigManager, BotConfig
from .exceptions import handle_unexpected_error
print("Config imports OK", flush=True, file=sys.stderr)

# Core components
from .summarization import SummarizationEngine, ClaudeClient
from .summarization.cache import SummaryCache, MemoryCache
from .message_processing import MessageProcessor
print("Core component imports OK", flush=True, file=sys.stderr)

# New modules
from .discord_bot import SummaryBot, EventHandler
print("Discord bot imports OK", flush=True, file=sys.stderr)
from .permissions import PermissionManager
from .command_handlers import (
    SummarizeCommandHandler,
    ConfigCommandHandler,
    ScheduleCommandHandler
)
from .scheduling import TaskScheduler
from .scheduling.executor import TaskExecutor
from .scheduling.persistence import TaskPersistence
from .webhook_service import WebhookServer
from .data import initialize_repositories, run_migrations
from .logging import CommandLogger, CommandLogRepository, LoggingConfig
import aiosqlite
print("All imports completed OK", flush=True, file=sys.stderr)


class SummaryBotApp:
    """Main application class for Summary Bot NG with full module integration."""

    def __init__(self):
        self.config: Optional[BotConfig] = None
        self.config_manager: Optional[ConfigManager] = None
        self.discord_bot: Optional[SummaryBot] = None
        self.summarization_engine: Optional[SummarizationEngine] = None
        self.message_processor: Optional[MessageProcessor] = None
        self.permission_manager: Optional[PermissionManager] = None
        self.task_scheduler: Optional[TaskScheduler] = None
        self.webhook_server: Optional[WebhookServer] = None
        self.command_logger = None  # Command logging system
        self.prompt_resolver = None  # Prompt template resolver
        self.guild_config_store = None  # Guild config store
        self.running = False
        self.webhook_only_mode = False  # True when DISCORD_TOKEN not set

        # Setup logging - file handler is optional (may fail if not writable)
        log_handlers = [logging.StreamHandler(sys.stdout)]
        try:
            # Try to create log file in data directory for persistence
            log_path = Path("data/summarybot.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handlers.append(logging.FileHandler(str(log_path)))
        except (OSError, PermissionError):
            # File logging not available, use stdout only
            pass

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=log_handlers
        )
        self.logger = logging.getLogger(__name__)

    async def initialize(self, config_path: Optional[str] = None, db_path: str = "data/summarybot.db"):
        """Initialize all application components.

        Args:
            config_path: Path to configuration file (optional)
            db_path: Path to SQLite database file
        """
        try:
            self.logger.info("Initializing Summary Bot NG...")

            # Load configuration
            self.config_manager = ConfigManager(config_path)
            self.config = await self.config_manager.load_config()

            # Set log level from config
            logging.getLogger().setLevel(self.config.log_level.value)
            self.logger.info("Configuration loaded successfully")

            # Check if running in webhook-only mode (no Discord token)
            self.webhook_only_mode = not self.config.discord_token
            if self.webhook_only_mode:
                self.logger.warning("=" * 60)
                self.logger.warning("WEBHOOK-ONLY MODE: DISCORD_TOKEN not set")
                self.logger.warning("Discord bot features disabled, dashboard API available")
                self.logger.warning("=" * 60)

            # Initialize database
            await self._initialize_database(db_path)

            # Initialize core components
            await self._initialize_core_components()

            # Initialize Discord bot (skip in webhook-only mode)
            if not self.webhook_only_mode:
                await self._initialize_discord_bot()

                # Initialize task scheduler (requires Discord bot)
                await self._initialize_scheduler()

            # Initialize webhook server (if enabled)
            if self.config.webhook_config.enabled:
                await self._initialize_webhook_server()

            self.logger.info("All components initialized successfully")

        except Exception as e:
            error = handle_unexpected_error(e)
            self.logger.error(f"Failed to initialize application: {error.to_log_string()}")
            raise

    async def _initialize_database(self, db_path: str):
        """Initialize database with migrations."""
        self.logger.info(f"Initializing database at {db_path}...")

        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Run migrations
        await run_migrations(db_path)

        # Initialize repositories
        initialize_repositories(
            backend="sqlite",
            db_path=db_path,
            pool_size=5
        )

        # Initialize command logging
        await self._initialize_command_logging(db_path)

        self.logger.info("Database initialized successfully")

    async def _initialize_command_logging(self, db_path: str):
        """Initialize command logging system."""
        try:
            self.logger.info("Initializing command logging system...")

            # Create database connection for command logging
            db_connection = await aiosqlite.connect(db_path)

            # Create repository
            repository = CommandLogRepository(db_connection)

            # Create logger with configuration from environment
            config = LoggingConfig.from_env()
            self.command_logger = CommandLogger(repository, config)

            # Start async processing if enabled
            if config.async_writes:
                await self.command_logger.start()

            self.logger.info(f"Command logging initialized (enabled={config.enabled}, retention={config.retention_days} days)")

        except Exception as e:
            self.logger.warning(f"Failed to initialize command logging: {e}")
            self.logger.warning("Bot will continue without command logging")
            self.command_logger = None

    def _select_llm_provider(self) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        """
        Select LLM provider based on environment.

        Development uses Claude Direct (Anthropic).
        Production/Runtime uses OpenRouter.

        Returns:
            tuple: (provider_name, api_key, base_url, model)
                   Returns (None, None, None, None) if no API key is configured
        """
        llm_route = os.getenv('LLM_ROUTE', '').lower()

        # Explicit configuration takes precedence
        if llm_route == 'openrouter':
            openrouter_key = os.getenv('OPENROUTER_API_KEY')
            if not openrouter_key:
                self.logger.warning(
                    "LLM_ROUTE is set to 'openrouter' but OPENROUTER_API_KEY is not configured. "
                    "Summarization features will be unavailable."
                )
                return (None, None, None, None)
            return (
                'openrouter',
                openrouter_key,
                'https://openrouter.ai/api',  # Client appends /v1/messages
                None  # Model selection handled by SummaryOptions
            )

        # If not explicitly set, try OpenRouter
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if not openrouter_key:
            self.logger.warning(
                "OPENROUTER_API_KEY is not set. Summarization features will be unavailable. "
                "Dashboard and health endpoints will still work."
            )
            return (None, None, None, None)

        return (
            'openrouter',
            openrouter_key,
            'https://openrouter.ai/api',  # Client appends /v1/messages
            None  # Model selection handled by SummaryOptions
        )

    def _is_production_environment(self) -> bool:
        """
        Detect if running in production environment.

        Returns:
            bool: True if production, False if development
        """
        production_indicators = [
            os.getenv('RAILWAY_ENVIRONMENT'),
            os.getenv('RENDER'),
            os.getenv('HEROKU_APP_NAME'),
            os.getenv('FLY_APP_NAME'),
            os.getenv('NODE_ENV') == 'production',
            os.getenv('ENVIRONMENT') == 'production',
        ]
        return any(production_indicators)

    async def _initialize_core_components(self):
        """Initialize core summarization and message processing components."""
        self.logger.info("Initializing core components...")

        # Select LLM provider based on environment
        provider_name, api_key, base_url, model = self._select_llm_provider()

        claude_client = None
        if provider_name and api_key:
            self.logger.info(
                f"LLM Provider: {provider_name} | Model: {model} | "
                f"Environment: {'production' if self._is_production_environment() else 'development'}"
            )

            # Initialize Claude client with selected provider
            if base_url:
                claude_client = ClaudeClient(
                    api_key=api_key,
                    base_url=base_url,
                    max_retries=3
                )
            else:
                claude_client = ClaudeClient(
                    api_key=api_key,
                    max_retries=3
                )
        else:
            self.logger.warning("No LLM provider configured - summarization will be unavailable")

        # Initialize cache
        cache_backend = MemoryCache(
            max_size=self.config.cache_config.max_size,
            default_ttl=self.config.cache_config.default_ttl
        )
        cache = SummaryCache(cache_backend)

        # Initialize prompt resolver for custom prompts
        prompt_resolver = None
        guild_config_store = None

        try:
            from .prompts import PromptTemplateResolver, GuildPromptConfigStore
            from .data.sqlite import SQLiteConnection
            from cryptography.fernet import Fernet

            # Get database path from config or use default
            db_path = self.config.database_config.url.replace('sqlite:///', '') if self.config.database_config else "data/summarybot.db"

            self.logger.info(f"Initializing prompt system with database: {db_path}")

            # Initialize database connection
            db_connection = SQLiteConnection(db_path=db_path)
            await db_connection.connect()

            # Get encryption key from environment (or generate one)
            encryption_key = os.environ.get('PROMPT_TOKEN_ENCRYPTION_KEY')
            if encryption_key:
                encryption_key = encryption_key.encode()
                self.logger.info("Using PROMPT_TOKEN_ENCRYPTION_KEY from environment")
            else:
                # Generate ephemeral key (tokens won't persist across restarts)
                encryption_key = Fernet.generate_key()
                self.logger.warning("No PROMPT_TOKEN_ENCRYPTION_KEY set - using ephemeral key (tokens won't persist)")

            # Initialize guild config store
            guild_config_store = GuildPromptConfigStore(
                connection=db_connection,
                encryption_key=encryption_key
            )

            # Initialize prompt resolver
            prompt_resolver = PromptTemplateResolver(config_store=guild_config_store)

            self.logger.info("✓ Prompt resolver initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize prompt resolver: {e}", exc_info=True)
            prompt_resolver = None
            guild_config_store = None

        # Initialize summarization engine with prompt resolver
        self.summarization_engine = SummarizationEngine(
            claude_client=claude_client,
            cache=cache,
            prompt_resolver=prompt_resolver
        )

        # Store prompt resolver and config store for command handler
        self.prompt_resolver = prompt_resolver
        self.guild_config_store = guild_config_store

        self.logger.info("Core components initialized")

    async def _initialize_discord_bot(self):
        """Initialize Discord bot with command handlers."""
        self.logger.info("Initializing Discord bot...")

        # Initialize permission manager
        self.permission_manager = PermissionManager(self.config)

        # Create Discord bot
        self.discord_bot = SummaryBot(self.config)

        # Initialize message processor
        self.message_processor = MessageProcessor(self.discord_bot.client)

        # Initialize command handlers and wire them into the bot
        summarize_handler = SummarizeCommandHandler(
            summarization_engine=self.summarization_engine,
            permission_manager=self.permission_manager,
            message_fetcher=None,  # Will use direct Discord API calls
            message_filter=None,
            message_cleaner=None,
            command_logger=self.command_logger,  # Add command logging
            config_manager=self.config_manager  # Enable cross-channel summarization
        )

        # Initialize config command handler
        config_handler = ConfigCommandHandler(
            summarization_engine=self.summarization_engine,
            permission_manager=self.permission_manager,
            config_manager=self.config_manager
        )

        # Initialize prompt config handler if prompt resolver is available
        prompt_config_handler = None
        if self.prompt_resolver and self.guild_config_store:
            try:
                from .command_handlers.prompt_config import PromptConfigCommandHandler
                prompt_config_handler = PromptConfigCommandHandler(
                    config_store=self.guild_config_store,
                    resolver=self.prompt_resolver,
                    permission_manager=self.permission_manager,
                    command_logger=self.command_logger
                )
                self.logger.info("✓ Prompt config handler created successfully")
            except Exception as e:
                self.logger.error(f"Failed to create prompt config handler: {e}", exc_info=True)
                prompt_config_handler = None
        else:
            self.logger.warning(f"Prompt config handler not created - prompt_resolver={self.prompt_resolver is not None}, guild_config_store={self.guild_config_store is not None}")

        # Note: schedule_handler will be created after task_scheduler initialization

        # Add command handlers to bot services
        if not self.discord_bot.services:
            self.discord_bot.services = {}
        self.discord_bot.services['summarize_handler'] = summarize_handler
        self.discord_bot.services['config_handler'] = config_handler
        if prompt_config_handler:
            self.discord_bot.services['prompt_config_handler'] = prompt_config_handler
            self.logger.info("Prompt config handler initialized")

        # Event handlers are already registered in SummaryBot.__init__
        # Slash commands will be set up when bot starts

        self.logger.info("Discord bot initialized with command handlers")

    async def _initialize_scheduler(self):
        """Initialize task scheduler for automated summaries."""
        self.logger.info("Initializing task scheduler...")

        # Create task executor
        task_executor = TaskExecutor(
            summarization_engine=self.summarization_engine,
            message_processor=self.message_processor,
            discord_client=self.discord_bot.client,
            command_logger=self.command_logger  # Add command logging
        )

        # Create task persistence for surviving restarts
        task_persistence = TaskPersistence(storage_path="data/tasks")

        # Create task scheduler with persistence
        self.task_scheduler = TaskScheduler(
            task_executor=task_executor,
            persistence=task_persistence
        )

        # Initialize schedule command handler and add to bot services
        schedule_handler = ScheduleCommandHandler(
            summarization_engine=self.summarization_engine,
            permission_manager=self.permission_manager,
            task_scheduler=self.task_scheduler
        )
        self.discord_bot.services['schedule_handler'] = schedule_handler

        # Start scheduler
        await self.task_scheduler.start()

        self.logger.info("Task scheduler initialized and started")

    async def _initialize_webhook_server(self):
        """Initialize webhook API server for external integrations."""
        self.logger.info("Initializing webhook server...")

        self.webhook_server = WebhookServer(
            config=self.config,
            summarization_engine=self.summarization_engine,
            discord_bot=self.discord_bot,
            task_scheduler=self.task_scheduler,
            config_manager=self.config_manager
        )

        # Start webhook server in background
        await self.webhook_server.start_server()

        self.logger.info(
            f"Webhook server started at http://{self.config.webhook_config.host}:"
            f"{self.config.webhook_config.port}"
        )

    async def start(self):
        """Start the application and all services."""
        if not self.config:
            raise RuntimeError("Application not initialized. Call initialize() first.")

        # In webhook-only mode, we don't need a Discord bot
        if not self.webhook_only_mode and not self.discord_bot:
            raise RuntimeError("Application not initialized. Call initialize() first.")

        self.running = True
        self.logger.info("=" * 60)
        self.logger.info("Starting Summary Bot NG...")
        self.logger.info("=" * 60)

        # Setup signal handlers for graceful shutdown
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, self._signal_handler)

        try:
            # Log startup status
            if self.webhook_only_mode:
                self.logger.info("Mode: Webhook-Only (Dashboard API)")
            else:
                self.logger.info(f"Discord Bot: Ready")
                self.logger.info(f"Permission Manager: Active")
                self.logger.info(f"Task Scheduler: Running")

            self.logger.info(f"Summarization Engine: Ready")
            if self.webhook_server:
                self.logger.info(
                    f"Webhook API: http://{self.config.webhook_config.host}:"
                    f"{self.config.webhook_config.port}"
                )

            self.logger.info("=" * 60)
            self.logger.info("Summary Bot NG is now online!")
            self.logger.info("=" * 60)

            if self.webhook_only_mode:
                # In webhook-only mode, keep running until shutdown signal
                # The webhook server is already running in the background
                self.logger.info("Running in webhook-only mode. Press Ctrl+C to stop.")
                while self.running:
                    await asyncio.sleep(1)
            else:
                # Start Discord client (this blocks until shutdown)
                await self.discord_bot.start()

        except Exception as e:
            error = handle_unexpected_error(e)
            self.logger.error(f"Failed to start application: {error.to_log_string()}")
            raise

    async def stop(self):
        """Stop the application gracefully, shutting down all services."""
        self.logger.info("=" * 60)
        self.logger.info("Initiating graceful shutdown...")
        self.logger.info("=" * 60)

        self.running = False

        # Stop services in reverse order of initialization
        if self.webhook_server:
            self.logger.info("Stopping webhook server...")
            await self.webhook_server.stop_server()

        if self.task_scheduler:
            self.logger.info("Stopping task scheduler...")
            await self.task_scheduler.stop()

        if self.discord_bot and not self.webhook_only_mode:
            self.logger.info("Stopping Discord bot...")
            await self.discord_bot.stop()

        self.logger.info("=" * 60)
        self.logger.info("Summary Bot NG stopped cleanly")
        self.logger.info("=" * 60)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals (SIGINT, SIGTERM)."""
        signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        self.logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        asyncio.create_task(self.stop())


async def main():
    """Main entry point for Summary Bot NG.

    Initializes and starts all components:
    - Discord bot with slash commands
    - Permission management system
    - AI-powered summarization engine
    - Automated task scheduling
    - REST API webhook server
    - SQLite database persistence
    """
    # Early startup message for debugging
    print("Summary Bot NG starting...", flush=True)

    app = SummaryBotApp()

    try:
        print("Initializing application...", flush=True)

        # Initialize with default database path (config_path may not exist, that's OK)
        await app.initialize(
            config_path=None,  # Use environment variables only
            db_path="data/summarybot.db"
        )

        print("Application initialized, starting services...", flush=True)

        # Start all services
        await app.start()

    except KeyboardInterrupt:
        await app.stop()
    except Exception as e:
        print(f"FATAL ERROR: {e}", flush=True)
        logging.error(f"Fatal error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def emergency_server():
    """Start a minimal server when main app fails to initialize.

    This ensures health checks pass and we can diagnose issues.
    """
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import uvicorn

    app = FastAPI(title="Summary Bot NG - Emergency Mode")

    @app.get("/health")
    async def health():
        return JSONResponse(
            status_code=200,
            content={
                "status": "emergency",
                "message": "Main application failed to start. Check logs for details.",
                "version": "2.0.0"
            }
        )

    @app.get("/")
    async def root():
        return {"status": "emergency", "message": "Application in emergency mode"}

    config = uvicorn.Config(app, host="0.0.0.0", port=5000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    print("=== Starting Summary Bot NG ===", flush=True, file=sys.stderr)
    try:
        asyncio.run(main())
    except Exception as e:
        # If main() fails, start emergency server for debugging
        print(f"MAIN FAILED: {e}", flush=True, file=sys.stderr)
        import traceback
        traceback.print_exc()
        print("Starting emergency server for diagnostics...", flush=True, file=sys.stderr)
        asyncio.run(emergency_server())
