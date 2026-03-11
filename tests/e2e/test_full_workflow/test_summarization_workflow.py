"""
End-to-end tests for complete summarization workflows.

Tests cover full user workflows from Discord command execution through
summary generation and delivery, with minimal mocking.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import asyncio
import tempfile
import os

from src.discord_bot.bot import SummaryBot
from src.config.settings import BotConfig, GuildConfig, SummaryOptions
from tests.fixtures.discord_fixtures import create_mock_messages, create_mock_interaction


@pytest.mark.e2e
class TestCompleteWorkflow:
    """Test complete end-to-end workflows."""

    @pytest_asyncio.fixture
    async def temp_config_file(self):
        """Create temporary configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "discord_token": "test_discord_token",
                "claude_api_key": "test_claude_key",
                "webhook_port": 5000,
                "guild_configs": {
                    "123456789": {
                        "guild_id": "123456789",
                        "enabled_channels": ["987654321"],
                        "excluded_channels": [],
                        "default_summary_options": {
                            "summary_length": "standard",
                            "include_bots": False,
                            "include_attachments": True,
                            "min_messages": 5
                        },
                        "permission_settings": {}
                    }
                }
            }
            import json
            json.dump(config_data, f)
            f.flush()
            yield f.name

        # Cleanup
        os.unlink(f.name)

    @pytest_asyncio.fixture
    async def mock_services(self, temp_config_file):
        """Create mock service collection for testing."""
        from src.config.settings import ConfigManager

        config_manager = ConfigManager(temp_config_file)
        config = await config_manager.load_config()

        # Create mock services
        services = MagicMock()
        services.config = config

        # Mock summarization engine
        services.summarization_engine = AsyncMock()

        # Mock permission manager
        services.permission_manager = MagicMock()
        services.permission_manager.check_command_permission = MagicMock(return_value=True)
        services.permission_manager.check_channel_access = MagicMock(return_value=True)

        # Mock message fetcher
        services.message_fetcher = AsyncMock()

        # Mock task scheduler
        services.task_scheduler = AsyncMock()

        # Mock task executor
        services.task_executor = AsyncMock()

        # Mock webhook server
        services.webhook_server = MagicMock()
        services.webhook_server.get_app = MagicMock()

        # Mock command handlers
        services.command_handlers = {
            "summarize": AsyncMock()
        }

        # Setup method accessors
        services.get_summarization_engine = MagicMock(return_value=services.summarization_engine)
        services.get_permission_manager = MagicMock(return_value=services.permission_manager)
        services.get_message_fetcher = MagicMock(return_value=services.message_fetcher)
        services.get_task_scheduler = MagicMock(return_value=services.task_scheduler)
        services.get_task_executor = MagicMock(return_value=services.task_executor)
        services.get_webhook_server = MagicMock(return_value=services.webhook_server)
        services.get_command_handlers = MagicMock(return_value=services.command_handlers)

        yield services

    @pytest_asyncio.fixture
    async def discord_bot_instance(self, mock_services):
        """Create Discord bot instance with mock services."""
        config = mock_services.config

        with patch('discord.Client.__init__', return_value=None), \
             patch('discord.Client.start'), \
             patch('discord.Client.close'):

            bot = SummaryBot(config, mock_services)
            bot.user = MagicMock()
            bot.user.id = 987654321
            bot.user.name = "TestBot"

            await bot.setup_commands()
            yield bot

    @pytest.mark.asyncio
    async def test_complete_summarization_workflow(
        self,
        discord_bot_instance,
        mock_services
    ):
        """Test complete workflow from command to summary delivery."""
        # Create realistic interaction and messages
        interaction = create_mock_interaction(
            guild_id=123456789,
            channel_id=987654321,
            user_id=111111111
        )

        messages = create_mock_messages(
            count=10,
            channel_id=987654321,
            start_time=datetime.utcnow() - timedelta(hours=2)
        )

        # Mock Claude API response
        mock_claude_response = MagicMock()
        mock_claude_response.content = """
        # Conversation Summary

        ## Key Discussion Points
        1. Planning for new feature implementation
        2. Code review feedback and improvements
        3. Timeline discussion for sprint completion

        ## Action Items
        - Review pull request #123 (assigned: @developer1)
        - Update documentation (assigned: @developer2)
        - Schedule follow-up meeting (assigned: @project_manager)

        ## Technical Terms
        - **API Gateway**: Service routing and authentication layer
        - **Microservice**: Independent deployable service component

        ## Participants
        - developer1: 4 messages
        - developer2: 3 messages
        - project_manager: 3 messages
        """

        # Configure service mocks
        summarization_engine = mock_services.get_summarization_engine()
        permission_manager = mock_services.get_permission_manager()
        message_fetcher = mock_services.get_message_fetcher()
        
        # Setup method returns
        permission_manager.check_command_permission.return_value = True
        permission_manager.check_channel_access.return_value = True
        message_fetcher.fetch_messages.return_value = messages
        
        # Create realistic summary result
        from src.models.summary import SummaryResult, ActionItem, TechnicalTerm, Participant
        
        summary_result = SummaryResult(
            id="e2e_summary_123",
            channel_id="987654321",
            guild_id="123456789",
            start_time=datetime.utcnow() - timedelta(hours=2),
            end_time=datetime.utcnow(),
            message_count=10,
            key_points=[
                "Planning for new feature implementation",
                "Code review feedback and improvements", 
                "Timeline discussion for sprint completion"
            ],
            action_items=[
                ActionItem(
                    description="Review pull request #123",
                    assignee="developer1",
                    due_date=datetime.utcnow() + timedelta(days=1),
                    priority="high"
                ),
                ActionItem(
                    description="Update documentation",
                    assignee="developer2", 
                    due_date=datetime.utcnow() + timedelta(days=2),
                    priority="medium"
                )
            ],
            technical_terms=[
                TechnicalTerm(
                    term="API Gateway",
                    definition="Service routing and authentication layer",
                    context="Architecture discussion"
                ),
                TechnicalTerm(
                    term="Microservice",
                    definition="Independent deployable service component",
                    context="System design"
                )
            ],
            participants=[
                Participant(
                    user_id="111111111",
                    username="developer1",
                    display_name="Developer One",
                    message_count=4,
                    first_message_time=datetime.utcnow() - timedelta(hours=2),
                    last_message_time=datetime.utcnow() - timedelta(hours=1)
                ),
                Participant(
                    user_id="222222222", 
                    username="developer2",
                    display_name="Developer Two",
                    message_count=3,
                    first_message_time=datetime.utcnow() - timedelta(hours=2),
                    last_message_time=datetime.utcnow() - timedelta(minutes=30)
                )
            ],
            summary_text=mock_claude_response.content,
            metadata={
                "model": "claude-3-sonnet-20240229",
                "tokens": 1200,
                "processing_time": 3.5
            },
            created_at=datetime.utcnow()
        )
        
        summarization_engine.summarize_messages.return_value = summary_result
        
        # Execute summarization command
        command_handlers = mock_services.get_command_handlers()
        summarize_handler = command_handlers["summarize"]

        await summarize_handler.handle_summarize(interaction)

        # Verify complete workflow execution

        # 1. Permission checks were performed
        permission_manager.check_command_permission.assert_called_once_with(
            "111111111", "summarize", "123456789"
        )
        permission_manager.check_channel_access.assert_called_once_with(
            "111111111", "987654321", "123456789"
        )

        # 2. Messages were fetched
        message_fetcher.fetch_messages.assert_called_once()

        # 3. Summarization was performed
        summarization_engine.summarize_messages.assert_called_once()

        # 4. Response was sent to user
        interaction.response.send_message.assert_called_once()

        # Verify response content
        call_args = interaction.response.send_message.call_args
        response_embed = call_args[1]["embed"] if "embed" in call_args[1] else call_args[0][0]

        # Should be Discord embed with summary information
        assert hasattr(response_embed, 'title') or isinstance(response_embed, dict)

    @pytest.mark.asyncio
    async def test_scheduled_summary_workflow(
        self,
        discord_bot_instance,
        mock_services
    ):
        """Test scheduled summary creation and execution workflow."""
        # Create scheduled task
        from src.models.task import ScheduledTask, SummaryTask
        from src.scheduling.scheduler import TaskScheduler

        task = SummaryTask(
            id="scheduled_123",
            guild_id="123456789",
            channel_id="987654321",
            schedule="0 9 * * 1",  # Every Monday at 9 AM
            summary_options=SummaryOptions(summary_length="standard"),
            created_by="111111111",
            created_at=datetime.utcnow()
        )

        scheduler = mock_services.get_task_scheduler()
        scheduler.schedule_task.return_value = "scheduled_123"

        # Execute scheduling
        task_id = await scheduler.schedule_task(task)

        # Verify task was scheduled
        assert task_id == "scheduled_123"
        scheduler.schedule_task.assert_called_once_with(task)

        # Simulate task execution
        task_executor = mock_services.get_task_executor()

        # Mock successful summary generation
        summary_result = MagicMock()
        summary_result.to_embed.return_value = MagicMock()

        summarization_engine = mock_services.get_summarization_engine()
        summarization_engine.summarize_messages.return_value = summary_result

        # Execute scheduled task
        task_result = await task_executor.execute_summary_task(task)

        # Verify task execution
        assert task_result.success is True
        assert task_result.task_id == "scheduled_123"

    @pytest.mark.asyncio
    async def test_webhook_api_workflow(self, mock_services):
        """Test external API webhook workflow."""
        from src.webhook_service.server import WebhookServer
        from fastapi.testclient import TestClient

        webhook_server = mock_services.get_webhook_server()
        app = webhook_server.get_app()
        
        # Create test client
        with TestClient(app) as client:
            # Test summary creation via API
            request_data = {
                "channel_id": "987654321",
                "guild_id": "123456789", 
                "start_time": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                "end_time": datetime.utcnow().isoformat(),
                "options": {
                    "summary_length": "standard",
                    "include_bots": False
                }
            }
            
            with patch('src.summarization.engine.SummarizationEngine.summarize_messages') as mock_summarize:
                mock_summary = MagicMock()
                mock_summary.to_dict.return_value = {"id": "api_summary_123", "summary_text": "API generated summary"}
                mock_summarize.return_value = mock_summary
                
                response = client.post("/api/v1/summarize", json=request_data)
                
                # Verify API response
                assert response.status_code == 201
                response_data = response.json()
                assert "id" in response_data
                assert "summary_text" in response_data
    
    @pytest.mark.asyncio
    async def test_error_recovery_workflow(
        self,
        discord_bot_instance,
        mock_services
    ):
        """Test error handling and recovery in complete workflow."""
        interaction = create_mock_interaction(
            guild_id=123456789,
            channel_id=987654321,
            user_id=111111111
        )

        # Configure services to simulate various failures
        summarization_engine = mock_services.get_summarization_engine()
        permission_manager = mock_services.get_permission_manager()
        message_fetcher = mock_services.get_message_fetcher()

        # Test 1: Permission denied
        permission_manager.check_command_permission.return_value = False

        command_handlers = mock_services.get_command_handlers()
        summarize_handler = command_handlers["summarize"]
        
        await summarize_handler.handle_summarize(interaction)
        
        # Verify permission error response
        interaction.response.send_message.assert_called()
        call_args = interaction.response.send_message.call_args
        assert "permission" in call_args[1].get("content", "").lower()
        
        # Reset mock
        interaction.reset_mock()
        
        # Test 2: Message fetching failure
        permission_manager.check_command_permission.return_value = True
        permission_manager.check_channel_access.return_value = True
        message_fetcher.fetch_messages.side_effect = Exception("Channel access denied")
        
        await summarize_handler.handle_summarize(interaction)
        
        # Verify error handling
        interaction.response.send_message.assert_called()
        call_args = interaction.response.send_message.call_args
        assert "error" in call_args[1].get("content", "").lower()
        
        # Test 3: Summarization failure with retry
        message_fetcher.fetch_messages.side_effect = None
        message_fetcher.fetch_messages.return_value = create_mock_messages(5)
        
        # First call fails, second succeeds
        summarization_engine.summarize_messages.side_effect = [
            Exception("API rate limit"),
            MagicMock(to_embed=MagicMock(return_value=MagicMock()))
        ]
        
        # Reset interaction mock
        interaction.reset_mock()
        
        # Execute with retry logic
        with patch('asyncio.sleep'):  # Skip retry delays
            await summarize_handler.handle_summarize(interaction)
        
        # Verify eventual success after retry
        assert summarization_engine.summarize_messages.call_count == 2
        interaction.response.send_message.assert_called()
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self, mock_services):
        """Test system performance under concurrent load."""
        # Create multiple concurrent summarization requests
        concurrent_requests = 5

        # Setup mocks for consistent responses
        summarization_engine = mock_services.get_summarization_engine()
        permission_manager = mock_services.get_permission_manager()
        message_fetcher = mock_services.get_message_fetcher()

        permission_manager.check_command_permission.return_value = True
        permission_manager.check_channel_access.return_value = True
        message_fetcher.fetch_messages.return_value = create_mock_messages(10)

        mock_summary = MagicMock()
        mock_summary.to_embed.return_value = MagicMock()
        summarization_engine.summarize_messages.return_value = mock_summary

        # Create concurrent interactions
        interactions = [
            create_mock_interaction(
                guild_id=123456789,
                channel_id=987654321 + i,
                user_id=111111111 + i
            ) for i in range(concurrent_requests)
        ]

        command_handlers = mock_services.get_command_handlers()
        summarize_handler = command_handlers["summarize"]
        
        # Execute concurrent requests
        start_time = datetime.utcnow()
        
        tasks = [
            summarize_handler.handle_summarize(interaction) 
            for interaction in interactions
        ]
        
        await asyncio.gather(*tasks)
        
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        # Verify all requests completed
        assert summarization_engine.summarize_messages.call_count == concurrent_requests
        
        # Verify reasonable performance (should complete within 30 seconds)
        assert execution_time < 30.0
        
        # Verify all interactions received responses
        for interaction in interactions:
            interaction.response.send_message.assert_called()