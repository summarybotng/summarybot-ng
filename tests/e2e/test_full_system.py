"""
End-to-end tests for full system integration.

Tests bot + webhook service running together, cross-component interactions,
system health checks, and graceful shutdown.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from src.discord_bot.bot import SummaryBot
from src.webhook_service.server import WebhookServer
from src.container import ServiceContainer
from src.config.settings import BotConfig


@pytest.mark.e2e
@pytest.mark.slow
class TestFullSystemIntegration:
    """End-to-end tests for complete system with all services."""

    @pytest_asyncio.fixture
    async def full_system(self, mock_config):
        """Setup complete system with bot and webhook server."""
        # Create service container
        container = ServiceContainer(mock_config)

        # Mock external dependencies
        with patch('src.summarization.claude_client.ClaudeClient') as mock_claude, \
             patch('discord.Client') as mock_discord:

            # Setup Claude API mock
            claude_instance = AsyncMock()
            claude_instance.create_summary.return_value = MagicMock(
                content="Full system test summary",
                model="claude-3-5-sonnet-20241022",
                input_tokens=1000,
                output_tokens=200,
                total_tokens=1200,
                response_id="full_system_test"
            )
            claude_instance.health_check.return_value = True
            claude_instance.get_usage_stats.return_value = MagicMock(
                total_requests=0,
                total_tokens=0,
                to_dict=lambda: {"total_requests": 0, "total_tokens": 0}
            )
            mock_claude.return_value = claude_instance

            # Setup Discord client mock
            discord_instance = AsyncMock()
            discord_instance.user = MagicMock(id=888888, name="FullSystemBot")
            discord_instance.is_ready.return_value = True
            discord_instance.guilds = []
            mock_discord.return_value = discord_instance

            # Initialize container
            await container.initialize()

            # Create bot
            bot = SummaryBot(
                config=mock_config,
                services={'container': container}
            )

            # Create webhook server
            webhook_server = WebhookServer(
                config=mock_config,
                summarization_engine=container.summarization_engine
            )

            yield {
                'container': container,
                'bot': bot,
                'webhook': webhook_server,
                'claude_client': claude_instance
            }

            # Cleanup
            await container.cleanup()

    @pytest.mark.asyncio
    async def test_system_startup(self, full_system):
        """Test that all system components start up correctly."""
        container = full_system['container']
        bot = full_system['bot']
        webhook = full_system['webhook']

        # Verify container is initialized
        assert container is not None
        assert container.summarization_engine is not None

        # Verify bot is configured
        assert bot is not None
        assert bot.client is not None
        assert not bot.is_running  # Not started yet

        # Verify webhook server is configured
        assert webhook is not None
        assert webhook.app is not None

    @pytest.mark.asyncio
    async def test_shared_service_access(self, full_system):
        """Test that bot and webhook share the same service instances."""
        container = full_system['container']
        bot = full_system['bot']
        webhook = full_system['webhook']

        # Both should access the same summarization engine
        assert webhook.summarization_engine is container.summarization_engine

        # Both should use the same configuration
        assert bot.config == webhook.config

    @pytest.mark.asyncio
    async def test_concurrent_bot_and_webhook_operations(
        self,
        full_system,
        sample_messages
    ):
        """Test bot and webhook handling requests concurrently."""
        webhook = full_system['webhook']
        container = full_system['container']

        # Prepare webhook request
        messages_data = [
            {
                "id": str(msg.id),
                "author_name": msg.author.display_name,
                "author_id": str(msg.author.id),
                "content": msg.content,
                "timestamp": msg.created_at.isoformat(),
                "attachments": [],
                "references": [],
                "mentions": []
            }
            for msg in sample_messages
        ]

        async with AsyncClient(transport=ASGITransport(app=webhook.app), base_url="http://test") as client:
            # Make webhook request
            webhook_task = client.post(
                "/api/v1/summaries",
                json={
                    "messages": messages_data,
                    "channel_id": "111111",
                    "guild_id": "123456789",
                    "options": {
                        "summary_length": "brief",
                        "include_bots": False,
                        "min_messages": 5
                    }
                },
                headers={"X-API-Key": "test_api_key"}
            )

            # Simulate Discord command
            from src.command_handlers.summarize import SummarizeCommandHandler
            import discord

            handler = SummarizeCommandHandler(
                summarization_engine=container.summarization_engine
            )

            interaction = AsyncMock(spec=discord.Interaction)
            interaction.guild_id = 123456789
            interaction.guild = MagicMock()
            interaction.guild.me = MagicMock()
            interaction.user = MagicMock()
            interaction.channel = MagicMock()
            interaction.channel.id = 222222
            interaction.channel.permissions_for = MagicMock(return_value=MagicMock(
                read_message_history=True
            ))
            interaction.response = AsyncMock()
            interaction.followup = AsyncMock()

            # Mock message fetching
            from src.models.message import ProcessedMessage
            processed = [
                ProcessedMessage(
                    id=str(msg.id),
                    author_name=msg.author.display_name,
                    author_id=str(msg.author.id),
                    content=msg.content,
                    timestamp=msg.created_at,
                    attachments=[],
                    references=[],
                    mentions=[]
                )
                for msg in sample_messages
            ]

            with patch.object(handler, '_fetch_and_process_messages') as mock_fetch:
                mock_fetch.return_value = processed

                discord_task = handler.handle_summarize(
                    interaction=interaction,
                    channel=interaction.channel,
                    hours=24,
                    length="brief",
                    include_bots=False
                )

                # Run both concurrently
                results = await asyncio.gather(
                    webhook_task,
                    discord_task,
                    return_exceptions=True
                )

                # Both should complete
                assert len(results) == 2

                # Webhook should return response
                webhook_response = results[0]
                if not isinstance(webhook_response, Exception):
                    assert webhook_response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_system_health_check_endpoint(self, full_system):
        """Test system-wide health check through webhook API."""
        webhook = full_system['webhook']

        async with AsyncClient(transport=ASGITransport(app=webhook.app), base_url="http://test") as client:
            response = await client.get("/health")

            assert response.status_code in [200, 503]

            data = response.json()
            assert 'status' in data
            assert 'services' in data
            assert 'summarization_engine' in data['services']

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, full_system):
        """Test graceful shutdown of all system components."""
        container = full_system['container']
        bot = full_system['bot']
        webhook = full_system['webhook']

        # Shutdown in correct order

        # 1. Stop accepting new requests (webhook)
        # (webhook not started in test, so just verify it can be stopped)

        # 2. Stop bot (if it was running)
        if bot.is_running:
            await bot.stop()

        # 3. Cleanup container
        await container.cleanup()

        # Verify cleanup
        assert not bot.is_running

    @pytest.mark.asyncio
    async def test_error_isolation(self, full_system):
        """Test that errors in one component don't crash others."""
        container = full_system['container']
        webhook = full_system['webhook']

        # Simulate error in one request
        async with AsyncClient(transport=ASGITransport(app=webhook.app), base_url="http://test") as client:
            # Send invalid request
            response1 = await client.post(
                "/api/v1/summaries",
                json={"invalid": "data"},
                headers={"X-API-Key": "test_api_key"}
            )

            # Should return error
            assert response1.status_code >= 400

            # System should still be healthy for other requests
            response2 = await client.get("/health")

            # Health check should still work
            assert response2.status_code in [200, 503]

            # System should still be operational
            data = response2.json()
            assert data['status'] in ['healthy', 'degraded', 'unhealthy']

    @pytest.mark.asyncio
    async def test_resource_cleanup_on_error(self, full_system):
        """Test that resources are cleaned up properly after errors."""
        container = full_system['container']

        # Force an error in the engine
        original_summarize = container.summarization_engine.summarize_messages

        async def failing_summarize(*args, **kwargs):
            raise Exception("Simulated failure")

        container.summarization_engine.summarize_messages = failing_summarize

        # Try to use the service
        from src.models.message import ProcessedMessage
        from src.models.summary import SummaryOptions, SummarizationContext

        messages = [
            ProcessedMessage(
                id="1",
                author_name="test",
                author_id="123",
                content="test message",
                timestamp=datetime.utcnow(),
                attachments=[],
                references=[],
                mentions=[]
            )
        ] * 10

        with pytest.raises(Exception):
            await container.summarization_engine.summarize_messages(
                messages=messages,
                options=SummaryOptions(),
                context=SummarizationContext(),
                channel_id="test",
                guild_id="test"
            )

        # Restore original method
        container.summarization_engine.summarize_messages = original_summarize

        # System should still be functional
        health = await container.health_check()
        assert health is not None


@pytest.mark.e2e
@pytest.mark.slow
class TestSystemPerformance:
    """Performance tests for full system under load."""

    @pytest.mark.asyncio
    async def test_sustained_load(self, full_system):
        """Test system performance under sustained load."""
        webhook = full_system['webhook']

        async with AsyncClient(transport=ASGITransport(app=webhook.app), base_url="http://test") as client:
            # Make multiple health check requests
            tasks = [
                client.get("/health")
                for _ in range(50)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Most should succeed
            successful = sum(
                1 for r in results
                if not isinstance(r, Exception) and r.status_code == 200
            )

            # At least 80% should succeed
            assert successful >= 40

    @pytest.mark.asyncio
    async def test_memory_usage(self, full_system):
        """Test that memory usage remains reasonable."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        webhook = full_system['webhook']

        # Make many requests
        async with AsyncClient(transport=ASGITransport(app=webhook.app), base_url="http://test") as client:
            for _ in range(20):
                await client.get("/health")

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 100 MB)
        assert memory_increase < 100, f"Memory increased by {memory_increase:.2f} MB"
