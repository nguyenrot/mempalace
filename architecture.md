# Architecture Audit And Target Design

## Repository Audit

### What the current system does

The current codebase is a local-first memory tool for AI workflows. It can:

- scan project directories and conversation exports
- chunk text and store verbatim segments in ChromaDB
- retrieve semantically similar chunks with optional wing/room filtering
- normalize several chat export formats into a shared transcript form
- maintain a separate SQLite knowledge graph for basic temporal facts
- expose read/write access through an MCP server
- generate a lightweight wake-up context from stored memory

### Current architecture and data flow

The repository is organized as a flat package with feature modules:

- `mempalace/cli.py`
  Dispatches commands directly into miners, search, repair, compression, and wake-up layers.
- `mempalace/miner.py`
  Scans project files, routes them to heuristic rooms, chunks content, and writes directly to Chroma.
- `mempalace/convo_miner.py`
  Scans conversation exports, normalizes them, chunks them, and writes directly to Chroma.
- `mempalace/searcher.py`
  Queries Chroma directly and returns verbatim chunks.
- `mempalace/mcp_server.py`
  Exposes a large tool surface and calls Chroma and the knowledge graph directly.
- `mempalace/knowledge_graph.py`
  Stores facts and temporal relations in SQLite, separate from the main memory store.
- `mempalace/layers.py`
  Builds a wake-up and recall stack by querying Chroma directly.

Current write flow:

1. CLI or MCP receives a request.
2. Miner scans files with local heuristics.
3. Text is chunked directly in the miner.
4. Chunks are written straight to Chroma with lightweight metadata.
5. A separate knowledge graph may be updated manually through MCP tools.

Current read flow:

1. CLI or MCP receives a search request.
2. Searcher queries Chroma directly.
3. Results are formatted in-place with limited provenance.

### What is good today

- Local-first operation is real, not aspirational.
- Raw verbatim retrieval is preserved rather than replaced by summaries.
- Conversation normalization coverage is useful and practical.
- The codebase already distinguishes project ingestion from conversation ingestion.
- There is meaningful test coverage around legacy behaviors.
- The knowledge graph is intentionally separated from vector memory, which is directionally correct.

### Likely weak points

- No clear boundary between domain logic, application services, storage, and interfaces.
- Chroma is treated as both the storage model and the query model.
- Metadata is too thin for reliable provenance, reindexing, or explainability.
- Ingestion is not modeled as an idempotent pipeline with explicit manifests or run records.
- Retrieval is not inspectable beyond a distance score.
- Heuristics are embedded inline rather than isolated behind replaceable policies.
- The MCP server knows too much about storage details and business rules.
- The knowledge graph and verbatim store are not joined by stable evidence records.

### Scalability, correctness, and maintainability risks

- Direct `chromadb.PersistentClient(...)` calls appear across many modules, increasing coupling and making backend changes expensive.
- Source identity is path-based and weakly modeled, so renames, edits, deduplication, and reindexing are brittle.
- Idempotence is approximate: “already mined” checks only detect whether a file path exists, not whether content changed.
- Metadata limits future multi-user or workspace support because there is no first-class workspace/session/source model.
- Retrieval explanations are shallow, which makes debugging ranking issues difficult.
- Chunking logic is duplicated across ingestion paths and does not consistently preserve offsets.
- Structured memory has no shared schema with the verbatim memory pipeline.
- Global initialization inside modules complicates tests and future hosted deployments.

### What to keep

- Local-first posture.
- Verbatim preservation as a first-class capability.
- Conversation normalization utilities.
- The idea of multiple retrieval modes.
- The temporal fact capability, but under a stronger schema and evidence model.

### What to rewrite

- Storage abstraction boundaries.
- Ingestion pipeline and indexing orchestration.
- Retrieval orchestration and explanation surfaces.
- Configuration and logging.
- MCP implementation to call service interfaces instead of storage directly.

### What to remove or demote

- Architecture-critical reliance on metaphorical naming such as wings, rooms, closets, and drawers.
- Inline routing heuristics as the primary storage taxonomy.
- Implicit globals for configuration and database initialization.
- README claims or terminology that obscure engineering tradeoffs.

## Target Architecture

The refactored system should behave like a local-first memory platform with clean internal layers.

### Implemented service-runtime slice

The repository now has a working local-first slice of this target architecture:

- filesystem and conversation ingestion through typed services
- explicit workspace/source/document/segment records in SQLite
- FTS5 keyword retrieval plus a deterministic local vector index
- deterministic fact extraction with evidence links
- legacy Chroma migration into the new runtime
- evidence-trail lookup around facts, segments, and documents
- episode recall derived from stored documents and conversation session metadata
- session-context compaction and startup-context preparation for agents
- CLI and MCP adapters that call the service layer rather than storage directly

### Core layers

- `domain`
  Canonical schemas and business concepts such as workspaces, sources, documents, segments, entities, relations, facts, episodes, retrieval plans, and evidence.
- `application`
  Use-case orchestration: ingest source, ingest directory, reindex, search, explain retrieval, fetch document, extract facts, prepare startup context.
- `infrastructure`
  Concrete adapters for SQLite, FTS5, vector index backends, file scanning, config loading, and logging.
- `interfaces`
  CLI, MCP, and future HTTP APIs that call application services.

### Domain model

Use conventional terms:

- `Workspace`
- `Session`
- `Source`
- `Document`
- `Segment`
- `MemoryRecord`
- `Fact`
- `Entity`
- `Relation`
- `Episode`
- `RetrievalPlan`
- `Evidence`

### Storage design

- Relational metadata store
  SQLite in local mode, with schemas that can map to Postgres later.
- Full-text search
  SQLite FTS5 in local mode.
- Vector storage
  A pluggable interface with a simple deterministic local implementation first and room for Chroma or Postgres-backed adapters later.
- Structured memory store
  Relational schema for entities, facts, relations, episodes, and provenance links back to source evidence.

### Ingestion architecture

Separate:

- source discovery
- source parsing
- document normalization
- segmentation
- metadata persistence
- vector indexing
- optional fact extraction

Each ingest run should have:

- a stable run ID
- explicit status
- per-file stats
- idempotent behavior
- content checksums
- incremental reindex semantics

### Retrieval architecture

The retrieval orchestrator should support:

- semantic search
- keyword/full-text search
- hybrid search
- time-bounded retrieval
- document fetch
- evidence trail lookup
- future fact/entity lookup
- future code-aware ranking

Each result must carry:

- source URI
- timestamp if known
- document ID
- segment ID
- raw and normalized scores
- retrieval reason
- verbatim evidence excerpt

### Observability

All important write and read paths should emit structured logs with:

- event name
- workspace ID
- run ID or request ID
- source/document/segment IDs where applicable
- timing
- counts
- warnings and failures

### Initial package layout

The repo should move toward this shape while keeping backward compatibility practical:

```text
mempalace/
  domain/
    models.py
  application/
    ingestion.py
    retrieval.py
    ports.py
  infrastructure/
    settings.py
    logging.py
    storage/
      sqlite_catalog.py
    vector/
      hashing.py
      sqlite_index.py
  interfaces/
    api.py
    cli/
    mcp/
  tests/
```

For now, the legacy flat modules remain in the top-level package and the new layers are added beside them.
