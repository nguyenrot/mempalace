"""
mcp_server.py — MCP Server (Compat Shim)
=======================================

This is the actual implementation of the MCP server.
It lives in compat/ so the root-level entrypoint can delegate.

Root entrypoint: python -m mempalace.mcp_server
Compat entrypoint: python -m mempalace.compat.mcp_server
"""

import hashlib
import json
import logging
import sys
from datetime import datetime

import chromadb

from mempalace.compat._legacy_chroma import add_texts, query_text
from mempalace.compat._legacy_config import MempalaceConfig
from mempalace.compat._legacy_knowledge_graph import KnowledgeGraph
from mempalace.compat._legacy_palace_graph import find_tunnels, graph_stats, traverse
from mempalace.compat._legacy_searcher import search_memories
from mempalace.interfaces.mcp.service_tools import (
    tool_compact_session_context_service,
    tool_explain_retrieval_service,
    tool_extract_facts_service,
    tool_fetch_document_service,
    tool_fetch_evidence_trail_service,
    tool_ingest_directory_service,
    tool_ingest_source_service,
    tool_migrate_legacy_service,
    tool_query_facts_service,
    tool_recall_episodes_service,
    tool_reindex_service,
    tool_search_memory_service,
    tool_search_time_range_service,
    tool_prepare_startup_context_service,
    tool_status_health_service,
)
from mempalace.version import __version__


_config = MempalaceConfig()


def _get_kg():
    """Lazily create the KnowledgeGraph singleton.

    Allows external patches to override via _kg_ref["instance"].
    """
    if _kg_ref["instance"] is not None:
        return _kg_ref["instance"]
    if not hasattr(_get_kg, "_instance"):
        _get_kg._instance = KnowledgeGraph()
    return _get_kg._instance


# Shared ref dict — allows root-level shim to inject a patched KG for tests
_kg_ref: dict = {"instance": None}


logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
logger = logging.getLogger("mempalace_mcp")


def _get_collection(create=False):
    """Return the ChromaDB collection, or None on failure."""
    try:
        client = chromadb.PersistentClient(path=_config.palace_path)
        if create:
            return client.get_or_create_collection(_config.collection_name)
        return client.get_collection(_config.collection_name)
    except Exception:
        return None


def _no_palace():
    return {
        "error": "No palace found",
        "hint": "Run: mempalace init <dir> && mempalace mine <dir>",
    }


def tool_status(runtime: str = "legacy", config_path: str = None, workspace_id: str = None):
    if runtime == "service" or config_path or workspace_id:
        result = tool_status_health_service(config_path=config_path, workspace_id=workspace_id)
        result["runtime"] = "service"
        return result

    col = _get_collection()
    if not col:
        return _no_palace()
    count = col.count()
    wings = {}
    rooms = {}
    try:
        all_meta = col.get(include=["metadatas"], limit=10000)["metadatas"]
        for m in all_meta:
            w = m.get("wing", "unknown")
            r = m.get("room", "unknown")
            wings[w] = wings.get(w, 0) + 1
            rooms[r] = rooms.get(r, 0) + 1
    except Exception:
        pass
    return {
        "total_drawers": count,
        "wings": wings,
        "rooms": rooms,
        "palace_path": _config.palace_path,
        "protocol": PALACE_PROTOCOL,
        "aaak_dialect": AAAK_SPEC,
    }


PALACE_PROTOCOL = """IMPORTANT — MemPalace Memory Protocol:
1. ON WAKE-UP: Call mempalace_status to load palace overview + AAAK spec.
2. BEFORE RESPONDING about any person, project, or past event: call mempalace_kg_query or mempalace_search FIRST. Never guess — verify.
3. IF UNSURE about a fact (name, gender, age, relationship): say "let me check" and query the palace. Wrong is worse than slow.
4. AFTER EACH SESSION: call mempalace_diary_write to record what happened, what you learned, what matters.
5. WHEN FACTS CHANGE: call mempalace_kg_invalidate on the old fact, mempalace_kg_add for the new one.

This protocol ensures the AI KNOWS before it speaks. Storage is not memory — but storage + this protocol = memory."""

AAAK_SPEC = """AAAK is a compressed memory dialect that MemPalace uses for efficient storage.
It is designed to be readable by both humans and LLMs without decoding.

FORMAT:
  ENTITIES: 3-letter uppercase codes. ALC=Alice, JOR=Jordan, RIL=Riley, MAX=Max, BEN=Ben.
  EMOTIONS: *action markers* before/during text. *warm*=joy, *fierce*=determined, *raw*=vulnerable, *bloom*=tenderness.
  STRUCTURE: Pipe-separated fields. FAM: family | PROJ: projects | ⚠: warnings/reminders.
  DATES: ISO format (2026-03-31). COUNTS: Nx = N mentions (e.g., 570x).
  IMPORTANCE: ★ to ★★★★★ (1-5 scale).
  HALLS: hall_facts, hall_events, hall_discoveries, hall_preferences, hall_advice.
  WINGS: wing_user, wing_agent, wing_team, wing_code, wing_myproject, wing_hardware, wing_ue5, wing_ai_research.
  ROOMS: Hyphenated slugs representing named ideas (e.g., chromadb-setup, gpu-pricing).

EXAMPLE:
  FAM: ALC→♡JOR | 2D(kids): RIL(18,sports) MAX(11,chess+swimming) | BEN(contributor)

Read AAAK naturally — expand codes mentally, treat *markers* as emotional context.
When WRITING AAAK: use entity codes, mark emotions, keep structure tight."""


def tool_list_wings():
    col = _get_collection()
    if not col:
        return _no_palace()
    wings = {}
    try:
        all_meta = col.get(include=["metadatas"], limit=10000)["metadatas"]
        for m in all_meta:
            w = m.get("wing", "unknown")
            wings[w] = wings.get(w, 0) + 1
    except Exception:
        pass
    return {"wings": wings}


def tool_list_rooms(wing: str = None):
    col = _get_collection()
    if not col:
        return _no_palace()
    rooms = {}
    try:
        kwargs = {"include": ["metadatas"], "limit": 10000}
        if wing:
            kwargs["where"] = {"wing": wing}
        all_meta = col.get(**kwargs)["metadatas"]
        for m in all_meta:
            r = m.get("room", "unknown")
            rooms[r] = rooms.get(r, 0) + 1
    except Exception:
        pass
    return {"wing": wing or "all", "rooms": rooms}


def tool_get_taxonomy():
    col = _get_collection()
    if not col:
        return _no_palace()
    taxonomy = {}
    try:
        all_meta = col.get(include=["metadatas"], limit=10000)["metadatas"]
        for m in all_meta:
            w = m.get("wing", "unknown")
            r = m.get("room", "unknown")
            if w not in taxonomy:
                taxonomy[w] = {}
            taxonomy[w][r] = taxonomy[w].get(r, 0) + 1
    except Exception:
        pass
    return {"taxonomy": taxonomy}


def tool_search(
    query: str,
    limit: int = 5,
    wing: str = None,
    room: str = None,
    runtime: str = "legacy",
    config_path: str = None,
    workspace_id: str = None,
    mode: str = "hybrid",
    start_time: str = None,
    end_time: str = None,
):
    if runtime == "service" or config_path or workspace_id or start_time or end_time:
        result = tool_search_memory_service(
            query=query,
            limit=limit,
            mode=mode,
            start_time=start_time,
            end_time=end_time,
            wing=wing,
            room=room,
            config_path=config_path,
            workspace_id=workspace_id,
        )
        result["runtime"] = "service"
        return result

    return search_memories(
        query, palace_path=_config.palace_path, wing=wing, room=room, n_results=limit,
    )


def tool_check_duplicate(content: str, threshold: float = 0.9):
    col = _get_collection()
    if not col:
        return _no_palace()
    try:
        results = query_text(
            col,
            content,
            n_results=5,
            include=["metadatas", "documents", "distances"],
        )
        duplicates = []
        if results["ids"] and results["ids"][0]:
            for i, drawer_id in enumerate(results["ids"][0]):
                dist = results["distances"][0][i]
                similarity = round(1 - dist, 3)
                if similarity >= threshold:
                    meta = results["metadatas"][0][i]
                    doc = results["documents"][0][i]
                    duplicates.append({
                        "id": drawer_id,
                        "wing": meta.get("wing", "?"),
                        "room": meta.get("room", "?"),
                        "similarity": similarity,
                        "content": doc[:200] + "..." if len(doc) > 200 else doc,
                    })
        return {"is_duplicate": len(duplicates) > 0, "matches": duplicates}
    except Exception as e:
        return {"error": str(e)}


def tool_get_aaak_spec():
    return {"aaak_spec": AAAK_SPEC}


def tool_traverse_graph(start_room: str, max_hops: int = 2):
    col = _get_collection()
    if not col:
        return _no_palace()
    return traverse(start_room, col=col, max_hops=max_hops)


def tool_find_tunnels(wing_a: str = None, wing_b: str = None):
    col = _get_collection()
    if not col:
        return _no_palace()
    return find_tunnels(wing_a, wing_b, col=col)


def tool_graph_stats():
    col = _get_collection()
    if not col:
        return _no_palace()
    return graph_stats(col=col)


def tool_add_drawer(wing: str, room: str, content: str, source_file: str = None, added_by: str = "mcp"):
    col = _get_collection(create=True)
    if not col:
        return _no_palace()

    dup = tool_check_duplicate(content, threshold=0.9)
    if dup.get("is_duplicate"):
        return {"success": False, "reason": "duplicate", "matches": dup["matches"]}

    drawer_id = f"drawer_{wing}_{room}_{hashlib.md5((content[:100] + datetime.now().isoformat()).encode()).hexdigest()[:16]}"

    try:
        add_texts(
            col,
            ids=[drawer_id],
            documents=[content],
            metadatas=[{
                "wing": wing, "room": room, "source_file": source_file or "",
                "chunk_index": 0, "added_by": added_by,
                "filed_at": datetime.now().isoformat(),
            }],
        )
        logger.info(f"Filed drawer: {drawer_id} → {wing}/{room}")
        return {"success": True, "drawer_id": drawer_id, "wing": wing, "room": room}
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_delete_drawer(drawer_id: str):
    col = _get_collection()
    if not col:
        return _no_palace()
    existing = col.get(ids=[drawer_id])
    if not existing["ids"]:
        return {"success": False, "error": f"Drawer not found: {drawer_id}"}
    try:
        col.delete(ids=[drawer_id])
        logger.info(f"Deleted drawer: {drawer_id}")
        return {"success": True, "drawer_id": drawer_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_kg_query(entity: str, as_of: str = None, direction: str = "both"):
    results = _get_kg().query_entity(entity, as_of=as_of, direction=direction)
    return {"entity": entity, "as_of": as_of, "facts": results, "count": len(results)}


def tool_kg_add(subject: str, predicate: str, object: str, valid_from: str = None, source_closet: str = None):
    triple_id = _get_kg().add_triple(subject, predicate, object, valid_from=valid_from, source_closet=source_closet)
    return {"success": True, "triple_id": triple_id, "fact": f"{subject} → {predicate} → {object}"}


def tool_kg_invalidate(subject: str, predicate: str, object: str, ended: str = None):
    _get_kg().invalidate(subject, predicate, object, ended=ended)
    return {"success": True, "fact": f"{subject} → {predicate} → {object}", "ended": ended or "today"}


def tool_kg_timeline(entity: str = None):
    results = _get_kg().timeline(entity)
    return {"entity": entity or "all", "timeline": results, "count": len(results)}


def tool_kg_stats():
    return _get_kg().stats()


def tool_diary_write(agent_name: str, entry: str, topic: str = "general"):
    wing = f"wing_{agent_name.lower().replace(' ', '_')}"
    room = "diary"
    col = _get_collection(create=True)
    if not col:
        return _no_palace()

    now = datetime.now()
    entry_id = f"diary_{wing}_{now.strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(entry[:50].encode()).hexdigest()[:8]}"

    try:
        add_texts(
            col,
            ids=[entry_id],
            documents=[entry],
            metadatas=[{
                "wing": wing, "room": room, "hall": "hall_diary",
                "topic": topic, "type": "diary_entry", "agent": agent_name,
                "filed_at": now.isoformat(), "date": now.strftime("%Y-%m-%d"),
            }],
        )
        logger.info(f"Diary entry: {entry_id} → {wing}/diary/{topic}")
        return {"success": True, "entry_id": entry_id, "agent": agent_name, "topic": topic, "timestamp": now.isoformat()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_diary_read(agent_name: str, last_n: int = 10):
    wing = f"wing_{agent_name.lower().replace(' ', '_')}"
    col = _get_collection()
    if not col:
        return _no_palace()

    try:
        results = col.get(
            where={"$and": [{"wing": wing}, {"room": "diary"}]},
            include=["documents", "metadatas"], limit=10000,
        )
        if not results["ids"]:
            return {"agent": agent_name, "entries": [], "message": "No diary entries yet."}

        entries = []
        for doc, meta in zip(results["documents"], results["metadatas"]):
            entries.append({
                "date": meta.get("date", ""),
                "timestamp": meta.get("filed_at", ""),
                "topic": meta.get("topic", ""),
                "content": doc,
            })
        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        entries = entries[:last_n]
        return {"agent": agent_name, "entries": entries, "total": len(results["ids"]), "showing": len(entries)}
    except Exception as e:
        return {"error": str(e)}


SERVICE_TOOLS = {
    "mempalace_legacy_status_hidden": {
        "description": "Health and storage counts for the new service-backed runtime.",
        "input_schema": {
            "type": "object",
            "properties": {
                "config_path": {"type": "string", "description": "Optional YAML config path for the service runtime"},
                "workspace_id": {"type": "string", "description": "Optional workspace override"},
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
    "mempalace_legacy_search_hidden": {
        "description": "Search memory through the new service-backed runtime.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "mode": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "wing": {"type": "string"},
                "room": {"type": "string"},
                "filters": {"type": "object"},
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
                "limit": {"type": "integer"},
                "mode": {"type": "string"},
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
                "limit": {"type": "integer"},
                "mode": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "wing": {"type": "string"},
                "room": {"type": "string"},
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
        "handler": tool_status,
    },
    "mempalace_list_wings": {
        "description": "List all wings with drawer counts",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_list_wings,
    },
    "mempalace_list_rooms": {
        "description": "List rooms within a wing",
        "input_schema": {
            "type": "object",
            "properties": {"wing": {"type": "string"}},
        },
        "handler": tool_list_rooms,
    },
    "mempalace_get_taxonomy": {
        "description": "Full taxonomy: wing → room → drawer count",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_get_taxonomy,
    },
    "mempalace_get_aaak_spec": {
        "description": "Get the AAAK dialect specification.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_get_aaak_spec,
    },
    "mempalace_kg_query": {
        "description": "Query the knowledge graph for an entity's relationships.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "as_of": {"type": "string"},
                "direction": {"type": "string"},
            },
            "required": ["entity"],
        },
        "handler": tool_kg_query,
    },
    "mempalace_kg_add": {
        "description": "Add a fact to the knowledge graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
                "valid_from": {"type": "string"},
                "source_closet": {"type": "string"},
            },
            "required": ["subject", "predicate", "object"],
        },
        "handler": tool_kg_add,
    },
    "mempalace_kg_invalidate": {
        "description": "Mark a fact as no longer true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
                "ended": {"type": "string"},
            },
            "required": ["subject", "predicate", "object"],
        },
        "handler": tool_kg_invalidate,
    },
    "mempalace_kg_timeline": {
        "description": "Chronological timeline of facts.",
        "input_schema": {
            "type": "object",
            "properties": {"entity": {"type": "string"}},
        },
        "handler": tool_kg_timeline,
    },
    "mempalace_kg_stats": {
        "description": "Knowledge graph overview.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_kg_stats,
    },
    "mempalace_traverse": {
        "description": "Walk the palace graph from a room.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_room": {"type": "string"},
                "max_hops": {"type": "integer"},
            },
            "required": ["start_room"],
        },
        "handler": tool_traverse_graph,
    },
    "mempalace_find_tunnels": {
        "description": "Find rooms that bridge two wings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wing_a": {"type": "string"},
                "wing_b": {"type": "string"},
            },
        },
        "handler": tool_find_tunnels,
    },
    "mempalace_graph_stats": {
        "description": "Palace graph overview.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_graph_stats,
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
                "runtime": {"type": "string"},
                "config_path": {"type": "string"},
                "workspace_id": {"type": "string"},
                "mode": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
            },
            "required": ["query"],
        },
        "handler": tool_search,
    },
    "mempalace_check_duplicate": {
        "description": "Check if content already exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "threshold": {"type": "number"},
            },
            "required": ["content"],
        },
        "handler": tool_check_duplicate,
    },
    "mempalace_add_drawer": {
        "description": "File verbatim content into the palace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string"},
                "room": {"type": "string"},
                "content": {"type": "string"},
                "source_file": {"type": "string"},
                "added_by": {"type": "string"},
            },
            "required": ["wing", "room", "content"],
        },
        "handler": tool_add_drawer,
    },
    "mempalace_delete_drawer": {
        "description": "Delete a drawer by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"drawer_id": {"type": "string"}},
            "required": ["drawer_id"],
        },
        "handler": tool_delete_drawer,
    },
    "mempalace_diary_write": {
        "description": "Write to your personal agent diary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string"},
                "entry": {"type": "string"},
                "topic": {"type": "string"},
            },
            "required": ["agent_name", "entry"],
        },
        "handler": tool_diary_write,
    },
    "mempalace_diary_read": {
        "description": "Read your recent diary entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string"},
                "last_n": {"type": "integer"},
            },
            "required": ["agent_name"],
        },
        "handler": tool_diary_read,
    },
}


MCP_VISIBLE_TOOL_NAMES = (
    "mempalace_status",
    "mempalace_ingest",
    "mempalace_ingest_source",
    "mempalace_migrate_legacy",
    "mempalace_search",
    "mempalace_search_time_range",
    "mempalace_explain_retrieval",
    "mempalace_fetch_document",
    "mempalace_fetch_evidence",
    "mempalace_extract_facts",
    "mempalace_query_facts",
    "mempalace_reindex",
    "mempalace_recall_episodes",
    "mempalace_compact_session_context",
    "mempalace_prepare_startup_context",
)
MCP_TOOLS = {name: SERVICE_TOOLS[name] for name in MCP_VISIBLE_TOOL_NAMES}


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
