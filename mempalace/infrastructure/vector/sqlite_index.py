"""Persistent SQLite vector index with cosine similarity search."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Sequence

from mempalace.domain.models import ScoredSegmentReference, SearchRequest


class SqliteVectorIndex:
    """Store embeddings in SQLite for small local deployments and deterministic tests."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        """Ensure vector tables exist."""
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS segment_vectors (
                    segment_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    embedding_provider TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_segment_vectors_workspace
                ON segment_vectors(workspace_id);
                """
            )

    def delete_document_segments(self, document_id: str) -> None:
        """Delete all vectors for a document."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM segment_vectors WHERE document_id = ?",
                (document_id,),
            )

    def upsert_embeddings(
        self,
        workspace_id: str,
        document_id: str,
        segment_ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        embedding_provider: str,
    ) -> None:
        """Insert or replace vectors for document segments."""
        with self._connect() as connection:
            for segment_id, embedding in zip(segment_ids, embeddings):
                connection.execute(
                    """
                    INSERT INTO segment_vectors (
                        segment_id, workspace_id, document_id, embedding_json, embedding_provider
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(segment_id) DO UPDATE SET
                        embedding_json=excluded.embedding_json,
                        embedding_provider=excluded.embedding_provider
                    """,
                    (
                        segment_id,
                        workspace_id,
                        document_id,
                        json.dumps(list(embedding)),
                        embedding_provider,
                    ),
                )

    def search(
        self,
        request: SearchRequest,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[ScoredSegmentReference]:
        """Run cosine similarity search in Python over persisted vectors."""
        sql = """
            SELECT segment_vectors.segment_id, segment_vectors.embedding_json
            FROM segment_vectors
            JOIN documents ON documents.document_id = segment_vectors.document_id
            WHERE segment_vectors.workspace_id = ?
        """
        params: list[str] = [request.workspace_id]
        if request.start_time is not None:
            sql += " AND COALESCE(documents.observed_at, documents.updated_at) >= ?"
            params.append(request.start_time.isoformat())
        if request.end_time is not None:
            sql += " AND COALESCE(documents.observed_at, documents.updated_at) <= ?"
            params.append(request.end_time.isoformat())

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()

        scored = []
        for segment_id, embedding_json in rows:
            embedding = json.loads(embedding_json)
            raw_score = self._cosine_similarity(query_embedding, embedding)
            if raw_score <= 0:
                continue
            scored.append((segment_id, raw_score))
        scored.sort(key=lambda item: item[1], reverse=True)

        return [
            ScoredSegmentReference(
                segment_id=segment_id,
                score=raw_score,
                raw_score=raw_score,
                rank=index,
                reason="cosine",
            )
            for index, (segment_id, raw_score) in enumerate(scored[:limit], start=1)
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _cosine_similarity(self, left: Sequence[float], right: Sequence[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)
