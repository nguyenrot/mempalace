"""Ingestion services for filesystem-backed documents."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mempalace.application.filesystem_scan import scan_files
from mempalace.application.ports import EmbeddingProvider, MetadataStore, VectorIndex
from mempalace.application.project_classification import ProjectClassifier
from mempalace.application.segmentation import TextSegmenter
from mempalace.domain.models import (
    DocumentRecord,
    IngestionFileResult,
    IngestionResult,
    IngestionRun,
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


@dataclass(slots=True)
class DirectoryIngestionService:
    """Ingest text-like files from a local directory into the memory platform."""

    settings: MemorySettings
    metadata_store: MetadataStore
    vector_index: VectorIndex
    embedding_provider: EmbeddingProvider
    segmenter: TextSegmenter
    logger: logging.Logger

    def ingest_directory(
        self,
        directory: str | Path,
        workspace_id: str | None = None,
        wing_override: str | None = None,
        respect_gitignore: bool = True,
        include_ignored: list[str] | None = None,
    ) -> IngestionResult:
        """Ingest one directory recursively using deterministic filesystem scanning."""
        started_at = _utc_now()
        resolved_directory = Path(directory).expanduser().resolve()
        resolved_workspace_id = workspace_id or self.settings.workspace_id
        project_classifier = ProjectClassifier.from_project_root(
            resolved_directory,
            manifest_filenames=self.settings.ingestion.project_manifest_filenames,
            default_room_name=self.settings.ingestion.default_room_name,
            wing_override=wing_override,
        )
        run_id = _stable_id(
            "ingest",
            resolved_workspace_id,
            resolved_directory.as_posix(),
            started_at.isoformat(),
        )

        self.metadata_store.initialize()
        self.vector_index.initialize()
        self.metadata_store.create_ingestion_run(
            IngestionRun(
                run_id=run_id,
                workspace_id=resolved_workspace_id,
                source_type="filesystem",
                started_at=started_at,
                finished_at=None,
                status="running",
                metadata={"directory": resolved_directory.as_posix()},
            )
        )
        self.metadata_store.upsert_workspace(
            WorkspaceRecord(
                workspace_id=resolved_workspace_id,
                name=resolved_directory.name or resolved_workspace_id,
                root_path=resolved_directory.as_posix(),
                created_at=started_at,
                updated_at=started_at,
                metadata={
                    "source_type": "filesystem",
                    "wing": project_classifier.manifest.wing,
                    "manifest_path": project_classifier.manifest.manifest_path,
                },
            )
        )

        log_event(
            self.logger,
            logging.INFO,
            "ingest_directory_started",
            workspace_id=resolved_workspace_id,
            run_id=run_id,
            directory=resolved_directory.as_posix(),
        )

        files_seen = 0
        files_read = 0
        documents_written = 0
        documents_updated = 0
        documents_skipped = 0
        segments_written = 0
        errors: list[str] = []
        file_results: list[IngestionFileResult] = []

        try:
            for file_path in self._iter_files(
                resolved_directory,
                respect_gitignore=respect_gitignore,
                include_ignored=include_ignored,
            ):
                files_seen += 1
                outcome = self._ingest_file(
                    file_path=file_path,
                    project_classifier=project_classifier,
                    workspace_id=resolved_workspace_id,
                    ingested_at=started_at,
                )
                file_results.append(outcome["file_result"])
                files_read += outcome["files_read"]
                documents_written += outcome["documents_written"]
                documents_updated += outcome["documents_updated"]
                documents_skipped += outcome["documents_skipped"]
                segments_written += outcome["segments_written"]
                errors.extend(outcome["errors"])
        finally:
            finished_at = _utc_now()
            status = "completed" if not errors else "completed_with_errors"
            self.metadata_store.complete_ingestion_run(
                run_id=run_id,
                finished_at=finished_at.isoformat(),
                status=status,
                stats={
                    "files_seen": files_seen,
                    "files_read": files_read,
                    "documents_written": documents_written,
                    "documents_updated": documents_updated,
                    "documents_skipped": documents_skipped,
                    "segments_written": segments_written,
                },
                error_text="\n".join(errors) if errors else None,
            )
            log_event(
                self.logger,
                logging.INFO,
                "ingest_directory_completed",
                workspace_id=resolved_workspace_id,
                run_id=run_id,
                files_seen=files_seen,
                documents_written=documents_written,
                documents_updated=documents_updated,
                documents_skipped=documents_skipped,
                segments_written=segments_written,
                error_count=len(errors),
            )

        return IngestionResult(
            run_id=run_id,
            workspace_id=resolved_workspace_id,
            source_type="filesystem",
            started_at=started_at,
            finished_at=finished_at,
            files_seen=files_seen,
            files_read=files_read,
            documents_written=documents_written,
            documents_updated=documents_updated,
            documents_skipped=documents_skipped,
            segments_written=segments_written,
            errors=tuple(errors),
            file_results=tuple(file_results),
        )

    def ingest_path(
        self,
        path: str | Path,
        workspace_id: str | None = None,
        wing_override: str | None = None,
    ) -> IngestionResult:
        """Ingest one explicit project file through the same pipeline."""
        started_at = _utc_now()
        resolved_path = Path(path).expanduser().resolve()
        resolved_workspace_id = workspace_id or self.settings.workspace_id
        project_classifier = ProjectClassifier.from_path(
            resolved_path,
            manifest_filenames=self.settings.ingestion.project_manifest_filenames,
            default_room_name=self.settings.ingestion.default_room_name,
            wing_override=wing_override,
        )
        run_id = _stable_id(
            "ingest_file",
            resolved_workspace_id,
            resolved_path.as_posix(),
            started_at.isoformat(),
        )

        self.metadata_store.initialize()
        self.vector_index.initialize()
        self.metadata_store.create_ingestion_run(
            IngestionRun(
                run_id=run_id,
                workspace_id=resolved_workspace_id,
                source_type="filesystem",
                started_at=started_at,
                finished_at=None,
                status="running",
                metadata={"path": resolved_path.as_posix()},
            )
        )
        self.metadata_store.upsert_workspace(
            WorkspaceRecord(
                workspace_id=resolved_workspace_id,
                name=project_classifier.project_root.name or resolved_workspace_id,
                root_path=project_classifier.project_root.as_posix(),
                created_at=started_at,
                updated_at=started_at,
                metadata={
                    "source_type": "filesystem",
                    "wing": project_classifier.manifest.wing,
                    "manifest_path": project_classifier.manifest.manifest_path,
                },
            )
        )

        outcome = self._ingest_file(
            file_path=resolved_path,
            project_classifier=project_classifier,
            workspace_id=resolved_workspace_id,
            ingested_at=started_at,
        )
        finished_at = _utc_now()
        status = "completed" if not outcome["errors"] else "completed_with_errors"
        self.metadata_store.complete_ingestion_run(
            run_id=run_id,
            finished_at=finished_at.isoformat(),
            status=status,
            stats={
                "files_seen": 1,
                "files_read": int(outcome["files_read"]),
                "documents_written": int(outcome["documents_written"]),
                "documents_updated": int(outcome["documents_updated"]),
                "documents_skipped": int(outcome["documents_skipped"]),
                "segments_written": int(outcome["segments_written"]),
            },
            error_text="\n".join(outcome["errors"]) if outcome["errors"] else None,
        )
        return IngestionResult(
            run_id=run_id,
            workspace_id=resolved_workspace_id,
            source_type="filesystem",
            started_at=started_at,
            finished_at=finished_at,
            files_seen=1,
            files_read=int(outcome["files_read"]),
            documents_written=int(outcome["documents_written"]),
            documents_updated=int(outcome["documents_updated"]),
            documents_skipped=int(outcome["documents_skipped"]),
            segments_written=int(outcome["segments_written"]),
            errors=tuple(outcome["errors"]),
            file_results=(outcome["file_result"],),
        )

    def _iter_files(
        self,
        root: Path,
        *,
        respect_gitignore: bool,
        include_ignored: list[str] | None,
    ) -> list[Path]:
        """Yield supported files while skipping configured directories."""
        skip_filenames = set(self.settings.ingestion.skip_filenames) | set(
            self.settings.ingestion.project_manifest_filenames
        )
        return scan_files(
            root,
            include_extensions={ext.lower() for ext in self.settings.ingestion.include_extensions},
            skip_directories=set(self.settings.ingestion.skip_directories),
            skip_filenames=skip_filenames,
            respect_gitignore=respect_gitignore,
            include_ignored=include_ignored,
        )

    def _ingest_file(
        self,
        file_path: Path,
        project_classifier: ProjectClassifier,
        workspace_id: str,
        ingested_at: datetime,
    ) -> dict[str, object]:
        """Read, normalize, segment, and persist one file."""
        uri = file_path.as_posix()
        try:
            raw_text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            message = f"{uri}: {exc}"
            log_event(self.logger, logging.WARNING, "ingest_file_failed", workspace_id=workspace_id, uri=uri, error=str(exc))
            return {
                "files_read": 0,
                "documents_written": 0,
                "documents_updated": 0,
                "documents_skipped": 0,
                "segments_written": 0,
                "errors": [message],
                "file_result": IngestionFileResult(uri=uri, status="error", checksum=None, document_id=None, segments_written=0, reason=str(exc)),
            }

        stripped_text = raw_text.strip()
        checksum = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if not stripped_text:
            return {
                "files_read": 1,
                "documents_written": 0,
                "documents_updated": 0,
                "documents_skipped": 1,
                "segments_written": 0,
                "errors": [],
                "file_result": IngestionFileResult(uri=uri, status="skipped", checksum=checksum, document_id=None, segments_written=0, reason="empty"),
            }

        existing_document = self.metadata_store.get_document_by_uri(workspace_id, uri)
        if existing_document and existing_document.checksum == checksum:
            log_event(self.logger, logging.DEBUG, "ingest_file_skipped", workspace_id=workspace_id, uri=uri, reason="unchanged")
            return {
                "files_read": 1,
                "documents_written": 0,
                "documents_updated": 0,
                "documents_skipped": 1,
                "segments_written": 0,
                "errors": [],
                "file_result": IngestionFileResult(uri=uri, status="skipped", checksum=checksum, document_id=existing_document.document_id, segments_written=0, reason="unchanged"),
            }

        observed_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
        source_id = _stable_id("src", workspace_id, uri)
        document_id = _stable_id("doc", workspace_id, uri)
        classification = project_classifier.classify(file_path, raw_text)
        relative_path = file_path.relative_to(project_classifier.project_root).as_posix()

        existing_source = self.metadata_store.get_source_by_uri(workspace_id, uri)
        source = SourceRecord(
            source_id=source_id,
            workspace_id=workspace_id,
            source_type="filesystem",
            uri=uri,
            checksum=checksum,
            first_seen_at=existing_source.first_seen_at if existing_source else ingested_at,
            last_seen_at=ingested_at,
            metadata={
                "path": uri,
                "project_root": project_classifier.project_root.as_posix(),
                "relative_path": relative_path,
                "wing": classification.wing,
            },
        )
        document = DocumentRecord(
            document_id=document_id,
            workspace_id=workspace_id,
            source_id=source_id,
            title=file_path.name,
            uri=uri,
            document_type="text",
            checksum=checksum,
            raw_text=raw_text,
            created_at=existing_document.created_at if existing_document else ingested_at,
            updated_at=ingested_at,
            observed_at=observed_at,
            metadata={
                "extension": file_path.suffix.lower(),
                "project_root": project_classifier.project_root.as_posix(),
                "relative_path": relative_path,
                "wing": classification.wing,
                "room": classification.room,
                "classification_strategy": classification.strategy,
                "classification_token": classification.matched_token,
                "manifest_path": project_classifier.manifest.manifest_path,
            },
        )
        segments = self.segmenter.segment_document(workspace_id=workspace_id, document_id=document_id, text=raw_text)
        segments = [
            SegmentRecord(
                segment_id=segment.segment_id,
                workspace_id=segment.workspace_id,
                document_id=segment.document_id,
                segment_index=segment.segment_index,
                text=segment.text,
                start_offset=segment.start_offset,
                end_offset=segment.end_offset,
                token_count=segment.token_count,
                checksum=segment.checksum,
                created_at=segment.created_at,
                metadata={
                    **dict(segment.metadata),
                    "project_root": project_classifier.project_root.as_posix(),
                    "relative_path": relative_path,
                    "wing": classification.wing,
                    "room": classification.room,
                    "classification_strategy": classification.strategy,
                    "classification_token": classification.matched_token,
                },
            )
            for segment in segments
        ]
        embeddings = self.embedding_provider.embed_texts([segment.text for segment in segments]) if segments else []

        self.metadata_store.upsert_source(source)
        self.metadata_store.upsert_document(document)
        self.metadata_store.replace_segments(workspace_id=workspace_id, document_id=document_id, segments=segments)
        self.vector_index.delete_document_segments(document_id)
        if segments:
            self.vector_index.upsert_embeddings(
                workspace_id=workspace_id,
                document_id=document_id,
                segment_ids=[segment.segment_id for segment in segments],
                embeddings=embeddings,
                embedding_provider=self.embedding_provider.name,
            )

        status = "updated" if existing_document else "ingested"
        log_event(
            self.logger,
            logging.INFO,
            "ingest_file_completed",
            workspace_id=workspace_id,
            uri=uri,
            document_id=document_id,
            wing=classification.wing,
            room=classification.room,
            classification_strategy=classification.strategy,
            segments_written=len(segments),
            status=status,
        )
        return {
            "files_read": 1,
            "documents_written": 0 if existing_document else 1,
            "documents_updated": 1 if existing_document else 0,
            "documents_skipped": 0,
            "segments_written": len(segments),
            "errors": [],
            "file_result": IngestionFileResult(
                uri=uri,
                status=status,
                checksum=checksum,
                document_id=document_id,
                segments_written=len(segments),
            ),
        }
