"""SQLite metadata catalog with FTS5-backed keyword retrieval."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from mempalace.domain.models import (
    DocumentRecord,
    EntityRecord,
    FactRecord,
    IngestionRun,
    ScoredSegmentReference,
    SearchRequest,
    SegmentBundle,
    SegmentRecord,
    SourceRecord,
    WorkspaceRecord,
)


SCHEMA_VERSION = 2


def _serialize_timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _deserialize_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SqliteMetadataStore:
    """SQLite-backed metadata store for the refactored ingestion and retrieval flows."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        """Ensure schema and indexes exist."""
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS schema_info (
                    schema_version INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(workspace_id, uri)
                );

                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    observed_at TEXT,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(workspace_id, uri)
                );

                CREATE TABLE IF NOT EXISTS segments (
                    segment_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    segment_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    token_count INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(document_id, segment_index)
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS segment_fts
                USING fts5(segment_id UNINDEXED, workspace_id UNINDEXED, document_id UNINDEXED, text);

                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    run_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    stats_json TEXT,
                    error_text TEXT
                );

                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(workspace_id, name)
                );

                CREATE TABLE IF NOT EXISTS facts (
                    fact_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    document_id TEXT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_text TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_segment_id TEXT,
                    observed_at TEXT,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_facts_workspace ON facts(workspace_id);
                CREATE INDEX IF NOT EXISTS idx_facts_document ON facts(document_id);
                CREATE INDEX IF NOT EXISTS idx_facts_subject_predicate ON facts(workspace_id, subject, predicate);
                """
            )
            existing = connection.execute("SELECT COUNT(*) FROM schema_info").fetchone()[0]
            if existing == 0:
                connection.execute(
                    "INSERT INTO schema_info (schema_version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            else:
                current = connection.execute("SELECT schema_version FROM schema_info LIMIT 1").fetchone()[0]
                if current < SCHEMA_VERSION:
                    connection.execute(
                        "UPDATE schema_info SET schema_version = ?",
                        (SCHEMA_VERSION,),
                    )

    def upsert_workspace(self, workspace: WorkspaceRecord) -> None:
        """Insert or update a workspace record."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workspaces (workspace_id, name, root_path, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    name=excluded.name,
                    root_path=excluded.root_path,
                    updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    workspace.workspace_id,
                    workspace.name,
                    workspace.root_path,
                    workspace.created_at.isoformat(),
                    workspace.updated_at.isoformat(),
                    json.dumps(dict(workspace.metadata)),
                ),
            )

    def get_source_by_uri(self, workspace_id: str, uri: str) -> SourceRecord | None:
        """Fetch a source record by workspace and URI."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT source_id, workspace_id, source_type, uri, checksum, first_seen_at, last_seen_at, metadata_json
                FROM sources WHERE workspace_id = ? AND uri = ?
                """,
                (workspace_id, uri),
            ).fetchone()
        return self._row_to_source(row) if row else None

    def upsert_source(self, source: SourceRecord) -> None:
        """Insert or update a source record."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sources (
                    source_id, workspace_id, source_type, uri, checksum, first_seen_at, last_seen_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    checksum=excluded.checksum,
                    last_seen_at=excluded.last_seen_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    source.source_id,
                    source.workspace_id,
                    source.source_type,
                    source.uri,
                    source.checksum,
                    source.first_seen_at.isoformat(),
                    source.last_seen_at.isoformat(),
                    json.dumps(dict(source.metadata)),
                ),
            )

    def get_document_by_uri(self, workspace_id: str, uri: str) -> DocumentRecord | None:
        """Fetch a document record by workspace and URI."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id, workspace_id, source_id, title, uri, document_type, checksum, raw_text,
                       created_at, updated_at, observed_at, metadata_json
                FROM documents WHERE workspace_id = ? AND uri = ?
                """,
                (workspace_id, uri),
            ).fetchone()
        return self._row_to_document(row) if row else None

    def upsert_document(self, document: DocumentRecord) -> None:
        """Insert or update a document record."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    document_id, workspace_id, source_id, title, uri, document_type, checksum, raw_text,
                    created_at, updated_at, observed_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    source_id=excluded.source_id,
                    title=excluded.title,
                    checksum=excluded.checksum,
                    raw_text=excluded.raw_text,
                    updated_at=excluded.updated_at,
                    observed_at=excluded.observed_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    document.document_id,
                    document.workspace_id,
                    document.source_id,
                    document.title,
                    document.uri,
                    document.document_type,
                    document.checksum,
                    document.raw_text,
                    document.created_at.isoformat(),
                    document.updated_at.isoformat(),
                    _serialize_timestamp(document.observed_at),
                    json.dumps(dict(document.metadata)),
                ),
            )

    def replace_segments(self, workspace_id: str, document_id: str, segments: Sequence[SegmentRecord]) -> None:
        """Replace the complete segment set for a document."""
        with self._connect() as connection:
            connection.execute("DELETE FROM segment_fts WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM segments WHERE document_id = ?", (document_id,))
            for segment in segments:
                connection.execute(
                    """
                    INSERT INTO segments (
                        segment_id, workspace_id, document_id, segment_index, text, start_offset,
                        end_offset, token_count, checksum, created_at, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        segment.segment_id,
                        workspace_id,
                        document_id,
                        segment.segment_index,
                        segment.text,
                        segment.start_offset,
                        segment.end_offset,
                        segment.token_count,
                        segment.checksum,
                        segment.created_at.isoformat(),
                        json.dumps(dict(segment.metadata)),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO segment_fts (segment_id, workspace_id, document_id, text)
                    VALUES (?, ?, ?, ?)
                    """,
                    (segment.segment_id, workspace_id, document_id, segment.text),
                )

    def create_ingestion_run(self, run: IngestionRun) -> None:
        """Persist a running ingestion record."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_runs (
                    run_id, workspace_id, source_type, started_at, finished_at, status, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.workspace_id,
                    run.source_type,
                    run.started_at.isoformat(),
                    _serialize_timestamp(run.finished_at),
                    run.status,
                    json.dumps(dict(run.metadata)),
                ),
            )

    def complete_ingestion_run(
        self,
        run_id: str,
        finished_at: str,
        status: str,
        stats: dict[str, int],
        error_text: str | None = None,
    ) -> None:
        """Mark an ingestion run as complete."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_runs
                SET finished_at = ?, status = ?, stats_json = ?, error_text = ?
                WHERE run_id = ?
                """,
                (finished_at, status, json.dumps(stats), error_text, run_id),
            )

    def keyword_search(self, request: SearchRequest, limit: int) -> list[ScoredSegmentReference]:
        """Execute a best-effort FTS query and return ranked segment references."""
        tokens = [token for token in self._tokenize_query(request.query) if len(token) > 1]
        if not tokens:
            return []

        query = " OR ".join(tokens)
        sql = """
            SELECT segment_fts.segment_id, bm25(segment_fts) AS rank
            FROM segment_fts
            JOIN documents ON documents.document_id = segment_fts.document_id
            WHERE segment_fts.text MATCH ? AND documents.workspace_id = ?
        """
        params: list[Any] = [query, request.workspace_id]
        if request.start_time is not None:
            sql += " AND COALESCE(documents.observed_at, documents.updated_at) >= ?"
            params.append(request.start_time.isoformat())
        if request.end_time is not None:
            sql += " AND COALESCE(documents.observed_at, documents.updated_at) <= ?"
            params.append(request.end_time.isoformat())
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()

        results: list[ScoredSegmentReference] = []
        for rank_index, (segment_id, raw_rank) in enumerate(rows, start=1):
            raw_score = float(raw_rank)
            normalized_score = 1.0 / (1.0 + abs(raw_score))
            results.append(
                ScoredSegmentReference(
                    segment_id=segment_id,
                    score=normalized_score,
                    raw_score=raw_score,
                    rank=rank_index,
                    reason="fts5",
                )
            )
        return results

    def get_segment_bundles(self, segment_ids: Sequence[str]) -> dict[str, SegmentBundle]:
        """Hydrate segments with their parent document and source records."""
        if not segment_ids:
            return {}

        placeholders = ",".join("?" for _ in segment_ids)
        sql = f"""
            SELECT
                segments.segment_id, segments.workspace_id, segments.document_id, segments.segment_index,
                segments.text, segments.start_offset, segments.end_offset, segments.token_count,
                segments.checksum, segments.created_at, segments.metadata_json,
                documents.document_id, documents.workspace_id, documents.source_id, documents.title,
                documents.uri, documents.document_type, documents.checksum, documents.raw_text,
                documents.created_at, documents.updated_at, documents.observed_at, documents.metadata_json,
                sources.source_id, sources.workspace_id, sources.source_type, sources.uri, sources.checksum,
                sources.first_seen_at, sources.last_seen_at, sources.metadata_json
            FROM segments
            JOIN documents ON documents.document_id = segments.document_id
            JOIN sources ON sources.source_id = documents.source_id
            WHERE segments.segment_id IN ({placeholders})
        """
        with self._connect() as connection:
            rows = connection.execute(sql, list(segment_ids)).fetchall()

        bundles = {}
        for row in rows:
            segment = SegmentRecord(
                segment_id=row[0],
                workspace_id=row[1],
                document_id=row[2],
                segment_index=row[3],
                text=row[4],
                start_offset=row[5],
                end_offset=row[6],
                token_count=row[7],
                checksum=row[8],
                created_at=_deserialize_timestamp(row[9]) or datetime.min,
                metadata=json.loads(row[10]),
            )
            document = DocumentRecord(
                document_id=row[11],
                workspace_id=row[12],
                source_id=row[13],
                title=row[14],
                uri=row[15],
                document_type=row[16],
                checksum=row[17],
                raw_text=row[18],
                created_at=_deserialize_timestamp(row[19]) or datetime.min,
                updated_at=_deserialize_timestamp(row[20]) or datetime.min,
                observed_at=_deserialize_timestamp(row[21]),
                metadata=json.loads(row[22]),
            )
            source = SourceRecord(
                source_id=row[23],
                workspace_id=row[24],
                source_type=row[25],
                uri=row[26],
                checksum=row[27],
                first_seen_at=_deserialize_timestamp(row[28]) or datetime.min,
                last_seen_at=_deserialize_timestamp(row[29]) or datetime.min,
                metadata=json.loads(row[30]),
            )
            bundles[segment.segment_id] = SegmentBundle(source=source, document=document, segment=segment)

        ordered = {}
        for segment_id in segment_ids:
            if segment_id in bundles:
                ordered[segment_id] = bundles[segment_id]
        return ordered

    def fetch_document(self, document_id: str) -> DocumentRecord | None:
        """Fetch a document by ID."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id, workspace_id, source_id, title, uri, document_type, checksum, raw_text,
                       created_at, updated_at, observed_at, metadata_json
                FROM documents WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        return self._row_to_document(row) if row else None

    def fetch_segment(self, segment_id: str) -> SegmentRecord | None:
        """Fetch a segment by ID."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT segment_id, workspace_id, document_id, segment_index, text, start_offset, end_offset,
                       token_count, checksum, created_at, metadata_json
                FROM segments
                WHERE segment_id = ?
                """,
                (segment_id,),
            ).fetchone()
        if row is None:
            return None
        return SegmentRecord(
            segment_id=row[0],
            workspace_id=row[1],
            document_id=row[2],
            segment_index=row[3],
            text=row[4],
            start_offset=row[5],
            end_offset=row[6],
            token_count=row[7],
            checksum=row[8],
            created_at=_deserialize_timestamp(row[9]) or datetime.min,
            metadata=json.loads(row[10]),
        )

    def list_documents(self, workspace_id: str) -> list[DocumentRecord]:
        """List documents for a workspace ordered by recency."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT document_id, workspace_id, source_id, title, uri, document_type, checksum, raw_text,
                       created_at, updated_at, observed_at, metadata_json
                FROM documents
                WHERE workspace_id = ?
                ORDER BY COALESCE(observed_at, updated_at) DESC, document_id ASC
                """,
                (workspace_id,),
            ).fetchall()
        return [self._row_to_document(row) for row in rows]

    def fetch_document_segments(self, document_id: str) -> list[SegmentRecord]:
        """Fetch ordered segments for a document."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT segment_id, workspace_id, document_id, segment_index, text, start_offset, end_offset,
                       token_count, checksum, created_at, metadata_json
                FROM segments
                WHERE document_id = ?
                ORDER BY segment_index ASC
                """,
                (document_id,),
            ).fetchall()
        return [
            SegmentRecord(
                segment_id=row[0],
                workspace_id=row[1],
                document_id=row[2],
                segment_index=row[3],
                text=row[4],
                start_offset=row[5],
                end_offset=row[6],
                token_count=row[7],
                checksum=row[8],
                created_at=_deserialize_timestamp(row[9]) or datetime.min,
                metadata=json.loads(row[10]),
            )
            for row in rows
        ]

    def get_status(self) -> dict[str, int]:
        """Return simple record counts."""
        with self._connect() as connection:
            return {
                "workspaces": connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0],
                "sources": connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "documents": connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                "segments": connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0],
                "ingestion_runs": connection.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0],
                "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                "facts": connection.execute("SELECT COUNT(*) FROM facts").fetchone()[0],
            }

    def upsert_entities(self, entities: Sequence[EntityRecord]) -> int:
        """Insert or update a set of entities."""
        if not entities:
            return 0
        with self._connect() as connection:
            for entity in entities:
                connection.execute(
                    """
                    INSERT INTO entities (
                        entity_id, workspace_id, name, entity_type, created_at, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_id) DO UPDATE SET
                        name=excluded.name,
                        entity_type=excluded.entity_type,
                        metadata_json=excluded.metadata_json
                    """,
                    (
                        entity.entity_id,
                        entity.workspace_id,
                        entity.name,
                        entity.entity_type,
                        entity.created_at.isoformat(),
                        json.dumps(dict(entity.metadata)),
                    ),
                )
        return len(entities)

    def replace_facts_for_document(
        self,
        workspace_id: str,
        document_id: str,
        facts: Sequence[FactRecord],
    ) -> int:
        """Replace the full fact set for one document."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM facts WHERE workspace_id = ? AND document_id = ?",
                (workspace_id, document_id),
            )
            for fact in facts:
                connection.execute(
                    """
                    INSERT INTO facts (
                        fact_id, workspace_id, document_id, subject, predicate, object_text, confidence,
                        evidence_segment_id, observed_at, created_at, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact.fact_id,
                        fact.workspace_id,
                        fact.document_id,
                        fact.subject,
                        fact.predicate,
                        fact.object,
                        fact.confidence,
                        fact.evidence_segment_id,
                        _serialize_timestamp(fact.observed_at),
                        fact.created_at.isoformat(),
                        json.dumps(dict(fact.metadata)),
                    ),
                )
        return len(facts)

    def query_facts(
        self,
        workspace_id: str,
        *,
        fact_id: str | None = None,
        document_id: str | None = None,
        evidence_segment_id: str | None = None,
        query: str | None = None,
        subject: str | None = None,
        predicate: str | None = None,
        object_text: str | None = None,
        limit: int = 20,
    ) -> list[FactRecord]:
        """Query facts by text and optional structured filters."""
        sql = """
            SELECT fact_id, workspace_id, document_id, subject, predicate, object_text, confidence,
                   evidence_segment_id, observed_at, created_at, metadata_json
            FROM facts
            WHERE workspace_id = ?
        """
        params: list[Any] = [workspace_id]
        if fact_id:
            sql += " AND fact_id = ?"
            params.append(fact_id)
        if document_id:
            sql += " AND document_id = ?"
            params.append(document_id)
        if evidence_segment_id:
            sql += " AND evidence_segment_id = ?"
            params.append(evidence_segment_id)
        if query:
            tokens = [token for token in query.split() if token.strip()]
            if tokens:
                token_clauses: list[str] = []
                for token in tokens:
                    token_clauses.append("(subject LIKE ? OR predicate LIKE ? OR object_text LIKE ?)")
                    pattern = f"%{token}%"
                    params.extend([pattern, pattern, pattern])
                sql += " AND (" + " OR ".join(token_clauses) + ")"
        if subject:
            sql += " AND subject = ?"
            params.append(subject)
        if predicate:
            sql += " AND predicate = ?"
            params.append(predicate)
        if object_text:
            sql += " AND object_text = ?"
            params.append(object_text)
        sql += " ORDER BY COALESCE(observed_at, created_at) DESC, fact_id ASC LIMIT ?"
        params.append(limit)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_fact(row) for row in rows]

    def query_entities(
        self,
        workspace_id: str,
        *,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[EntityRecord]:
        """Query entities by name and optional exact type."""
        sql = """
            SELECT entity_id, workspace_id, name, entity_type, created_at, metadata_json
            FROM entities
            WHERE workspace_id = ?
        """
        params: list[Any] = [workspace_id]
        if query:
            sql += " AND name LIKE ?"
            params.append(f"%{query}%")
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY name ASC, entity_id ASC LIMIT ?"
        params.append(limit)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [
            EntityRecord(
                entity_id=row["entity_id"],
                workspace_id=row["workspace_id"],
                name=row["name"],
                entity_type=row["entity_type"],
                created_at=_deserialize_timestamp(row["created_at"]) or datetime.min,
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _row_to_source(self, row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            source_id=row["source_id"],
            workspace_id=row["workspace_id"],
            source_type=row["source_type"],
            uri=row["uri"],
            checksum=row["checksum"],
            first_seen_at=_deserialize_timestamp(row["first_seen_at"]) or datetime.min,
            last_seen_at=_deserialize_timestamp(row["last_seen_at"]) or datetime.min,
            metadata=json.loads(row["metadata_json"]),
        )

    def _row_to_document(self, row: sqlite3.Row) -> DocumentRecord:
        return DocumentRecord(
            document_id=row["document_id"],
            workspace_id=row["workspace_id"],
            source_id=row["source_id"],
            title=row["title"],
            uri=row["uri"],
            document_type=row["document_type"],
            checksum=row["checksum"],
            raw_text=row["raw_text"],
            created_at=_deserialize_timestamp(row["created_at"]) or datetime.min,
            updated_at=_deserialize_timestamp(row["updated_at"]) or datetime.min,
            observed_at=_deserialize_timestamp(row["observed_at"]),
            metadata=json.loads(row["metadata_json"]),
        )

    def _row_to_fact(self, row: sqlite3.Row) -> FactRecord:
        return FactRecord(
            fact_id=row["fact_id"],
            workspace_id=row["workspace_id"],
            document_id=row["document_id"],
            subject=row["subject"],
            predicate=row["predicate"],
            object=row["object_text"],
            confidence=float(row["confidence"]),
            evidence_segment_id=row["evidence_segment_id"],
            observed_at=_deserialize_timestamp(row["observed_at"]),
            created_at=_deserialize_timestamp(row["created_at"]) or datetime.min,
            metadata=json.loads(row["metadata_json"]),
        )

    def _tokenize_query(self, query: str) -> list[str]:
        return [token.replace('"', "") for token in query.split() if token.strip()]
