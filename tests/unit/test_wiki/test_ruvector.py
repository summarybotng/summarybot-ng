"""
Tests for RuVector components (ADR-057).

Tests embedding service, knowledge extraction, and vector store.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.wiki.ruvector.models import (
    KnowledgeUnit,
    KnowledgeUnitType,
    Edge,
    EdgeType,
    SearchResult,
    ExtractionResult,
)
from src.wiki.ruvector.embeddings import EmbeddingService, EMBEDDING_DIMENSIONS
from src.wiki.ruvector.knowledge_extractor import KnowledgeExtractor


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    def test_mock_embedding_dimensions(self):
        """Mock embeddings should have correct dimensions."""
        service = EmbeddingService()
        embedding = service._mock_embedding("test text")

        assert len(embedding) == EMBEDDING_DIMENSIONS
        assert all(isinstance(v, float) for v in embedding)

    def test_mock_embedding_deterministic(self):
        """Same text should produce same mock embedding."""
        service = EmbeddingService()
        embedding1 = service._mock_embedding("test text")
        embedding2 = service._mock_embedding("test text")

        assert embedding1 == embedding2

    def test_mock_embedding_different_for_different_text(self):
        """Different text should produce different embeddings."""
        service = EmbeddingService()
        embedding1 = service._mock_embedding("text one")
        embedding2 = service._mock_embedding("text two")

        assert embedding1 != embedding2

    def test_cosine_similarity_identical(self):
        """Identical vectors should have similarity of 1."""
        service = EmbeddingService()
        embedding = service._mock_embedding("test")

        similarity = service.cosine_similarity(embedding, embedding)
        assert abs(similarity - 1.0) < 0.001

    def test_cosine_similarity_orthogonal(self):
        """Orthogonal vectors should have similarity near 0."""
        service = EmbeddingService()
        # Create two simple orthogonal vectors
        vec1 = [1.0, 0.0, 0.0] + [0.0] * (EMBEDDING_DIMENSIONS - 3)
        vec2 = [0.0, 1.0, 0.0] + [0.0] * (EMBEDDING_DIMENSIONS - 3)

        similarity = service.cosine_similarity(vec1, vec2)
        assert abs(similarity) < 0.001

    def test_cosine_similarity_opposite(self):
        """Opposite vectors should have similarity of -1."""
        service = EmbeddingService()
        vec1 = [1.0] * EMBEDDING_DIMENSIONS
        vec2 = [-1.0] * EMBEDDING_DIMENSIONS

        similarity = service.cosine_similarity(vec1, vec2)
        assert abs(similarity - (-1.0)) < 0.001

    @pytest.mark.asyncio
    async def test_embed_without_api_key(self):
        """Should fall back to mock when no API key."""
        service = EmbeddingService(api_key=None)
        # Clear any env var
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}, clear=False):
            result = await service.embed("test text")

        assert result.embedding is not None
        assert len(result.embedding) == EMBEDDING_DIMENSIONS
        assert result.model in ["mock", "mock-fallback"]

    @pytest.mark.asyncio
    async def test_embed_batch_without_api_key(self):
        """Batch embed should work with mock."""
        service = EmbeddingService(api_key=None)
        texts = ["text one", "text two", "text three"]

        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}, clear=False):
            results = await service.embed_batch(texts)

        assert len(results) == 3
        for result in results:
            assert len(result.embedding) == EMBEDDING_DIMENSIONS

    def test_cache_operations(self):
        """Cache should store and retrieve embeddings."""
        service = EmbeddingService(cache_enabled=True)

        # Initially empty
        assert service.cache_size == 0

        # Add to cache manually via mock embedding
        text = "test text"
        embedding = service._mock_embedding(text)
        cache_key = service._cache_key(text)
        service._cache[cache_key] = embedding

        assert service.cache_size == 1

        # Clear cache
        cleared = service.clear_cache()
        assert cleared == 1
        assert service.cache_size == 0


class TestKnowledgeExtractor:
    """Tests for KnowledgeExtractor."""

    def test_heuristic_extract_question(self):
        """Should identify questions."""
        extractor = KnowledgeExtractor(claude_client=None)

        units = extractor._extract_heuristic(
            guild_id="guild-1",
            source_id="source-1",
            source_type="summary",
            content="How should we handle authentication?",
            channel_name="#engineering",
            source_date=datetime.now(),
        )

        assert len(units) >= 1
        question_units = [u for u in units if u.unit_type == KnowledgeUnitType.QUESTION]
        assert len(question_units) >= 1

    def test_heuristic_extract_action_item(self):
        """Should identify action items."""
        extractor = KnowledgeExtractor(claude_client=None)

        units = extractor._extract_heuristic(
            guild_id="guild-1",
            source_id="source-1",
            source_type="summary",
            content="John will create the migration guide by Friday.",
            channel_name="#engineering",
            source_date=datetime.now(),
        )

        assert len(units) >= 1
        action_units = [u for u in units if u.unit_type == KnowledgeUnitType.ACTION_ITEM]
        assert len(action_units) >= 1

    def test_heuristic_extract_decision(self):
        """Should identify decisions."""
        extractor = KnowledgeExtractor(claude_client=None)

        units = extractor._extract_heuristic(
            guild_id="guild-1",
            source_id="source-1",
            source_type="summary",
            content="We decided to use OAuth 2.0 for the new API.",
            channel_name="#engineering",
            source_date=datetime.now(),
        )

        assert len(units) >= 1
        decision_units = [u for u in units if u.unit_type == KnowledgeUnitType.DECISION]
        assert len(decision_units) >= 1

    def test_heuristic_extract_multiple(self):
        """Should extract multiple unit types from mixed content."""
        extractor = KnowledgeExtractor(claude_client=None)

        content = """
        We decided to migrate to the new API framework.
        John will handle the backend changes.
        How should we handle backward compatibility?
        The deadline is next Friday.
        """

        units = extractor._extract_heuristic(
            guild_id="guild-1",
            source_id="source-1",
            source_type="summary",
            content=content,
            channel_name="#engineering",
            source_date=datetime.now(),
        )

        # Should have multiple units of different types
        types = set(u.unit_type for u in units)
        assert len(types) >= 2  # At least 2 different types

    def test_sentence_splitting(self):
        """Should split content into sentences."""
        extractor = KnowledgeExtractor(claude_client=None)

        sentences = extractor._split_sentences(
            "First sentence. Second sentence! Third sentence?"
        )

        assert len(sentences) == 3

    def test_bullet_point_splitting(self):
        """Should handle bullet points."""
        extractor = KnowledgeExtractor(claude_client=None)

        sentences = extractor._split_sentences(
            "Items:\n- First item\n- Second item\n- Third item"
        )

        assert len(sentences) >= 3

    @pytest.mark.asyncio
    async def test_extract_from_summary(self):
        """Should extract units from summary."""
        extractor = KnowledgeExtractor(claude_client=None)

        result = await extractor.extract_from_summary(
            guild_id="guild-1",
            summary_id="summary-1",
            summary_text="The team discussed the API migration. John will create docs.",
            channel_name="#engineering",
            summary_date=datetime.now(),
        )

        assert isinstance(result, ExtractionResult)
        assert result.source_id == "summary-1"
        assert len(result.units) >= 1
        assert result.extraction_model == "heuristic"

    @pytest.mark.asyncio
    async def test_extract_from_messages(self):
        """Should extract units from raw messages."""
        extractor = KnowledgeExtractor(claude_client=None)

        messages = [
            {"author": "John", "content": "I think we should use OAuth", "timestamp": "2024-01-15T10:00:00Z"},
            {"author": "Jane", "content": "Agreed. Who will implement it?", "timestamp": "2024-01-15T10:05:00Z"},
        ]

        result = await extractor.extract_from_messages(
            guild_id="guild-1",
            messages=messages,
            channel_name="#engineering",
        )

        assert isinstance(result, ExtractionResult)
        assert len(result.units) >= 1


class TestKnowledgeUnit:
    """Tests for KnowledgeUnit model."""

    def test_to_dict(self):
        """Should serialize to dictionary."""
        unit = KnowledgeUnit(
            id="unit-1",
            guild_id="guild-1",
            content="Test content",
            unit_type=KnowledgeUnitType.CLAIM,
            source_id="source-1",
            source_type="summary",
            source_channel="#engineering",
            source_date=datetime(2024, 1, 15, 10, 0, 0),
            confidence=0.9,
        )

        data = unit.to_dict()

        assert data["id"] == "unit-1"
        assert data["content"] == "Test content"
        assert data["unit_type"] == "claim"
        assert data["confidence"] == 0.9


class TestEdge:
    """Tests for Edge model."""

    def test_edge_types(self):
        """Should support all edge types."""
        edge_types = [
            EdgeType.RELATES_TO,
            EdgeType.DEPENDS_ON,
            EdgeType.CONTRADICTS,
            EdgeType.SUPERSEDES,
            EdgeType.SUPPORTS,
            EdgeType.ANSWERS,
            EdgeType.IMPLEMENTS,
        ]

        for edge_type in edge_types:
            edge = Edge(
                guild_id="guild-1",
                from_unit_id="unit-1",
                to_unit_id="unit-2",
                edge_type=edge_type,
            )
            assert edge.edge_type == edge_type


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_search_result_creation(self):
        """Should create search result with all fields."""
        result = SearchResult(
            unit_id="unit-1",
            content="Test content",
            unit_type=KnowledgeUnitType.CLAIM,
            score=0.95,
            source_id="source-1",
            source_channel="#engineering",
        )

        assert result.unit_id == "unit-1"
        assert result.score == 0.95
        assert result.related_units == []
