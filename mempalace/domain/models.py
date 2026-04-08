"""Canonical domain models for the new service-oriented memory core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class SearchMode(str, Enum):
    """Supported retrieval modes."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@dataclass(slots=True, frozen=True)
class WorkspaceRecord:
    """Logical tenant boundary for local-first and future multi-user operation."""

    workspace_id: str
    name: str
    root_path: str | None
    created_at: datetime
    updated_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SourceRecord:
    """Raw source descriptor such as a filesystem path or import artifact."""

    source_id: str
    workspace_id: str
    source_type: str
    uri: str
    checksum: str
    first_seen_at: datetime
    last_seen_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class DocumentRecord:
    """Persisted raw document with stable identity and verbatim content."""

    document_id: str
    workspace_id: str
    source_id: str
    title: str
    uri: str
    document_type: str
    checksum: str
    raw_text: str
    created_at: datetime
    updated_at: datetime
    observed_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SegmentRecord:
    """Document segment used for retrieval and provenance."""

    segment_id: str
    workspace_id: str
    document_id: str
    segment_index: int
    text: str
    start_offset: int
    end_offset: int
    token_count: int
    checksum: str
    created_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SegmentBundle:
    """Joined view of a segment and its parent document/source."""

    source: SourceRecord
    document: DocumentRecord
    segment: SegmentRecord


@dataclass(slots=True, frozen=True)
class MemoryRecord:
    """Convenience aggregate used by higher-level services."""

    source: SourceRecord
    document: DocumentRecord
    segments: tuple[SegmentRecord, ...]


@dataclass(slots=True, frozen=True)
class EntityRecord:
    """Structured entity extracted or curated from memory."""

    entity_id: str
    workspace_id: str
    name: str
    entity_type: str
    created_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RelationRecord:
    """Directed relationship between entities with provenance and validity."""

    relation_id: str
    workspace_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str
    valid_from: datetime | None
    valid_to: datetime | None
    confidence: float
    evidence_segment_id: str | None
    created_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class FactRecord:
    """Structured fact linked to evidence."""

    fact_id: str
    workspace_id: str
    document_id: str | None
    subject: str
    predicate: str
    object: str
    confidence: float
    evidence_segment_id: str | None
    observed_at: datetime | None
    created_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class EpisodeRecord:
    """Session- or event-scoped unit of time-aware memory."""

    episode_id: str
    workspace_id: str
    title: str
    started_at: datetime | None
    ended_at: datetime | None
    summary: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class IngestionRun:
    """One execution of an ingestion pipeline."""

    run_id: str
    workspace_id: str
    source_type: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class IngestionFileResult:
    """Per-file ingestion outcome."""

    uri: str
    status: str
    checksum: str | None
    document_id: str | None
    segments_written: int
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class IngestionResult:
    """Summary returned by an ingestion service."""

    run_id: str
    workspace_id: str
    source_type: str
    started_at: datetime
    finished_at: datetime
    files_seen: int
    files_read: int
    documents_written: int
    documents_updated: int
    documents_skipped: int
    segments_written: int
    errors: tuple[str, ...] = ()
    file_results: tuple[IngestionFileResult, ...] = ()


@dataclass(slots=True, frozen=True)
class MigrationDrawerResult:
    """Per-drawer migration outcome from a legacy store."""

    legacy_drawer_id: str
    status: str
    document_id: str | None
    segment_id: str | None
    checksum: str | None
    legacy_source_file: str | None = None
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class MigrationResult:
    """Summary returned by a legacy migration service."""

    run_id: str
    workspace_id: str
    source_type: str
    started_at: datetime
    finished_at: datetime
    drawers_seen: int
    drawers_migrated: int
    drawers_skipped: int
    segments_written: int
    errors: tuple[str, ...] = ()
    drawer_results: tuple[MigrationDrawerResult, ...] = ()


@dataclass(slots=True, frozen=True)
class FactExtractionDocumentResult:
    """Per-document fact extraction outcome."""

    document_id: str
    status: str
    facts_written: int
    entities_written: int
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class FactExtractionResult:
    """Summary returned by a deterministic fact extraction run."""

    workspace_id: str
    documents_seen: int
    documents_processed: int
    facts_written: int
    entities_written: int
    errors: tuple[str, ...] = ()
    document_results: tuple[FactExtractionDocumentResult, ...] = ()


@dataclass(slots=True, frozen=True)
class ReindexDocumentResult:
    """Per-document vector reindex outcome."""

    document_id: str
    status: str
    segments_indexed: int
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class ReindexResult:
    """Summary returned by a reindex run."""

    workspace_id: str
    documents_seen: int
    documents_reindexed: int
    documents_skipped: int
    segments_indexed: int
    errors: tuple[str, ...] = ()
    document_results: tuple[ReindexDocumentResult, ...] = ()


@dataclass(slots=True, frozen=True)
class SearchRequest:
    """User-facing retrieval request."""

    workspace_id: str
    query: str
    mode: SearchMode = SearchMode.HYBRID
    limit: int = 5
    start_time: datetime | None = None
    end_time: datetime | None = None
    filters: Mapping[str, str] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RetrievalPlan:
    """Inspectible explanation of the retrieval route used."""

    mode: SearchMode
    keyword_limit: int
    semantic_limit: int
    filters: Mapping[str, str]
    candidate_counts: Mapping[str, int] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ScoreBreakdown:
    """Score components for a retrieval result."""

    combined: float
    keyword: float | None = None
    semantic: float | None = None
    keyword_rank: int | None = None
    semantic_rank: int | None = None
    raw_keyword_score: float | None = None
    raw_semantic_score: float | None = None


@dataclass(slots=True, frozen=True)
class Evidence:
    """Retrieval result with provenance and verbatim evidence."""

    source_uri: str
    document_id: str
    segment_id: str
    document_title: str
    timestamp: datetime | None
    excerpt: str
    retrieval_reason: str
    scores: ScoreBreakdown
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SearchResponse:
    """Search output returned by the retrieval service."""

    request: SearchRequest
    plan: RetrievalPlan
    results: tuple[Evidence, ...]


@dataclass(slots=True, frozen=True)
class EvidenceTrail:
    """Focused provenance bundle for a document segment or extracted fact."""

    workspace_id: str
    generated_at: datetime
    source: SourceRecord | None
    document: DocumentRecord | None
    focus_segment: SegmentRecord | None
    focus_fact: FactRecord | None = None
    evidence: tuple[Evidence, ...] = ()
    related_facts: tuple[FactRecord, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class CompactedSessionContext:
    """Agent-ready compact context assembled from evidence, facts, and episodes."""

    workspace_id: str
    query: str | None
    generated_at: datetime
    context_text: str
    max_chars: int
    truncated: bool
    evidence: tuple[Evidence, ...] = ()
    facts: tuple[FactRecord, ...] = ()
    episodes: tuple[EpisodeRecord, ...] = ()


@dataclass(slots=True, frozen=True)
class StartupContext:
    """Startup context prepared for an agent entering a workspace."""

    workspace_id: str
    agent_name: str
    generated_at: datetime
    startup_text: str
    status_counts: Mapping[str, int] = field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()
    facts: tuple[FactRecord, ...] = ()
    episodes: tuple[EpisodeRecord, ...] = ()


@dataclass(slots=True, frozen=True)
class ScoredSegmentReference:
    """Internal ranking record emitted by keyword or semantic backends."""

    segment_id: str
    score: float
    raw_score: float
    rank: int
    reason: str
