# Migration Guide

## Who This Guide Is For

This guide is for three kinds of users:

- users moving from legacy `palace` storage to the project-local service runtime
- users moving from old CLI names to the unified CLI
- operators updating MCP clients to the aligned tool names

## Migration Strategy

This project now treats the service runtime as the default path.

That means:

- CLI defaults to the service runtime
- MCP exposes only service-runtime tools
- legacy behavior still exists, but only behind explicit `legacy-*` commands or migration utilities

## The Big Conceptual Change

Before:

- storage was often global under `~/.mempalace/`
- “palace” and Chroma were the main runtime shape
- MCP and CLI exposed a mix of old and new behavior

Now:

- each repo can own its own `.mempalace/`
- the primary runtime is SQLite-backed and project-local
- CLI and MCP are aligned around the same service concepts

## CLI Command Mapping

### Primary Command Renames

| Old command | New command | Notes |
| --- | --- | --- |
| `mempalace workspace-init` | `mempalace init` | `workspace-init` still works as an alias |
| `mempalace ingest-directory` | `mempalace ingest` | `ingest-directory` still works as an alias |
| `mempalace search-memory` | `mempalace search` | `search-memory` still works as an alias |
| `mempalace status-health` | `mempalace status` | `status-health` still works as an alias |

### Legacy Runtime Commands

Legacy commands are no longer part of the primary flow.

Use these only when you explicitly want the old backend behavior:

| Legacy behavior | Explicit command |
| --- | --- |
| legacy init | `mempalace legacy-init` |
| legacy mine | `mempalace legacy-mine` |
| legacy search | `mempalace legacy-search` |
| legacy status | `mempalace legacy-status` |

## MCP Tool Mapping

The MCP server no longer publishes the older mixed tool surface.

### New MCP Tool Names

| Purpose | MCP tool |
| --- | --- |
| status | `mempalace_status` |
| ingest directory | `mempalace_ingest` |
| ingest one source | `mempalace_ingest_source` |
| search | `mempalace_search` |
| search in time range | `mempalace_search_time_range` |
| explain retrieval | `mempalace_explain_retrieval` |
| fetch document | `mempalace_fetch_document` |
| fetch evidence | `mempalace_fetch_evidence` |
| extract facts | `mempalace_extract_facts` |
| query facts | `mempalace_query_facts` |
| reindex | `mempalace_reindex` |
| recall episodes | `mempalace_recall_episodes` |
| compact session context | `mempalace_compact_session_context` |
| prepare startup context | `mempalace_prepare_startup_context` |
| migrate legacy data | `mempalace_migrate_legacy` |

### Old MCP Names That Should No Longer Be Used

Examples of older service-runtime MCP names:

- `mempalace_status_health`
- `mempalace_ingest_directory`
- `mempalace_search_memory`
- `mempalace_fetch_evidence_trail`

Examples of older legacy MCP names that are intentionally hidden:

- `mempalace_list_wings`
- `mempalace_list_rooms`
- `mempalace_add_drawer`
- `mempalace_kg_add`

If a client still uses those names, update the client configuration or prompts to the new tool names above.

## Legacy Terminology Mapping

The codebase still contains some older metaphor-heavy terms. The service runtime prefers conventional names.

| Legacy term | Service-runtime meaning |
| --- | --- |
| wing | workspace grouping or classification facet |
| room | document or segment classification facet |
| drawer | segment or migrated legacy document |
| palace | local memory store |
| closet | not used in the service runtime model |
| hall / tunnel | relation or cross-link idea, not a first-class runtime term |

## Recommended Migration Path For A Repository

### Step 1: Install The Current Package

Inside the target repo:

```bash
cd /path/to/project
python -m venv .venv
./.venv/bin/pip install git+https://github.com/nguyenrot/mempalace.git
```

Or with `uv`:

```bash
cd /path/to/project
uv venv
uv pip install git+https://github.com/nguyenrot/mempalace.git
```

### Step 2: Initialize The Project-Local Runtime

```bash
./.venv/bin/mempalace init
```

This creates:

- `.mempalace/config.yaml`
- `.mempalace/.gitignore`
- `.mempalace/runtime/`

### Step 3: Ingest Project Data

```bash
./.venv/bin/mempalace ingest
```

### Step 4: Ingest Chat History If Needed

```bash
./.venv/bin/mempalace ingest-chat-history /path/to/chat-exports
```

### Step 5: Verify Retrieval

```bash
./.venv/bin/mempalace search "your query"
./.venv/bin/mempalace status
```

## Migrating Legacy Chroma Data

The service runtime includes an explicit migration command:

```bash
./.venv/bin/mempalace migrate-legacy /path/to/legacy-palace --config ./.mempalace/config.yaml
```

Current migration behavior:

- reads from the legacy Chroma collection
- preserves verbatim drawer text
- preserves legacy metadata like `wing`, `room`, `source_file`, `chunk_index`, and `filed_at`
- stores each drawer as one `legacy_drawer` document with one segment in the new runtime

This is conservative on purpose.

It does not try to reconstruct original full files when the legacy data does not reliably contain them.

## Legacy Storage To Service Runtime: Practical Checklist

Before migration:

- identify the old palace path
- back it up
- initialize a project-local `.mempalace/`

Recommended sequence:

```bash
cp -R ~/.mempalace/palace ~/.mempalace/palace.backup
./.venv/bin/mempalace init
./.venv/bin/mempalace migrate-legacy ~/.mempalace/palace --config ./.mempalace/config.yaml
./.venv/bin/mempalace search "migration smoke test"
```

## What Does Not Migrate Yet

Not everything from the legacy world is automatically mapped.

Current gaps:

- legacy embedding vectors are not preserved; migrated content is re-indexed by the new runtime
- legacy knowledge-graph state is not fully migrated into the newer structured-memory model
- migrated legacy drawers are not reconstructed into multi-segment original documents

## Rollback Strategy

Rollback is simple because the new runtime is project-local.

To roll back:

1. keep the original legacy palace untouched or backed up
2. remove or archive the project’s `.mempalace/runtime/`
3. continue using `legacy-*` commands if needed

Because the runtimes are separated, rollback does not require mutating the legacy Chroma store.

## Updating MCP Clients

After upgrading to the current branch:

1. restart the MCP client
2. refresh the tool list
3. update any saved prompts or automations that mention older MCP names

Examples:

- replace `mempalace_search_memory` with `mempalace_search`
- replace `mempalace_ingest_directory` with `mempalace_ingest`
- replace `mempalace_status_health` with `mempalace_status`
- replace `mempalace_fetch_evidence_trail` with `mempalace_fetch_evidence`

## Updating Scripts And Docs

If you have shell scripts, onboarding docs, or internal notes using older CLI names, update them like this:

| Old usage | New usage |
| --- | --- |
| `mempalace workspace-init` | `mempalace init` |
| `mempalace ingest-directory` | `mempalace ingest` |
| `mempalace search-memory` | `mempalace search` |
| `mempalace status-health` | `mempalace status` |

## Common Migration Mistakes

### Using MCP Tool Names In CLI

Wrong:

```bash
mempalace mempalace_search
```

Right:

```bash
mempalace search "query"
```

### Calling Legacy MCP Tool Names

Wrong:

- `mempalace_list_wings`
- `mempalace_add_drawer`

These are intentionally hidden from MCP now.

### Expecting `legacy-search` To Read `.mempalace/config.yaml`

It will not.

`legacy-search` reads the legacy store path, not the service runtime config.

### Expecting `migrate-legacy` To Rebuild Original Files

It does not.

It preserves exact legacy drawer evidence rather than inventing reconstructed documents.

## What “Migration Complete” Means

For a typical repo, migration is complete when:

- `mempalace init` has been run
- project data has been ingested into `.mempalace/runtime/`
- any required legacy drawers have been imported
- CLI workflows use `init`, `ingest`, `search`, and `status`
- MCP clients use the aligned tool names
- the operator has a backup of `.mempalace/config.yaml` and `.mempalace/runtime/metadata.sqlite3`

At that point, the project is operating on the current service runtime rather than the older mixed legacy surface.
