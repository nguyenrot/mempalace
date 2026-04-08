"""Application-facing interfaces for storage and embedding adapters."""

from __future__ import annotations

from typing import Protocol, Sequence

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


class MetadataStore(Protocol):
    """Persistent catalog for workspaces, sources, documents, and segments."""

    def initialize(self) -> None:
        """Ensure schema and indexes exist."""

    def upsert_workspace(self, workspace: WorkspaceRecord) -> None:
        """Insert or update a workspace definition."""

    def get_source_by_uri(self, workspace_id: str, uri: str) -> SourceRecord | None:
        """Fetch a source by its canonical URI."""

    def upsert_source(self, source: SourceRecord) -> None:
        """Insert or update a source record."""

    def get_document_by_uri(self, workspace_id: str, uri: str) -> DocumentRecord | None:
        """Fetch a document by its canonical URI."""

    def upsert_document(self, document: DocumentRecord) -> None:
        """Insert or update a document record."""

    def replace_segments(self, workspace_id: str, document_id: str, segments: Sequence[SegmentRecord]) -> None:
        """Replace the complete segment set for a document."""

    def create_ingestion_run(self, run: IngestionRun) -> None:
        """Persist a newly started ingestion run."""

    def complete_ingestion_run(
        self,
        run_id: str,
        finished_at: str,
        status: str,
        stats: dict[str, int],
        error_text: str | None = None,
    ) -> None:
        """Mark an ingestion run as complete."""

    def keyword_search(self, request: SearchRequest, limit: int) -> list[ScoredSegmentReference]:
        """Execute an FTS-backed keyword search."""

    def get_segment_bundles(self, segment_ids: Sequence[str]) -> dict[str, SegmentBundle]:
        """Hydrate segment IDs into provenance-rich bundles."""

    def fetch_document(self, document_id: str) -> DocumentRecord | None:
        """Fetch one document by ID."""

    def fetch_segment(self, segment_id: str) -> SegmentRecord | None:
        """Fetch one segment by ID."""

    def list_documents(self, workspace_id: str) -> list[DocumentRecord]:
        """List documents for a workspace."""

    def fetch_document_segments(self, document_id: str) -> list[SegmentRecord]:
        """Fetch segments for a document ordered by segment index."""

    def get_status(self) -> dict[str, int]:
        """Return lightweight storage status counts."""


class FactStore(Protocol):
    """Persistent store for extracted entities and facts."""

    def initialize(self) -> None:
        """Ensure schema and indexes exist."""

    def upsert_entities(self, entities: Sequence[EntityRecord]) -> int:
        """Insert or update a set of entities and return how many were processed."""

    def replace_facts_for_document(
        self,
        workspace_id: str,
        document_id: str,
        facts: Sequence[FactRecord],
    ) -> int:
        """Replace all facts for a document and return how many were written."""

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
        """Query facts by free text or exact-match fields."""

    def query_entities(
        self,
        workspace_id: str,
        *,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[EntityRecord]:
        """Query extracted entities by name and optional exact type."""


class EmbeddingProvider(Protocol):
    """Embeds text into vectors."""

    @property
    def name(self) -> str:
        """Stable provider name."""

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a sequence of texts."""


class VectorIndex(Protocol):
    """Persistent vector index for segment embeddings."""

    def initialize(self) -> None:
        """Ensure storage exists."""

    def delete_document_segments(self, document_id: str) -> None:
        """Remove all vectors for a document."""

    def upsert_embeddings(
        self,
        workspace_id: str,
        document_id: str,
        segment_ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        embedding_provider: str,
    ) -> None:
        """Insert or replace embeddings for document segments."""

    def search(
        self,
        request: SearchRequest,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[ScoredSegmentReference]:
        """Perform a similarity search."""
