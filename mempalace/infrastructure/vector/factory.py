"""Factory for creating embedding providers based on configuration."""

from __future__ import annotations

import logging
from typing import Union

from mempalace.infrastructure.settings import StorageSettings
from mempalace.infrastructure.vector.hashing import HashingEmbeddingProvider

logger = logging.getLogger("mempalace.embeddings")


def create_embedding_provider(
    storage: StorageSettings | None = None,
) -> Union["HashingEmbeddingProvider", "SentenceTransformerEmbeddingProvider"]:
    """Create the best available embedding provider.

    Strategy:
    - ``"auto"`` (default): try sentence-transformers, fall back to hashing
    - ``"sentence-transformer"``: require sentence-transformers, error if missing
    - ``"hashing"``: always use deterministic hashing (fast, zero-dependency)
    """
    if storage is None:
        storage = StorageSettings()

    provider_name = storage.embedding_provider
    model_name = storage.embedding_model

    if provider_name == "hashing":
        logger.info("Using hashing embedding provider (deterministic, no model download)")
        return HashingEmbeddingProvider()

    if provider_name in ("auto", "sentence-transformer"):
        try:
            import sentence_transformers  # noqa: F401

            from mempalace.infrastructure.vector.sentence_transformer import (
                SentenceTransformerEmbeddingProvider,
            )

            provider = SentenceTransformerEmbeddingProvider(model_name=model_name)
            logger.info(
                "Using sentence-transformer embedding provider: %s (%d-dim)",
                model_name, provider.dimensions,
            )
            return provider
        except ImportError:
            if provider_name == "sentence-transformer":
                raise ImportError(
                    "sentence-transformers is required but not installed. "
                    "Install with: pip install mempalace[embeddings]"
                )
            logger.warning(
                "sentence-transformers not installed. Falling back to hashing embeddings. "
                "For better search quality, install: pip install mempalace[embeddings]"
            )
            return HashingEmbeddingProvider()

    raise ValueError(
        f"Unknown embedding provider: {provider_name!r}. "
        "Choose from: 'auto', 'sentence-transformer', 'hashing'"
    )
