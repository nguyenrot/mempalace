"""Vector reindexing services for persisted memory documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mempalace.application.ports import EmbeddingProvider, MetadataStore, VectorIndex
from mempalace.domain.models import ReindexDocumentResult, ReindexResult
from mempalace.infrastructure.logging import log_event


@dataclass(slots=True)
class ReindexingService:
    """Rebuild vector entries from persisted document segments."""

    metadata_store: MetadataStore
    vector_index: VectorIndex
    embedding_provider: EmbeddingProvider
    logger: logging.Logger

    def reindex_workspace(
        self,
        workspace_id: str,
        *,
        document_id: str | None = None,
    ) -> ReindexResult:
        """Reindex one document or an entire workspace from stored segments."""
        self.metadata_store.initialize()
        self.vector_index.initialize()

        documents = (
            [self.metadata_store.fetch_document(document_id)] if document_id else self.metadata_store.list_documents(workspace_id)
        )
        documents = [document for document in documents if document is not None]

        log_event(
            self.logger,
            logging.INFO,
            "reindex_started",
            workspace_id=workspace_id,
            document_id=document_id,
            document_count=len(documents),
        )

        document_results: list[ReindexDocumentResult] = []
        errors: list[str] = []
        documents_reindexed = 0
        documents_skipped = 0
        segments_indexed = 0

        for document in documents:
            try:
                result = self._reindex_document(workspace_id=workspace_id, document_id=document.document_id)
            except Exception as exc:
                errors.append(f"{document.document_id}: {exc}")
                document_results.append(
                    ReindexDocumentResult(
                        document_id=document.document_id,
                        status="error",
                        segments_indexed=0,
                        reason=str(exc),
                    )
                )
                continue

            document_results.append(result)
            if result.status == "reindexed":
                documents_reindexed += 1
                segments_indexed += result.segments_indexed
            else:
                documents_skipped += 1

        log_event(
            self.logger,
            logging.INFO,
            "reindex_completed",
            workspace_id=workspace_id,
            document_id=document_id,
            documents_seen=len(documents),
            documents_reindexed=documents_reindexed,
            documents_skipped=documents_skipped,
            segments_indexed=segments_indexed,
            error_count=len(errors),
        )
        return ReindexResult(
            workspace_id=workspace_id,
            documents_seen=len(documents),
            documents_reindexed=documents_reindexed,
            documents_skipped=documents_skipped,
            segments_indexed=segments_indexed,
            errors=tuple(errors),
            document_results=tuple(document_results),
        )

    def _reindex_document(self, *, workspace_id: str, document_id: str) -> ReindexDocumentResult:
        document = self.metadata_store.fetch_document(document_id)
        if document is None:
            return ReindexDocumentResult(
                document_id=document_id,
                status="skipped",
                segments_indexed=0,
                reason="document_not_found",
            )

        segments = self.metadata_store.fetch_document_segments(document_id)
        if not segments:
            self.vector_index.delete_document_segments(document_id)
            return ReindexDocumentResult(
                document_id=document_id,
                status="skipped",
                segments_indexed=0,
                reason="no_segments",
            )

        embeddings = self.embedding_provider.embed_texts([segment.text for segment in segments])
        self.vector_index.delete_document_segments(document_id)
        self.vector_index.upsert_embeddings(
            workspace_id=workspace_id,
            document_id=document_id,
            segment_ids=[segment.segment_id for segment in segments],
            embeddings=embeddings,
            embedding_provider=self.embedding_provider.name,
        )
        return ReindexDocumentResult(
            document_id=document_id,
            status="reindexed",
            segments_indexed=len(segments),
        )
