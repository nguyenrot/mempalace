"""Deterministic structured fact extraction over stored documents and segments."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Pattern

from mempalace.application.ports import FactStore, MetadataStore
from mempalace.domain.models import (
    EntityRecord,
    FactExtractionDocumentResult,
    FactExtractionResult,
    FactRecord,
)
from mempalace.infrastructure.logging import log_event


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n\"'`.,:;()[]{}")


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for chunk in re.split(r"(?<=[.!?])\s+|\n+", text):
        cleaned = _normalize_space(chunk)
        if len(cleaned) >= 12:
            sentences.append(cleaned)
    return sentences


def _looks_like_natural_language(text: str) -> bool:
    letters = sum(character.isalpha() for character in text)
    spaces = text.count(" ")
    symbols = sum(not character.isalnum() and not character.isspace() for character in text)
    return letters >= 8 and spaces >= 1 and symbols <= max(letters, 1)


def _normalize_entity_name(value: str) -> str:
    normalized = _normalize_space(value)
    if normalized.lower() == "we":
        return "team"
    return normalized


def _should_materialize_entity(value: str) -> bool:
    normalized = _normalize_entity_name(value)
    return 1 <= len(normalized) <= 64 and "," not in normalized and " because " not in normalized.lower()


@dataclass(slots=True, frozen=True)
class FactPattern:
    """One deterministic extraction rule."""

    name: str
    predicate: str
    confidence: float
    regex: Pattern[str]
    subject_factory: Callable[[re.Match[str]], str]
    object_factory: Callable[[re.Match[str]], str]


FACT_PATTERNS: tuple[FactPattern, ...] = (
    FactPattern(
        name="uses",
        predicate="uses",
        confidence=0.86,
        regex=re.compile(r"(?i)(?P<subject>.+?)\s+(?:uses|use|used)\s+(?P<object>[^.]+)"),
        subject_factory=lambda match: _normalize_entity_name(match.group("subject")),
        object_factory=lambda match: _normalize_space(match.group("object")),
    ),
    FactPattern(
        name="depends_on",
        predicate="depends_on",
        confidence=0.83,
        regex=re.compile(r"(?i)(?P<subject>.+?)\s+(?:depends on|relies on)\s+(?P<object>[^.]+)"),
        subject_factory=lambda match: _normalize_entity_name(match.group("subject")),
        object_factory=lambda match: _normalize_space(match.group("object")),
    ),
    FactPattern(
        name="stored_in",
        predicate="stored_in",
        confidence=0.8,
        regex=re.compile(r"(?i)(?P<subject>.+?)\s+(?:is|are)\s+stored in\s+(?P<object>[^.]+)"),
        subject_factory=lambda match: _normalize_entity_name(match.group("subject")),
        object_factory=lambda match: _normalize_space(match.group("object")),
    ),
    FactPattern(
        name="requires",
        predicate="requires",
        confidence=0.78,
        regex=re.compile(r"(?i)(?P<subject>.+?)\s+(?:must include|requires?)\s+(?P<object>[^.]+)"),
        subject_factory=lambda match: _normalize_entity_name(match.group("subject")),
        object_factory=lambda match: _normalize_space(match.group("object")),
    ),
    FactPattern(
        name="decided_to",
        predicate="decided_to",
        confidence=0.8,
        regex=re.compile(r"(?i)(?:we|the team)\s+(?:decided|chose|picked)\s+to\s+(?P<object>[^.]+)"),
        subject_factory=lambda match: "team",
        object_factory=lambda match: _normalize_space(match.group("object")),
    ),
    FactPattern(
        name="decision",
        predicate="decision",
        confidence=0.72,
        regex=re.compile(r"(?i)(?:the final decision|decision)\s+(?:favored|was|is)\s+(?P<object>[^.]+)"),
        subject_factory=lambda match: "team",
        object_factory=lambda match: _normalize_space(match.group("object")),
    ),
    FactPattern(
        name="migrates_to",
        predicate="migrates_to",
        confidence=0.79,
        regex=re.compile(r"(?i)(?:migrate|migrated|migrating)\s+(?P<subject>[^.]+?)\s+to\s+(?P<object>[^.]+)"),
        subject_factory=lambda match: _normalize_entity_name(match.group("subject")),
        object_factory=lambda match: _normalize_space(match.group("object")),
    ),
)


@dataclass(slots=True)
class FactExtractionService:
    """Extract deterministic facts from stored segments and persist them."""

    metadata_store: MetadataStore
    fact_store: FactStore
    logger: logging.Logger

    def extract_workspace(
        self,
        workspace_id: str,
        *,
        document_id: str | None = None,
    ) -> FactExtractionResult:
        """Extract facts for one document or an entire workspace."""
        self.metadata_store.initialize()
        self.fact_store.initialize()
        documents = (
            [self.metadata_store.fetch_document(document_id)] if document_id else self.metadata_store.list_documents(workspace_id)
        )
        documents = [document for document in documents if document is not None]

        log_event(
            self.logger,
            logging.INFO,
            "fact_extraction_started",
            workspace_id=workspace_id,
            document_id=document_id,
            document_count=len(documents),
        )

        errors: list[str] = []
        document_results: list[FactExtractionDocumentResult] = []
        facts_written = 0
        entities_written = 0
        documents_processed = 0

        for document in documents:
            try:
                result = self._extract_document(document.document_id, workspace_id=workspace_id)
            except Exception as exc:
                errors.append(f"{document.document_id}: {exc}")
                document_results.append(
                    FactExtractionDocumentResult(
                        document_id=document.document_id,
                        status="error",
                        facts_written=0,
                        entities_written=0,
                        reason=str(exc),
                    )
                )
                continue

            documents_processed += 1
            facts_written += result.facts_written
            entities_written += result.entities_written
            document_results.append(result)

        log_event(
            self.logger,
            logging.INFO,
            "fact_extraction_completed",
            workspace_id=workspace_id,
            documents_seen=len(documents),
            documents_processed=documents_processed,
            facts_written=facts_written,
            entities_written=entities_written,
            error_count=len(errors),
        )
        return FactExtractionResult(
            workspace_id=workspace_id,
            documents_seen=len(documents),
            documents_processed=documents_processed,
            facts_written=facts_written,
            entities_written=entities_written,
            errors=tuple(errors),
            document_results=tuple(document_results),
        )

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
    ) -> tuple[FactRecord, ...]:
        """Query extracted facts."""
        self.fact_store.initialize()
        return tuple(
            self.fact_store.query_facts(
                workspace_id,
                fact_id=fact_id,
                document_id=document_id,
                evidence_segment_id=evidence_segment_id,
                query=query,
                subject=subject,
                predicate=predicate,
                object_text=object_text,
                limit=limit,
            )
        )

    def query_entities(
        self,
        workspace_id: str,
        *,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> tuple[EntityRecord, ...]:
        """Query extracted entities."""
        self.fact_store.initialize()
        return tuple(
            self.fact_store.query_entities(
                workspace_id,
                query=query,
                entity_type=entity_type,
                limit=limit,
            )
        )

    def _extract_document(self, document_id: str, *, workspace_id: str) -> FactExtractionDocumentResult:
        """Extract and persist facts for one document."""
        document = self.metadata_store.fetch_document(document_id)
        if document is None:
            return FactExtractionDocumentResult(
                document_id=document_id,
                status="skipped",
                facts_written=0,
                entities_written=0,
                reason="document_not_found",
            )

        segments = self.metadata_store.fetch_document_segments(document_id)
        if not segments:
            self.fact_store.replace_facts_for_document(workspace_id, document_id, facts=())
            return FactExtractionDocumentResult(
                document_id=document_id,
                status="skipped",
                facts_written=0,
                entities_written=0,
                reason="no_segments",
            )

        bundles = self.metadata_store.get_segment_bundles([segment.segment_id for segment in segments])
        facts: list[FactRecord] = []
        entities: dict[str, EntityRecord] = {}
        seen_fact_keys: set[tuple[str, str, str, str | None]] = set()
        extracted_at = _utc_now()

        for segment in segments:
            bundle = bundles.get(segment.segment_id)
            if bundle is None:
                continue
            for sentence in _split_sentences(segment.text):
                if not _looks_like_natural_language(sentence):
                    continue
                candidate_sentence = sentence.split(":", 1)[-1].strip() if ":" in sentence else sentence
                for pattern in FACT_PATTERNS:
                    match = pattern.regex.search(candidate_sentence)
                    if match is None:
                        continue
                    subject = pattern.subject_factory(match)
                    object_text = pattern.object_factory(match)
                    if not subject or not object_text:
                        continue
                    fact_key = (subject, pattern.predicate, object_text, segment.segment_id)
                    if fact_key in seen_fact_keys:
                        continue
                    seen_fact_keys.add(fact_key)
                    facts.append(
                        FactRecord(
                            fact_id=_stable_id(
                                "fact",
                                workspace_id,
                                document_id,
                                segment.segment_id,
                                pattern.name,
                                subject,
                                object_text,
                            ),
                            workspace_id=workspace_id,
                            document_id=document_id,
                            subject=subject,
                            predicate=pattern.predicate,
                            object=object_text,
                            confidence=pattern.confidence,
                            evidence_segment_id=segment.segment_id,
                            observed_at=bundle.document.observed_at,
                            created_at=extracted_at,
                            metadata={
                                "pattern_name": pattern.name,
                                "sentence": candidate_sentence,
                                "document_id": document_id,
                                "source_uri": bundle.source.uri,
                                "document_title": bundle.document.title,
                                "wing": bundle.document.metadata.get("wing") or bundle.segment.metadata.get("wing"),
                                "room": bundle.document.metadata.get("room") or bundle.segment.metadata.get("room"),
                            },
                        )
                    )
                    for entity_name in (subject, object_text):
                        if not _should_materialize_entity(entity_name):
                            continue
                        normalized_entity = _normalize_entity_name(entity_name)
                        entity_id = _stable_id("ent", workspace_id, normalized_entity.lower())
                        entities.setdefault(
                            entity_id,
                            EntityRecord(
                                entity_id=entity_id,
                                workspace_id=workspace_id,
                                name=normalized_entity,
                                entity_type="concept",
                                created_at=extracted_at,
                                metadata={
                                    "document_id": document_id,
                                    "source_uri": bundle.source.uri,
                                },
                            ),
                        )

        entities_written = self.fact_store.upsert_entities(tuple(entities.values()))
        facts_written = self.fact_store.replace_facts_for_document(workspace_id, document_id, facts=tuple(facts))
        status = "extracted" if facts_written else "no_facts"
        return FactExtractionDocumentResult(
            document_id=document_id,
            status=status,
            facts_written=facts_written,
            entities_written=entities_written,
            reason=None if facts_written else "no_matching_patterns",
        )
