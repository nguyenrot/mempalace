"""Migration services for importing legacy Chroma drawers into the new runtime."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mempalace.application.ports import EmbeddingProvider, MetadataStore, VectorIndex
from mempalace.domain.models import (
    DocumentRecord,
    IngestionRun,
    MigrationDrawerResult,
    MigrationResult,
    SegmentRecord,
    SourceRecord,
    WorkspaceRecord,
)
from mempalace.infrastructure.logging import log_event
from mempalace.infrastructure.settings import MemorySettings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _token_count(text: str) -> int:
    return len(text.split())


def _parse_legacy_timestamp(value: str | None) -> datetime | None:
    """Parse a best-effort legacy timestamp into UTC when possible."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class LegacyChromaMigrationService:
    """Import legacy Chroma drawers into the new metadata and vector runtime."""

    settings: MemorySettings
    metadata_store: MetadataStore
    vector_index: VectorIndex
    embedding_provider: EmbeddingProvider
    logger: logging.Logger

    def migrate_collection(
        self,
        palace_path: str | Path,
        *,
        workspace_id: str | None = None,
        collection_name: str = "mempalace_drawers",
        batch_size: int = 500,
    ) -> MigrationResult:
        """Migrate one legacy Chroma collection into the new runtime."""
        started_at = _utc_now()
        resolved_workspace_id = workspace_id or self.settings.workspace_id
        resolved_palace_path = Path(palace_path).expanduser().resolve()
        run_id = _stable_id(
            "migrate_legacy",
            resolved_workspace_id,
            resolved_palace_path.as_posix(),
            collection_name,
            started_at.isoformat(),
        )

        self.metadata_store.initialize()
        self.vector_index.initialize()
        self.metadata_store.create_ingestion_run(
            IngestionRun(
                run_id=run_id,
                workspace_id=resolved_workspace_id,
                source_type="legacy_chroma",
                started_at=started_at,
                finished_at=None,
                status="running",
                metadata={
                    "palace_path": resolved_palace_path.as_posix(),
                    "collection_name": collection_name,
                    "migration_type": "legacy_chroma",
                },
            )
        )
        self.metadata_store.upsert_workspace(
            WorkspaceRecord(
                workspace_id=resolved_workspace_id,
                name=f"{resolved_workspace_id}-legacy" if resolved_workspace_id else resolved_palace_path.name,
                root_path=resolved_palace_path.as_posix(),
                created_at=started_at,
                updated_at=started_at,
                metadata={
                    "source_type": "legacy_chroma",
                    "legacy_collection_name": collection_name,
                },
            )
        )

        log_event(
            self.logger,
            logging.INFO,
            "legacy_migration_started",
            workspace_id=resolved_workspace_id,
            run_id=run_id,
            palace_path=resolved_palace_path.as_posix(),
            collection_name=collection_name,
        )

        errors: list[str] = []
        drawer_results: list[MigrationDrawerResult] = []
        drawers_seen = 0
        drawers_migrated = 0
        drawers_skipped = 0
        segments_written = 0

        try:
            collection = self._open_collection(resolved_palace_path, collection_name)
            total = collection.count()
            for offset in range(0, total, batch_size):
                batch = collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=["documents", "metadatas"],
                )
                ids = batch.get("ids", [])
                documents = batch.get("documents", [])
                metadatas = batch.get("metadatas", [])
                for legacy_drawer_id, content, metadata in zip(ids, documents, metadatas):
                    drawers_seen += 1
                    outcome = self._migrate_drawer(
                        legacy_drawer_id=str(legacy_drawer_id),
                        content=str(content or ""),
                        metadata=dict(metadata or {}),
                        palace_path=resolved_palace_path,
                        collection_name=collection_name,
                        workspace_id=resolved_workspace_id,
                        migrated_at=started_at,
                    )
                    drawer_results.append(outcome["drawer_result"])
                    drawers_migrated += outcome["drawers_migrated"]
                    drawers_skipped += outcome["drawers_skipped"]
                    segments_written += outcome["segments_written"]
                    errors.extend(outcome["errors"])
        except Exception as exc:
            errors.append(str(exc))
        finally:
            finished_at = _utc_now()
            status = "completed" if not errors else "completed_with_errors"
            self.metadata_store.complete_ingestion_run(
                run_id=run_id,
                finished_at=finished_at.isoformat(),
                status=status,
                stats={
                    "drawers_seen": drawers_seen,
                    "drawers_migrated": drawers_migrated,
                    "drawers_skipped": drawers_skipped,
                    "segments_written": segments_written,
                },
                error_text="\n".join(errors) if errors else None,
            )
            log_event(
                self.logger,
                logging.INFO,
                "legacy_migration_completed",
                workspace_id=resolved_workspace_id,
                run_id=run_id,
                drawers_seen=drawers_seen,
                drawers_migrated=drawers_migrated,
                drawers_skipped=drawers_skipped,
                segments_written=segments_written,
                error_count=len(errors),
            )

        return MigrationResult(
            run_id=run_id,
            workspace_id=resolved_workspace_id,
            source_type="legacy_chroma",
            started_at=started_at,
            finished_at=finished_at,
            drawers_seen=drawers_seen,
            drawers_migrated=drawers_migrated,
            drawers_skipped=drawers_skipped,
            segments_written=segments_written,
            errors=tuple(errors),
            drawer_results=tuple(drawer_results),
        )

    def _open_collection(self, palace_path: Path, collection_name: str):
        """Open the requested legacy Chroma collection."""
        import chromadb

        client = chromadb.PersistentClient(path=palace_path.as_posix())
        return client.get_collection(collection_name)

    def _migrate_drawer(
        self,
        *,
        legacy_drawer_id: str,
        content: str,
        metadata: dict[str, object],
        palace_path: Path,
        collection_name: str,
        workspace_id: str,
        migrated_at: datetime,
    ) -> dict[str, object]:
        """Convert one legacy drawer into a source, document, and segment."""
        stripped_content = content.strip()
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        source_file = str(metadata.get("source_file") or "") or None
        wing = str(metadata.get("wing") or "") or None
        room = str(metadata.get("room") or "") or None
        chunk_index = int(metadata.get("chunk_index", 0) or 0)
        filed_at = _parse_legacy_timestamp(str(metadata.get("filed_at") or "")) or migrated_at
        source_uri = source_file or f"legacy-chroma://{collection_name}/sources/{legacy_drawer_id}"
        document_uri = f"legacy-chroma://{collection_name}/drawers/{legacy_drawer_id}"

        if not stripped_content:
            return {
                "drawers_migrated": 0,
                "drawers_skipped": 1,
                "segments_written": 0,
                "errors": [],
                "drawer_result": MigrationDrawerResult(
                    legacy_drawer_id=legacy_drawer_id,
                    legacy_source_file=source_file,
                    status="skipped",
                    document_id=None,
                    segment_id=None,
                    checksum=checksum,
                    reason="empty",
                ),
            }

        existing_document = self.metadata_store.get_document_by_uri(workspace_id, document_uri)
        if existing_document and existing_document.checksum == checksum:
            return {
                "drawers_migrated": 0,
                "drawers_skipped": 1,
                "segments_written": 0,
                "errors": [],
                "drawer_result": MigrationDrawerResult(
                    legacy_drawer_id=legacy_drawer_id,
                    legacy_source_file=source_file,
                    status="skipped",
                    document_id=existing_document.document_id,
                    segment_id=_stable_id("seg", existing_document.document_id, "0"),
                    checksum=checksum,
                    reason="unchanged",
                ),
            }

        source_id = _stable_id("src", workspace_id, collection_name, source_uri)
        document_id = _stable_id("doc", workspace_id, collection_name, legacy_drawer_id)
        segment_id = _stable_id("seg", document_id, "0")
        existing_source = self.metadata_store.get_source_by_uri(workspace_id, source_uri)

        source = SourceRecord(
            source_id=source_id,
            workspace_id=workspace_id,
            source_type="legacy_chroma_source",
            uri=source_uri,
            checksum=checksum,
            first_seen_at=existing_source.first_seen_at if existing_source else migrated_at,
            last_seen_at=migrated_at,
            metadata={
                "legacy_collection_name": collection_name,
                "legacy_palace_path": palace_path.as_posix(),
                "legacy_source_file": source_file,
                "wing": wing,
            },
        )
        title_base = Path(source_file).name if source_file else legacy_drawer_id
        document = DocumentRecord(
            document_id=document_id,
            workspace_id=workspace_id,
            source_id=source_id,
            title=f"{title_base}#chunk-{chunk_index}",
            uri=document_uri,
            document_type="legacy_drawer",
            checksum=checksum,
            raw_text=content,
            created_at=existing_document.created_at if existing_document else filed_at,
            updated_at=migrated_at,
            observed_at=filed_at,
            metadata={
                "legacy_drawer_id": legacy_drawer_id,
                "legacy_collection_name": collection_name,
                "legacy_palace_path": palace_path.as_posix(),
                "legacy_source_file": source_file,
                "legacy_chunk_index": chunk_index,
                "legacy_added_by": metadata.get("added_by"),
                "ingest_mode": metadata.get("ingest_mode"),
                "extract_mode": metadata.get("extract_mode"),
                "wing": wing,
                "room": room,
            },
        )
        segment = SegmentRecord(
            segment_id=segment_id,
            workspace_id=workspace_id,
            document_id=document_id,
            segment_index=0,
            text=content,
            start_offset=0,
            end_offset=len(content),
            token_count=_token_count(content),
            checksum=checksum,
            created_at=filed_at,
            metadata={
                "legacy_drawer_id": legacy_drawer_id,
                "legacy_chunk_index": chunk_index,
                "wing": wing,
                "room": room,
                "ingest_mode": metadata.get("ingest_mode"),
                "extract_mode": metadata.get("extract_mode"),
            },
        )
        embedding = self.embedding_provider.embed_texts([segment.text])[0]

        self.metadata_store.upsert_source(source)
        self.metadata_store.upsert_document(document)
        self.metadata_store.replace_segments(
            workspace_id=workspace_id,
            document_id=document_id,
            segments=[segment],
        )
        self.vector_index.delete_document_segments(document_id)
        self.vector_index.upsert_embeddings(
            workspace_id=workspace_id,
            document_id=document_id,
            segment_ids=[segment.segment_id],
            embeddings=[embedding],
            embedding_provider=self.embedding_provider.name,
        )

        return {
            "drawers_migrated": 1,
            "drawers_skipped": 0,
            "segments_written": 1,
            "errors": [],
            "drawer_result": MigrationDrawerResult(
                legacy_drawer_id=legacy_drawer_id,
                legacy_source_file=source_file,
                status="migrated" if existing_document is None else "updated",
                document_id=document_id,
                segment_id=segment.segment_id,
                checksum=checksum,
            ),
        }
