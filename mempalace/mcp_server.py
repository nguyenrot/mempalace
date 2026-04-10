"""
mcp_server.py — MCP Server Entry Point
=====================================

This is the thin shim that delegates to the actual implementation in
mempalace/compat/mcp_server.py. Keeping it here maintains the original
entry point `python -m mempalace.mcp_server` without breaking anything.

The actual implementation lives in mempalace/compat/mcp_server.py.
"""

# Delegate to the compat namespaced implementation
from mempalace.compat.mcp_server import (
    MCP_TOOLS,
    MCP_VISIBLE_TOOL_NAMES,
    SERVICE_TOOLS,
    _config,
    _get_kg,
    handle_request,
    main,
    tool_add_drawer,
    tool_check_duplicate,
    tool_delete_drawer,
    tool_diary_read,
    tool_diary_write,
    tool_find_tunnels,
    tool_get_aaak_spec,
    tool_get_taxonomy,
    tool_kg_add,
    tool_kg_invalidate,
    tool_kg_query,
    tool_kg_stats,
    tool_kg_timeline,
    tool_list_rooms,
    tool_list_wings,
    tool_search,
    tool_status,
    tool_traverse_graph,
    tool_graph_stats,
)

# Re-export _kg / _get_kg for backward compat (tests patch _kg via _kg_ref)
from mempalace.compat.mcp_server import _kg_ref as _kg_ref_compat

_kg_ref = _kg_ref_compat


def _kg():
    return _get_kg()


# Re-export for backward compatibility
__all__ = [
    "MCP_TOOLS",
    "MCP_VISIBLE_TOOL_NAMES",
    "SERVICE_TOOLS",
    "_config",
    "_get_kg",
    "_kg",
    "_kg_ref",
    "handle_request",
    "main",
    "tool_add_drawer",
    "tool_check_duplicate",
    "tool_delete_drawer",
    "tool_diary_read",
    "tool_diary_write",
    "tool_find_tunnels",
    "tool_get_aaak_spec",
    "tool_get_taxonomy",
    "tool_kg_add",
    "tool_kg_invalidate",
    "tool_kg_query",
    "tool_kg_stats",
    "tool_kg_timeline",
    "tool_list_rooms",
    "tool_list_wings",
    "tool_search",
    "tool_status",
    "tool_traverse_graph",
    "tool_graph_stats",
]
