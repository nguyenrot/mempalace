"""Conversation ingestion services for transcript and chat export files."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mempalace.application.ports import EmbeddingProvider, MetadataStore, VectorIndex
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


def normalize(path: str) -> str:
    """Read and normalize a file's text content (replaces legacy normalize module)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    # Basic whitespace normalization
    lines = text.splitlines()
    normalized = "\n".join(line.rstrip() for line in lines)
    return normalized.strip() + "\n" if normalized.strip() else ""


def extract_memories(content: str) -> list[dict]:
    """Extract classified memory chunks from text (replaces legacy general_extractor)."""
    paragraphs = re.split(r"\n{2,}", content.strip())
    memories = []
    for para in paragraphs:
        text = para.strip()
        if len(text) < 20:
            continue
        memories.append({
            "content": text,
            "memory_type": detect_conversation_room(text),
        })
    return memories


CONVERSATION_SKIP_DIRECTORIES = {"tool-results", "memory"}
TOPIC_KEYWORDS = {
    "technical": [
        "code",
        "python",
        "function",
        "bug",
        "error",
        "api",
        "database",
        "server",
        "deploy",
        "git",
        "test",
        "debug",
        "refactor",
    ],
    "architecture": [
        "architecture",
        "design",
        "pattern",
        "structure",
        "schema",
        "interface",
        "module",
        "component",
        "service",
        "layer",
    ],
    "planning": [
        "plan",
        "roadmap",
        "milestone",
        "deadline",
        "priority",
        "sprint",
        "backlog",
        "scope",
        "requirement",
        "spec",
    ],
    "decisions": [
        "decided",
        "chose",
        "picked",
        "switched",
        "migrated",
        "replaced",
        "trade-off",
        "alternative",
        "option",
        "approach",
    ],
    "problems": [
        "problem",
        "issue",
        "broken",
        "failed",
        "crash",
        "stuck",
        "workaround",
        "fix",
        "solved",
        "resolved",
    ],
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _token_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _extract_conversation_metadata(file_path: Path) -> dict[str, str]:
    """Best-effort extraction of stable conversation metadata without using an LLM."""
    metadata: dict[str, str] = {}
    suffix = file_path.suffix.lower()

    try:
        raw_content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw_content = ""

    stripped = raw_content.strip()
    if not stripped:
        return metadata

    if sum(1 for line in stripped.splitlines() if line.strip().startswith(">")) >= 3:
        metadata["source_format"] = "transcript_text"
        return metadata

    if suffix == ".jsonl":
        metadata["source_format"] = "jsonl"
        for line in stripped.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            payload_type = payload.get("type")
            if payload_type == "session_meta":
                session_id = payload.get("session_id")
                if isinstance(session_id, str) and session_id.strip():
                    metadata["session_id"] = session_id.strip()
                metadata["source_format"] = "codex_jsonl"
            elif payload_type == "event_msg":
                metadata["source_format"] = "codex_jsonl"
            elif payload_type in {"human", "assistant", "user"}:
                metadata["source_format"] = "claude_code_jsonl"
        return metadata

    if suffix == ".json" or stripped[:1] in {"{", "["}:
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return metadata

        if isinstance(payload, dict) and isinstance(payload.get("mapping"), dict):
            metadata["source_format"] = "chatgpt_export"
            conversation_id = payload.get("conversation_id") or payload.get("id")
            if isinstance(conversation_id, str) and conversation_id.strip():
                metadata["session_id"] = conversation_id.strip()
            return metadata

        if isinstance(payload, dict) and (
            isinstance(payload.get("messages"), list) or isinstance(payload.get("chat_messages"), list)
        ):
            metadata["source_format"] = "claude_export"
            conversation_id = payload.get("uuid") or payload.get("id")
            if isinstance(conversation_id, str) and conversation_id.strip():
                metadata["session_id"] = conversation_id.strip()
            return metadata

        if isinstance(payload, list) and payload:
            first_item = payload[0]
            if isinstance(first_item, dict) and first_item.get("type") == "message":
                metadata["source_format"] = "slack_export"
                return metadata
            if isinstance(first_item, dict) and "chat_messages" in first_item:
                metadata["source_format"] = "claude_export"
                conversation_id = first_item.get("uuid") or first_item.get("id")
                if isinstance(conversation_id, str) and conversation_id.strip():
                    metadata["session_id"] = conversation_id.strip()
                return metadata

    metadata["source_format"] = "plain_text"
    return metadata


@dataclass(slots=True, frozen=True)
class ConversationChunk:
    """Normalized conversation chunk with offsets and classification."""

    text: str
    start_offset: int
    end_offset: int
    chunk_index: int
    room: str


def detect_conversation_room(content: str) -> str:
    """Classify conversation content into a coarse room label."""
    lowered = content[:3000].lower()
    scores: dict[str, int] = {}
    for room, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > 0:
            scores[room] = score
    return max(scores, key=scores.get) if scores else "general"


def chunk_conversation_exchange(content: str, min_chunk_size: int = 30) -> list[ConversationChunk]:
    """Chunk a normalized transcript into exchange-pair segments."""
    lines = content.splitlines(keepends=True)
    quote_lines = sum(1 for line in lines if line.strip().startswith(">"))
    if quote_lines >= 3:
        chunks = _chunk_by_exchange(lines, min_chunk_size=min_chunk_size)
        if chunks:
            return chunks
    return _chunk_by_paragraph(content, min_chunk_size=min_chunk_size)


def chunk_conversation_general(content: str, min_chunk_size: int = 20) -> list[ConversationChunk]:
    """Extract classified memories from a normalized transcript."""
    extracted = extract_memories(content)
    chunks: list[ConversationChunk] = []
    cursor = 0
    for item in extracted:
        chunk_text = item["content"].strip()
        if len(chunk_text) < min_chunk_size:
            continue
        position = content.find(chunk_text, cursor)
        if position == -1:
            position = content.find(chunk_text)
        if position == -1:
            continue
        end_position = position + len(chunk_text)
        cursor = end_position
        chunks.append(
            ConversationChunk(
                text=chunk_text,
                start_offset=position,
                end_offset=end_position,
                chunk_index=len(chunks),
                room=item.get("memory_type", "general"),
            )
        )
    return chunks


def _chunk_by_exchange(lines: list[str], min_chunk_size: int) -> list[ConversationChunk]:
    chunks: list[ConversationChunk] = []
    offset = 0
    line_ranges = []
    for line in lines:
        start = offset
        offset += len(line)
        line_ranges.append((line, start, offset))

    index = 0
    while index < len(line_ranges):
        line, start_offset, _ = line_ranges[index]
        if not line.strip().startswith(">"):
            index += 1
            continue

        user_turn = line.strip()
        included_ai_lines: list[str] = []
        end_offset = start_offset + len(line)
        index += 1

        while index < len(line_ranges):
            next_line, next_start, next_end = line_ranges[index]
            stripped = next_line.strip()
            if stripped.startswith(">") or stripped.startswith("---"):
                break
            if stripped:
                if len(included_ai_lines) < 8:
                    included_ai_lines.append(stripped)
                    end_offset = next_end
            index += 1

        chunk_text = f"{user_turn}\n{' '.join(included_ai_lines)}".strip()
        if len(chunk_text) > min_chunk_size:
            chunks.append(
                ConversationChunk(
                    text=chunk_text,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    chunk_index=len(chunks),
                    room=detect_conversation_room(chunk_text),
                )
            )
    return chunks


def _chunk_by_paragraph(content: str, min_chunk_size: int) -> list[ConversationChunk]:
    chunks: list[ConversationChunk] = []
    paragraph_matches = list(re.finditer(r"(?:^|\n\n)(.+?)(?=\n\n|\Z)", content, flags=re.S))
    if len(paragraph_matches) <= 1 and content.count("\n") > 20:
        lines = content.splitlines(keepends=True)
        offset = 0
        line_offsets = []
        for line in lines:
            start = offset
            offset += len(line)
            line_offsets.append((line, start, offset))
        for index in range(0, len(line_offsets), 25):
            block = line_offsets[index : index + 25]
            if not block:
                continue
            start_offset = block[0][1]
            end_offset = block[-1][2]
            text = content[start_offset:end_offset].strip()
            if len(text) > min_chunk_size:
                chunks.append(
                    ConversationChunk(
                        text=text,
                        start_offset=content.find(text, start_offset),
                        end_offset=content.find(text, start_offset) + len(text),
                        chunk_index=len(chunks),
                        room=detect_conversation_room(text),
                    )
                )
        return chunks

    for match in paragraph_matches:
        text = match.group(1).strip()
        if len(text) <= min_chunk_size:
            continue
        start_offset = content.find(text, match.start())
        end_offset = start_offset + len(text)
        chunks.append(
            ConversationChunk(
                text=text,
                start_offset=start_offset,
                end_offset=end_offset,
                chunk_index=len(chunks),
                room=detect_conversation_room(text),
            )
        )
    return chunks


@dataclass(slots=True)
class ConversationDirectoryIngestionService:
    """Ingest conversation exports into the new metadata/vector runtime."""

    settings: MemorySettings
    metadata_store: MetadataStore
    vector_index: VectorIndex
    embedding_provider: EmbeddingProvider
    logger: logging.Logger

    def ingest_directory(
        self,
        directory: str | Path,
        workspace_id: str | None = None,
        extract_mode: str = "exchange",
    ) -> IngestionResult:
        """Ingest one directory of conversation files."""
        started_at = _utc_now()
        resolved_directory = Path(directory).expanduser().resolve()
        resolved_workspace_id = workspace_id or self.settings.workspace_id
        run_id = _stable_id(
            "ingest_convo",
            resolved_workspace_id,
            resolved_directory.as_posix(),
            extract_mode,
            started_at.isoformat(),
        )

        self.metadata_store.initialize()
        self.vector_index.initialize()
        self.metadata_store.create_ingestion_run(
            IngestionRun(
                run_id=run_id,
                workspace_id=resolved_workspace_id,
                source_type="conversation_files",
                started_at=started_at,
                finished_at=None,
                status="running",
                metadata={
                    "directory": resolved_directory.as_posix(),
                    "extract_mode": extract_mode,
                },
            )
        )
        self.metadata_store.upsert_workspace(
            WorkspaceRecord(
                workspace_id=resolved_workspace_id,
                name=resolved_directory.name or resolved_workspace_id,
                root_path=resolved_directory.as_posix(),
                created_at=started_at,
                updated_at=started_at,
                metadata={"source_type": "conversation_files"},
            )
        )

        log_event(
            self.logger,
            logging.INFO,
            "conversation_ingest_started",
            workspace_id=resolved_workspace_id,
            run_id=run_id,
            directory=resolved_directory.as_posix(),
            extract_mode=extract_mode,
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
            for file_path in self._iter_files(resolved_directory):
                files_seen += 1
                outcome = self._ingest_file(
                    file_path=file_path,
                    workspace_id=resolved_workspace_id,
                    ingested_at=started_at,
                    extract_mode=extract_mode,
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
                "conversation_ingest_completed",
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
            source_type="conversation_files",
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
        extract_mode: str = "exchange",
    ) -> IngestionResult:
        """Ingest one explicit conversation file."""
        started_at = _utc_now()
        resolved_path = Path(path).expanduser().resolve()
        resolved_workspace_id = workspace_id or self.settings.workspace_id
        run_id = _stable_id(
            "ingest_convo_file",
            resolved_workspace_id,
            resolved_path.as_posix(),
            extract_mode,
            started_at.isoformat(),
        )

        self.metadata_store.initialize()
        self.vector_index.initialize()
        self.metadata_store.create_ingestion_run(
            IngestionRun(
                run_id=run_id,
                workspace_id=resolved_workspace_id,
                source_type="conversation_files",
                started_at=started_at,
                finished_at=None,
                status="running",
                metadata={
                    "path": resolved_path.as_posix(),
                    "extract_mode": extract_mode,
                },
            )
        )
        self.metadata_store.upsert_workspace(
            WorkspaceRecord(
                workspace_id=resolved_workspace_id,
                name=resolved_path.parent.name or resolved_workspace_id,
                root_path=resolved_path.parent.as_posix(),
                created_at=started_at,
                updated_at=started_at,
                metadata={"source_type": "conversation_files"},
            )
        )

        outcome = self._ingest_file(
            file_path=resolved_path,
            workspace_id=resolved_workspace_id,
            ingested_at=started_at,
            extract_mode=extract_mode,
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
            source_type="conversation_files",
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

    def _iter_files(self, root: Path) -> list[Path]:
        """Yield conversation-like files while skipping configured directories."""
        allowed_extensions = {ext.lower() for ext in self.settings.ingestion.conversation_extensions}
        skip_directories = set(self.settings.ingestion.skip_directories) | CONVERSATION_SKIP_DIRECTORIES
        discovered: list[Path] = []
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            if any(part in skip_directories for part in path.parts):
                continue
            if path.name.endswith(".meta.json"):
                continue
            if path.suffix.lower() not in allowed_extensions:
                continue
            discovered.append(path)
        return sorted(discovered)

    def _ingest_file(
        self,
        file_path: Path,
        workspace_id: str,
        ingested_at: datetime,
        extract_mode: str,
    ) -> dict[str, object]:
        """Normalize, chunk, and persist one conversation file."""
        uri = file_path.as_posix()
        try:
            normalized_content = normalize(uri)
        except (OSError, ValueError) as exc:
            message = f"{uri}: {exc}"
            log_event(
                self.logger,
                logging.WARNING,
                "conversation_ingest_file_failed",
                workspace_id=workspace_id,
                uri=uri,
                error=str(exc),
            )
            return {
                "files_read": 0,
                "documents_written": 0,
                "documents_updated": 0,
                "documents_skipped": 0,
                "segments_written": 0,
                "errors": [message],
                "file_result": IngestionFileResult(
                    uri=uri,
                    status="error",
                    checksum=None,
                    document_id=None,
                    segments_written=0,
                    reason=str(exc),
                ),
            }

        normalized_text = normalized_content.strip()
        checksum = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
        conversation_metadata = _extract_conversation_metadata(file_path)
        if not normalized_text:
            return {
                "files_read": 1,
                "documents_written": 0,
                "documents_updated": 0,
                "documents_skipped": 1,
                "segments_written": 0,
                "errors": [],
                "file_result": IngestionFileResult(
                    uri=uri,
                    status="skipped",
                    checksum=checksum,
                    document_id=None,
                    segments_written=0,
                    reason="empty",
                ),
            }

        existing_document = self.metadata_store.get_document_by_uri(workspace_id, uri)
        if existing_document and existing_document.checksum == checksum:
            return {
                "files_read": 1,
                "documents_written": 0,
                "documents_updated": 0,
                "documents_skipped": 1,
                "segments_written": 0,
                "errors": [],
                "file_result": IngestionFileResult(
                    uri=uri,
                    status="skipped",
                    checksum=checksum,
                    document_id=existing_document.document_id,
                    segments_written=0,
                    reason="unchanged",
                ),
            }

        if extract_mode == "general":
            chunks = chunk_conversation_general(normalized_content)
        else:
            chunks = chunk_conversation_exchange(normalized_content)

        if not chunks:
            return {
                "files_read": 1,
                "documents_written": 0,
                "documents_updated": 0,
                "documents_skipped": 1,
                "segments_written": 0,
                "errors": [],
                "file_result": IngestionFileResult(
                    uri=uri,
                    status="skipped",
                    checksum=checksum,
                    document_id=existing_document.document_id if existing_document else None,
                    segments_written=0,
                    reason="no_chunks",
                ),
            }

        observed_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
        source_id = _stable_id("src", workspace_id, uri)
        document_id = _stable_id("doc", workspace_id, uri)
        existing_source = self.metadata_store.get_source_by_uri(workspace_id, uri)

        source = SourceRecord(
            source_id=source_id,
            workspace_id=workspace_id,
            source_type="conversation_file",
            uri=uri,
            checksum=checksum,
            first_seen_at=existing_source.first_seen_at if existing_source else ingested_at,
            last_seen_at=ingested_at,
            metadata={"path": uri, **conversation_metadata},
        )
        document = DocumentRecord(
            document_id=document_id,
            workspace_id=workspace_id,
            source_id=source_id,
            title=file_path.name,
            uri=uri,
            document_type="conversation_transcript",
            checksum=checksum,
            raw_text=normalized_content,
            created_at=existing_document.created_at if existing_document else ingested_at,
            updated_at=ingested_at,
            observed_at=observed_at,
            metadata={
                "extension": file_path.suffix.lower(),
                "ingest_mode": "convos",
                "extract_mode": extract_mode,
                **conversation_metadata,
            },
        )
        segments = [
            SegmentRecord(
                segment_id=_stable_id("seg", document_id, str(chunk.chunk_index), chunk.text),
                workspace_id=workspace_id,
                document_id=document_id,
                segment_index=chunk.chunk_index,
                text=chunk.text,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                token_count=_token_count(chunk.text),
                checksum=hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
                created_at=ingested_at,
                metadata={
                    "room": chunk.room,
                    "ingest_mode": "convos",
                    "extract_mode": extract_mode,
                    **conversation_metadata,
                },
            )
            for chunk in chunks
        ]
        embeddings = self.embedding_provider.embed_texts([segment.text for segment in segments])

        self.metadata_store.upsert_source(source)
        self.metadata_store.upsert_document(document)
        self.metadata_store.replace_segments(workspace_id=workspace_id, document_id=document_id, segments=segments)
        self.vector_index.delete_document_segments(document_id)
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
            "conversation_ingest_file_completed",
            workspace_id=workspace_id,
            uri=uri,
            document_id=document_id,
            segments_written=len(segments),
            status=status,
            extract_mode=extract_mode,
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
