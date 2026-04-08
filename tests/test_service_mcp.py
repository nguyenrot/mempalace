"""Integration tests for service-backed MCP tools."""

from __future__ import annotations

import json
from pathlib import Path

import chromadb

from mempalace.mcp_server import handle_request


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_config(path: Path) -> Path:
    config_path = path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "workspace_id: mcp-workspace",
                "storage:",
                f"  base_dir: {path / 'runtime'}",
                f"  metadata_path: {path / 'runtime' / 'memory.sqlite3'}",
                "logging:",
                "  json: false",
                "  level: INFO",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _seed_legacy_palace(path: Path) -> Path:
    palace_path = path / "legacy-palace"
    client = chromadb.PersistentClient(path=str(palace_path))
    collection = client.get_or_create_collection("mempalace_drawers")
    collection.add(
        ids=["drawer_notes_planning_001", "drawer_project_backend_002"],
        documents=[
            "Vector search migration planning says we should preserve provenance in Q3.",
            "Vector search backend integration uses PostgreSQL and pgbouncer.",
        ],
        embeddings=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        metadatas=[
            {
                "wing": "notes",
                "room": "planning",
                "source_file": "sprint.md",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-04T00:00:00",
            },
            {
                "wing": "project",
                "room": "backend",
                "source_file": "db.py",
                "chunk_index": 0,
                "added_by": "miner",
                "filed_at": "2026-01-02T00:00:00",
            },
        ],
    )
    return palace_path


def _call_tool(name: str, arguments: dict) -> dict:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    assert "result" in response
    return json.loads(response["result"]["content"][0]["text"])


def test_service_tools_are_listed() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert response is not None
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert "mempalace_status_health" in names
    assert "mempalace_ingest_directory" in names
    assert "mempalace_ingest_source" in names
    assert "mempalace_migrate_legacy" in names
    assert "mempalace_extract_facts" in names
    assert "mempalace_query_facts" in names
    assert "mempalace_search_memory" in names
    assert "mempalace_search_time_range" in names
    assert "mempalace_explain_retrieval" in names
    assert "mempalace_fetch_document" in names
    assert "mempalace_fetch_evidence_trail" in names
    assert "mempalace_reindex" in names
    assert "mempalace_recall_episodes" in names
    assert "mempalace_compact_session_context" in names
    assert "mempalace_prepare_startup_context" in names


def test_service_mcp_tools_end_to_end(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "notes" / "architecture.md",
        "\n".join(
            [
                "We are moving to a service-backed memory runtime.",
                "The retrieval path must return provenance and explainable scores.",
                "SQLite metadata plus FTS5 is the first local storage backend.",
            ]
        ),
    )
    config_path = _write_config(tmp_path)

    ingest_payload = _call_tool(
        "mempalace_ingest_directory",
        {"directory": str(workspace), "config_path": str(config_path)},
    )
    assert ingest_payload["documents_written"] == 1
    document_id = ingest_payload["file_results"][0]["document_id"]
    assert document_id

    status_payload = _call_tool(
        "mempalace_status_health",
        {"config_path": str(config_path)},
    )
    assert status_payload["workspace_id"] == "mcp-workspace"
    assert status_payload["counts"]["documents"] == 1

    search_payload = _call_tool(
        "mempalace_search_memory",
        {"query": "provenance scores", "config_path": str(config_path), "mode": "hybrid"},
    )
    assert search_payload["results"]
    assert search_payload["results"][0]["source_uri"].endswith("architecture.md")
    assert search_payload["results"][0]["retrieval_reason"]

    fetch_payload = _call_tool(
        "mempalace_fetch_document",
        {"document_id": document_id, "config_path": str(config_path)},
    )
    assert fetch_payload["document"]["document_id"] == document_id
    assert len(fetch_payload["segments"]) >= 1


def test_legacy_mcp_tool_names_can_use_service_runtime(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "notes" / "compat.md",
        "\n".join(
            [
                "Compatibility mode should let legacy MCP tools read the service runtime.",
                "Retrieval output still needs provenance and score explanations.",
            ]
        ),
    )
    config_path = _write_config(tmp_path)

    ingest_payload = _call_tool(
        "mempalace_ingest_directory",
        {"directory": str(workspace), "config_path": str(config_path)},
    )
    assert ingest_payload["documents_written"] == 1

    status_payload = _call_tool(
        "mempalace_status",
        {"runtime": "service", "config_path": str(config_path)},
    )
    assert status_payload["runtime"] == "service"
    assert status_payload["counts"]["documents"] == 1

    search_payload = _call_tool(
        "mempalace_search",
        {
            "query": "provenance explanations",
            "runtime": "service",
            "config_path": str(config_path),
            "mode": "hybrid",
        },
    )
    assert search_payload["runtime"] == "service"
    assert search_payload["results"]
    assert search_payload["results"][0]["retrieval_reason"]


def test_service_mcp_conversation_ingest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "chat.jsonl",
        "\n".join(
            [
                '{"type":"session_meta","session_id":"1"}',
                '{"type":"event_msg","payload":{"type":"user_message","message":"Why did we switch to SQLite?"}}',
                '{"type":"event_msg","payload":{"type":"agent_message","message":"Because local-first metadata and FTS5 are simpler to operate."}}',
                '{"type":"event_msg","payload":{"type":"user_message","message":"What about provenance?"}}',
                '{"type":"event_msg","payload":{"type":"agent_message","message":"Each segment should keep source and document identifiers."}}',
            ]
        ),
    )
    config_path = _write_config(tmp_path)

    ingest_payload = _call_tool(
        "mempalace_ingest_directory",
        {
            "directory": str(workspace),
            "config_path": str(config_path),
            "mode": "convos",
            "extract_mode": "exchange",
        },
    )
    assert ingest_payload["source_type"] == "conversation_files"
    assert ingest_payload["documents_written"] == 1
    assert ingest_payload["segments_written"] >= 1

    search_payload = _call_tool(
        "mempalace_search_memory",
        {"query": "SQLite provenance", "config_path": str(config_path), "mode": "hybrid"},
    )
    assert search_payload["results"]


def test_service_mcp_legacy_migration_and_filtered_search(tmp_path: Path) -> None:
    palace_path = _seed_legacy_palace(tmp_path)
    config_path = _write_config(tmp_path)

    migration_payload = _call_tool(
        "mempalace_migrate_legacy",
        {"palace_path": str(palace_path), "config_path": str(config_path)},
    )
    assert migration_payload["drawers_migrated"] == 2
    assert migration_payload["source_type"] == "legacy_chroma"

    search_payload = _call_tool(
        "mempalace_search",
        {
            "query": "vector search",
            "runtime": "service",
            "config_path": str(config_path),
            "wing": "notes",
            "room": "planning",
        },
    )
    assert search_payload["runtime"] == "service"
    assert search_payload["results"]
    assert search_payload["results"][0]["source_uri"] == "sprint.md"


def test_service_mcp_project_ingest_supports_manifest_filters(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "mempalace.yaml",
        "\n".join(
            [
                "wing: billing_app",
                "rooms:",
                "  - name: backend",
                "    keywords: [api, database]",
                "  - name: planning",
                "    keywords: [roadmap, milestone]",
            ]
        ),
    )
    _write(
        workspace / "backend" / "service.py",
        "\n".join(
            [
                "def build_api_service():",
                "    return 'database-backed service'",
            ]
        ),
    )
    _write(
        workspace / "notes" / "plan.md",
        "This roadmap milestone explains the billing migration plan for next quarter.",
    )
    config_path = _write_config(tmp_path)

    ingest_payload = _call_tool(
        "mempalace_ingest_directory",
        {"directory": str(workspace), "config_path": str(config_path)},
    )
    assert ingest_payload["documents_written"] == 2

    search_payload = _call_tool(
        "mempalace_search_memory",
        {
            "query": "roadmap migration",
            "config_path": str(config_path),
            "wing": "billing_app",
            "room": "planning",
        },
    )
    assert search_payload["results"]
    assert search_payload["results"][0]["source_uri"].endswith("plan.md")


def test_service_mcp_project_ingest_respects_gitignore_overrides(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(workspace / ".gitignore", "docs/\n")
    _write(workspace / "src" / "main.py", "print('main')\n" * 20)
    _write(workspace / "docs" / "guide.md", "# Guide\n" * 20)
    config_path = _write_config(tmp_path)

    ingest_payload = _call_tool(
        "mempalace_ingest_directory",
        {"directory": str(workspace), "config_path": str(config_path)},
    )
    assert ingest_payload["documents_written"] == 1

    include_payload = _call_tool(
        "mempalace_ingest_directory",
        {
            "directory": str(workspace),
            "config_path": str(config_path),
            "include_ignored": ["docs"],
        },
    )
    assert any(file_result["uri"].endswith("guide.md") for file_result in include_payload["file_results"])


def test_service_mcp_fact_tools_end_to_end(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "docs" / "decision.md",
        "\n".join(
            [
                "We decided to migrate authentication to passkeys in Q3.",
                "Authentication uses JWT access tokens and refresh tokens.",
                "Refresh tokens are stored in HttpOnly cookies.",
            ]
        ),
    )
    config_path = _write_config(tmp_path)

    ingest_payload = _call_tool(
        "mempalace_ingest_directory",
        {"directory": str(workspace), "config_path": str(config_path)},
    )
    assert ingest_payload["documents_written"] == 1

    extract_payload = _call_tool(
        "mempalace_extract_facts",
        {"config_path": str(config_path)},
    )
    assert extract_payload["facts_written"] >= 3

    query_payload = _call_tool(
        "mempalace_query_facts",
        {"query": "JWT", "predicate": "uses", "config_path": str(config_path)},
    )
    assert query_payload
    assert query_payload[0]["predicate"] == "uses"


def test_service_mcp_context_and_reindex_tools_end_to_end(tmp_path: Path) -> None:
    project_workspace = tmp_path / "project-workspace"
    convo_workspace = tmp_path / "convo-workspace"
    source_path = project_workspace / "docs" / "decision.md"
    _write(
        source_path,
        "\n".join(
            [
                "We decided to migrate authentication to passkeys in Q3.",
                "Authentication uses JWT access tokens and refresh tokens.",
                "Retrieval should keep provenance and evidence excerpts.",
            ]
        ),
    )
    _write(
        convo_workspace / "chat.jsonl",
        "\n".join(
            [
                '{"type":"session_meta","session_id":"startup-001"}',
                '{"type":"event_msg","payload":{"type":"user_message","message":"Why keep provenance in retrieval?"}}',
                '{"type":"event_msg","payload":{"type":"agent_message","message":"Because agents need exact evidence and source identifiers."}}',
            ]
        ),
    )
    config_path = _write_config(tmp_path)

    ingest_source_payload = _call_tool(
        "mempalace_ingest_source",
        {"path": str(source_path), "config_path": str(config_path)},
    )
    assert ingest_source_payload["documents_written"] == 1

    convo_payload = _call_tool(
        "mempalace_ingest_directory",
        {
            "directory": str(convo_workspace),
            "mode": "convos",
            "config_path": str(config_path),
        },
    )
    assert convo_payload["documents_written"] == 1

    extract_payload = _call_tool(
        "mempalace_extract_facts",
        {"config_path": str(config_path)},
    )
    assert extract_payload["facts_written"] >= 2

    facts_payload = _call_tool(
        "mempalace_query_facts",
        {"query": "JWT", "predicate": "uses", "config_path": str(config_path)},
    )
    fact_id = facts_payload[0]["fact_id"]

    evidence_payload = _call_tool(
        "mempalace_fetch_evidence_trail",
        {"fact_id": fact_id, "config_path": str(config_path)},
    )
    assert evidence_payload["focus_fact"]["fact_id"] == fact_id
    assert evidence_payload["evidence"]

    explain_payload = _call_tool(
        "mempalace_explain_retrieval",
        {"query": "JWT provenance", "config_path": str(config_path)},
    )
    assert explain_payload["plan"]["candidate_counts"]["merged_hits"] >= 1

    time_search_payload = _call_tool(
        "mempalace_search_time_range",
        {
            "query": "provenance",
            "start_time": "2024-01-01T00:00:00+00:00",
            "end_time": "2030-01-01T00:00:00+00:00",
            "config_path": str(config_path),
        },
    )
    assert time_search_payload["results"]

    episodes_payload = _call_tool(
        "mempalace_recall_episodes",
        {"query": "provenance", "config_path": str(config_path)},
    )
    assert any(item["metadata"].get("session_id") == "startup-001" for item in episodes_payload)

    compact_payload = _call_tool(
        "mempalace_compact_session_context",
        {"query": "JWT provenance", "config_path": str(config_path)},
    )
    assert compact_payload["context_text"]
    assert compact_payload["evidence"]

    startup_payload = _call_tool(
        "mempalace_prepare_startup_context",
        {"agent_name": "codex", "query": "JWT provenance", "config_path": str(config_path)},
    )
    assert startup_payload["agent_name"] == "codex"
    assert startup_payload["startup_text"]

    reindex_payload = _call_tool(
        "mempalace_reindex",
        {"config_path": str(config_path)},
    )
    assert reindex_payload["documents_reindexed"] >= 1
