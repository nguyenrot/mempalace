# MemPalace 🧠

**A local-first memory platform for AI assistants and coding agents.**

Give your AI persistent memory — no API keys, no cloud, no vendor lock-in. MemPalace stores and retrieves project context using semantic search, backed by SQLite + FTS5.

[![CI](https://github.com/nguyenrot/mempalace/actions/workflows/ci.yml/badge.svg)](https://github.com/nguyenrot/mempalace/actions)
[![PyPI](https://img.shields.io/pypi/v/mempalace)](https://pypi.org/project/mempalace/)
[![Python](https://img.shields.io/pypi/pyversions/mempalace)](https://pypi.org/project/mempalace/)
[![License](https://img.shields.io/github/license/nguyenrot/mempalace)](LICENSE)

---

## ⚡ Quick Start

```bash
# Install
pip install mempalace

# (Optional) Enable semantic search — highly recommended
pip install mempalace[embeddings]

# Initialize in your project
cd your-project/
mempalace init

# Ingest your codebase
mempalace ingest .

# Search your memory
mempalace search "authentication JWT"
```

## 🔌 MCP Setup

MemPalace works as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server, giving AI assistants like Claude, Gemini, and Cursor persistent memory.

### Gemini / Antigravity

Add to `~/.gemini/antigravity/mcp_config.json`:

```json
{
  "mcpServers": {
    "mempalace-project": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["-m", "mempalace.mcp_server"]
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mempalace": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["-m", "mempalace.mcp_server"]
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "mempalace": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["-m", "mempalace.mcp_server"]
    }
  }
}
```

## 🏗️ How It Works

```
┌────────────────────────────────────────────────────┐
│                  MCP Server                         │
│  15 tools: search, ingest, facts, episodes, ...    │
├────────────────────────────────────────────────────┤
│                Application Layer                    │
│  Ingestion → Segmentation → Embedding → Indexing   │
│  Retrieval → Hybrid Search (FTS5 + Vector)         │
│  Fact Extraction → Evidence Trails                  │
├────────────────────────────────────────────────────┤
│              Infrastructure Layer                   │
│  SQLite Metadata │ FTS5 Keywords │ Vector Index    │
│  Sentence-Transformers (all-MiniLM-L6-v2, 384d)   │
└────────────────────────────────────────────────────┘
```

### Key Features

| Feature | Description |
|---------|-------------|
| **Semantic Search** | Real embeddings via `all-MiniLM-L6-v2` (384-dim) |
| **Hybrid Retrieval** | Combines FTS5 keyword + vector similarity |
| **Fact Extraction** | Deterministic structured facts from documents |
| **Episode Recall** | Time-bounded memory retrieval |
| **Evidence Trails** | Full provenance for every search result |
| **Conversation Ingestion** | Import Claude, ChatGPT, Codex chat exports |
| **Project-Local** | Each repo gets its own isolated memory |
| **Zero Cloud** | Everything runs locally — no API keys needed |

## 📖 API Reference

```python
from mempalace import LocalMemoryPlatform
from mempalace.infrastructure.settings import MemorySettings

# Create platform
settings = MemorySettings.from_yaml("mempalace.yaml")
platform = LocalMemoryPlatform.from_settings(settings)

# Ingest a project
result = platform.ingest_directory("/path/to/project")
print(f"Ingested {result.documents_written} documents, {result.segments_written} segments")

# Search
from mempalace.domain.models import SearchRequest, SearchMode
response = platform.search(SearchRequest(
    query="authentication flow",
    mode=SearchMode.HYBRID,
    limit=5,
))
for hit in response.results:
    print(f"[{hit.score:.3f}] {hit.document_title}: {hit.text[:100]}")

# Extract facts
facts = platform.extract_facts()
for fact in facts.facts:
    print(f"{fact.subject} → {fact.predicate} → {fact.object_text}")
```

## ⚙️ Configuration

Create `mempalace.yaml` in your project root:

```yaml
workspace_id: my-project

storage:
  base_dir: ~/.mempalace/runtime
  metadata_path: ~/.mempalace/runtime/metadata.sqlite3
  embedding_provider: auto          # auto | sentence-transformer | hashing
  embedding_model: all-MiniLM-L6-v2 # any sentence-transformers model

segmenter:
  max_chars: 900
  overlap_chars: 120

retrieval:
  default_limit: 5
  keyword_weight: 0.6
  semantic_weight: 0.4
```

### Embedding Providers

| Provider | Install | Quality | Speed |
|----------|---------|---------|-------|
| `sentence-transformer` | `pip install mempalace[embeddings]` | ★★★★★ | ~80MB model download |
| `hashing` | Built-in | ★★☆☆☆ | Instant, zero dependency |
| `auto` (default) | — | Best available | Tries sentence-transformer first |

## 🛠️ MCP Tools

MemPalace exposes 15 tools via MCP:

| Tool | Description |
|------|-------------|
| `mempalace_status` | Palace health overview |
| `mempalace_ingest` | Ingest a directory |
| `mempalace_ingest_source` | Ingest a single file |
| `mempalace_search` | Semantic/hybrid search |
| `mempalace_search_time_range` | Time-bounded search |
| `mempalace_explain_retrieval` | Debug search results |
| `mempalace_fetch_document` | Get document + segments |
| `mempalace_fetch_evidence` | Provenance trail |
| `mempalace_extract_facts` | Extract structured facts |
| `mempalace_query_facts` | Query fact store |
| `mempalace_reindex` | Rebuild vector index |
| `mempalace_recall_episodes` | Recall recent episodes |
| `mempalace_compact_session_context` | Agent context block |
| `mempalace_prepare_startup_context` | Agent startup context |
| `mempalace_migrate_legacy` | Import legacy Chroma data |

## 🤝 Contributing

```bash
# Clone and setup
git clone https://github.com/nguyenrot/mempalace.git
cd mempalace
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,embeddings]"

# Run tests
pytest tests/ -v

# Lint
ruff check mempalace/
```

## 📄 License

MIT © [phamkynguyen](https://github.com/nguyenrot)
