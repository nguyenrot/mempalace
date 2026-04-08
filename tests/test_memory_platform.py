"""Tests for the new service-oriented memory platform slice."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import chromadb

from mempalace.api import LocalMemoryPlatform
from mempalace.domain.models import SearchMode, SearchRequest
from mempalace.infrastructure.settings import MemorySettings


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_platform(tmp_path: Path) -> LocalMemoryPlatform:
    settings = MemorySettings.from_mapping(
        {
            "workspace_id": "test-workspace",
            "storage": {
                "base_dir": str(tmp_path / "runtime"),
                "metadata_path": str(tmp_path / "runtime" / "memory.sqlite3"),
            },
            "logging": {"json": False, "level": "DEBUG"},
        }
    )
    return LocalMemoryPlatform.from_settings(settings)


def test_ingest_directory_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "docs" / "auth.md",
        "\n".join(
            [
                "Authentication uses JWT access tokens and refresh tokens.",
                "Refresh tokens are stored in HttpOnly cookies for browser clients.",
                "Access tokens expire after fifteen minutes to limit replay risk.",
            ]
        ),
    )
    _write(
        workspace / "notes" / "planning.md",
        "\n".join(
            [
                "Sprint plan: migrate authentication to passkeys in Q3.",
                "Keep the legacy JWT path during the rollout.",
                "Evaluate the retrieval explanation output before release.",
            ]
        ),
    )

    platform = _build_platform(tmp_path)
    first_result = platform.ingest_directory(workspace)
    second_result = platform.ingest_directory(workspace)

    assert first_result.documents_written == 2
    assert first_result.documents_skipped == 0
    assert first_result.segments_written >= 2

    assert second_result.documents_written == 0
    assert second_result.documents_updated == 0
    assert second_result.documents_skipped == 2

    status = platform.status()
    assert status["documents"] == 2
    assert status["segments"] >= 2


def test_ingest_directory_updates_changed_documents(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    auth_file = workspace / "docs" / "auth.md"
    _write(
        auth_file,
        "\n".join(
            [
                "Authentication uses JWT access tokens.",
                "Refresh tokens are stored in HttpOnly cookies.",
                "Rotation happens every login event.",
            ]
        ),
    )

    platform = _build_platform(tmp_path)
    first_result = platform.ingest_directory(workspace)
    document_id = first_result.file_results[0].document_id
    assert document_id is not None

    _write(
        auth_file,
        "\n".join(
            [
                "Authentication uses JWT access tokens.",
                "Refresh tokens are stored in encrypted server-side sessions.",
                "Rotation happens every login event and after credential reset.",
            ]
        ),
    )

    second_result = platform.ingest_directory(workspace)
    assert second_result.documents_updated == 1
    stored_document = platform.fetch_document(document_id)
    assert stored_document is not None
    assert "encrypted server-side sessions" in stored_document.raw_text


def test_hybrid_search_returns_provenance_and_score_breakdown(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "docs" / "auth.md",
        "\n".join(
            [
                "Authentication uses JWT access tokens and refresh tokens.",
                "Refresh tokens are stored in HttpOnly cookies for browser clients.",
                "The security review required shorter expiry windows.",
                "The final decision favored JWT because mobile clients already depended on it.",
            ]
        ),
    )
    _write(
        workspace / "docs" / "database.md",
        "\n".join(
            [
                "Database migrations are managed with Alembic.",
                "Connection pooling goes through PgBouncer.",
            ]
        ),
    )

    platform = _build_platform(tmp_path)
    platform.ingest_directory(workspace)

    response = platform.search("JWT refresh tokens", mode=SearchMode.HYBRID, limit=3)
    assert response.results

    top = response.results[0]
    assert top.source_uri.endswith("auth.md")
    assert top.document_id
    assert top.segment_id
    assert top.excerpt
    assert top.retrieval_reason
    assert top.scores.combined > 0
    assert top.scores.keyword is not None
    assert top.scores.semantic is not None


def test_time_bounded_search_filters_by_observed_time(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    older = workspace / "docs" / "older.md"
    newer = workspace / "docs" / "newer.md"

    _write(older, "We decided to migrate auth to passkeys after the mobile review.")
    _write(newer, "We decided to migrate billing to Stripe usage-based pricing.")

    older_time = datetime(2024, 1, 15, tzinfo=timezone.utc).timestamp()
    newer_time = datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp()
    os.utime(older, (older_time, older_time))
    os.utime(newer, (newer_time, newer_time))

    platform = _build_platform(tmp_path)
    platform.ingest_directory(workspace)

    request = SearchRequest(
        workspace_id="test-workspace",
        query="migrate",
        mode=SearchMode.KEYWORD,
        limit=5,
        start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
    )
    response = platform.retrieval_service.search(request)

    assert len(response.results) == 1
    assert response.results[0].source_uri.endswith("newer.md")


def test_platform_can_ingest_conversation_exports(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "chat.jsonl",
        "\n".join(
            [
                '{"type":"session_meta","session_id":"abc"}',
                '{"type":"event_msg","payload":{"type":"user_message","message":"Why do we keep raw history?"}}',
                '{"type":"event_msg","payload":{"type":"agent_message","message":"Because summaries lose provenance and exact wording."}}',
                '{"type":"event_msg","payload":{"type":"user_message","message":"How should retrieval explain itself?"}}',
                '{"type":"event_msg","payload":{"type":"agent_message","message":"By returning scores, source URIs, document IDs, and excerpts."}}',
            ]
        ),
    )

    platform = _build_platform(tmp_path)
    result = platform.ingest_directory(workspace, mode="convos", extract_mode="exchange")

    assert result.source_type == "conversation_files"
    assert result.documents_written == 1
    assert result.segments_written >= 1

    response = platform.search("provenance exact wording", mode=SearchMode.HYBRID, limit=3)
    assert response.results
    assert response.results[0].source_uri.endswith("chat.jsonl")


def test_platform_can_migrate_legacy_chroma_and_filter_results(tmp_path: Path) -> None:
    palace_path = tmp_path / "legacy-palace"
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

    platform = _build_platform(tmp_path)
    result = platform.migrate_legacy_palace(palace_path)

    assert result.drawers_migrated == 2
    assert result.segments_written == 2

    response = platform.search_request(
        SearchRequest(
            workspace_id="test-workspace",
            query="vector search",
            mode=SearchMode.HYBRID,
            limit=5,
            filters={"wing": "notes", "room": "planning"},
        )
    )
    assert response.results
    assert response.results[0].source_uri == "sprint.md"
    assert response.results[0].metadata["wing"] == "notes"
    assert response.results[0].metadata["room"] == "planning"


def test_platform_project_ingest_assigns_wing_and_room_metadata(tmp_path: Path) -> None:
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

    platform = _build_platform(tmp_path)
    result = platform.ingest_directory(workspace)

    assert result.documents_written == 2
    response = platform.search_request(
        SearchRequest(
            workspace_id="test-workspace",
            query="billing migration roadmap",
            mode=SearchMode.HYBRID,
            limit=5,
            filters={"wing": "billing_app", "room": "planning"},
        )
    )
    assert response.results
    top = response.results[0]
    assert top.source_uri.endswith("plan.md")
    assert top.metadata["wing"] == "billing_app"
    assert top.metadata["room"] == "planning"

    backend_docs = platform.search_request(
        SearchRequest(
            workspace_id="test-workspace",
            query="database service",
            mode=SearchMode.HYBRID,
            limit=5,
            filters={"wing": "billing_app", "room": "backend"},
        )
    )
    assert backend_docs.results
    assert backend_docs.results[0].source_uri.endswith("service.py")


def test_platform_project_ingest_respects_gitignore_and_include_overrides(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(workspace / ".gitignore", "docs/\n")
    _write(workspace / "src" / "main.py", "print('main')\n" * 20)
    _write(workspace / "docs" / "guide.md", "# Guide\n" * 20)

    platform = _build_platform(tmp_path)
    result = platform.ingest_directory(workspace)
    assert result.documents_written == 1
    assert result.file_results[0].uri.endswith("main.py")

    include_result = platform.ingest_directory(
        workspace,
        include_ignored=["docs"],
    )
    assert include_result.documents_written == 1
    assert any(file_result.uri.endswith("guide.md") for file_result in include_result.file_results)


def test_platform_can_extract_and_query_facts(tmp_path: Path) -> None:
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

    platform = _build_platform(tmp_path)
    ingest_result = platform.ingest_directory(workspace)
    document_id = ingest_result.file_results[0].document_id
    assert document_id is not None

    extraction_result = platform.extract_facts()
    assert extraction_result.documents_processed == 1
    assert extraction_result.facts_written >= 3
    assert extraction_result.entities_written >= 2

    facts = platform.query_facts(predicate="uses", limit=10)
    assert facts
    assert facts[0].document_id == document_id
    assert facts[0].subject == "Authentication"
    assert "JWT access tokens" in facts[0].object

    second_extraction = platform.extract_facts(document_id=document_id)
    assert second_extraction.facts_written >= 3

    status = platform.status()
    assert status["facts"] >= 3
    assert status["entities"] >= 2


def test_platform_can_ingest_single_source_and_reindex_vectors(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(
        workspace / "mempalace.yaml",
        "\n".join(
            [
                "wing: billing_app",
                "rooms:",
                "  - name: backend",
                "    keywords: [handler, database]",
            ]
        ),
    )
    source_path = workspace / "services" / "billing" / "handler.py"
    _write(
        source_path,
        "\n".join(
            [
                "def build_handler():",
                "    return 'database-backed handler'",
            ]
        ),
    )

    platform = _build_platform(tmp_path)
    ingest_result = platform.ingest_source(source_path)

    assert ingest_result.documents_written == 1
    document_id = ingest_result.file_results[0].document_id
    assert document_id is not None

    document = platform.fetch_document(document_id)
    assert document is not None
    assert document.metadata["wing"] == "billing_app"
    assert document.metadata["room"] == "backend"

    reindex_result = platform.reindex()
    assert reindex_result.documents_seen == 1
    assert reindex_result.documents_reindexed == 1
    assert reindex_result.segments_indexed >= 1


def test_platform_can_build_evidence_trail_episode_recall_and_startup_context(tmp_path: Path) -> None:
    project_workspace = tmp_path / "project-workspace"
    convo_workspace = tmp_path / "convo-workspace"
    _write(
        project_workspace / "docs" / "decision.md",
        "\n".join(
            [
                "We decided to migrate authentication to passkeys in Q3.",
                "Authentication uses JWT access tokens and refresh tokens.",
                "Refresh tokens are stored in HttpOnly cookies.",
                "Retrieval should always return provenance and exact evidence excerpts.",
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

    platform = _build_platform(tmp_path)
    platform.ingest_directory(project_workspace)
    platform.ingest_directory(convo_workspace, mode="convos", extract_mode="exchange")
    platform.extract_facts()

    fact = platform.query_facts(query="JWT", predicate="uses", limit=1)[0]
    evidence_trail = platform.fetch_evidence_trail(fact_id=fact.fact_id, neighbor_count=1)
    assert evidence_trail.focus_fact is not None
    assert evidence_trail.focus_fact.fact_id == fact.fact_id
    assert evidence_trail.document is not None
    assert evidence_trail.evidence
    assert evidence_trail.related_facts

    explained = platform.explain_retrieval("JWT provenance", limit=3)
    assert explained.results
    assert explained.plan.candidate_counts["merged_hits"] >= 1
    assert explained.plan.candidate_counts["filtered_hits"] >= 1

    episodes = platform.recall_episodes(query="provenance", limit=3)
    assert episodes
    assert any(episode.metadata.get("session_id") == "startup-001" for episode in episodes)

    compacted = platform.compact_session_context(query="JWT provenance", max_chars=1000)
    assert compacted.evidence
    assert compacted.facts
    assert "JWT" in compacted.context_text or "provenance" in compacted.context_text

    startup = platform.prepare_startup_context(agent_name="codex", query="JWT provenance", max_chars=1400)
    assert startup.agent_name == "codex"
    assert startup.evidence
    assert startup.facts
    assert "documents=" in startup.startup_text
