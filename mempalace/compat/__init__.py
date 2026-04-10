"""
compat/ — Legacy Compatibility Layer
===================================

This directory holds the legacy runtime modules from before the
service-layer refactor. All code here is either:

  (a) used only by legacy CLI commands (`mempalace legacy-*`)
  (b) used only by legacy MCP tools
  (c) a compatibility shim re-exported at the package root

No new features are being added here. The canonical implementations
live in the sibling directories:

  interfaces/   — CLI, MCP, and API entrypoints (canonical)
  application/  — use-case orchestration
  domain/       — data models
  infrastructure/ — storage and vector adapters

Import path reminder::

  Old (root-level)       →  New (compat/ namespaced)
  -----------------------     ----------------------------
  from mempalace.config import MempalaceConfig
    → from mempalace.compat.config import MempalaceConfig
  from mempalace.knowledge_graph import KnowledgeGraph
    → from mempalace.compat.knowledge_graph import KnowledgeGraph
  from mempalace.miner import mine
    → from mempalace.compat.miner import mine
  from mempalace.searcher import search
    → from mempalace.compat.searcher import search
  from mempalace.layers import MemoryStack
    → from mempalace.compat.layers import MemoryStack
  from mempalace.dialect import Dialect
    → from mempalace.compat.dialect import Dialect
  from mempalace.palace_graph import traverse
    → from mempalace.compat.palace_graph import traverse
  from mempalace.knowledge_graph import KnowledgeGraph
    → from mempalace.compat.knowledge_graph import KnowledgeGraph

The package root re-exports the most commonly used shims so that
existing external code does not break immediately. Those root re-exports
will emit deprecation warnings in a future release.
"""

__all__ = []
