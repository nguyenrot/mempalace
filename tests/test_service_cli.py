"""Integration tests for service-backed CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import chromadb

from mempalace.cli import main


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_config(path: Path) -> Path:
    config_path = path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "workspace_id: cli-workspace",
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


def test_service_cli_commands_end_to_end(tmp_path: Path, monkeypatch, capsys) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "docs" / "decision.md",
        "\n".join(
            [
                "We decided to migrate authentication to passkeys in Q3.",
                "The rollout keeps JWT support until mobile clients are upgraded.",
                "Observability must include provenance-rich retrieval output.",
            ]
        ),
    )
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "ingest-directory", str(workspace), "--config", str(config_path)],
    )
    main()
    ingest_payload = json.loads(capsys.readouterr().out)
    assert ingest_payload["documents_written"] == 1
    document_id = ingest_payload["file_results"][0]["document_id"]
    assert document_id

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "search-memory",
            "passkeys provenance",
            "--config",
            str(config_path),
            "--mode",
            "hybrid",
        ],
    )
    main()
    search_payload = json.loads(capsys.readouterr().out)
    assert search_payload["plan"]["mode"] == "hybrid"
    assert search_payload["results"]
    assert search_payload["results"][0]["source_uri"].endswith("decision.md")

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "fetch-document", document_id, "--config", str(config_path)],
    )
    main()
    fetch_payload = json.loads(capsys.readouterr().out)
    assert fetch_payload["document"]["document_id"] == document_id
    assert len(fetch_payload["segments"]) >= 1

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "status-health", "--config", str(config_path)],
    )
    main()
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["workspace_id"] == "cli-workspace"
    assert status_payload["counts"]["documents"] == 1


def test_legacy_command_names_can_use_service_runtime(tmp_path: Path, monkeypatch, capsys) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "docs" / "search.md",
        "\n".join(
            [
                "The new retrieval runtime returns evidence with provenance.",
                "Search results should explain their score and source.",
            ]
        ),
    )
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "ingest-directory", str(workspace), "--config", str(config_path)],
    )
    main()
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "search",
            "provenance score",
            "--runtime",
            "service",
            "--config",
            str(config_path),
        ],
    )
    main()
    search_output = capsys.readouterr().out
    assert "Service Results for" in search_output
    assert "search.md" in search_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "status",
            "--runtime",
            "service",
            "--config",
            str(config_path),
        ],
    )
    main()
    status_output = capsys.readouterr().out
    assert "Service Runtime Status" in status_output
    assert "documents" in status_output


def test_mine_command_can_use_service_runtime(tmp_path: Path, monkeypatch, capsys) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "src" / "memory.py",
        "\n".join(
            [
                "def build_memory_runtime():",
                "    return 'service-backed'",
                "",
                "def explain_retrieval():",
                "    return 'provenance and score breakdown'",
            ]
        ),
    )
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "mine",
            str(workspace),
            "--runtime",
            "service",
            "--config",
            str(config_path),
        ],
    )
    main()
    output = capsys.readouterr().out
    assert "Service Runtime Ingest" in output
    assert "Documents written: 1" in output


def test_mine_service_runtime_supports_convos_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "chat.md",
        "> What is memory?\nMemory is persistence.\n\n> Why does it matter?\nIt enables continuity.\n\n> How do we build it?\nWith structured storage.\n",
    )
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "mine",
            str(workspace),
            "--mode",
            "convos",
            "--runtime",
            "service",
            "--config",
            str(config_path),
        ],
    )
    main()
    output = capsys.readouterr().out
    assert "Service Runtime Ingest" in output
    assert "conversation_files" in output
    assert "Segments written:" in output


def test_migrate_legacy_command_supports_filtered_service_search(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    palace_path = _seed_legacy_palace(tmp_path)
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "migrate-legacy",
            str(palace_path),
            "--config",
            str(config_path),
        ],
    )
    main()
    migration_payload = json.loads(capsys.readouterr().out)
    assert migration_payload["drawers_migrated"] == 2
    assert migration_payload["source_type"] == "legacy_chroma"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "search",
            "vector search",
            "--runtime",
            "service",
            "--config",
            str(config_path),
            "--wing",
            "notes",
            "--room",
            "planning",
        ],
    )
    main()
    search_output = capsys.readouterr().out
    assert "Service Results for" in search_output
    assert "sprint.md" in search_output
    assert "db.py" not in search_output


def test_service_project_ingest_supports_manifest_filters(
    tmp_path: Path, monkeypatch, capsys
) -> None:
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

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "mine",
            str(workspace),
            "--runtime",
            "service",
            "--config",
            str(config_path),
        ],
    )
    main()
    output = capsys.readouterr().out
    assert "Documents written: 2" in output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "search",
            "roadmap migration",
            "--runtime",
            "service",
            "--config",
            str(config_path),
            "--wing",
            "billing_app",
            "--room",
            "planning",
        ],
    )
    main()
    search_output = capsys.readouterr().out
    assert "plan.md" in search_output
    assert "service.py" not in search_output


def test_service_mine_runtime_respects_gitignore_overrides(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    _write(workspace / ".gitignore", "docs/\n")
    _write(workspace / "src" / "main.py", "print('main')\n" * 20)
    _write(workspace / "docs" / "guide.md", "# Guide\n" * 20)
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "mine",
            str(workspace),
            "--runtime",
            "service",
            "--config",
            str(config_path),
        ],
    )
    main()
    first_output = capsys.readouterr().out
    assert "Documents written: 1" in first_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "mine",
            str(workspace),
            "--runtime",
            "service",
            "--config",
            str(config_path),
            "--include-ignored",
            "docs",
        ],
    )
    main()
    second_output = capsys.readouterr().out
    assert "guide.md" in second_output


def test_service_fact_commands_end_to_end(tmp_path: Path, monkeypatch, capsys) -> None:
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

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "ingest-directory", str(workspace), "--config", str(config_path)],
    )
    main()
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "extract-facts", "--config", str(config_path)],
    )
    main()
    extraction_payload = json.loads(capsys.readouterr().out)
    assert extraction_payload["facts_written"] >= 3

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "query-facts",
            "JWT",
            "--predicate",
            "uses",
            "--config",
            str(config_path),
        ],
    )
    main()
    query_payload = json.loads(capsys.readouterr().out)
    assert query_payload
    assert query_payload[0]["predicate"] == "uses"


def test_service_cli_context_and_reindex_commands_end_to_end(
    tmp_path: Path, monkeypatch, capsys
) -> None:
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

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "ingest-source", str(source_path), "--config", str(config_path)],
    )
    main()
    ingest_payload = json.loads(capsys.readouterr().out)
    assert ingest_payload["documents_written"] == 1

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mempalace",
            "ingest-directory",
            str(convo_workspace),
            "--mode",
            "convos",
            "--config",
            str(config_path),
        ],
    )
    main()
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "extract-facts", "--config", str(config_path)],
    )
    main()
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "query-facts", "JWT", "--predicate", "uses", "--config", str(config_path)],
    )
    main()
    fact_payload = json.loads(capsys.readouterr().out)
    fact_id = fact_payload[0]["fact_id"]

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "fetch-evidence", "--fact-id", fact_id, "--config", str(config_path)],
    )
    main()
    evidence_payload = json.loads(capsys.readouterr().out)
    assert evidence_payload["focus_fact"]["fact_id"] == fact_id
    assert evidence_payload["evidence"]

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "explain-retrieval", "JWT provenance", "--config", str(config_path)],
    )
    main()
    explain_payload = json.loads(capsys.readouterr().out)
    assert explain_payload["plan"]["candidate_counts"]["merged_hits"] >= 1

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "recall-episodes", "provenance", "--config", str(config_path)],
    )
    main()
    episodes_payload = json.loads(capsys.readouterr().out)
    assert any(item["metadata"].get("session_id") == "startup-001" for item in episodes_payload)

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "prepare-startup-context", "JWT provenance", "--agent-name", "codex", "--config", str(config_path)],
    )
    main()
    startup_payload = json.loads(capsys.readouterr().out)
    assert startup_payload["agent_name"] == "codex"
    assert startup_payload["startup_text"]

    monkeypatch.setattr(
        sys,
        "argv",
        ["mempalace", "reindex", "--config", str(config_path)],
    )
    main()
    reindex_payload = json.loads(capsys.readouterr().out)
    assert reindex_payload["documents_reindexed"] >= 1
