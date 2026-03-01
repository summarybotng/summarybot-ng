"""
Pytest configuration and fixtures for Summary Bot NG test suite.

This module provides shared fixtures and configuration for all test modules,
supporting unit, integration, and end-to-end testing scenarios.
"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import discord
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Test environment setup
os.environ["TESTING"] = "1"
os.environ["CLAUDE_API_KEY"] = "test_api_key"
os.environ["DISCORD_TOKEN"] = "test_discord_token"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    from src.config.settings import BotConfig, GuildConfig, SummaryOptions, WebhookConfig, DatabaseConfig

    guild_config = GuildConfig(
        guild_id="123456789",
        enabled_channels=["channel1", "channel2"],
        excluded_channels=["excluded1"],
        default_summary_options=SummaryOptions(
            summary_length="standard",
            include_bots=False,
            include_attachments=True,
            min_messages=5
        ),
        permission_settings={}
    )

    webhook_config = WebhookConfig(
        host="127.0.0.1",
        port=5000,

        api_keys={"test_api_key": "test_user"},
        rate_limit=100,
        cors_origins=["*"]
    )

    database_config = DatabaseConfig(
        url="sqlite+aiosqlite:///:memory:",
        pool_size=5,
        max_overflow=10
    )

    return BotConfig(
        discord_token="test_token",
        guild_configs={"123456789": guild_config},
        webhook_config=webhook_config,
        database_config=database_config,
        max_message_batch=10000,
        cache_ttl=3600
    )


@pytest.fixture
def mock_discord_client():
    """Mock Discord client for testing."""
    client = AsyncMock(spec=discord.Client)
    client.user = MagicMock()
    client.user.id = 987654321
    client.user.name = "TestBot"
    client.user.discriminator = "0000"
    client.user.bot = True

    # Mock common async methods
    client.wait_until_ready = AsyncMock()
    client.close = AsyncMock()
    client.start = AsyncMock()
    client.login = AsyncMock()

    # Mock properties
    client.guilds = []
    client.latency = 0.05
    client.is_closed.return_value = False
    client.is_ready.return_value = True

    return client


@pytest.fixture
def mock_bot():
    """Mock Discord bot (commands.Bot) for testing."""
    from discord.ext import commands

    bot = AsyncMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = 987654321
    bot.user.name = "TestBot"
    bot.user.discriminator = "0000"
    bot.user.bot = True

    # Mock command tree for app commands
    bot.tree = AsyncMock()
    bot.tree.sync = AsyncMock()

    # Mock methods
    bot.wait_until_ready = AsyncMock()
    bot.close = AsyncMock()
    bot.add_cog = AsyncMock()
    bot.remove_cog = AsyncMock()

    # Mock properties
    bot.guilds = []
    bot.commands = []
    bot.cogs = {}
    bot.extensions = {}

    return bot


@pytest.fixture
def mock_discord_guild():
    """Mock Discord guild for testing."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.member_count = 100
    return guild


@pytest.fixture
def mock_discord_channel():
    """Mock Discord text channel for testing."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 987654321
    channel.name = "test-channel"
    channel.guild = MagicMock()
    channel.guild.id = 123456789
    return channel


@pytest.fixture
def mock_discord_user():
    """Mock Discord user for testing."""
    user = MagicMock(spec=discord.User)
    user.id = 111111111
    user.name = "testuser"
    user.display_name = "Test User"
    user.bot = False
    return user


@pytest.fixture
def mock_discord_message(mock_discord_user, mock_discord_channel):
    """Mock Discord message for testing."""
    message = MagicMock(spec=discord.Message)
    message.id = 555555555
    message.author = mock_discord_user
    message.channel = mock_discord_channel
    message.content = "Test message content"
    message.created_at = datetime.utcnow()
    message.attachments = []
    message.embeds = []
    message.reference = None
    return message


@pytest.fixture
def sample_messages(mock_discord_user, mock_discord_channel):
    """Generate sample Discord messages for testing."""
    messages = []
    base_time = datetime.utcnow() - timedelta(hours=1)
    
    for i in range(10):
        message = MagicMock(spec=discord.Message)
        message.id = 1000000000 + i
        message.author = mock_discord_user
        message.channel = mock_discord_channel
        message.content = f"Test message {i+1}"
        message.created_at = base_time + timedelta(minutes=i * 5)
        message.attachments = []
        message.embeds = []
        message.reference = None
        messages.append(message)
    
    return messages


@pytest.fixture
def mock_claude_client():
    """Mock Claude API client for testing."""
    from src.summarization.claude_client import ClaudeClient, ClaudeResponse

    client = AsyncMock(spec=ClaudeClient)

    # Default successful response
    default_response = ClaudeResponse(
        content="This is a test summary of the conversation.",
        model="claude-3-sonnet-20240229",
        usage={
            "input_tokens": 1000,
            "output_tokens": 200
        },
        stop_reason="end_turn",
        response_id="test_response_123",
        created_at=datetime.utcnow()
    )

    client.create_summary.return_value = default_response
    client.health_check.return_value = True
    client.get_usage_stats.return_value = MagicMock(
        total_requests=10,
        total_input_tokens=10000,
        total_output_tokens=2000,
        total_cost_usd=0.156,
        errors_count=0,
        rate_limit_hits=0
    )
    client.estimate_cost.return_value = 0.0156

    return client


@pytest.fixture
def claude_response_factory():
    """Factory for creating ClaudeResponse test objects."""
    from src.summarization.claude_client import ClaudeResponse

    def create_response(**kwargs):
        defaults = {
            "content": "Test summary content",
            "model": "claude-3-sonnet-20240229",
            "usage": {"input_tokens": 1000, "output_tokens": 200},
            "stop_reason": "end_turn",
            "response_id": "test_response_123",
            "created_at": datetime.utcnow()
        }
        defaults.update(kwargs)
        return ClaudeResponse(**defaults)

    return create_response


@pytest.fixture
def mock_database():
    """Mock database session for testing."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_cache():
    """Mock cache interface for testing."""
    from src.cache.base import CacheInterface
    
    cache = AsyncMock(spec=CacheInterface)
    cache.get.return_value = None
    cache.set.return_value = True
    cache.delete.return_value = True
    cache.clear.return_value = 0
    return cache


@pytest_asyncio.fixture
async def test_db_engine():
    """Create test database engine with automatic schema setup."""
    from src.models.base import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_db_engine):
    """Create test database session with automatic rollback."""
    async_session = sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )

    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def test_db_session_factory(test_db_engine):
    """Factory for creating multiple test database sessions."""
    async_session = sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async def create_session():
        async with async_session() as session:
            yield session

    return create_session


@pytest.fixture
def mock_summarization_engine():
    """Mock summarization engine for testing."""
    from src.summarization.engine import SummarizationEngine
    
    engine = AsyncMock(spec=SummarizationEngine)
    engine.summarize_messages.return_value = MagicMock(
        id="test_summary_123",
        channel_id="987654321",
        guild_id="123456789",
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow(),
        message_count=10,
        key_points=["Point 1", "Point 2"],
        action_items=[],
        technical_terms=[],
        participants=["testuser"],
        summary_text="This is a test summary.",
        metadata={},
        created_at=datetime.utcnow()
    )
    return engine


@pytest.fixture
def mock_permission_manager():
    """Mock permission manager for testing."""
    from src.permissions.manager import PermissionManager
    
    manager = AsyncMock(spec=PermissionManager)
    manager.check_channel_access.return_value = True
    manager.check_command_permission.return_value = True
    manager.get_user_permissions.return_value = MagicMock(
        can_summarize=True,
        can_schedule=True,
        can_configure=False
    )
    return manager


@pytest.fixture
def mock_message_fetcher():
    """Mock message fetcher for testing."""
    from src.message_processing.fetcher import MessageFetcher
    
    fetcher = AsyncMock(spec=MessageFetcher)
    return fetcher


@pytest.fixture
def mock_task_scheduler():
    """Mock task scheduler for testing."""
    from src.scheduling.scheduler import TaskScheduler
    
    scheduler = AsyncMock(spec=TaskScheduler)
    scheduler.schedule_task.return_value = "task_123"
    scheduler.cancel_task.return_value = True
    scheduler.get_scheduled_tasks.return_value = []
    return scheduler


@pytest.fixture
def mock_webhook_server():
    """Mock webhook server for testing."""
    from src.webhook_service.server import WebhookServer
    
    server = AsyncMock(spec=WebhookServer)
    return server


# Test data factories
@pytest.fixture
def summary_result_factory():
    """Factory for creating SummaryResult test objects."""
    def create_summary_result(**kwargs):
        from src.models.summary import SummaryResult
        
        defaults = {
            "id": "test_summary_123",
            "channel_id": "987654321",
            "guild_id": "123456789",
            "start_time": datetime.utcnow() - timedelta(hours=1),
            "end_time": datetime.utcnow(),
            "message_count": 10,
            "key_points": ["Point 1", "Point 2"],
            "action_items": [],
            "technical_terms": [],
            "participants": ["testuser"],
            "summary_text": "This is a test summary.",
            "metadata": {},
            "created_at": datetime.utcnow()
        }
        defaults.update(kwargs)
        return SummaryResult(**defaults)
    
    return create_summary_result


@pytest.fixture
def processed_message_factory():
    """Factory for creating ProcessedMessage test objects."""
    def create_processed_message(**kwargs):
        from src.models.message import ProcessedMessage
        
        defaults = {
            "id": "555555555",
            "author_name": "testuser",
            "author_id": "111111111",
            "content": "Test message content",
            "timestamp": datetime.utcnow(),
            "thread_info": None,
            "attachments": [],
            "references": []
        }
        defaults.update(kwargs)
        return ProcessedMessage(**defaults)
    
    return create_processed_message


# Error simulation fixtures
@pytest.fixture
def claude_api_error():
    """Simulate Claude API error."""
    from src.exceptions.summarization import ClaudeAPIError
    return ClaudeAPIError("API rate limit exceeded", "RATE_LIMIT_EXCEEDED")


@pytest.fixture
def discord_permission_error():
    """Simulate Discord permission error."""
    from src.exceptions.discord_errors import DiscordPermissionError
    return DiscordPermissionError("Missing read message history permission", "MISSING_PERMISSIONS")


@pytest.fixture
def insufficient_content_error():
    """Simulate insufficient content error."""
    from src.exceptions.summarization import InsufficientContentError
    return InsufficientContentError("Not enough messages for summarization", "INSUFFICIENT_CONTENT")


# Test utilities
@pytest.fixture
def assert_logs():
    """Utility for asserting log messages in tests."""
    def _assert_logs(caplog, level, message_contains):
        assert any(
            level.upper() in record.levelname and message_contains in record.message
            for record in caplog.records
        )
    return _assert_logs


@pytest.fixture
def performance_monitor():
    """Monitor performance during tests."""
    import time
    
    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def duration(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None
    
    return PerformanceMonitor()


# Async test markers
pytest_asyncio.plugin.pytest_asyncio_mode = "auto"


# Custom markers for test categorization
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )


@pytest_asyncio.fixture
async def mock_discord_bot_instance():
    """Mock fully configured bot instance for integration testing."""
    from src.discord_bot.bot import SummaryBot

    bot = AsyncMock(spec=SummaryBot)
    bot.config = MagicMock()
    bot.summarization_engine = AsyncMock()
    bot.message_fetcher = AsyncMock()
    bot.permission_manager = AsyncMock()
    bot.task_scheduler = AsyncMock()

    # Mock methods
    bot.setup_hook = AsyncMock()
    bot.on_ready = AsyncMock()
    bot.on_message = AsyncMock()
    bot.on_command_error = AsyncMock()

    return bot


@pytest.fixture
def mock_http_client():
    """Mock aiohttp client session for testing."""
    from aiohttp import ClientSession

    session = AsyncMock(spec=ClientSession)

    # Mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"status": "success"})
    mock_response.text = AsyncMock(return_value="Success")
    mock_response.read = AsyncMock(return_value=b"Success")

    session.get.return_value.__aenter__.return_value = mock_response
    session.post.return_value.__aenter__.return_value = mock_response
    session.close = AsyncMock()

    return session


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    redis = AsyncMock()

    # Mock common Redis operations
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    redis.expire = AsyncMock(return_value=True)
    redis.ttl = AsyncMock(return_value=-1)
    redis.keys = AsyncMock(return_value=[])
    redis.flushdb = AsyncMock(return_value=True)

    # Mock pipeline
    pipeline = AsyncMock()
    pipeline.execute = AsyncMock(return_value=[])
    redis.pipeline.return_value = pipeline

    return redis


# Cleanup hooks
@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Cleanup resources after each test."""
    yield
    # Synchronous cleanup only
    pass


@pytest.fixture
def freeze_time():
    """Freeze time for testing time-dependent functionality."""
    frozen_time = datetime(2024, 1, 15, 12, 0, 0)

    def get_frozen_time():
        return frozen_time

    return get_frozen_time


@pytest.fixture
def env_vars(monkeypatch):
    """Fixture for managing environment variables in tests."""
    def set_env(**kwargs):
        for key, value in kwargs.items():
            monkeypatch.setenv(key, str(value))

    return set_env


@pytest.fixture
def mock_file_system(tmp_path):
    """Create a mock file system structure for testing."""
    # Create common directories
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "cache").mkdir()
    (tmp_path / "config").mkdir()

    # Create sample config file
    config_file = tmp_path / "config" / "bot_config.json"
    config_file.write_text('{"version": "1.0.0"}')

    return tmp_path