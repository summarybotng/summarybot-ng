"""
Tests for Wiki Ingest Agent (ADR-056).

Tests cover:
- Summary ingestion into wiki pages
- Topic extraction and page creation
- Expert/participant tracking
- Source document creation
- Link management
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.wiki.agents.ingest_agent import WikiIngestAgent, IngestResult
from src.wiki.models import WikiPage, WikiSource, WikiSourceType


@pytest.fixture
def mock_repository():
    """Create mock wiki repository."""
    repo = AsyncMock()
    repo.save_page = AsyncMock()
    repo.save_source = AsyncMock()
    repo.get_page = AsyncMock(return_value=None)
    repo.log_operation = AsyncMock()
    repo.update_link_counts = AsyncMock()
    return repo


@pytest.fixture
def ingest_agent(mock_repository):
    """Create ingest agent with mock repository."""
    return WikiIngestAgent(mock_repository)


@pytest.fixture
def sample_summary_data():
    """Sample summary data for testing."""
    return {
        "guild_id": "guild-123",
        "summary_id": "sum-456",
        "summary_text": "Discussion about API authentication using OAuth2...",
        "key_points": [
            "OAuth2 is preferred for authentication",
            "JWT tokens should expire after 1 hour",
            "Refresh tokens need secure storage",
        ],
        "action_items": [
            "Update auth documentation",
            "Implement token rotation",
        ],
        "participants": ["Alice", "Bob", "Charlie"],
        "technical_terms": ["OAuth2", "JWT", "RBAC", "API Gateway"],
        "channel_name": "#backend",
        "timestamp": datetime(2024, 1, 15, 10, 0, 0),
    }


class TestSummaryIngestion:
    """Test summary ingestion process."""

    @pytest.mark.asyncio
    async def test_ingest_summary_creates_source(self, ingest_agent, mock_repository, sample_summary_data):
        """Test ingestion creates immutable source document."""
        result = await ingest_agent.ingest_summary(**sample_summary_data)

        mock_repository.save_source.assert_called_once()
        source_call = mock_repository.save_source.call_args[0][0]
        assert source_call.source_type == WikiSourceType.SUMMARY
        assert sample_summary_data["summary_id"] in source_call.id

    @pytest.mark.asyncio
    async def test_ingest_summary_returns_result(self, ingest_agent, mock_repository, sample_summary_data):
        """Test ingestion returns IngestResult."""
        result = await ingest_agent.ingest_summary(**sample_summary_data)

        assert isinstance(result, IngestResult)
        assert result.source_id is not None
        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_ingest_handles_errors_gracefully(self, ingest_agent, mock_repository, sample_summary_data):
        """Test ingestion handles errors without crashing."""
        mock_repository.save_source.side_effect = Exception("Database error")

        result = await ingest_agent.ingest_summary(**sample_summary_data)

        assert result.success is False
        assert "Database error" in result.error


class TestTopicExtraction:
    """Test topic extraction and page creation."""

    @pytest.mark.asyncio
    async def test_creates_pages_for_technical_terms(self, ingest_agent, mock_repository, sample_summary_data):
        """Test creates wiki pages for technical terms."""
        await ingest_agent.ingest_summary(**sample_summary_data)

        # Should create pages for OAuth2, JWT, RBAC, API Gateway
        assert mock_repository.save_page.call_count >= 4

        page_paths = [call[0][0].path for call in mock_repository.save_page.call_args_list]
        # At least some technical terms should have pages
        assert any("oauth2" in path.lower() for path in page_paths)

    @pytest.mark.asyncio
    async def test_updates_existing_pages(self, ingest_agent, mock_repository, sample_summary_data):
        """Test updates existing pages instead of duplicating."""
        existing_page = WikiPage(
            id="existing-123",
            guild_id="guild-123",
            path="topics/oauth2.md",
            title="OAuth2",
            content="Previous content about OAuth2",
            topics=["oauth2"],
        )
        mock_repository.get_page.return_value = existing_page

        result = await ingest_agent.ingest_summary(**sample_summary_data)

        # Should have updated pages
        assert len(result.pages_updated) > 0 or len(result.pages_created) > 0

    @pytest.mark.asyncio
    async def test_normalizes_topic_paths(self, ingest_agent, mock_repository, sample_summary_data):
        """Test topic paths are normalized."""
        sample_summary_data["technical_terms"] = ["API Gateway", "HTTP/2"]

        await ingest_agent.ingest_summary(**sample_summary_data)

        page_paths = [call[0][0].path for call in mock_repository.save_page.call_args_list]
        # Paths should be normalized (lowercase, slugified)
        for path in page_paths:
            assert " " not in path
            assert path == path.lower() or path.startswith("topics/") or path.startswith("experts/")


class TestExpertTracking:
    """Test participant/expert tracking."""

    @pytest.mark.asyncio
    async def test_creates_expertise_map_page(self, ingest_agent, mock_repository, sample_summary_data):
        """Test creates expertise map page for participants."""
        await ingest_agent.ingest_summary(**sample_summary_data)

        page_paths = [call[0][0].path for call in mock_repository.save_page.call_args_list]
        # Should have expertise map
        assert any("expert" in path.lower() for path in page_paths)

    @pytest.mark.asyncio
    async def test_tracks_participant_topics(self, ingest_agent, mock_repository, sample_summary_data):
        """Test links participants to discussed topics."""
        await ingest_agent.ingest_summary(**sample_summary_data)

        # Find expertise map page
        expert_pages = [
            call[0][0] for call in mock_repository.save_page.call_args_list
            if "expert" in call[0][0].path.lower()
        ]

        if expert_pages:
            expert_page = expert_pages[0]
            # Should mention participants
            assert any(p in expert_page.content for p in sample_summary_data["participants"])


class TestKeyPointExtraction:
    """Test key point extraction into wiki."""

    @pytest.mark.asyncio
    async def test_key_points_added_to_relevant_pages(self, ingest_agent, mock_repository, sample_summary_data):
        """Test key points are added to topic pages."""
        await ingest_agent.ingest_summary(**sample_summary_data)

        # Get all saved pages
        saved_pages = [call[0][0] for call in mock_repository.save_page.call_args_list]

        # At least one page should contain key point content
        all_content = " ".join(p.content for p in saved_pages)
        assert "OAuth2" in all_content or "authentication" in all_content.lower()


class TestSourceReferences:
    """Test source reference tracking."""

    @pytest.mark.asyncio
    async def test_pages_reference_source(self, ingest_agent, mock_repository, sample_summary_data):
        """Test created pages reference the source."""
        await ingest_agent.ingest_summary(**sample_summary_data)

        # All created pages should have source refs
        for call in mock_repository.save_page.call_args_list:
            page = call[0][0]
            assert len(page.source_refs) > 0

    @pytest.mark.asyncio
    async def test_source_metadata_preserved(self, ingest_agent, mock_repository, sample_summary_data):
        """Test source metadata is preserved."""
        await ingest_agent.ingest_summary(**sample_summary_data)

        source_call = mock_repository.save_source.call_args[0][0]
        assert source_call.metadata.get("channel_name") == "#backend"


class TestOperationLogging:
    """Test operation logging."""

    @pytest.mark.asyncio
    async def test_ingest_returns_statistics(self, ingest_agent, mock_repository, sample_summary_data):
        """Test ingestion returns operation statistics."""
        result = await ingest_agent.ingest_summary(**sample_summary_data)

        # Result should include pages created/updated counts
        assert hasattr(result, 'pages_created')
        assert hasattr(result, 'pages_updated')

    @pytest.mark.asyncio
    async def test_ingest_result_has_source_id(self, ingest_agent, mock_repository, sample_summary_data):
        """Test ingest result includes source ID."""
        result = await ingest_agent.ingest_summary(**sample_summary_data)

        assert result.source_id is not None
        assert sample_summary_data["summary_id"] in result.source_id


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_handles_empty_summary(self, ingest_agent, mock_repository):
        """Test handles empty summary gracefully."""
        result = await ingest_agent.ingest_summary(
            guild_id="guild-123",
            summary_id="empty-sum",
            summary_text="",
            key_points=[],
            action_items=[],
            participants=[],
            technical_terms=[],
            channel_name="#test",
            timestamp=datetime.utcnow(),
        )

        # Should still succeed but create minimal content
        assert result.success is True

    @pytest.mark.asyncio
    async def test_handles_unicode_content(self, ingest_agent, mock_repository, sample_summary_data):
        """Test handles unicode in content."""
        sample_summary_data["summary_text"] = "Discussion about émojis 🚀 and unicode: 日本語"
        sample_summary_data["technical_terms"] = ["Café API", "日本語"]

        result = await ingest_agent.ingest_summary(**sample_summary_data)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_handles_very_long_content(self, ingest_agent, mock_repository, sample_summary_data):
        """Test handles very long content."""
        sample_summary_data["summary_text"] = "A" * 100000  # 100k chars
        sample_summary_data["key_points"] = [f"Point {i}" for i in range(100)]

        result = await ingest_agent.ingest_summary(**sample_summary_data)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_deduplicates_technical_terms(self, ingest_agent, mock_repository, sample_summary_data):
        """Test deduplicates similar technical terms."""
        sample_summary_data["technical_terms"] = ["OAuth", "oauth", "OAUTH", "OAuth2"]

        await ingest_agent.ingest_summary(**sample_summary_data)

        # Should not create duplicate pages for OAuth variants
        page_paths = [call[0][0].path for call in mock_repository.save_page.call_args_list]
        oauth_pages = [p for p in page_paths if "oauth" in p.lower()]
        # Should have <= 2 OAuth-related pages (oauth and oauth2)
        assert len(oauth_pages) <= 3


class TestRelevanceFiltering:
    """Test key point relevance filtering."""

    def test_filter_relevant_points_exact_match(self, ingest_agent):
        """Test filtering with exact topic match."""
        key_points = [
            "Database migration completed",
            "API endpoint added for users",
            "Fixed database connection issue",
            "Updated login page styling",
        ]

        relevant = ingest_agent._filter_relevant_points("database", key_points)

        assert len(relevant) == 2
        assert "Database migration completed" in relevant
        assert "Fixed database connection issue" in relevant
        assert "API endpoint added for users" not in relevant

    def test_filter_relevant_points_multi_word_topic(self, ingest_agent):
        """Test filtering with multi-word topic."""
        key_points = [
            "Machine learning model trained",
            "Updated button styling",
            "Learning rate adjusted",
            "Fixed machine performance issue",
        ]

        relevant = ingest_agent._filter_relevant_points("machine-learning", key_points)

        # Should match "machine" OR "learning"
        assert len(relevant) == 3
        assert "Machine learning model trained" in relevant
        assert "Learning rate adjusted" in relevant
        assert "Fixed machine performance issue" in relevant
        assert "Updated button styling" not in relevant

    def test_filter_relevant_points_no_matches(self, ingest_agent):
        """Test filtering returns empty when no relevant points."""
        key_points = [
            "Updated login page styling",
            "Fixed button alignment",
            "Changed color scheme",
        ]

        relevant = ingest_agent._filter_relevant_points("quantum-computing", key_points)

        assert len(relevant) == 0

    def test_filter_relevant_points_user_driven_topic(self, ingest_agent):
        """Test filtering works for arbitrary user-driven topics."""
        key_points = [
            "Kubernetes cluster scaled up",
            "Fixed kubernetes networking issue",
            "Updated documentation",
            "Added k8s monitoring dashboard",
        ]

        relevant = ingest_agent._filter_relevant_points("kubernetes", key_points)

        assert len(relevant) == 2
        assert "Kubernetes cluster scaled up" in relevant
        assert "Fixed kubernetes networking issue" in relevant
        assert "Updated documentation" not in relevant

    def test_filter_relevant_points_case_insensitive(self, ingest_agent):
        """Test filtering is case insensitive."""
        key_points = [
            "GRAPHQL endpoint added",
            "GraphQL schema updated",
            "Fixed unrelated bug",
        ]

        relevant = ingest_agent._filter_relevant_points("graphql", key_points)

        assert len(relevant) == 2

    def test_filter_relevant_points_short_topic_words_ignored(self, ingest_agent):
        """Test very short topic words (< 3 chars) are ignored."""
        key_points = [
            "Fixed API response format",
            "UI styling updated",
            "Added API documentation",
        ]

        # Topic "ui-api" has "ui" (2 chars, ignored) and "api" (3 chars, kept)
        relevant = ingest_agent._filter_relevant_points("ui-api", key_points)

        assert len(relevant) == 2
        assert "Fixed API response format" in relevant
        assert "Added API documentation" in relevant
        # "UI styling updated" should NOT match since "ui" is too short
        assert "UI styling updated" not in relevant
