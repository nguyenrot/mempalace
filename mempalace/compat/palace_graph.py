"""
palace_graph.py — Graph traversal layer (Compat Namespace)
==========================================================

Thin re-export wrapper for the actual implementation in _legacy_palace_graph.
"""

from mempalace.compat._legacy_palace_graph import (
    build_graph,
    find_tunnels,
    graph_stats,
    traverse,
)

__all__ = ["build_graph", "find_tunnels", "graph_stats", "traverse"]
