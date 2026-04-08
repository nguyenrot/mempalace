# Migration Notes

## Why a migration path is needed

The current repository stores most memory directly in Chroma metadata and exposes behavior through flat feature modules. The refactor introduces a layered service core with explicit models and storage interfaces. That is a worthwhile breaking direction, but it should happen incrementally.

## Legacy to new concepts

| Legacy term | New term |
| --- | --- |
| wing | workspace or source grouping |
| room | document classification or retrieval facet |
| drawer | segment |
| palace | local memory store |
| closet | not used in new core |
| hall/tunnel | relation, facet, or cross-source linkage |

## Legacy modules and likely successors

| Legacy module | Successor direction |
| --- | --- |
| `mempalace/miner.py` | `mempalace/application/ingestion.py` |
| `mempalace/convo_miner.py` | source adapters plus ingestion services |
| `mempalace/searcher.py` | `mempalace/application/retrieval.py` |
| `mempalace/mcp_server.py` | interfaces backed by application services |
| `mempalace/config.py` | `mempalace/infrastructure/settings.py` |
| `mempalace/knowledge_graph.py` | future structured memory store under the new domain schema |

## Compatibility approach

- Keep legacy CLI commands available during the migration.
- Add the new architecture beside the old modules first.
- Move interfaces to the new service layer once the vertical slices are proven.
- Only remove legacy modules after behavior is covered by tests and replacement APIs.

## Data migration

There is now a first-pass migration utility from the legacy Chroma-first storage layout into the new runtime:

```bash
mempalace migrate-legacy ~/.mempalace/palace --config ./config.yaml
```

What it does:

- reads legacy drawers from the configured Chroma collection
- preserves verbatim drawer text
- preserves legacy provenance in metadata: `wing`, `room`, `source_file`, `chunk_index`, `filed_at`, and legacy drawer ID
- stores each drawer as one `legacy_drawer` document with one segment in the new runtime

Why it is conservative:

- the legacy store does not reliably contain the original full file for every drawer
- reconstructing full files from chunks would add hidden heuristics and could introduce incorrect history
- one-drawer-per-document preserves correctness and auditability

Current guidance:

- legacy data remains readable by legacy commands
- migrated data becomes searchable through the new SQLite-backed runtime
- service-runtime search can now apply exact metadata filters such as `wing` and `room` when that metadata is present

Known limitations:

- migration does not preserve legacy embedding vectors; the new runtime re-embeds migrated text through its configured embedding provider
- migrated legacy drawers are not reconstructed into full multi-chunk documents
- structured facts and knowledge-graph records still require a separate migration path
