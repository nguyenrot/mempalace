"""
convo_miner.py — Conversation miner (Compat Namespace)
======================================================

Thin re-export wrapper for the actual implementation in _legacy_convo_miner.
"""

from mempalace.compat._legacy_convo_miner import (
    CONVO_EXTENSIONS,
    SKIP_DIRS,
    MIN_CHUNK_SIZE,
    chunk_exchanges,
    get_collection,
    mine_convos,
)

__all__ = [
    "CONVO_EXTENSIONS",
    "SKIP_DIRS",
    "MIN_CHUNK_SIZE",
    "chunk_exchanges",
    "get_collection",
    "mine_convos",
]
