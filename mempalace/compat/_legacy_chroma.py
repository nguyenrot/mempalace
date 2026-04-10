"""Shared helpers for the legacy Chroma-backed runtime.

The legacy runtime originally relied on Chroma's default embedding path.
That can trigger slow or unstable behavior in offline test environments.
These helpers keep legacy storage working while using deterministic local
embeddings instead of model-backed defaults.
"""

from __future__ import annotations

from typing import Any

from mempalace.infrastructure.vector.hashing import HashingEmbeddingProvider


_EMBEDDINGS = HashingEmbeddingProvider()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return deterministic local embeddings for a batch of texts."""
    return _EMBEDDINGS.embed_texts(texts)


def add_texts(collection: Any, *, ids: list[str], documents: list[str], metadatas: list[dict]) -> None:
    """Add documents to a Chroma collection with explicit local embeddings."""
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embed_texts(documents),
        metadatas=metadatas,
    )


def query_text(collection: Any, query: str, *, n_results: int, where: dict | None = None, include: list[str] | None = None) -> dict:
    """Query a Chroma collection with an explicit deterministic embedding."""
    kwargs: dict[str, Any] = {
        "query_embeddings": embed_texts([query]),
        "n_results": n_results,
    }
    if include is not None:
        kwargs["include"] = include
    if where:
        kwargs["where"] = where
    return collection.query(**kwargs)
