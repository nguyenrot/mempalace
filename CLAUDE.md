# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MemPalace is a local-first memory platform for AI assistants and coding agents. It provides persistent memory using SQLite + FTS5 with optional semantic search via sentence-transformers. The project is in a transitional state—new development should use the canonical service runtime under `mempalace/interfaces/` and `mempalace/application/`, while legacy code is isolated under `mempalace/compat/`.

## Commands

### Development Setup

```bash
# Create virtual environment and install with dev dependencies
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,embeddings]"
```

### Running Tests

```bash
# Run full test suite
pytest tests/ -v

# Run a single test file
pytest tests/test_memory_platform.py -v

# Run a single test function
pytest tests/test_memory_platform.py::test_ingest_and_search -v

# Run with coverage
pytest tests/ -v --cov=mempalace --cov-report=html
```

### Linting

```bash
# Check code
ruff check mempalace/

# Format code in place
ruff format mempalace/
```

### Building and Installing

```bash
# Build wheel
pip install build
python -m build

# Install from local build
pip install dist/mempalace-*.whl

# Or install in editable mode (dev)
pip install -e ".[dev,embeddings]"
```

### CLI Reference

The unified CLI (canonical runtime) lives in `mempalace/cli.py` but delegates to `mempalace/interfaces/api.py`:

```bash
# Initialize a project-local runtime
mempalace init

# Ingest a directory
mempalace ingest /path/to/project

# Ingest conversation exports (ChatGPT, Claude, etc.)
mempalace ingest-chat-history /path/to/chats/

# Search memory
mempalace search "authentication flow"

# Health check
mempalace status

# Extract facts
mempalace extract-facts

# Query facts
mempalace query-facts --subject "User" --predicate "uses"

# Rebuild vector index
mempalace reindex

# Migrate legacy Chroma data
mempalace migrate-legacy /path/to/legacy/palace

# Fetch document by ID
mempalace fetch-document <document_id>

# Fetch evidence trail
mempalace fetch-evidence --segment_id <id>

# Recall recent episodes
mempalace recall-episodes
```

### MCP Server

```bash
# Run MCP server (used by Claude Desktop, Cursor, etc.)
python -m mempalace.mcp_server
```

## Architecture: Where Things Live

### Canonical vs Compat

The codebase separates **canonical** (active development) from **compat** (legacy migration only):

- **Canonical**: `mempalace/interfaces/`, `mempalace/application/`, `mempalace/domain/`, `mempalace/infrastructure/`
- **Compat**: `mempalace/compat/` — all modules here are for backward compatibility only. They delegate to `_legacy_*.py` implementations and receive no new features.

Root-level shims (`cli.py`, `mcp_server.py`, `api.py`, etc.) route to either canonical or compat based on dispatch logic.

### Key Modules

| Area | Canonical Path | Purpose |
|------|---------------|---------|
| High-level API | `mempalace/interfaces/api.py` | `LocalMemoryPlatform` orchestrates all services |
| CLI handlers | `mempalace/interfaces/cli/service_cli.py` | Canonical CLI command implementations |
| MCP tools | `mempalace/interfaces/mcp/service_tools.py` | Canonical MCP tool handlers |
| Settings | `mempalace/infrastructure/settings.py` | Typed YAML-based configuration |
| Storage | `mempalace/infrastructure/storage/sqlite_catalog.py` | SQLite metadata + FTS5 |
| Vector index | `mempalace/infrastructure/vector/sqlite_index.py` | Local vector search |
| Embeddings | `mempalace/infrastructure/vector/factory.py` | Provider selection (sentence-transformer or hashing) |
| Ingestion | `mempalace/application/ingestion.py` | Project directory ingestion |
| Conversation ingestion | `mempalace/application/conversation_ingestion.py` | Chat history import |
| Retrieval | `mempalace/application/retrieval.py` | Search orchestration (hybrid, keyword, semantic) |
| Context | `mempalace/application/context.py` | Session context and episode recall |
| Fact extraction | `mempalace/application/fact_extraction.py` | Deterministic fact extraction |
| Reindexing | `mempalace/application/reindexing.py` | Vector index rebuild |
| Project classification | `mempalace/application/project_classification.py` | Wing/room assignment |
| Domain models | `mempalace/domain/models.py` | `DocumentRecord`, `SegmentRecord`, `SearchRequest`, etc. |

### Runtime Data Layout

After `mempalace init`, project creates:
```
<project>/
  .mempalace/
    config.yaml
    runtime/
      metadata.sqlite3
```

The single SQLite file stores: metadata, FTS5, facts, entities, and the local vector index.

## Important Patterns

- **Settings**: Use `MemorySettings.from_yaml()` to load config. `settings.ensure_directories()` creates storage paths.
- **Services**: Each use case (ingestion, retrieval, fact extraction) has its own service class. They accept dependencies via constructor.
- **Idempotence**: Ingestion is content-based (checksums). Changed files are updated, unchanged are skipped.
- **Logging**: Use `configure_logging(settings.logging)` and pass the logger to services.
- **Tests**: All tests rely on `conftest.py` which isolates HOME to a temp directory. Never write tests that touch real user data.

## Testing Considerations

- Tests must run without network access or API keys.
- `pytest` auto-uses fixtures from `tests/conftest.py`:
  - `tmp_dir` gives an isolated temp directory
  - HOME is redirected for the entire session
- For integration-style tests, create a fresh `LocalMemoryPlatform.from_settings()` with temp paths.

## Migration Work

If touching legacy code:
- Do NOT add features to `compat/` modules.
- New code must import from canonical paths.
- Legacy shims exist only for user migration; they are frozen.

## Code Style

- Format: Ruff with 100-char line limit
- Naming: `snake_case` for functions/vars, `PascalCase` for classes
- Type hints: preferred but not required everywhere
- Docstrings: on all public modules and functions

## Configuration Reference

`mempalace.yaml` example:
```yaml
workspace_id: my-project

storage:
  base_dir: ~/.mempalace/runtime
  metadata_path: ~/.mempalace/runtime/metadata.sqlite3
  embedding_provider: auto      # auto | sentence-transformer | hashing
  embedding_model: all-MiniLM-L6-v2

segmenter:
  max_chars: 900
  overlap_chars: 120

retrieval:
  default_limit: 5
  keyword_weight: 0.6
  semantic_weight: 0.4

logging:
  level: INFO
  format: structured
```

## Additional Resources

- `README.md` — user-facing documentation
- `architecture.md` — detailed design document (essential for understanding the project)
- `CONTRIBUTING.md` — contribution guidelines
- `migration.md` — migration guide for users
