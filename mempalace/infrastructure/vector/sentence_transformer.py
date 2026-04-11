"""Semantic embedding provider using sentence-transformers.

Provides high-quality 384-dimensional embeddings via the all-MiniLM-L6-v2 model.
This is the recommended provider for production deployments. Falls back to
HashingEmbeddingProvider if sentence-transformers is not installed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

logger = logging.getLogger("mempalace.embeddings")


@dataclass(slots=True)
class SentenceTransformerEmbeddingProvider:
    """Real semantic embeddings via sentence-transformers.

    Uses all-MiniLM-L6-v2 by default (384-dim, 22M params, ~80MB).
    Model is lazy-loaded on first embed call to avoid startup cost.
    """

    model_name: str = "all-MiniLM-L6-v2"
    dimensions: int = 384
    _model: Any = field(default=None, repr=False)

    @property
    def name(self) -> str:
        """Stable provider identifier."""
        return f"sentence-transformer-{self.model_name}"

    def _load_model(self) -> Any:
        """Lazy-load the sentence-transformers model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for semantic embeddings. "
                    "Install it with: pip install mempalace[embeddings]"
                )
            logger.info("Loading embedding model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            actual_dim = self._model.get_embedding_dimension()
            if actual_dim != self.dimensions:
                logger.warning(
                    "Model %s has %d dimensions, expected %d. Updating.",
                    self.model_name, actual_dim, self.dimensions,
                )
                self.dimensions = actual_dim
        return self._model

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a sequence of texts using the sentence-transformer model."""
        model = self._load_model()
        embeddings = model.encode(list(texts), show_progress_bar=False, normalize_embeddings=True)
        return [embedding.tolist() for embedding in embeddings]
