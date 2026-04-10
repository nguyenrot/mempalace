"""
searcher.py — ChromaDB-backed semantic search (Compat Namespace)
==============================================================

Thin re-export wrapper for the actual implementation in _legacy_searcher.
"""

from mempalace.compat._legacy_searcher import SearchError, search, search_memories

__all__ = ["SearchError", "search", "search_memories"]
