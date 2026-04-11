"""
mcp_server.py — MemPalace MCP Server
=====================================

Service-only MCP server exposing 15 canonical tools backed
by the refactored SQLite + FTS5 runtime.

Entry point: python -m mempalace.mcp_server
"""

import json
import logging
import sys

from mempalace.interfaces.mcp.service_tools import (
    tool_compact_session_context_service,
    tool_explain_retrieval_service,
    tool_extract_facts_service,
    tool_fetch_document_service,
    tool_fetch_evidence_trail_service,
    tool_ingest_directory_service,
    tool_ingest_source_service,
    tool_migrate_legacy_service,
    tool_prepare_startup_context_service,
    tool_query_facts_service,
    tool_recall_episodes_service,
    tool_reindex_service,
    tool_search_memory_service,
    tool_search_time_range_service,
    tool_status_health_service,
)
from mempalace.version import __version__

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
logger = logging.getLogger("mempalace_mcp")


# ── Tool Registry ───────────────────────────────────────────────────────

MCP_TOOLS = {
    "mempalace_status": {
        "description": "Palace overview — total drawers, wing and room counts",
        "input_schema": {
            "type": "object",
            "properties": {
                "runtime": {"type": "string", "description": "legacy (default) or service"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
        },
        "handler": tool_status_health_service,
    },
    "mempalace_ingest": {
        "description": "Ingest a directory through the new service-backed runtime.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to ingest"},
                "mode": {"type": "string", "description": "projects (default) or convos"},
                "extract_mode": {"type": "string", "description": "exchange (default) or general when mode=convos"},
                "wing": {"type": "string", "description": "Optional wing override"},
                "respect_gitignore": {"type": "boolean", "description": "Whether to respect .gitignore"},
                "include_ignored": {"type": "array", "items": {"type": "string"}, "description": "Paths to ingest even if ignored"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
            "required": ["directory"],
        },
        "handler": tool_ingest_directory_service,
    },
    "mempalace_ingest_source": {
        "description": "Ingest one explicit file through the new service-backed runtime.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to ingest"},
                "mode": {"type": "string"},
                "extract_mode": {"type": "string"},
                "wing": {"type": "string"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
            "required": ["path"],
        },
        "handler": tool_ingest_source_service,
    },
    "mempalace_migrate_legacy": {
        "description": "Import a legacy Chroma palace into the new service-backed runtime.",
        "input_schema": {
            "type": "object",
            "properties": {
                "palace_path": {"type": "string", "description": "Path to the legacy Chroma palace directory"},
                "collection_name": {"type": "string", "description": "Legacy Chroma collection name"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
            "required": ["palace_path"],
        },
        "handler": tool_migrate_legacy_service,
    },
    "mempalace_search": {
        "description": "Semantic search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "wing": {"type": "string"},
                "room": {"type": "string"},
                "mode": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
            "required": ["query"],
        },
        "handler": tool_search_memory_service,
    },
    "mempalace_search_time_range": {
        "description": "Search memory within an explicit inclusive time range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "mode": {"type": "string"},
                "limit": {"type": "integer"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
            "required": ["query", "start_time", "end_time"],
        },
        "handler": tool_search_time_range_service,
    },
    "mempalace_explain_retrieval": {
        "description": "Return the full inspectable retrieval payload.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {"type": "string"},
                "wing": {"type": "string"},
                "room": {"type": "string"},
                "limit": {"type": "integer"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "filters": {"type": "object"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
            "required": ["query"],
        },
        "handler": tool_explain_retrieval_service,
    },
    "mempalace_fetch_document": {
        "description": "Fetch one document and its indexed segments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "config_path": {"type": "string"},
            },
            "required": ["document_id"],
        },
        "handler": tool_fetch_document_service,
    },
    "mempalace_fetch_evidence": {
        "description": "Fetch a provenance trail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact_id": {"type": "string"},
                "segment_id": {"type": "string"},
                "document_id": {"type": "string"},
                "neighbor_count": {"type": "integer"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
        },
        "handler": tool_fetch_evidence_trail_service,
    },
    "mempalace_extract_facts": {
        "description": "Extract deterministic structured facts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
        },
        "handler": tool_extract_facts_service,
    },
    "mempalace_query_facts": {
        "description": "Query structured facts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object_text": {"type": "string"},
                "limit": {"type": "integer"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
        },
        "handler": tool_query_facts_service,
    },
    "mempalace_reindex": {
        "description": "Rebuild vector entries from stored segments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
        },
        "handler": tool_reindex_service,
    },
    "mempalace_recall_episodes": {
        "description": "Recall recent or query-matched episodes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "limit": {"type": "integer"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
        },
        "handler": tool_recall_episodes_service,
    },
    "mempalace_compact_session_context": {
        "description": "Assemble a compact agent-ready context block.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "evidence_limit": {"type": "integer"},
                "fact_limit": {"type": "integer"},
                "episode_limit": {"type": "integer"},
                "max_chars": {"type": "integer"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
        },
        "handler": tool_compact_session_context_service,
    },
    "mempalace_prepare_startup_context": {
        "description": "Prepare startup context for an agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string"},
                "query": {"type": "string"},
                "evidence_limit": {"type": "integer"},
                "fact_limit": {"type": "integer"},
                "episode_limit": {"type": "integer"},
                "max_chars": {"type": "integer"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
            },
        },
        "handler": tool_prepare_startup_context_service,
    },
}


# ── JSON-RPC Handler ────────────────────────────────────────────────────

def handle_request(request):
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mempalace", "version": __version__},
            },
        }
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {"name": n, "description": t["description"], "inputSchema": t["input_schema"]}
                    for n, t in MCP_TOOLS.items()
                ]
            },
        }
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        if tool_name not in MCP_TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }
        # Coerce types based on schema
        schema_props = MCP_TOOLS[tool_name]["input_schema"].get("properties", {})
        for key, value in list(tool_args.items()):
            prop_schema = schema_props.get(key, {})
            declared_type = prop_schema.get("type")
            if declared_type == "integer" and not isinstance(value, int):
                tool_args[key] = int(value)
            elif declared_type == "number" and not isinstance(value, (int, float)):
                tool_args[key] = float(value)
        try:
            result = MCP_TOOLS[tool_name]["handler"](**tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }
        except Exception:
            logger.exception(f"Tool error in {tool_name}")
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": "Internal tool error"}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


# ── Main Loop ───────────────────────────────────────────────────────────

def main():
    logger.info("MemPalace MCP Server starting...")
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Server error: {e}")


if __name__ == "__main__":
    main()
