"""
layers.py — 4-Layer Memory Stack for mempalace
=============================================

Load only what you need, when you need it.

    Layer 0: Identity       (~100 tokens)   — Always loaded. "Who am I?"
    Layer 1: Essential Story (~500-800)      — Always loaded. Top moments from the palace.
    Layer 2: On-Demand      (~200-500 each)  — Loaded when a topic/wing comes up.
    Layer 3: Deep Search    (unlimited)      — Full ChromaDB semantic search.

Wake-up cost: ~600-900 tokens (L0+L1). Leaves 95%+ of context free.

This file lives in compat/ because it belongs to the legacy ChromaDB-backed
runtime. The canonical runtime uses ContextService for startup context
preparation.
"""

import os
from collections import defaultdict
from pathlib import Path

import chromadb

from mempalace.compat._legacy_config import MempalaceConfig


class Layer0:
    """~100 tokens. Always loaded."""

    def __init__(self, identity_path: str = None):
        if identity_path is None:
            identity_path = os.path.expanduser("~/.mempalace/identity.txt")
        self.path = identity_path
        self._text = None

    def render(self) -> str:
        if self._text is not None:
            return self._text
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                self._text = f.read().strip()
        else:
            self._text = "## L0 — IDENTITY\nNo identity configured. Create ~/.mempalace/identity.txt"
        return self._text

    def token_estimate(self) -> int:
        return len(self.render()) // 4


class Layer1:
    """~500-800 tokens. Always loaded."""

    MAX_DRAWERS = 15
    MAX_CHARS = 3200

    def __init__(self, palace_path: str = None, wing: str = None):
        cfg = MempalaceConfig()
        self.palace_path = palace_path or cfg.palace_path
        self.wing = wing

    def generate(self) -> str:
        try:
            client = chromadb.PersistentClient(path=self.palace_path)
            col = client.get_collection("mempalace_drawers")
        except Exception:
            return "## L1 — No palace found. Run: mempalace mine <dir>"

        _BATCH = 500
        docs, metas = [], []
        offset = 0
        while True:
            kwargs = {"include": ["documents", "metadatas"], "limit": _BATCH, "offset": offset}
            if self.wing:
                kwargs["where"] = {"wing": self.wing}
            try:
                batch = col.get(**kwargs)
            except Exception:
                break
            batch_docs = batch.get("documents", [])
            if not batch_docs:
                break
            docs.extend(batch_docs)
            metas.extend(batch.get("metadatas", []))
            offset += len(batch_docs)
            if len(batch_docs) < _BATCH:
                break

        if not docs:
            return "## L1 — No memories yet."

        scored = []
        for doc, meta in zip(docs, metas):
            importance = 3
            for key in ("importance", "emotional_weight", "weight"):
                val = meta.get(key)
                if val is not None:
                    try:
                        importance = float(val)
                    except (ValueError, TypeError):
                        pass
                    break
            scored.append((importance, meta, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: self.MAX_DRAWERS]

        by_room = defaultdict(list)
        for imp, meta, doc in top:
            room = meta.get("room", "general")
            by_room[room].append((imp, meta, doc))

        lines = ["## L1 — ESSENTIAL STORY"]
        total_len = 0
        for room, entries in sorted(by_room.items()):
            room_line = f"\n[{room}]"
            lines.append(room_line)
            total_len += len(room_line)
            for imp, meta, doc in entries:
                source = Path(meta.get("source_file", "")).name if meta.get("source_file") else ""
                snippet = doc.strip().replace("\n", " ")
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                entry_line = f"  - {snippet}"
                if source:
                    entry_line += f"  ({source})"
                if total_len + len(entry_line) > self.MAX_CHARS:
                    lines.append("  ... (more in L3 search)")
                    return "\n".join(lines)
                lines.append(entry_line)
                total_len += len(entry_line)
        return "\n".join(lines)


class Layer2:
    """~200-500 tokens per retrieval."""

    def __init__(self, palace_path: str = None):
        cfg = MempalaceConfig()
        self.palace_path = palace_path or cfg.palace_path

    def retrieve(self, wing: str = None, room: str = None, n_results: int = 10) -> str:
        try:
            client = chromadb.PersistentClient(path=self.palace_path)
            col = client.get_collection("mempalace_drawers")
        except Exception:
            return "No palace found."

        where = {}
        if wing and room:
            where = {"$and": [{"wing": wing}, {"room": room}]}
        elif wing:
            where = {"wing": wing}
        elif room:
            where = {"room": room}

        kwargs = {"include": ["documents", "metadatas"], "limit": n_results}
        if where:
            kwargs["where"] = where

        try:
            results = col.get(**kwargs)
        except Exception as e:
            return f"Retrieval error: {e}"

        docs = results.get("documents", [])
        metas = results.get("metadatas", [])

        if not docs:
            label = f"wing={wing}" if wing else ""
            if room:
                label += f" room={room}" if label else f"room={room}"
            return f"No drawers found for {label}."

        lines = [f"## L2 — ON-DEMAND ({len(docs)} drawers)"]
        for doc, meta in zip(docs[:n_results], metas[:n_results]):
            room_name = meta.get("room", "?")
            source = Path(meta.get("source_file", "")).name if meta.get("source_file") else ""
            snippet = doc.strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."
            entry = f"  [{room_name}] {snippet}"
            if source:
                entry += f"  ({source})"
            lines.append(entry)
        return "\n".join(lines)


class Layer3:
    """Unlimited depth. Semantic search via ChromaDB."""

    def __init__(self, palace_path: str = None):
        cfg = MempalaceConfig()
        self.palace_path = palace_path or cfg.palace_path

    def search(self, query: str, wing: str = None, room: str = None, n_results: int = 5) -> str:
        try:
            client = chromadb.PersistentClient(path=self.palace_path)
            col = client.get_collection("mempalace_drawers")
        except Exception:
            return "No palace found."

        where = {}
        if wing and room:
            where = {"$and": [{"wing": wing}, {"room": room}]}
        elif wing:
            where = {"wing": wing}
        elif room:
            where = {"room": room}

        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = col.query(**kwargs)
        except Exception as e:
            return f"Search error: {e}"

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        if not docs:
            return "No results found."

        lines = [f'## L3 — SEARCH RESULTS for "{query}"']
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
            similarity = round(1 - dist, 3)
            wing_name = meta.get("wing", "?")
            room_name = meta.get("room", "?")
            source = Path(meta.get("source_file", "")).name if meta.get("source_file") else ""
            snippet = doc.strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."
            lines.append(f"  [{i}] {wing_name}/{room_name} (sim={similarity})")
            lines.append(f"      {snippet}")
            if source:
                lines.append(f"      src: {source}")
        return "\n".join(lines)

    def search_raw(self, query: str, wing: str = None, room: str = None, n_results: int = 5) -> list:
        try:
            client = chromadb.PersistentClient(path=self.palace_path)
            col = client.get_collection("mempalace_drawers")
        except Exception:
            return []

        where = {}
        if wing and room:
            where = {"$and": [{"wing": wing}, {"room": room}]}
        elif wing:
            where = {"wing": wing}
        elif room:
            where = {"room": room}

        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = col.query(**kwargs)
        except Exception:
            return []

        hits = []
        for doc, meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            hits.append({
                "text": doc,
                "wing": meta.get("wing", "unknown"),
                "room": meta.get("room", "unknown"),
                "source_file": Path(meta.get("source_file", "?")).name,
                "similarity": round(1 - dist, 3),
                "metadata": meta,
            })
        return hits


class MemoryStack:
    """The full 4-layer stack."""

    def __init__(self, palace_path: str = None, identity_path: str = None):
        cfg = MempalaceConfig()
        self.palace_path = palace_path or cfg.palace_path
        self.identity_path = identity_path or os.path.expanduser("~/.mempalace/identity.txt")
        self.l0 = Layer0(self.identity_path)
        self.l1 = Layer1(self.palace_path)
        self.l2 = Layer2(self.palace_path)
        self.l3 = Layer3(self.palace_path)

    def wake_up(self, wing: str = None) -> str:
        parts = [self.l0.render(), ""]
        if wing:
            self.l1.wing = wing
        parts.append(self.l1.generate())
        return "\n".join(parts)

    def recall(self, wing: str = None, room: str = None, n_results: int = 10) -> str:
        return self.l2.retrieve(wing=wing, room=room, n_results=n_results)

    def search(self, query: str, wing: str = None, room: str = None, n_results: int = 5) -> str:
        return self.l3.search(query, wing=wing, room=room, n_results=n_results)

    def status(self) -> dict:
        result = {
            "palace_path": self.palace_path,
            "L0_identity": {
                "path": self.identity_path,
                "exists": os.path.exists(self.identity_path),
                "tokens": self.l0.token_estimate(),
            },
            "L1_essential": {"description": "Auto-generated from top palace drawers"},
            "L2_on_demand": {"description": "Wing/room filtered retrieval"},
            "L3_deep_search": {"description": "Full semantic search via ChromaDB"},
        }
        try:
            client = chromadb.PersistentClient(path=self.palace_path)
            col = client.get_collection("mempalace_drawers")
            result["total_drawers"] = col.count()
        except Exception:
            result["total_drawers"] = 0
        return result
