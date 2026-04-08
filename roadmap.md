# Roadmap

## Current Status Snapshot

The local-first service runtime now covers the main vertical slice:

- typed domain models and explicit storage ports
- SQLite metadata, FTS5 keyword search, and deterministic local vectors
- project and conversation ingestion with idempotent run tracking
- hybrid/time-bounded retrieval with provenance and score breakdowns
- legacy Chroma migration into the new runtime
- deterministic fact extraction plus entity storage
- evidence trails, episode recall, session-context compaction, and startup-context preparation
- CLI and MCP interfaces for the service runtime

The remaining work is mostly around deeper structured-memory modeling, alternative backends, and deployment polish rather than the absence of a usable core.

## Phase 0: Repository Audit And Architecture Notes

Goals:

- document the current architecture and risks
- define the target package layout
- identify what will be preserved versus replaced

Deliverables:

- `architecture.md`
- `roadmap.md`
- `migration.md`

Exit criteria:

- the team has a grounded map of the current codebase
- the next implementation steps are explicit and sequenced

## Phase 1: Domain Model And Storage Refactor

Goals:

- introduce typed domain models
- create explicit ports for metadata storage, vector indexing, and embeddings
- establish schema versioning and persistent local metadata

Deliverables:

- `Workspace`, `Source`, `Document`, `Segment`, `Fact`, `Entity`, `Relation`, `Episode`
- SQLite metadata catalog
- FTS5 indexing
- vector index abstraction
- deterministic local embedding provider

Exit criteria:

- one ingestable source type can be stored with stable IDs and provenance
- metadata and segment records can be fetched without going through Chroma-specific code

## Phase 2: Ingestion Pipeline Redesign

Goals:

- separate scanning, parsing, normalization, segmentation, and indexing
- make ingestion idempotent and observable
- support incremental reindexing

Deliverables:

- ingestion requests and run records
- content hashing and deduplication policy
- source adapters for filesystem text and code files
- follow-up adapters for ChatGPT, Claude, Slack, and transcript imports

Exit criteria:

- rerunning ingest on unchanged content is a no-op
- changed files reindex cleanly without duplicate segments
- ingest logs show what happened and why

## Phase 3: Retrieval Pipeline Redesign

Goals:

- make retrieval explainable and mode-driven
- support keyword, semantic, hybrid, and time-aware recall

Deliverables:

- retrieval planner
- provenance-rich evidence records
- score breakdowns
- exact quote and document fetch paths

Exit criteria:

- retrieval results consistently explain source, score, and reason
- hybrid retrieval can be debugged without reading storage internals

## Phase 4: Agent Tooling And API Surface

Goals:

- move external interfaces onto the service layer
- reduce storage knowledge inside CLI and MCP adapters

Deliverables:

- clean Python API
- CLI commands for ingest, reindex, search, fetch, and status
- MCP adapter backed by application services

Exit criteria:

- CLI and MCP no longer query storage adapters directly
- tool behavior can be tested via service mocks or fixtures

## Phase 5: Observability, Testing, And Benchmarks

Goals:

- make correctness and regressions visible
- avoid benchmark theater by making claims reproducible

Deliverables:

- structured logs
- unit tests for core logic
- integration tests for ingestion and retrieval
- benchmark harness with documented datasets and modes

Exit criteria:

- critical paths have deterministic tests
- benchmark scripts state exact mode, backend, and dataset assumptions

## Phase 6: Packaging, Docs, And Deployment

Goals:

- present a coherent public package
- prepare for future hosted or multi-user deployment

Deliverables:

- cleaned package exports
- operator docs
- deployment notes
- migration guide for legacy users

Exit criteria:

- new users can understand the modern architecture from docs alone
- the codebase is ready for optional Postgres or hosted backends without rewriting core logic

## Prioritized Implementation Order

Implement first:

1. domain models
2. metadata store
3. segment persistence and FTS
4. deterministic embeddings and vector abstraction
5. ingestion service
6. retrieval service
7. legacy data migration utility
8. tests and docs

Stub for now:

- fact extraction pipelines
- reranker adapters
- multi-user access control
- hosted deployment adapters
- advanced code-aware ranking

Defer until the service core is stable:

- Chroma compatibility adapter
- Postgres backend
- HTTP API
- session compaction and startup-context synthesis

Breaking changes worth making now:

- introduce conventional domain terminology in new code
- stop baking storage details into CLI and MCP handlers
- treat ingestion as explicit runs with stable records instead of ad hoc file writes
