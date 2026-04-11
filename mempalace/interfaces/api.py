"""Composable Python service API for the refactored memory core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mempalace.application.conversation_ingestion import ConversationDirectoryIngestionService
from mempalace.application.context import ContextService
from mempalace.application.fact_extraction import FactExtractionService
from mempalace.application.ingestion import DirectoryIngestionService
from mempalace.application.legacy_migration import LegacyChromaMigrationService
from mempalace.application.reindexing import ReindexingService
from mempalace.application.retrieval import RetrievalService
from mempalace.application.segmentation import TextSegmenter
from mempalace.domain.models import (
    CompactedSessionContext,
    DocumentRecord,
    EpisodeRecord,
    EvidenceTrail,
    FactExtractionResult,
    FactRecord,
    MigrationResult,
    ReindexResult,
    SearchMode,
    SearchRequest,
    SearchResponse,
    SegmentRecord,
    StartupContext,
)
from mempalace.infrastructure.logging import configure_logging
from mempalace.infrastructure.settings import MemorySettings
from mempalace.infrastructure.storage.sqlite_catalog import SqliteMetadataStore
from mempalace.infrastructure.vector.factory import create_embedding_provider
from mempalace.infrastructure.vector.sqlite_index import SqliteVectorIndex


@dataclass(slots=True)
class LocalMemoryPlatform:
    """High-level local-first API backed by the new layered core."""

    settings: MemorySettings
    ingestion_service: DirectoryIngestionService
    conversation_ingestion_service: ConversationDirectoryIngestionService
    legacy_migration_service: LegacyChromaMigrationService
    fact_extraction_service: FactExtractionService
    retrieval_service: RetrievalService
    context_service: ContextService
    reindexing_service: ReindexingService
    metadata_store: SqliteMetadataStore
    vector_index: SqliteVectorIndex

    @classmethod
    def from_settings(cls, settings: MemorySettings) -> "LocalMemoryPlatform":
        """Build a platform instance from typed settings."""
        settings.ensure_directories()
        logger = configure_logging(settings.logging)
        metadata_store = SqliteMetadataStore(settings.storage.resolved_metadata_path())
        vector_index = SqliteVectorIndex(settings.storage.resolved_metadata_path())
        embedding_provider = create_embedding_provider(settings.storage)
        segmenter = TextSegmenter(
            max_chars=settings.segmenter.max_chars,
            overlap_chars=settings.segmenter.overlap_chars,
            min_chars=settings.segmenter.min_chars,
        )

        ingestion_service = DirectoryIngestionService(
            settings=settings,
            metadata_store=metadata_store,
            vector_index=vector_index,
            embedding_provider=embedding_provider,
            segmenter=segmenter,
            logger=logger,
        )
        conversation_ingestion_service = ConversationDirectoryIngestionService(
            settings=settings,
            metadata_store=metadata_store,
            vector_index=vector_index,
            embedding_provider=embedding_provider,
            logger=logger,
        )
        legacy_migration_service = LegacyChromaMigrationService(
            settings=settings,
            metadata_store=metadata_store,
            vector_index=vector_index,
            embedding_provider=embedding_provider,
            logger=logger,
        )
        fact_extraction_service = FactExtractionService(
            metadata_store=metadata_store,
            fact_store=metadata_store,
            logger=logger,
        )
        retrieval_service = RetrievalService(
            metadata_store=metadata_store,
            vector_index=vector_index,
            embedding_provider=embedding_provider,
            settings=settings.retrieval,
            logger=logger,
        )
        context_service = ContextService(
            metadata_store=metadata_store,
            fact_service=fact_extraction_service,
            retrieval_service=retrieval_service,
            logger=logger,
        )
        reindexing_service = ReindexingService(
            metadata_store=metadata_store,
            vector_index=vector_index,
            embedding_provider=embedding_provider,
            logger=logger,
        )
        return cls(
            settings=settings,
            ingestion_service=ingestion_service,
            conversation_ingestion_service=conversation_ingestion_service,
            legacy_migration_service=legacy_migration_service,
            fact_extraction_service=fact_extraction_service,
            retrieval_service=retrieval_service,
            context_service=context_service,
            reindexing_service=reindexing_service,
            metadata_store=metadata_store,
            vector_index=vector_index,
        )

    @classmethod
    def from_config_file(cls, path: str | Path) -> "LocalMemoryPlatform":
        """Build a platform instance from a YAML config file."""
        return cls.from_settings(MemorySettings.from_yaml(path))

    def ingest_directory(
        self,
        directory: str | Path,
        *,
        mode: str = "projects",
        extract_mode: str = "exchange",
        wing_override: str | None = None,
        respect_gitignore: bool = True,
        include_ignored: list[str] | None = None,
    ):
        """Ingest a local directory recursively."""
        if mode == "convos":
            return self.conversation_ingestion_service.ingest_directory(
                directory,
                workspace_id=self.settings.workspace_id,
                extract_mode=extract_mode,
            )
        return self.ingestion_service.ingest_directory(
            directory,
            workspace_id=self.settings.workspace_id,
            wing_override=wing_override,
            respect_gitignore=respect_gitignore,
            include_ignored=include_ignored,
        )

    def ingest_source(
        self,
        path: str | Path,
        *,
        mode: str = "projects",
        extract_mode: str = "exchange",
        wing_override: str | None = None,
    ):
        """Ingest one explicit source file."""
        if mode == "convos":
            return self.conversation_ingestion_service.ingest_path(
                path,
                workspace_id=self.settings.workspace_id,
                extract_mode=extract_mode,
            )
        return self.ingestion_service.ingest_path(
            path,
            workspace_id=self.settings.workspace_id,
            wing_override=wing_override,
        )

    def search(
        self,
        query: str,
        *,
        mode: SearchMode = SearchMode.HYBRID,
        limit: int | None = None,
    ) -> SearchResponse:
        """Search memory using the requested retrieval mode."""
        return self.retrieval_service.search(
            SearchRequest(
                workspace_id=self.settings.workspace_id,
                query=query,
                mode=mode,
                limit=limit or self.settings.retrieval.default_limit,
            )
        )

    def search_request(self, request: SearchRequest) -> SearchResponse:
        """Run a prebuilt search request."""
        return self.retrieval_service.search(request)

    def search_by_time_range(
        self,
        query: str,
        *,
        start_time: datetime,
        end_time: datetime,
        mode: SearchMode = SearchMode.HYBRID,
        limit: int | None = None,
    ) -> SearchResponse:
        """Search memory within an explicit inclusive time range."""
        return self.retrieval_service.search(
            SearchRequest(
                workspace_id=self.settings.workspace_id,
                query=query,
                mode=mode,
                limit=limit or self.settings.retrieval.default_limit,
                start_time=start_time,
                end_time=end_time,
            )
        )

    def explain_retrieval(
        self,
        query: str,
        *,
        mode: SearchMode = SearchMode.HYBRID,
        limit: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        filters: dict[str, str] | None = None,
    ) -> SearchResponse:
        """Return a search response intended for direct inspection or debugging."""
        return self.retrieval_service.search(
            SearchRequest(
                workspace_id=self.settings.workspace_id,
                query=query,
                mode=mode,
                limit=limit or self.settings.retrieval.default_limit,
                start_time=start_time,
                end_time=end_time,
                filters=filters or {},
            )
        )

    def fetch_document(self, document_id: str) -> DocumentRecord | None:
        """Fetch a document by ID."""
        return self.metadata_store.fetch_document(document_id)

    def migrate_legacy_palace(
        self,
        palace_path: str | Path,
        *,
        collection_name: str = "mempalace_drawers",
    ) -> MigrationResult:
        """Import a legacy Chroma palace into the new runtime."""
        return self.legacy_migration_service.migrate_collection(
            palace_path,
            workspace_id=self.settings.workspace_id,
            collection_name=collection_name,
        )

    def fetch_document_segments(self, document_id: str) -> tuple[SegmentRecord, ...]:
        """Fetch all segments belonging to a document."""
        return tuple(self.metadata_store.fetch_document_segments(document_id))

    def extract_facts(self, document_id: str | None = None) -> FactExtractionResult:
        """Extract deterministic facts from one document or an entire workspace."""
        return self.fact_extraction_service.extract_workspace(
            self.settings.workspace_id,
            document_id=document_id,
        )

    def query_facts(
        self,
        *,
        fact_id: str | None = None,
        document_id: str | None = None,
        evidence_segment_id: str | None = None,
        query: str | None = None,
        subject: str | None = None,
        predicate: str | None = None,
        object_text: str | None = None,
        limit: int = 20,
    ) -> tuple[FactRecord, ...]:
        """Query extracted facts."""
        return self.fact_extraction_service.query_facts(
            self.settings.workspace_id,
            fact_id=fact_id,
            document_id=document_id,
            evidence_segment_id=evidence_segment_id,
            query=query,
            subject=subject,
            predicate=predicate,
            object_text=object_text,
            limit=limit,
        )

    def query_entities(
        self,
        *,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 20,
    ):
        """Query extracted entities."""
        return self.fact_extraction_service.query_entities(
            self.settings.workspace_id,
            query=query,
            entity_type=entity_type,
            limit=limit,
        )

    def fetch_evidence_trail(
        self,
        *,
        fact_id: str | None = None,
        segment_id: str | None = None,
        document_id: str | None = None,
        neighbor_count: int = 1,
    ) -> EvidenceTrail:
        """Return a provenance trail around a fact, segment, or document."""
        return self.context_service.fetch_evidence_trail(
            self.settings.workspace_id,
            fact_id=fact_id,
            segment_id=segment_id,
            document_id=document_id,
            neighbor_count=neighbor_count,
        )

    def recall_episodes(
        self,
        *,
        query: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 5,
    ) -> tuple[EpisodeRecord, ...]:
        """Recall recent or query-matched episodes."""
        return self.context_service.recall_episodes(
            self.settings.workspace_id,
            query=query,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def compact_session_context(
        self,
        *,
        query: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        evidence_limit: int = 5,
        fact_limit: int = 5,
        episode_limit: int = 3,
        max_chars: int = 4000,
    ) -> CompactedSessionContext:
        """Compact relevant memory into an agent-ready context block."""
        return self.context_service.compact_session_context(
            self.settings.workspace_id,
            query=query,
            start_time=start_time,
            end_time=end_time,
            evidence_limit=evidence_limit,
            fact_limit=fact_limit,
            episode_limit=episode_limit,
            max_chars=max_chars,
        )

    def prepare_startup_context(
        self,
        *,
        agent_name: str = "assistant",
        query: str | None = None,
        evidence_limit: int = 6,
        fact_limit: int = 6,
        episode_limit: int = 4,
        max_chars: int = 6000,
    ) -> StartupContext:
        """Prepare startup context for an agent entering the workspace."""
        return self.context_service.prepare_startup_context(
            self.settings.workspace_id,
            agent_name=agent_name,
            query=query,
            evidence_limit=evidence_limit,
            fact_limit=fact_limit,
            episode_limit=episode_limit,
            max_chars=max_chars,
        )

    def reindex(self, *, document_id: str | None = None) -> ReindexResult:
        """Rebuild vector entries from stored segments."""
        return self.reindexing_service.reindex_workspace(
            self.settings.workspace_id,
            document_id=document_id,
        )

    def status(self) -> dict[str, int]:
        """Return lightweight status counts."""
        self.metadata_store.initialize()
        return self.metadata_store.get_status()

    def health(self) -> dict[str, object]:
        """Return runtime health details and storage counts."""
        counts = self.status()
        return {
            "workspace_id": self.settings.workspace_id,
            "metadata_path": str(self.settings.storage.resolved_metadata_path()),
            "vector_backend": self.settings.storage.vector_backend,
            "counts": counts,
        }
