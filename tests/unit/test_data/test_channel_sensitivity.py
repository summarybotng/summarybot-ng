"""
Tests for ADR-046: Channel Sensitivity Configuration.

Tests the config repository's sensitivity methods and
the summary filtering logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.data.sqlite.config_repository import SQLiteConfigRepository
from src.models.stored_summary import StoredSummary, SummarySource


@pytest.fixture
def mock_connection():
    """Create a mock SQLite connection."""
    connection = AsyncMock()
    return connection


@pytest.fixture
def config_repo(mock_connection):
    """Create a config repository with mocked connection."""
    return SQLiteConfigRepository(mock_connection)


class TestChannelSensitivityConfig:
    """Tests for channel sensitivity configuration methods."""

    @pytest.mark.asyncio
    async def test_get_sensitive_channels_empty(self, config_repo, mock_connection):
        """Test getting sensitive channels when none are configured."""
        mock_connection.fetch_one.return_value = None

        result = await config_repo.get_sensitive_channels("guild123")

        assert result == []
        mock_connection.fetch_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_sensitive_channels_with_data(self, config_repo, mock_connection):
        """Test getting sensitive channels with configured data."""
        mock_connection.fetch_one.return_value = {
            "sensitive_channels": '["chan1", "chan2", "chan3"]'
        }

        result = await config_repo.get_sensitive_channels("guild123")

        assert result == ["chan1", "chan2", "chan3"]

    @pytest.mark.asyncio
    async def test_get_sensitive_channels_invalid_json(self, config_repo, mock_connection):
        """Test handling of invalid JSON in sensitive_channels."""
        mock_connection.fetch_one.return_value = {
            "sensitive_channels": "not valid json"
        }

        result = await config_repo.get_sensitive_channels("guild123")

        assert result == []

    @pytest.mark.asyncio
    async def test_set_sensitive_channels(self, config_repo, mock_connection):
        """Test setting sensitive channels."""
        await config_repo.set_sensitive_channels("guild123", ["chan1", "chan2"])

        mock_connection.execute.assert_called_once()
        call_args = mock_connection.execute.call_args
        assert "UPDATE guild_configs" in call_args[0][0]
        assert '["chan1", "chan2"]' in call_args[0][1]

    @pytest.mark.asyncio
    async def test_get_channel_sensitivity_config_defaults(self, config_repo, mock_connection):
        """Test getting sensitivity config when no config exists."""
        mock_connection.fetch_one.return_value = None

        result = await config_repo.get_channel_sensitivity_config("guild123")

        assert result == {
            "sensitive_channels": [],
            "sensitive_categories": [],
            "auto_mark_private_sensitive": True,
        }

    @pytest.mark.asyncio
    async def test_get_channel_sensitivity_config_with_data(self, config_repo, mock_connection):
        """Test getting full sensitivity config."""
        mock_connection.fetch_one.return_value = {
            "sensitive_channels": '["chan1", "chan2"]',
            "sensitive_categories": '["cat1"]',
            "auto_mark_private_sensitive": False,
        }

        result = await config_repo.get_channel_sensitivity_config("guild123")

        assert result == {
            "sensitive_channels": ["chan1", "chan2"],
            "sensitive_categories": ["cat1"],
            "auto_mark_private_sensitive": False,
        }

    @pytest.mark.asyncio
    async def test_set_channel_sensitivity_config_partial(self, config_repo, mock_connection):
        """Test setting partial sensitivity config."""
        await config_repo.set_channel_sensitivity_config(
            "guild123",
            sensitive_channels=["chan1"],
        )

        mock_connection.execute.assert_called_once()
        call_args = mock_connection.execute.call_args
        assert "sensitive_channels = ?" in call_args[0][0]
        # Should not include other fields
        assert "sensitive_categories" not in call_args[0][0]
        assert "auto_mark_private_sensitive" not in call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_channel_sensitivity_config_all_fields(self, config_repo, mock_connection):
        """Test setting all sensitivity config fields."""
        await config_repo.set_channel_sensitivity_config(
            "guild123",
            sensitive_channels=["chan1"],
            sensitive_categories=["cat1"],
            auto_mark_private_sensitive=False,
        )

        mock_connection.execute.assert_called_once()
        call_args = mock_connection.execute.call_args
        assert "sensitive_channels = ?" in call_args[0][0]
        assert "sensitive_categories = ?" in call_args[0][0]
        assert "auto_mark_private_sensitive = ?" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_is_channel_sensitive_true(self, config_repo, mock_connection):
        """Test checking if channel is sensitive - true case."""
        mock_connection.fetch_one.return_value = {
            "sensitive_channels": '["chan1", "chan2"]'
        }

        result = await config_repo.is_channel_sensitive("guild123", "chan1")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_channel_sensitive_false(self, config_repo, mock_connection):
        """Test checking if channel is sensitive - false case."""
        mock_connection.fetch_one.return_value = {
            "sensitive_channels": '["chan1", "chan2"]'
        }

        result = await config_repo.is_channel_sensitive("guild123", "chan3")

        assert result is False

    @pytest.mark.asyncio
    async def test_add_sensitive_channel_new(self, config_repo, mock_connection):
        """Test adding a new sensitive channel."""
        mock_connection.fetch_one.return_value = {
            "sensitive_channels": '["chan1"]'
        }

        await config_repo.add_sensitive_channel("guild123", "chan2")

        mock_connection.execute.assert_called_once()
        call_args = mock_connection.execute.call_args
        # Should include both channels
        assert "chan1" in call_args[0][1][0]
        assert "chan2" in call_args[0][1][0]

    @pytest.mark.asyncio
    async def test_add_sensitive_channel_already_exists(self, config_repo, mock_connection):
        """Test adding a channel that's already sensitive."""
        mock_connection.fetch_one.return_value = {
            "sensitive_channels": '["chan1", "chan2"]'
        }

        await config_repo.add_sensitive_channel("guild123", "chan1")

        # Should not call execute since channel already exists
        mock_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_sensitive_channel(self, config_repo, mock_connection):
        """Test removing a sensitive channel."""
        mock_connection.fetch_one.return_value = {
            "sensitive_channels": '["chan1", "chan2"]'
        }

        await config_repo.remove_sensitive_channel("guild123", "chan1")

        mock_connection.execute.assert_called_once()
        call_args = mock_connection.execute.call_args
        # Should only include chan2
        assert "chan1" not in call_args[0][1][0]
        assert "chan2" in call_args[0][1][0]

    @pytest.mark.asyncio
    async def test_remove_sensitive_channel_not_exists(self, config_repo, mock_connection):
        """Test removing a channel that isn't sensitive."""
        mock_connection.fetch_one.return_value = {
            "sensitive_channels": '["chan1"]'
        }

        await config_repo.remove_sensitive_channel("guild123", "chan2")

        # Should not call execute since channel wasn't in list
        mock_connection.execute.assert_not_called()


class TestSummaryContainsSensitiveChannels:
    """Tests for the summary sensitivity checking helper function."""

    def test_no_sensitive_channels(self):
        """Test when no channels are marked sensitive."""
        from src.dashboard.routes.summaries import _summary_contains_sensitive_channels

        summary = MagicMock()
        summary.source_channel_ids = ["chan1", "chan2"]

        result = _summary_contains_sensitive_channels(summary, set())

        assert result is False

    def test_summary_has_sensitive_channel(self):
        """Test when summary contains a sensitive channel."""
        from src.dashboard.routes.summaries import _summary_contains_sensitive_channels

        summary = MagicMock()
        summary.source_channel_ids = ["chan1", "chan2"]

        result = _summary_contains_sensitive_channels(summary, {"chan2", "chan3"})

        assert result is True

    def test_summary_no_sensitive_channel(self):
        """Test when summary doesn't contain any sensitive channels."""
        from src.dashboard.routes.summaries import _summary_contains_sensitive_channels

        summary = MagicMock()
        summary.source_channel_ids = ["chan1", "chan2"]

        result = _summary_contains_sensitive_channels(summary, {"chan3", "chan4"})

        assert result is False

    def test_empty_source_channels(self):
        """Test when summary has no source channels."""
        from src.dashboard.routes.summaries import _summary_contains_sensitive_channels

        summary = MagicMock()
        summary.source_channel_ids = []

        result = _summary_contains_sensitive_channels(summary, {"chan1"})

        assert result is False

    def test_none_source_channels(self):
        """Test when summary has None source channels."""
        from src.dashboard.routes.summaries import _summary_contains_sensitive_channels

        summary = MagicMock()
        summary.source_channel_ids = None

        result = _summary_contains_sensitive_channels(summary, {"chan1"})

        assert result is False
