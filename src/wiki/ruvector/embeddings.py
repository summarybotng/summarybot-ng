"""
Embedding service for RuVector (ADR-057).

Generates vector embeddings using OpenAI's text-embedding-3-small model.
Supports batching for efficiency and caching for cost optimization.

ADR-090: Also supports OpenRouter for embeddings via OPENROUTER_API_KEY.
"""

import logging
import asyncio
import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import hashlib
import json

import numpy as np

logger = logging.getLogger(__name__)

# Embedding dimensions for text-embedding-3-small
EMBEDDING_DIMENSIONS = 1536
DEFAULT_MODEL = "text-embedding-3-small"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    embedding: List[float]
    model: str
    tokens_used: int
    cached: bool = False


class EmbeddingService:
    """
    Generate embeddings for knowledge units using OpenAI API.

    ADR-057: Uses text-embedding-3-small ($0.02/1M tokens) for cost efficiency.
    Supports batching up to 2048 inputs per request.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        cache_enabled: bool = True,
        max_batch_size: int = 100,
    ):
        """
        Initialize the embedding service.

        Args:
            api_key: API key (checks OPENROUTER_API_KEY, then OPENAI_API_KEY)
            base_url: Custom API base URL (auto-detected for OpenRouter)
            model: Embedding model to use
            cache_enabled: Whether to cache embeddings
            max_batch_size: Maximum texts per batch request
        """
        self.model = model
        self.cache_enabled = cache_enabled
        self.max_batch_size = max_batch_size
        self._cache: Dict[str, List[float]] = {}
        self._client = None
        self._api_key = api_key
        self._base_url = base_url

    def _get_client(self):
        """Lazy initialization of OpenAI-compatible client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                # Check for OpenRouter first, then OpenAI
                api_key = self._api_key
                base_url = self._base_url

                if not api_key:
                    # Try OpenRouter first
                    openrouter_key = os.getenv("OPENROUTER_API_KEY")
                    if openrouter_key:
                        api_key = openrouter_key
                        base_url = base_url or OPENROUTER_BASE_URL
                        logger.info("Using OpenRouter for embeddings")
                    else:
                        # Fall back to OpenAI
                        api_key = os.getenv("OPENAI_API_KEY")

                if not api_key:
                    logger.warning("No API key set (OPENROUTER_API_KEY or OPENAI_API_KEY), using mock embeddings")
                    return None

                # Create client with optional base_url for OpenRouter
                client_kwargs = {"api_key": api_key}
                if base_url:
                    client_kwargs["base_url"] = base_url
                    logger.info(f"Embedding service using base URL: {base_url}")

                self._client = AsyncOpenAI(**client_kwargs)
            except ImportError:
                logger.warning("OpenAI package not installed, using mock embeddings")
                return None
        return self._client

    def _cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.sha256(f"{self.model}:{text}".encode()).hexdigest()[:32]

    async def embed(self, text: str) -> EmbeddingResult:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            EmbeddingResult with embedding vector
        """
        # Check cache
        if self.cache_enabled:
            cache_key = self._cache_key(text)
            if cache_key in self._cache:
                return EmbeddingResult(
                    embedding=self._cache[cache_key],
                    model=self.model,
                    tokens_used=0,
                    cached=True,
                )

        # Get embedding from API
        client = self._get_client()
        if client is None:
            # Mock embedding for development/testing
            embedding = self._mock_embedding(text)
            return EmbeddingResult(
                embedding=embedding,
                model="mock",
                tokens_used=len(text.split()),
                cached=False,
            )

        try:
            response = await client.embeddings.create(
                model=self.model,
                input=text,
            )

            embedding = response.data[0].embedding
            tokens_used = response.usage.total_tokens

            # Cache result
            if self.cache_enabled:
                self._cache[cache_key] = embedding

            return EmbeddingResult(
                embedding=embedding,
                model=self.model,
                tokens_used=tokens_used,
                cached=False,
            )

        except Exception as e:
            logger.error(f"Embedding API error: {e}")
            # Fall back to mock on error
            return EmbeddingResult(
                embedding=self._mock_embedding(text),
                model="mock-fallback",
                tokens_used=0,
                cached=False,
            )

    async def embed_batch(
        self,
        texts: List[str],
    ) -> List[EmbeddingResult]:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of EmbeddingResult objects
        """
        if not texts:
            return []

        results: List[EmbeddingResult] = [None] * len(texts)  # type: ignore
        texts_to_embed: List[tuple[int, str]] = []

        # Check cache first
        for i, text in enumerate(texts):
            if self.cache_enabled:
                cache_key = self._cache_key(text)
                if cache_key in self._cache:
                    results[i] = EmbeddingResult(
                        embedding=self._cache[cache_key],
                        model=self.model,
                        tokens_used=0,
                        cached=True,
                    )
                    continue
            texts_to_embed.append((i, text))

        # Batch embed remaining texts
        if texts_to_embed:
            client = self._get_client()

            # Process in batches
            for batch_start in range(0, len(texts_to_embed), self.max_batch_size):
                batch = texts_to_embed[batch_start:batch_start + self.max_batch_size]
                batch_texts = [t[1] for t in batch]
                batch_indices = [t[0] for t in batch]

                if client is None:
                    # Mock embeddings
                    for idx, text in zip(batch_indices, batch_texts):
                        results[idx] = EmbeddingResult(
                            embedding=self._mock_embedding(text),
                            model="mock",
                            tokens_used=len(text.split()),
                            cached=False,
                        )
                else:
                    try:
                        response = await client.embeddings.create(
                            model=self.model,
                            input=batch_texts,
                        )

                        tokens_per_text = response.usage.total_tokens // len(batch_texts)

                        for j, (idx, text) in enumerate(zip(batch_indices, batch_texts)):
                            embedding = response.data[j].embedding

                            # Cache result
                            if self.cache_enabled:
                                cache_key = self._cache_key(text)
                                self._cache[cache_key] = embedding

                            results[idx] = EmbeddingResult(
                                embedding=embedding,
                                model=self.model,
                                tokens_used=tokens_per_text,
                                cached=False,
                            )

                    except Exception as e:
                        logger.error(f"Batch embedding error: {e}")
                        # Fall back to mock on error
                        for idx, text in zip(batch_indices, batch_texts):
                            results[idx] = EmbeddingResult(
                                embedding=self._mock_embedding(text),
                                model="mock-fallback",
                                tokens_used=0,
                                cached=False,
                            )

        return results

    def _mock_embedding(self, text: str) -> List[float]:
        """
        Generate a deterministic mock embedding for testing.

        Uses text hash to produce consistent embeddings for same input.
        """
        import struct

        # Use hash of text to seed pseudo-random generation
        text_hash = hashlib.sha256(text.encode()).digest()

        # Generate deterministic float values from hash bytes
        embedding = []
        for i in range(EMBEDDING_DIMENSIONS):
            # Cycle through hash bytes
            byte_idx = i % 32
            # Create float from byte value, normalized to [-1, 1]
            val = (text_hash[byte_idx] / 255.0) * 2 - 1
            # Add some variation based on position
            val = val * (0.5 + 0.5 * ((i % 64) / 64))
            embedding.append(val)

        # Normalize to unit vector
        magnitude = sum(v * v for v in embedding) ** 0.5
        if magnitude > 0:
            embedding = [v / magnitude for v in embedding]

        return embedding

    def cosine_similarity(
        self,
        embedding_a: List[float],
        embedding_b: List[float],
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Uses numpy for vectorized computation to avoid blocking the event loop.

        Args:
            embedding_a: First embedding vector
            embedding_b: Second embedding vector

        Returns:
            Cosine similarity score (-1 to 1, higher is more similar)
        """
        if len(embedding_a) != len(embedding_b):
            raise ValueError("Embeddings must have same dimensions")

        # Use numpy for fast vectorized computation
        a = np.array(embedding_a, dtype=np.float32)
        b = np.array(embedding_b, dtype=np.float32)

        dot_product = np.dot(a, b)
        magnitude_a = np.linalg.norm(a)
        magnitude_b = np.linalg.norm(b)

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return float(dot_product / (magnitude_a * magnitude_b))

    def clear_cache(self) -> int:
        """Clear the embedding cache. Returns number of entries cleared."""
        count = len(self._cache)
        self._cache.clear()
        return count

    @property
    def cache_size(self) -> int:
        """Number of cached embeddings."""
        return len(self._cache)
