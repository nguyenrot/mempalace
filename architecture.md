# MemPalace Architecture

## Purpose

`mempalace` is a local-first memory layer for AI assistants and coding agents.

Its job is not to replace an LLM. Its job is to:

- preserve raw source material
- index that material for retrieval
- attach provenance to every result
- expose a predictable tool and CLI surface for agents

The current branch standardizes around a project-local runtime:

- each repository has its own `.mempalace/`
- each repository has its own storage
- each repository can run its own MCP server

## Product Model

At a high level, the system behaves like this:

1. `mempalace init` creates a project-local runtime.
2. `mempalace ingest` or `mempalace ingest-chat-history` stores documents and segments.
3. `mempalace search` and related commands retrieve evidence with provenance.
4. MCP tools expose the same capabilities to agents.

The implementation favors explicit data models, deterministic processing where practical, and inspectable retrieval over opaque heuristics.

## Design Principles

- Local-first by default
- Preserve raw source text whenever possible
- Keep storage interfaces swappable
- Make retrieval inspectable
- Make write paths observable
- Prefer deterministic pipelines over hidden LLM behavior
- Keep CLI and MCP naming aligned
- Treat migration from legacy behavior as explicit work, not magic

## Current Runtime Topology

```mermaid
flowchart TD
    A["CLI commands"] --> D["Application services"]
    B["MCP tools"] --> D
    C["Python API"] --> D
    D --> E["Metadata store (SQLite)"]
    D --> F["FTS5 search index"]
    D --> G["Vector index (SQLite-backed)"]
    D --> H["Filesystem scanner / conversation normalizer"]
```

## Runtime Layout On Disk

Inside a project repository, the standard layout is:

```text
<repo>/
  .mempalace/
    config.yaml
    .gitignore
    runtime/
      metadata.sqlite3
```

Important notes:

- `.mempalace/config.yaml` is the project-local runtime config.
- `.mempalace/runtime/metadata.sqlite3` currently stores metadata, FTS state, facts, and the local vector index.
- `.mempalace/.gitignore` keeps runtime data out of source control.

## Layered Architecture

The codebase keeps legacy modules for compatibility, but the main service runtime is organized into layered responsibilities.

### Interfaces

Public entrypoints:

- [`mempalace/cli.py`](mempalace/cli.py)
- [`mempalace/mcp_server.py`](mempalace/mcp_server.py)
- [`mempalace/interfaces/api.py`](mempalace/interfaces/api.py)

Responsibilities:

- parse CLI or MCP inputs
- normalize arguments
- call application services
- serialize results back to JSON or human-readable output

Current public surface:

- CLI is unified around `init`, `ingest`, `search`, `status`
- MCP uses aligned names such as `mempalace_ingest`, `mempalace_search`, `mempalace_status`

## Compat Shim Table (Legacy Path vs Canonical Path)

This table tells you **which file is the authoritative implementation** and **which files exist only for backward compatibility**.

For users migrating from the old runtime, all legacy modules have been consolidated under the `compat/` namespace. The root-level files are thin shims that re-export from `compat/`.

| Public Interface | Canonical (chính thức — đang phát triển) | Compat Shim (legacy) — chỉ dùng cho migration |
|---|---|---|
| **CLI entry** | `interfaces/cli/service_cli.py` | `cli.py` → thin shim → `compat/cli.py` |
| **MCP entry** | `interfaces/mcp/service_tools.py` | `mcp_server.py` → thin shim → `compat/mcp_server.py` |
| **High-level API** | `interfaces/api.py` (`LocalMemoryPlatform`) | `api.py` (re-export wrapper) |
| **Config** | `infrastructure/settings.py` (`MemorySettings`, YAML) | `config.py` → shim → `compat/config.py` |
| **Metadata store** | `infrastructure/storage/sqlite_catalog.py` | `knowledge_graph.py` → shim → `compat/knowledge_graph.py` |
| **Vector index** | `infrastructure/vector/sqlite_index.py` | `miner.py` / `searcher.py` → shim → `compat/miner.py`, `compat/searcher.py` |
| **Palace graph** | *(canonical không dùng palace metaphor)* | `palace_graph.py` → shim → `compat/palace_graph.py` |
| **Memory layers** | `application/context.py` | `layers.py` → shim → `compat/layers.py` |
| **AAAK dialect** | *(canonical không dùng AAAK)* | `dialect.py` → shim → `compat/dialect.py` |
| **Entity registry** | *(canonical dùng domain models)* | `entity_registry.py` / `entity_detector.py` → shims → `compat/` |
| **Onboarding** | *(canonical không còn onboarding CLI)* | `onboarding.py` / `spellcheck.py` / `split_mega_files.py` → shims → `compat/` |
| **Conversation mining** | `application/conversation_ingestion.py` | `convo_miner.py` / `normalize.py` → shims → `compat/` |
| **General extraction** | *(canonical dùng fact_extraction)* | `general_extractor.py` → shim → `compat/general_extractor.py` |
| **Room detection** | *(canonical dùng project_classification)* | `room_detector_local.py` → shim → `compat/room_detector_local.py` |

**How to read this table:**

- **Canonical column** = where new development happens. When you add a feature, it goes here.
- **Compat Shim column** = kept only so existing users can migrate (`mempalace migrate-legacy`) or run `mempalace legacy-*` commands. They will not receive new features.
- The root-level shims (`cli.py`, `mcp_server.py`, `config.py`, `api.py`) preserve the original entry points without breaking existing code. They delegate to either canonical service entrypoints or legacy `compat/` modules as appropriate.
- **Import path change**: external code that used to `from mempalace.miner import mine` should migrate to `from mempalace.compat.miner import mine` or `from mempalace.compat.cli import cmd_legacy_mine` for CLI commands.

### Application

Use-case orchestration lives in:

- [`mempalace/application/ingestion.py`](mempalace/application/ingestion.py)
- [`mempalace/application/conversation_ingestion.py`](mempalace/application/conversation_ingestion.py)
- [`mempalace/application/retrieval.py`](mempalace/application/retrieval.py)
- [`mempalace/application/fact_extraction.py`](mempalace/application/fact_extraction.py)
- [`mempalace/application/context.py`](mempalace/application/context.py)
- [`mempalace/application/reindexing.py`](mempalace/application/reindexing.py)
- [`mempalace/application/legacy_migration.py`](mempalace/application/legacy_migration.py)
- [`mempalace/application/project_profiles.py`](mempalace/application/project_profiles.py)
- [`mempalace/application/project_classification.py`](mempalace/application/project_classification.py)
- [`mempalace/application/filesystem_scan.py`](mempalace/application/filesystem_scan.py)
- [`mempalace/application/segmentation.py`](mempalace/application/segmentation.py)

Responsibilities:

- directory and file ingest
- conversation import
- project classification
- segmentation
- retrieval planning
- evidence lookup
- deterministic fact extraction
- context compaction
- legacy migration

### Domain

Canonical models live in:

- [`mempalace/domain/models.py`](mempalace/domain/models.py)

The runtime avoids metaphorical names and uses conventional records:

- `WorkspaceRecord`
- `SourceRecord`
- `DocumentRecord`
- `SegmentRecord`
- `FactRecord`
- `EntityRecord`
- `RelationRecord`
- `EpisodeRecord`
- `IngestionRun`
- `SearchRequest`
- `SearchResponse`
- `EvidenceTrail`

### Infrastructure

Concrete adapters live in:

- [`mempalace/infrastructure/settings.py`](mempalace/infrastructure/settings.py)
- [`mempalace/infrastructure/logging.py`](mempalace/infrastructure/logging.py)
- [`mempalace/infrastructure/storage/sqlite_catalog.py`](mempalace/infrastructure/storage/sqlite_catalog.py)
- [`mempalace/infrastructure/vector/hashing.py`](mempalace/infrastructure/vector/hashing.py)
- [`mempalace/infrastructure/vector/sqlite_index.py`](mempalace/infrastructure/vector/sqlite_index.py)

Responsibilities:

- load typed settings
- create storage directories
- persist metadata, FTS, facts, and entities in SQLite
- generate deterministic embeddings
- provide vector search over the local store
- configure structured logging

## Core Data Model

### Workspace

The top-level tenant boundary.

Current state:

- single-user and project-local
- one workspace per project config

Future direction:

- multi-workspace and multi-user hosting can be added without renaming core objects

### Source

Represents the origin of raw data:

- filesystem file
- chat export file
- future external importer output

Important fields:

- `source_type`
- `uri`
- `checksum`
- `first_seen_at`
- `last_seen_at`

### Document

Represents one persisted raw document.

Examples:

- a source file
- a normalized conversation transcript
- one migrated legacy drawer

Important properties:

- stable `document_id`
- verbatim `raw_text`
- `checksum`
- `observed_at`
- metadata such as `wing`, `room`, `relative_path`, `session_id`

### Segment

Represents the retrieval unit.

Important properties:

- `segment_index`
- `text`
- `start_offset`
- `end_offset`
- `token_count`
- metadata copied or derived from the document

### Fact, Entity, Relation

The current fact layer is deterministic and conservative.

What exists now:

- `FactRecord`
- `EntityRecord`
- `RelationRecord` model types
- fact and entity persistence in the SQLite catalog

What is not yet fully implemented:

- a complete relation graph replacing the legacy knowledge graph
- higher-order reasoning or LLM-driven extraction pipelines

### Episode

Represents time-aware memory for session or event recall.

Current behavior:

- derived from documents and conversation metadata
- useful for session startup and continuity

## Ingestion Architecture

There are two primary ingest paths.

### Project Ingestion

Entry:

- `mempalace ingest`
- MCP: `mempalace_ingest`

Processing flow:

1. Discover project-local config.
2. Scan the directory recursively.
3. Respect `.gitignore` by default.
4. Allow explicit include overrides with `include_ignored`.
5. Filter by configured extensions and selected no-extension filenames.
6. Load file contents.
7. Compute checksums.
8. Determine whether each source is new, changed, or unchanged.
9. Classify `wing` and `room` using project manifest rules when present.
10. Persist document and segment records.
11. Update FTS and vector index.

Current project classification order:

1. path pattern match
2. filename match
3. keyword scoring
4. fallback to `default_room_name`

Manifest files supported today:

- `mempalace.yaml`
- `mempalace.yml`
- `mempal.yaml`
- `mempal.yml`

### Conversation Ingestion

Entry:

- `mempalace ingest-chat-history`
- MCP: `mempalace_ingest` with `mode="convos"`

Processing flow:

1. Scan files with configured conversation extensions.
2. Normalize supported export shapes into a common transcript form.
3. Extract segments with `exchange` or `general` mode.
4. Persist documents and segments.
5. Store session metadata when available.
6. Index the normalized text for retrieval.

### Idempotence

Current ingest idempotence is content-based, not path-only.

What the runtime records:

- source checksum
- document checksum
- per-run results

Operational effect:

- unchanged files are skipped
- changed files are updated
- per-file results show `written`, `updated`, or `skipped`

## Retrieval Architecture

### Supported Modes

Current supported search modes:

- `keyword`
- `semantic`
- `hybrid`

Additional supported retrieval forms:

- explicit time-range search
- document fetch
- evidence trail lookup
- episode recall
- startup-context preparation

### Current Retrieval Pipeline

1. Build a `SearchRequest`.
2. Run keyword retrieval via FTS.
3. Run semantic retrieval via deterministic embeddings plus vector index.
4. Merge candidate sets.
5. Apply scoring weights from config.
6. Apply time filters and exact metadata filters.
7. Build provenance-rich results and a retrieval plan.

### Provenance Guarantees

Search results now include:

- `source_uri`
- `document_id`
- `segment_id`
- `observed_at` or best-known time
- score breakdowns
- retrieval reason
- verbatim excerpt

This is one of the main architectural goals of the refactor: retrieval should be inspectable, not just “similar.”

## Fact Extraction And Evidence

Current fact behavior:

- deterministic pattern-based extraction
- fact records store confidence and evidence links
- evidence trails can reconstruct the surrounding document context

This makes the system useful for agent workflows without overclaiming semantic precision.

## CLI And MCP Surfaces

### Primary CLI (Canonical)

All commands delegate to the service runtime:

| Command | Handler |
|---|---|
| `mempalace init` | `service_cli.py` → `cmd_workspace_init()` |
| `mempalace ingest` | `service_cli.py` → `cmd_ingest_directory()` |
| `mempalace ingest-chat-history` | `service_cli.py` → `cmd_ingest_chat_history()` |
| `mempalace search` | `service_cli.py` → `cmd_search_memory()` |
| `mempalace status` | `service_cli.py` → `cmd_status_health()` |
| `mempalace fetch-document` | `service_cli.py` → `cmd_fetch_document()` |
| `mempalace fetch-evidence` | `service_cli.py` → `cmd_fetch_evidence()` |
| `mempalace extract-facts` | `service_cli.py` → `cmd_extract_facts()` |
| `mempalace query-facts` | `service_cli.py` → `cmd_query_facts()` |
| `mempalace reindex` | `service_cli.py` → `cmd_reindex()` |
| `mempalace recall-episodes` | `service_cli.py` → `cmd_recall_episodes()` |
| `mempalace compact-session-context` | `service_cli.py` → `cmd_compact_session_context()` |
| `mempalace prepare-startup-context` | `service_cli.py` → `cmd_prepare_startup_context()` |
| `mempalace migrate-legacy` | `service_cli.py` → `cmd_migrate_legacy()` |

### Legacy CLI (Compatibility Shim)

These commands exist only for users transitioning from the old runtime. They use `cli.py`'s dispatcher → `cmd_legacy_*` helpers:

```bash
mempalace legacy-init <dir>
mempalace legacy-mine <dir>
mempalace legacy-search "query"
mempalace legacy-status
```

They will **not** receive new features and may be removed in a future major version.

### MCP Tools

### MCP Tools (Canonical — visible to agents)

The MCP server exposes service-runtime tools with names aligned to CLI commands. All tools listed in `MCP_VISIBLE_TOOL_NAMES`:

| Tool | Handler |
|---|---|
| `mempalace_status` | `tool_status_health_service()` |
| `mempalace_ingest` | `tool_ingest_directory_service()` |
| `mempalace_ingest_source` | `tool_ingest_directory_service()` (alias) |
| `mempalace_search` | `tool_search_memory_service()` |
| `mempalace_search_time_range` | `tool_search_time_range_service()` |
| `mempalace_explain_retrieval` | `tool_explain_retrieval()` |
| `mempalace_fetch_document` | `tool_fetch_document()` |
| `mempalace_fetch_evidence` | `tool_fetch_evidence()` |
| `mempalace_extract_facts` | `tool_extract_facts()` |
| `mempalace_query_facts` | `tool_query_facts()` |
| `mempalace_reindex` | `tool_reindex()` |
| `mempalace_recall_episodes` | `tool_recall_episodes()` |
| `mempalace_compact_session_context` | `tool_compact_session_context()` |
| `mempalace_prepare_startup_context` | `tool_prepare_startup_context()` |
| `mempalace_migrate_legacy` | `tool_migrate_legacy()` |

### MCP Tools (Legacy — hidden)

Legacy tools (ChromaDB-backed) are defined in `mcp_server.py` but are **not listed in `MCP_VISIBLE_TOOL_NAMES`** and are not exposed to agents. They exist so that `tool_search()` can still switch to legacy runtime via `runtime="legacy"` during migration:

- `mempalace_status`
- `mempalace_ingest`
- `mempalace_ingest_source`
- `mempalace_search`
- `mempalace_search_time_range`
- `mempalace_explain_retrieval`
- `mempalace_fetch_document`
- `mempalace_fetch_evidence`
- `mempalace_extract_facts`
- `mempalace_query_facts`
- `mempalace_reindex`
- `mempalace_recall_episodes`
- `mempalace_compact_session_context`
- `mempalace_prepare_startup_context`
- `mempalace_migrate_legacy`

Legacy MCP tools are intentionally hidden.

## Observability

The current runtime emits structured logs for important paths.

Examples of events emitted by services:

- ingest started/completed
- retrieval started/completed
- fact extraction events
- reindex events

Important identifiers:

- `workspace_id`
- `run_id`
- `document_id`
- `segment_id`
- event-specific counts

Logging configuration is controlled through:

- [`config.example.yaml`](config.example.yaml)
- [`mempalace/infrastructure/settings.py`](mempalace/infrastructure/settings.py)

## Operational Model

### Recommended Per-Repo Setup

1. Create a repo-local virtual environment.
2. Install `mempalace` into that environment.
3. Run `mempalace init` inside the repository.
4. Run `mempalace ingest`.
5. Optionally ingest chat history.
6. Start the MCP server from the repo root.

### Backup And Restore

Current project data can be backed up by copying:

- `.mempalace/config.yaml`
- `.mempalace/runtime/metadata.sqlite3`

This is enough to restore the local runtime state for the current backend.

### Reindexing

If index state needs rebuilding without re-reading source files:

- use `mempalace reindex`

This keeps reindex behavior separate from ingest behavior.

## Security And Privacy

Current posture:

- local-first storage
- no required external API for the default runtime
- MCP server runs against repo-local storage

Operational caution:

- chat exports and codebases can contain secrets
- `.mempalace/` should stay uncommitted unless deliberately redacted
- agent tool clients should launch MCP with the intended repo root as `cwd`

## Known Limitations

Current branch limitations:

- the vector backend is deterministic and local, not production-grade semantic ranking
- the structured memory layer is still simpler than a full graph model
- legacy compat modules still exist under `compat/` for migration — no new features are added there
- hosted deployment, Postgres, and alternative vector backends are not yet first-class runtime options

## Legacy Compat Namespace (`compat/`)

The `compat/` directory isolates all legacy modules from the canonical runtime. This prevents accidental use of old code paths in new feature development and makes the codebase easier to navigate.

### Compat Directory Layout

```text
mempalace/
  compat/                        ← Legacy code, no new development
    _legacy_config.py          ← Actual legacy config implementation
    _legacy_knowledge_graph.py
    _legacy_palace_graph.py
    _legacy_miner.py
    _legacy_searcher.py
    _legacy_layers.py
    _legacy_dialect.py
    _legacy_convo_miner.py
    _legacy_normalize.py
    _legacy_entity_registry.py
    _legacy_entity_detector.py
    _legacy_general_extractor.py
    _legacy_onboarding.py
    _legacy_spellcheck.py
    _legacy_split_mega_files.py
    _legacy_room_detector.py
    config.py                   ← Thin shim re-exporting _legacy_config
    knowledge_graph.py          ← Thin shim re-exporting _legacy_knowledge_graph
    palace_graph.py             ← Thin shim re-exporting _legacy_palace_graph
    miner.py                    ← Thin shim re-exporting _legacy_miner
    searcher.py                ← Thin shim re-exporting _legacy_searcher
    layers.py                  ← Thin shim re-exporting _legacy_layers
    dialect.py                  ← Thin shim re-exporting _legacy_dialect
    convo_miner.py             ← Thin shim re-exporting _legacy_convo_miner
    normalize.py               ← Thin shim re-exporting _legacy_normalize
    entity_registry.py          ← Thin shim re-exporting _legacy_entity_registry
    entity_detector.py         ← Thin shim re-exporting _legacy_entity_detector
    general_extractor.py        ← Thin shim re-exporting _legacy_general_extractor
    onboarding.py              ← Thin shim re-exporting _legacy_onboarding
    spellcheck.py              ← Thin shim re-exporting _legacy_spellcheck
    split_mega_files.py         ← Thin shim re-exporting _legacy_split_mega_files
    room_detector_local.py     ← Thin shim re-exporting _legacy_room_detector
    cli.py                     ← Legacy CLI command handlers (not in service_cli)
    mcp_server.py              ← Legacy MCP tools (not in service_tools)
```

### Design Rationale

- Every compat module is either a thin shim (`*.py`) or the actual implementation (`_legacy_*.py`).
- Thin shims exist only to maintain backward-compatible import paths for code that still references `from mempalace.X import ...`.
- All actual implementation lives in `_legacy_*.py` files so other compat modules can import from them using the full `mempalace.compat._legacy_X` path.
- The root-level files (`cli.py`, `mcp_server.py`, `config.py`, `api.py`) are thin shims that delegate to `compat/`. They keep the original entry points working without duplication.
- New code must never import from `compat/_legacy_*.py` — those are private to the compat namespace.

## Target Direction

The current architecture is intentionally pragmatic.

What is already true:

- the public CLI is unified around the service runtime
- MCP and CLI use aligned names
- retrieval is provenance-aware
- storage is no longer hard-coded to Chroma in the main runtime
- legacy modules are isolated under `compat/` — canonical vs. legacy boundary is now explicit in the package layout

What still remains to reach the longer-term target:

- richer schema versioning and operator migration tooling
- configurable embedding and vector backends
- more capable structured relation modeling
- optional hosted and multi-user deployment support
- stronger benchmark and operator documentation around larger datasets
- removal of legacy compat once migration tooling is stable
