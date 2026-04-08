# MemPalace

MemPalace is evolving from a single-package local memory tool into a production-oriented memory platform for AI assistants and coding agents.

The repository currently contains two tracks:

- Legacy modules that power the existing CLI, Chroma-backed indexing, and MCP tools.
- A new layered service core for predictable ingestion, inspectable retrieval, and long-term maintainability.

The goal is not a benchmark demo. The goal is a local-first memory operating layer that a normal backend engineer can understand, test, debug, and extend.

## Principles

- Preserve raw source data whenever possible.
- Keep ingestion, indexing, extraction, and retrieval as separate concerns.
- Make storage backends swappable.
- Make retrieval paths explainable and provenance-rich.
- Make write paths observable and idempotent.
- Minimize hidden LLM-dependent behavior.

## Repository Status

The original implementation is still present and usable. The current refactor introduces a new architecture alongside it so the project can migrate incrementally instead of via a risky rewrite.

The new direction starts with:

- typed domain models
- explicit storage interfaces
- SQLite-backed metadata and FTS for local mode
- a deterministic local embedding path for tests and offline operation
- service-layer ingestion and retrieval flows
- structured logging

## Docs

- [Architecture audit and target design](./architecture.md)
- [Phased roadmap](./roadmap.md)
- [Migration notes](./migration.md)
- [Example configuration](./config.example.yaml)

## Current Package Layout

The refactor keeps the existing `mempalace/` package for compatibility and adds cleaner internal layers under it:

```text
mempalace/
  domain/
  application/
  infrastructure/
  interfaces/
```

The long-term target is documented in [architecture.md](./architecture.md). The legacy flat modules remain in place until the new service core can absorb their behavior with acceptable compatibility shims.

## Service-Backed Commands

The new core already has a usable CLI surface alongside the legacy commands:

```bash
mempalace workspace-init
mempalace ingest-directory
mempalace ingest-chat-history /path/to/chats
mempalace search-memory "jwt refresh tokens"
mempalace search-time-range "jwt" --start-time 2025-01-01 --end-time 2025-12-31
mempalace explain-retrieval "jwt provenance"
mempalace fetch-document <document_id>
mempalace fetch-evidence --fact-id <fact_id>
mempalace extract-facts
mempalace query-facts "JWT" --predicate uses
mempalace reindex
mempalace recall-episodes "provenance"
mempalace compact-session-context "jwt provenance"
mempalace prepare-startup-context "jwt provenance" --agent-name codex
mempalace status-health
mempalace migrate-legacy ~/.mempalace/palace
```

These commands use the refactored SQLite/FTS/vector service layer rather than the legacy direct-to-Chroma path.

### Per-Repo Installation

The recommended model is local-per-project:

- each repo has its own virtual environment
- each repo has its own `.mempalace/`
- each repo runs its own MCP server
- no global shared memory is required

Install inside a repository:

```bash
cd /path/to/project
uv venv
uv pip install git+https://github.com/nguyenrot/mempalace.git
```

Or, when developing against a local checkout:

```bash
cd /path/to/project
uv venv
uv pip install -e /Users/kynguyenpham/Memory
```

### CLI-first Project Setup

For day-to-day usage, the new CLI no longer requires hand-editing YAML just to get started:

```bash
cd /path/to/project
./.venv/bin/mempalace workspace-init
./.venv/bin/mempalace ingest-directory
```

What these do:

- `mempalace workspace-init` creates a project-local runtime config at `.mempalace/config.yaml`
- `mempalace workspace-init` also creates `.mempalace/.gitignore` so runtime data stays local and untracked
- `mempalace workspace-init` seeds a broader developer-oriented extension list by default, including `swift`, `go`, `java`, `kt`, `rs`, `c/cpp`, `sh`, `plist`, `pbxproj`, and common web/backend formats
- `mempalace workspace-init` also seeds common no-extension developer filenames such as `Dockerfile`, `Makefile`, `Podfile`, `Gemfile`, and `Package.swift`
- `mempalace ingest-directory` ingests the current directory when no path is passed

For chat exports:

```bash
cd /path/to/chat-exports
./.venv/bin/mempalace workspace-init --workspace-id myproject_chats
./.venv/bin/mempalace ingest-chat-history
```

The service runtime now auto-discovers config in this order when `--config` is omitted:

1. a project-local `.mempalace/config.yaml` in the current directory or a parent directory

If no local project config is found, service-backed commands now fail fast and ask you to run `mempalace workspace-init`.

You can still pass `--config` explicitly whenever you want to target a different workspace.

If you already initialized a repo before the broader extension support was added, refresh the local config with:

```bash
./.venv/bin/mempalace workspace-init --force
```

For project ingestion, the service runtime now supports deterministic project routing:

- if a project contains `mempalace.yaml`, the runtime reads `wing` and `rooms`
- room assignment follows a predictable order: path match, filename match, then content keyword scoring
- assigned `wing`, `room`, `relative_path`, and classification strategy are stored in document and segment metadata

For a softer migration, familiar commands can also target the new runtime explicitly:

```bash
mempalace mine /path/to/workspace --runtime service --config ./config.yaml
mempalace mine /path/to/chats --mode convos --runtime service --config ./config.yaml
mempalace search "jwt refresh tokens" --runtime service --config ./config.yaml --wing notes --room planning
mempalace status --runtime service --config ./config.yaml
```

The MCP server also exposes service-backed tools:

- `mempalace_status_health`
- `mempalace_ingest_directory`
- `mempalace_ingest_source`
- `mempalace_migrate_legacy`
- `mempalace_extract_facts`
- `mempalace_query_facts`
- `mempalace_search_memory`
- `mempalace_search_time_range`
- `mempalace_explain_retrieval`
- `mempalace_fetch_document`
- `mempalace_fetch_evidence_trail`
- `mempalace_reindex`
- `mempalace_recall_episodes`
- `mempalace_compact_session_context`
- `mempalace_prepare_startup_context`

## Per-Repo Usage Workflow

For a normal development repository:

```bash
cd /path/to/project
uv venv
uv pip install git+https://github.com/nguyenrot/mempalace.git
./.venv/bin/mempalace workspace-init
./.venv/bin/mempalace ingest-directory
./.venv/bin/mempalace extract-facts
./.venv/bin/mempalace search-memory "authentication jwt"
```

When the codebase changes substantially:

```bash
./.venv/bin/mempalace ingest-directory
./.venv/bin/mempalace extract-facts
```

When you also want AI chat history in the same repo memory:

```bash
./.venv/bin/mempalace ingest-chat-history /path/to/chat-exports
```

## MCP For AI IDEs And CLI Agents

The service runtime is easiest to consume through MCP. The important rule is:

- the MCP server must run with the repository root as its working directory

That allows it to resolve `.mempalace/config.yaml` automatically for that repo.

The server command is:

```bash
./.venv/bin/python -m mempalace.mcp_server
```

### Generic MCP Template

Any MCP client that supports `command`, `args`, and `cwd` can use a config shaped like this:

```json
{
  "mcpServers": {
    "mempalace-project": {
      "transport": "stdio",
      "command": "./.venv/bin/python",
      "args": ["-m", "mempalace.mcp_server"],
      "cwd": "/path/to/project"
    }
  }
}
```

### Antigravity Example

Antigravity stores MCP config in a user-level file, but the server itself can still be project-local.

Example:

```json
{
  "mcpServers": {
    "mempalace-ios": {
      "transport": "stdio",
      "command": "zsh",
      "args": [
        "-lc",
        "cd /path/to/project && ./.venv/bin/python -m mempalace.mcp_server"
      ]
    }
  }
}
```

Antigravity CLI can also add the server:

```bash
/Users/kynguyenpham/.antigravity/antigravity/bin/antigravity --add-mcp '{"name":"mempalace-ios","transport":"stdio","command":"zsh","args":["-lc","cd /path/to/project && ./.venv/bin/python -m mempalace.mcp_server"]}'
```

### Codex / OpenAI CLI-Style Agents

For tools that can launch an MCP stdio server per workspace, use the same per-repo command:

```bash
cd /path/to/project
./.venv/bin/python -m mempalace.mcp_server
```

If the client supports MCP config files, use the generic template above with `cwd` set to the repo root.

### Claude Code / Other MCP Clients

If the client supports adding stdio MCP servers from the shell, point it at the repo-local Python executable:

```bash
cd /path/to/project
./.venv/bin/python -m mempalace.mcp_server
```

The exact registration command varies by client, but the important pieces stay the same:

- run the repo-local interpreter, not a global one
- use `-m mempalace.mcp_server`
- start it from the project root or configure `cwd` to the project root

## Legacy Migration

The new runtime now includes a first-pass migration path from the legacy Chroma palace:

```bash
mempalace migrate-legacy ~/.mempalace/palace --config ./config.yaml
```

This migration is intentionally conservative:

- each legacy drawer becomes one `legacy_drawer` document in the new runtime
- original `wing`, `room`, `source_file`, `chunk_index`, and `filed_at` values are preserved as metadata
- the original drawer text is preserved verbatim as both document raw text and the indexed segment text

This avoids inventing reconstructed full files that the legacy store does not actually contain.

## Structured Facts

The service runtime now includes a deterministic structured fact path:

```bash
mempalace extract-facts --config ./config.yaml
mempalace query-facts "JWT" --predicate uses --config ./config.yaml
```

Current behavior:

- facts are extracted from indexed segments using explicit regex-based patterns
- each fact keeps `evidence_segment_id`, `document_id`, `source_uri`, and extraction pattern metadata
- facts are stored separately from retrieval indexes in the local SQLite runtime

This is intentionally conservative. It is inspectable and testable, but still a first-pass fact layer rather than a full knowledge graph replacement.

## Context And Evidence

The service runtime now has the core primitives needed for agent memory workflows:

- explicit evidence trails around facts, segments, and documents
- episode recall derived from stored documents and conversation sessions
- compact session-context assembly with facts, episodes, and verbatim evidence
- startup-context preparation for agents entering a workspace
- vector reindexing from persisted segments without re-ingesting source files

The current implementation stays local-first and deterministic:

- project ingest preserves raw files, segment offsets, and classification metadata
- conversation ingest preserves normalized raw transcripts and captures `session_id` when available
- retrieval returns provenance-rich evidence with score breakdowns and candidate counts
- context-building logic is explicit Python service code rather than hidden prompt heuristics

## Development

Install the project with development dependencies:

```bash
uv sync --extra dev
```

Run tests:

```bash
uv run pytest
```

## Legacy Commands

The existing CLI is still available:

```bash
mempalace init <dir>
mempalace mine <dir>
mempalace search "query"
mempalace status
```

These commands currently use the legacy modules. The refactor is introducing a cleaner application core that future CLI and MCP surfaces will call into directly.
