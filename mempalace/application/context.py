"""Context assembly services for evidence trails, episodes, and agent startup."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from mempalace.application.fact_extraction import FactExtractionService
from mempalace.application.ports import MetadataStore
from mempalace.application.retrieval import RetrievalService
from mempalace.domain.models import (
    CompactedSessionContext,
    DocumentRecord,
    EpisodeRecord,
    Evidence,
    EvidenceTrail,
    FactRecord,
    ScoreBreakdown,
    SearchMode,
    SearchRequest,
    SegmentBundle,
    SegmentRecord,
    StartupContext,
)
from mempalace.infrastructure.logging import log_event


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def _document_timestamp(document: DocumentRecord) -> datetime:
    return document.observed_at or document.updated_at


@dataclass(slots=True)
class ContextService:
    """Build inspectable evidence and compact contexts for agent workflows."""

    metadata_store: MetadataStore
    fact_service: FactExtractionService
    retrieval_service: RetrievalService
    logger: logging.Logger

    def fetch_evidence_trail(
        self,
        workspace_id: str,
        *,
        fact_id: str | None = None,
        segment_id: str | None = None,
        document_id: str | None = None,
        neighbor_count: int = 1,
    ) -> EvidenceTrail:
        """Build a provenance trail around one fact, segment, or document."""
        self.metadata_store.initialize()

        focus_fact: FactRecord | None = None
        focus_segment: SegmentRecord | None = None
        notes: list[str] = []

        if fact_id:
            facts = self.fact_service.query_facts(workspace_id, fact_id=fact_id, limit=1)
            focus_fact = facts[0] if facts else None
            if focus_fact is not None and focus_fact.evidence_segment_id:
                focus_segment = self.metadata_store.fetch_segment(focus_fact.evidence_segment_id)
                notes.append("focused on extracted fact evidence")
            else:
                notes.append("fact was found without a direct evidence segment")
            if focus_fact and focus_fact.document_id and not document_id:
                document_id = focus_fact.document_id

        if focus_segment is None and segment_id:
            focus_segment = self.metadata_store.fetch_segment(segment_id)
            if focus_segment is not None:
                notes.append("focused on explicit segment")
            if focus_segment and not document_id:
                document_id = focus_segment.document_id

        if focus_segment is None and document_id:
            segments = self.metadata_store.fetch_document_segments(document_id)
            focus_segment = segments[0] if segments else None
            if focus_segment is not None:
                notes.append("defaulted to the first segment in the document")

        if focus_segment is None or document_id is None:
            return EvidenceTrail(
                workspace_id=workspace_id,
                generated_at=_utc_now(),
                source=None,
                document=None,
                focus_segment=None,
                focus_fact=focus_fact,
                evidence=(),
                related_facts=(),
                notes=tuple(notes or ["no matching fact, segment, or document was found"]),
            )

        all_segments = self.metadata_store.fetch_document_segments(document_id)
        neighboring_segments = self._select_neighbor_segments(
            all_segments,
            focus_segment_id=focus_segment.segment_id,
            neighbor_count=neighbor_count,
        )
        bundles = self.metadata_store.get_segment_bundles([segment.segment_id for segment in neighboring_segments])
        ordered_bundles = [bundles[segment.segment_id] for segment in neighboring_segments if segment.segment_id in bundles]
        focus_bundle = bundles.get(focus_segment.segment_id)

        related_facts = self.fact_service.query_facts(
            workspace_id,
            document_id=document_id,
            limit=max(20, neighbor_count * 10),
        )
        notes.append(f"returned {len(ordered_bundles)} evidence segment(s)")
        if focus_fact is not None:
            notes.append(f"found {len(related_facts)} related fact(s) in the same document")

        return EvidenceTrail(
            workspace_id=workspace_id,
            generated_at=_utc_now(),
            source=focus_bundle.source if focus_bundle else None,
            document=focus_bundle.document if focus_bundle else self.metadata_store.fetch_document(document_id),
            focus_segment=focus_segment,
            focus_fact=focus_fact,
            evidence=tuple(
                self._bundle_to_evidence(bundle, reason="neighboring segment for evidence trail")
                for bundle in ordered_bundles
            ),
            related_facts=tuple(related_facts),
            notes=tuple(notes),
        )

    def recall_episodes(
        self,
        workspace_id: str,
        *,
        query: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 5,
    ) -> tuple[EpisodeRecord, ...]:
        """Recall recent or query-matched episodes represented by stored documents."""
        self.metadata_store.initialize()
        documents: list[DocumentRecord]

        if query:
            response = self.retrieval_service.search(
                SearchRequest(
                    workspace_id=workspace_id,
                    query=query,
                    mode=SearchMode.HYBRID,
                    limit=max(limit * 3, limit),
                    start_time=start_time,
                    end_time=end_time,
                )
            )
            ordered_document_ids: list[str] = []
            seen_document_ids: set[str] = set()
            for result in response.results:
                if result.document_id in seen_document_ids:
                    continue
                seen_document_ids.add(result.document_id)
                ordered_document_ids.append(result.document_id)
                if len(ordered_document_ids) >= limit:
                    break
            documents = [
                document
                for document in (self.metadata_store.fetch_document(document_id) for document_id in ordered_document_ids)
                if document is not None
            ]
        else:
            documents = self.metadata_store.list_documents(workspace_id)
            documents = [
                document
                for document in documents
                if self._matches_time_window(document, start_time=start_time, end_time=end_time)
            ][:limit]

        episodes = [self._document_to_episode(document) for document in documents[:limit]]
        return tuple(episodes)

    def compact_session_context(
        self,
        workspace_id: str,
        *,
        query: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        evidence_limit: int = 5,
        fact_limit: int = 5,
        episode_limit: int = 3,
        max_chars: int = 4000,
    ) -> CompactedSessionContext:
        """Assemble a compact agent-readable context block."""
        evidence = self._collect_context_evidence(
            workspace_id,
            query=query,
            start_time=start_time,
            end_time=end_time,
            limit=evidence_limit,
        )
        facts = self.fact_service.query_facts(workspace_id, query=query, limit=fact_limit)
        episodes = self.recall_episodes(
            workspace_id,
            query=query,
            start_time=start_time,
            end_time=end_time,
            limit=episode_limit,
        )
        context_text, truncated = self._render_context_text(
            workspace_id=workspace_id,
            query=query,
            evidence=evidence,
            facts=facts,
            episodes=episodes,
            max_chars=max_chars,
        )
        log_event(
            self.logger,
            logging.INFO,
            "session_context_compacted",
            workspace_id=workspace_id,
            query=query,
            evidence_count=len(evidence),
            fact_count=len(facts),
            episode_count=len(episodes),
            truncated=truncated,
        )
        return CompactedSessionContext(
            workspace_id=workspace_id,
            query=query,
            generated_at=_utc_now(),
            context_text=context_text,
            max_chars=max_chars,
            truncated=truncated,
            evidence=tuple(evidence),
            facts=tuple(facts),
            episodes=tuple(episodes),
        )

    def prepare_startup_context(
        self,
        workspace_id: str,
        *,
        agent_name: str = "assistant",
        query: str | None = None,
        evidence_limit: int = 6,
        fact_limit: int = 6,
        episode_limit: int = 4,
        max_chars: int = 6000,
    ) -> StartupContext:
        """Build startup context for an agent entering a workspace."""
        counts = self.metadata_store.get_status()
        compacted = self.compact_session_context(
            workspace_id,
            query=query,
            evidence_limit=evidence_limit,
            fact_limit=fact_limit,
            episode_limit=episode_limit,
            max_chars=max_chars,
        )
        header_lines = [
            f"Agent: {agent_name}",
            f"Workspace: {workspace_id}",
            (
                "Status counts: "
                f"documents={counts.get('documents', 0)}, "
                f"segments={counts.get('segments', 0)}, "
                f"facts={counts.get('facts', 0)}, "
                f"entities={counts.get('entities', 0)}"
            ),
            "",
            compacted.context_text,
        ]
        startup_text = _truncate_text("\n".join(line for line in header_lines if line is not None), max_chars)
        return StartupContext(
            workspace_id=workspace_id,
            agent_name=agent_name,
            generated_at=_utc_now(),
            startup_text=startup_text,
            status_counts=counts,
            evidence=compacted.evidence,
            facts=compacted.facts,
            episodes=compacted.episodes,
        )

    def _collect_context_evidence(
        self,
        workspace_id: str,
        *,
        query: str | None,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
    ) -> list[Evidence]:
        if query:
            response = self.retrieval_service.search(
                SearchRequest(
                    workspace_id=workspace_id,
                    query=query,
                    mode=SearchMode.HYBRID,
                    limit=limit,
                    start_time=start_time,
                    end_time=end_time,
                )
            )
            return list(response.results)

        documents = [
            document
            for document in self.metadata_store.list_documents(workspace_id)
            if self._matches_time_window(document, start_time=start_time, end_time=end_time)
        ][:limit]
        segment_ids: list[str] = []
        for document in documents:
            segments = self.metadata_store.fetch_document_segments(document.document_id)
            if segments:
                segment_ids.append(segments[0].segment_id)
        bundles = self.metadata_store.get_segment_bundles(segment_ids)
        return [
            self._bundle_to_evidence(bundles[segment_id], reason="recent document segment for startup context")
            for segment_id in segment_ids
            if segment_id in bundles
        ]

    def _render_context_text(
        self,
        *,
        workspace_id: str,
        query: str | None,
        evidence: list[Evidence],
        facts: tuple[FactRecord, ...],
        episodes: tuple[EpisodeRecord, ...],
        max_chars: int,
    ) -> tuple[str, bool]:
        sections: list[list[str]] = []
        intro = [f"Workspace context for: {workspace_id}"]
        if query:
            intro.append(f"Query focus: {query}")
        sections.append(intro)

        fact_lines = ["Facts:"] if facts else ["Facts: none"]
        for index, fact in enumerate(facts, start=1):
            fact_lines.append(
                f"- [{index}] {fact.subject} {fact.predicate} {fact.object} "
                f"(confidence={fact.confidence:.2f})"
            )
        sections.append(fact_lines)

        episode_lines = ["Episodes:"] if episodes else ["Episodes: none"]
        for index, episode in enumerate(episodes, start=1):
            when = episode.started_at.isoformat() if episode.started_at else "unknown"
            summary = episode.summary or ""
            episode_lines.append(f"- [{index}] {episode.title} @ {when} :: {summary}")
        sections.append(episode_lines)

        evidence_lines = ["Evidence:"] if evidence else ["Evidence: none"]
        for index, item in enumerate(evidence, start=1):
            source_name = item.metadata.get("document_uri", item.source_uri)
            evidence_lines.append(
                f"- [{index}] {item.document_title} :: {source_name} :: {item.excerpt}"
            )
        sections.append(evidence_lines)

        lines: list[str] = []
        truncated = False
        for section in sections:
            for line in section:
                candidate = "\n".join(lines + [line]).strip()
                if len(candidate) > max_chars:
                    truncated = True
                    break
                lines.append(line)
            if truncated:
                break
            lines.append("")

        rendered = "\n".join(line for line in lines if line is not None).strip()
        return _truncate_text(rendered, max_chars), truncated

    def _document_to_episode(self, document: DocumentRecord) -> EpisodeRecord:
        segments = self.metadata_store.fetch_document_segments(document.document_id)
        summary_source = segments[0].text if segments else document.raw_text
        summary = _truncate_text(" ".join(summary_source.split()), 240) if summary_source else None
        timestamp = _document_timestamp(document)
        session_id = document.metadata.get("session_id")
        episode_id = session_id or f"episode::{document.document_id}"
        return EpisodeRecord(
            episode_id=episode_id,
            workspace_id=document.workspace_id,
            title=document.title,
            started_at=timestamp,
            ended_at=timestamp,
            summary=summary,
            metadata={
                "document_id": document.document_id,
                "document_type": document.document_type,
                "source_uri": document.uri,
                "session_id": session_id,
                "source_format": document.metadata.get("source_format"),
                "wing": document.metadata.get("wing"),
                "room": document.metadata.get("room"),
                "segment_count": len(segments),
            },
        )

    def _select_neighbor_segments(
        self,
        segments: list[SegmentRecord],
        *,
        focus_segment_id: str,
        neighbor_count: int,
    ) -> list[SegmentRecord]:
        if not segments:
            return []
        focus_index = next(
            (index for index, segment in enumerate(segments) if segment.segment_id == focus_segment_id),
            0,
        )
        start = max(focus_index - max(neighbor_count, 0), 0)
        end = min(focus_index + max(neighbor_count, 0) + 1, len(segments))
        return segments[start:end]

    def _bundle_to_evidence(self, bundle: SegmentBundle, *, reason: str) -> Evidence:
        metadata = {
            "document_uri": bundle.document.uri,
            "start_offset": bundle.segment.start_offset,
            "end_offset": bundle.segment.end_offset,
        }
        for key in ("wing", "room", "session_id", "source_format"):
            value = bundle.segment.metadata.get(key)
            if value is None:
                value = bundle.document.metadata.get(key)
            if value is not None:
                metadata[key] = value
        return Evidence(
            source_uri=bundle.source.uri,
            document_id=bundle.document.document_id,
            segment_id=bundle.segment.segment_id,
            document_title=bundle.document.title,
            timestamp=bundle.document.observed_at,
            excerpt=_truncate_text(" ".join(bundle.segment.text.split()), 320),
            retrieval_reason=reason,
            scores=ScoreBreakdown(combined=0.0),
            metadata=metadata,
        )

    def _matches_time_window(
        self,
        document: DocumentRecord,
        *,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> bool:
        timestamp = _document_timestamp(document)
        if start_time and timestamp < start_time:
            return False
        if end_time and timestamp > end_time:
            return False
        return True
