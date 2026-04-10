"""
knowledge_graph.py — Temporal Entity-Relationship Graph (Compat Namespace)
=========================================================================

Thin re-export wrapper: imports the actual implementation from compat level,
then re-exports it at the old `mempalace.knowledge_graph` path for backward compat.

The actual logic lives in `mempalace.compat._legacy_knowledge_graph`.
"""

from mempalace.compat._legacy_knowledge_graph import DEFAULT_KG_PATH, KnowledgeGraph

__all__ = ["DEFAULT_KG_PATH", "KnowledgeGraph"]
