"""Deterministic local embedding provider for offline tests and simple deployments."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Sequence


@dataclass(slots=True)
class HashingEmbeddingProvider:
    """Map tokens into a fixed-size normalized vector with no external dependencies."""

    dimensions: int = 128

    @property
    def name(self) -> str:
        """Stable provider identifier."""
        return f"hashing-v1-{self.dimensions}"

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a sequence of texts."""
        return [self._embed_text(text) for text in texts]

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"\b\w+\b", text.lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8"), usedforsecurity=False).hexdigest()
            index = int(digest[:8], 16) % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]
