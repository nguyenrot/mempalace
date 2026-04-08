# Roadmap

## Roadmap Philosophy

The project no longer needs a vague “someday architecture” plan. It already has a usable local-first runtime, so the roadmap should answer a more operational question:

What do we finish next to make this safe, maintainable, and boring in production-like use?

The answer is:

1. finish the local runtime properly
2. make migrations and operator behavior predictable
3. make alternative backends possible without rewriting the core

## Current Snapshot

The current branch already includes:

- a unified CLI built around the service runtime
- aligned MCP tool names
- project-local configuration and storage
- SQLite metadata and FTS-backed keyword search
- deterministic local vector indexing
- project ingestion and conversation ingestion
- evidence trails and retrieval explanations
- deterministic fact extraction
- startup-context and compact-context services
- legacy Chroma migration into the new runtime

What remains is less about “can it work?” and more about “can operators trust it and evolve it?”

## Release Themes

### Theme 1: Stabilize The Local Runtime

Scope:

- schema versioning
- better migration tooling
- clearer operational docs
- stronger backup and restore guidance

### Theme 2: Harden Retrieval And Structured Memory

Scope:

- stronger fact and relation modeling
- better code-aware ranking
- optional reranking
- clearer explainability surfaces

### Theme 3: Prepare For Swappable Backends

Scope:

- embedding provider abstraction beyond local hashing
- vector backend abstraction beyond current SQLite implementation
- relational backend path for Postgres

### Theme 4: Prepare For Hosted And Multi-User Operation

Scope:

- explicit workspace ownership
- service deployment boundaries
- authn/authz design
- operator-grade persistence assumptions

## Phase 0: Audit And Architecture Notes

Status: Completed

Goals:

- document the real codebase
- define terminology
- capture architectural risks

Deliverables already present:

- [`architecture.md`](/Users/kynguyenpham/Memory/architecture.md)
- [`roadmap.md`](/Users/kynguyenpham/Memory/roadmap.md)
- [`migration.md`](/Users/kynguyenpham/Memory/migration.md)

Exit criteria met:

- there is now a grounded description of the existing runtime
- the refactor direction is explicit

## Phase 1: Domain Model And Storage Refactor

Status: Mostly completed

Goals:

- introduce stable domain records
- isolate storage behind interfaces
- persist retrieval metadata explicitly

Delivered:

- typed records for workspaces, sources, documents, segments, facts, entities, relations, and episodes
- SQLite metadata catalog
- FTS-backed search path
- deterministic local vector backend
- typed settings and structured logging

Remaining work:

- formal schema version table and migration IDs
- tighter separation between metadata store and fact/relation store
- more explicit workspace lifecycle records

Exit criteria:

- one source can be stored without Chroma-specific assumptions
- retrieval can operate on the new metadata model alone

## Phase 2: Ingestion Pipeline Redesign

Status: In progress, usable

Goals:

- make ingest idempotent
- separate scanning, parsing, normalization, segmentation, indexing
- keep project and conversation ingest deterministic

Delivered:

- per-run ingest summaries
- checksum-based skipping and updates
- filesystem scanning with `.gitignore` support
- project classification via `mempalace.yaml`
- conversation normalization and extraction modes

Remaining work:

- explicit ingest manifest records beyond run summaries
- import adapters for more export formats with tighter validation
- richer duplicate detection beyond checksum equivalence
- operator-facing retry and partial-failure strategy

Exit criteria:

- rerunning ingest on unchanged data is a no-op
- changed sources update cleanly
- operators can explain why a file was written, updated, or skipped

## Phase 3: Retrieval Pipeline Redesign

Status: In progress, usable

Goals:

- make retrieval explainable
- support multiple search modes consistently
- make evidence trails a first-class output

Delivered:

- `keyword`, `semantic`, and `hybrid` modes
- time-bounded search
- exact metadata filters
- explainable retrieval payloads
- evidence trail lookup

Remaining work:

- pluggable reranker interface
- code-aware ranking signals
- better candidate set tuning for narrow metadata filters
- operator tools for retrieval debugging at larger scales

Exit criteria:

- every search result explains source, segment, score, and reason
- operators can inspect a retrieval plan without reading internal storage code

## Phase 4: Agent Tooling And API Surface

Status: Largely completed for local runtime

Goals:

- unify public entrypoints on the service layer
- align naming across CLI and MCP
- remove MCP dependence on legacy tool naming

Delivered:

- unified CLI around `init`, `ingest`, `search`, `status`
- aligned MCP names like `mempalace_ingest`, `mempalace_search`, `mempalace_status`
- hidden legacy MCP tools
- Python API via `LocalMemoryPlatform`

Remaining work:

- optional HTTP or RPC service layer
- richer operator commands for maintenance and data export
- explicit “doctor” or “inspect” commands for runtime diagnostics

Exit criteria:

- CLI, MCP, and Python API all talk to the same application services
- legacy behavior is opt-in rather than the default interface

## Phase 5: Observability, Testing, And Benchmarks

Status: In progress

Goals:

- make behavior visible
- make regressions reproducible
- avoid benchmark theater

Delivered:

- structured logging configuration
- unit and integration coverage across CLI, MCP, ingest, and retrieval
- CI on supported Python versions

Remaining work:

- benchmark harness with documented corpora
- operational metrics definitions
- explicit trace or request correlation IDs across more services
- larger-scale regression datasets

Exit criteria:

- performance or retrieval claims can be rerun
- critical operational flows have deterministic tests

## Phase 6: Packaging, Docs, And Deployment

Status: In progress

Goals:

- publish a coherent package identity
- provide operator documentation
- make deployment assumptions explicit

Delivered:

- package metadata aligned to the new fork ownership
- per-repo installation docs
- MCP integration docs
- architecture, roadmap, and migration docs

Remaining work:

- release process docs
- operator upgrade checklist
- backup, restore, and disaster-recovery playbook
- hosted deployment notes

Exit criteria:

- a new operator can install, configure, migrate, and recover a project without reading the code

## Next Priority Milestones

### Milestone A: Storage And Migration Safety

Priority: Highest

Why:

- this is the last major trust gap for long-term use

Tasks:

- add schema versioning to the SQLite runtime
- add a clear migration history table
- add a `mempalace doctor` or equivalent inspection command
- document backup and restore with examples

### Milestone B: Structured Memory Depth

Priority: High

Why:

- facts exist, but relation modeling is still shallower than the target design

Tasks:

- formalize relation persistence and query behavior
- connect entity and relation queries to evidence trails
- define confidence handling and invalidation rules

### Milestone C: Retrieval Extensibility

Priority: High

Why:

- current retrieval is good enough locally, but not yet extensible enough for future backends

Tasks:

- define reranker interface
- add embedding provider abstraction with at least one non-hashing provider
- define vector backend adapter contract for Chroma/Postgres

### Milestone D: Hosted Readiness

Priority: Medium

Why:

- current runtime is intentionally local-first, but the architecture aims at future hosted support

Tasks:

- make workspace ownership and tenancy assumptions explicit
- document API boundaries for a service deployment
- define minimum auth, audit, and storage guarantees

## Deferred Work

These are intentionally deferred, not forgotten:

- full HTTP API surface
- multi-user auth and permissions
- Postgres backend
- external vector DB adapters
- LLM-assisted extraction pipelines
- hosted deployment automation

They should not block finishing the local runtime correctly.

## Breaking Changes Worth Making

These changes are acceptable and already aligned with the direction of the branch:

- make the service runtime the default CLI behavior
- keep legacy commands behind explicit names
- keep MCP limited to service-runtime tools
- prefer conventional domain names over the old memory-metaphor vocabulary
- require explicit migration instead of implicit cross-runtime behavior

## Definition Of “Operationally Complete”

For this project, “complete” should mean:

- new users can install and initialize a repo without editing code
- agents can use MCP without guessing tool names
- ingest is repeatable and explainable
- retrieval is provenance-rich and inspectable
- migration from legacy storage is documented and testable
- operators can back up and restore project-local memory safely

That is the standard the remaining work should aim at.
