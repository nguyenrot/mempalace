"""Retrieval orchestration with explainable score breakdowns."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Mapping

from mempalace.application.ports import EmbeddingProvider, MetadataStore, VectorIndex
from mempalace.domain.models import (
    Evidence,
    RetrievalPlan,
    ScoreBreakdown,
    ScoredSegmentReference,
    SearchMode,
    SearchRequest,
    SearchResponse,
    SegmentBundle,
)
from mempalace.infrastructure.logging import log_event
from mempalace.infrastructure.settings import RetrievalSettings


def _normalized_rank_score(rank: int) -> float:
    return 1.0 / float(rank)


def _excerpt(text: str, query: str, max_chars: int = 320) -> str:
    """Return a compact verbatim excerpt centered on the first query token match when possible."""
    if len(text) <= max_chars:
        return text

    tokens = [token for token in re.findall(r"\w+", query.lower()) if len(token) > 2]
    lowered = text.lower()
    for token in tokens:
        position = lowered.find(token)
        if position != -1:
            start = max(position - max_chars // 3, 0)
            end = min(start + max_chars, len(text))
            return text[start:end].strip()
    return text[:max_chars].strip()


@dataclass(slots=True)
class RetrievalService:
    """Coordinate keyword and semantic retrieval and return provenance-rich results."""

    metadata_store: MetadataStore
    vector_index: VectorIndex
    embedding_provider: EmbeddingProvider
    settings: RetrievalSettings
    logger: logging.Logger

    def search(self, request: SearchRequest) -> SearchResponse:
        """Execute a keyword, semantic, or hybrid search."""
        self.metadata_store.initialize()
        self.vector_index.initialize()

        candidate_multiplier = 10 if request.filters else 3
        keyword_limit = max(request.limit * candidate_multiplier, request.limit)
        semantic_limit = max(request.limit * candidate_multiplier, request.limit)
        plan = RetrievalPlan(
            mode=request.mode,
            keyword_limit=keyword_limit if request.mode in (SearchMode.KEYWORD, SearchMode.HYBRID) else 0,
            semantic_limit=semantic_limit if request.mode in (SearchMode.SEMANTIC, SearchMode.HYBRID) else 0,
            filters=request.filters,
            candidate_counts={},
            notes=(
                "timestamp filtering uses observed_at when available",
                "metadata filters are applied after candidate retrieval",
            ),
        )

        log_event(
            self.logger,
            logging.INFO,
            "retrieval_started",
            workspace_id=request.workspace_id,
            query=request.query,
            mode=request.mode.value,
            limit=request.limit,
        )

        keyword_hits: list[ScoredSegmentReference] = []
        semantic_hits: list[ScoredSegmentReference] = []

        if request.mode in (SearchMode.KEYWORD, SearchMode.HYBRID):
            keyword_hits = self.metadata_store.keyword_search(request, limit=keyword_limit)
        if request.mode in (SearchMode.SEMANTIC, SearchMode.HYBRID):
            query_embedding = self.embedding_provider.embed_texts([request.query])[0]
            semantic_hits = self.vector_index.search(request, query_embedding=query_embedding, limit=semantic_limit)

        merged = self._merge_hits(keyword_hits=keyword_hits, semantic_hits=semantic_hits)
        bundles = self.metadata_store.get_segment_bundles([item["segment_id"] for item in merged])
        candidate_counts = {
            "keyword_hits": len(keyword_hits),
            "semantic_hits": len(semantic_hits),
            "merged_hits": len(merged),
        }
        if request.filters:
            merged = [
                item
                for item in merged
                if self._bundle_matches_filters(bundles.get(item["segment_id"]), request.filters)
            ]
        candidate_counts["filtered_hits"] = len(merged)
        plan = RetrievalPlan(
            mode=plan.mode,
            keyword_limit=plan.keyword_limit,
            semantic_limit=plan.semantic_limit,
            filters=plan.filters,
            candidate_counts=candidate_counts,
            notes=plan.notes,
        )

        results: list[Evidence] = []
        for item in merged[: request.limit]:
            bundle = bundles.get(item["segment_id"])
            if bundle is None:
                continue
            results.append(self._build_evidence(bundle=bundle, query=request.query, item=item))

        log_event(
            self.logger,
            logging.INFO,
            "retrieval_completed",
            workspace_id=request.workspace_id,
            query=request.query,
            mode=request.mode.value,
            result_count=len(results),
        )
        return SearchResponse(request=request, plan=plan, results=tuple(results))

    def fetch_document(self, document_id: str) -> SegmentBundle | None:
        """Fetch the first segment bundle for a document as a light document lookup primitive."""
        document = self.metadata_store.fetch_document(document_id)
        if document is None:
            return None
        segments = self.metadata_store.fetch_document_segments(document_id)
        if not segments:
            return None
        bundles = self.metadata_store.get_segment_bundles([segments[0].segment_id])
        return bundles.get(segments[0].segment_id)

    def _merge_hits(
        self,
        keyword_hits: list[ScoredSegmentReference],
        semantic_hits: list[ScoredSegmentReference],
    ) -> list[dict[str, object]]:
        """Merge ranking outputs by segment ID."""
        merged: dict[str, dict[str, object]] = {}

        for hit in keyword_hits:
            normalized = hit.score if hit.score > 0 else _normalized_rank_score(hit.rank)
            merged.setdefault(hit.segment_id, {"segment_id": hit.segment_id})
            merged[hit.segment_id].update(
                {
                    "keyword_score": normalized,
                    "raw_keyword_score": hit.raw_score,
                    "keyword_rank": hit.rank,
                }
            )

        for hit in semantic_hits:
            normalized = hit.score if hit.score > 0 else _normalized_rank_score(hit.rank)
            merged.setdefault(hit.segment_id, {"segment_id": hit.segment_id})
            merged[hit.segment_id].update(
                {
                    "semantic_score": normalized,
                    "raw_semantic_score": hit.raw_score,
                    "semantic_rank": hit.rank,
                }
            )

        ranked: list[dict[str, object]] = []
        for entry in merged.values():
            keyword_score = float(entry.get("keyword_score", 0.0))
            semantic_score = float(entry.get("semantic_score", 0.0))
            combined = (
                self.settings.keyword_weight * keyword_score
                + self.settings.semantic_weight * semantic_score
            )
            if keyword_score and semantic_score:
                reason = "matched keyword and semantic retrieval"
            elif keyword_score:
                reason = "matched keyword retrieval"
            else:
                reason = "matched semantic retrieval"
            entry["combined_score"] = combined
            entry["reason"] = reason
            ranked.append(entry)

        ranked.sort(key=lambda item: float(item["combined_score"]), reverse=True)
        return ranked

    def _build_evidence(self, bundle: SegmentBundle, query: str, item: dict[str, object]) -> Evidence:
        """Convert a hydrated segment bundle into an evidence record."""
        evidence_metadata = {
            "document_uri": bundle.document.uri,
            "start_offset": bundle.segment.start_offset,
            "end_offset": bundle.segment.end_offset,
        }
        for key in ("wing", "room"):
            value = self._lookup_filter_value(bundle, key)
            if value is not None:
                evidence_metadata[key] = value
        return Evidence(
            source_uri=bundle.source.uri,
            document_id=bundle.document.document_id,
            segment_id=bundle.segment.segment_id,
            document_title=bundle.document.title,
            timestamp=bundle.document.observed_at,
            excerpt=_excerpt(bundle.segment.text, query=query),
            retrieval_reason=str(item["reason"]),
            scores=ScoreBreakdown(
                combined=float(item["combined_score"]),
                keyword=float(item["keyword_score"]) if "keyword_score" in item else None,
                semantic=float(item["semantic_score"]) if "semantic_score" in item else None,
                keyword_rank=int(item["keyword_rank"]) if "keyword_rank" in item else None,
                semantic_rank=int(item["semantic_rank"]) if "semantic_rank" in item else None,
                raw_keyword_score=float(item["raw_keyword_score"]) if "raw_keyword_score" in item else None,
                raw_semantic_score=float(item["raw_semantic_score"]) if "raw_semantic_score" in item else None,
            ),
            metadata=evidence_metadata,
        )

    def _bundle_matches_filters(self, bundle: SegmentBundle | None, filters: Mapping[str, str]) -> bool:
        """Return true when a hydrated bundle matches all exact-match filters."""
        if bundle is None:
            return False
        for key, expected in filters.items():
            actual = self._lookup_filter_value(bundle, key)
            if actual is None:
                return False
            if str(actual).strip().lower() != str(expected).strip().lower():
                return False
        return True

    def _lookup_filter_value(self, bundle: SegmentBundle, key: str) -> object | None:
        """Resolve a filter key from segment, document, or source scope."""
        if key in bundle.segment.metadata:
            return bundle.segment.metadata[key]
        if key in bundle.document.metadata:
            return bundle.document.metadata[key]
        if key in bundle.source.metadata:
            return bundle.source.metadata[key]

        direct_values = {
            "source_uri": bundle.source.uri,
            "source_type": bundle.source.source_type,
            "document_uri": bundle.document.uri,
            "document_type": bundle.document.document_type,
            "document_title": bundle.document.title,
        }
        return direct_values.get(key)
