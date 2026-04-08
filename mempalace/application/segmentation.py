"""Deterministic text segmentation with stable offsets."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from mempalace.domain.models import SegmentRecord


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _stable_segment_id(document_id: str, segment_index: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"seg_{document_id}_{segment_index:04d}_{digest}"


@dataclass(slots=True)
class TextSegmenter:
    """Split text into overlapping segments while preserving verbatim offsets."""

    max_chars: int = 900
    overlap_chars: int = 120
    min_chars: int = 80

    def segment_document(self, workspace_id: str, document_id: str, text: str) -> list[SegmentRecord]:
        """Return segment records for a document."""
        if not text.strip():
            return []

        created_at = _utc_now()
        segments: list[SegmentRecord] = []
        cursor = 0
        segment_index = 0
        text_length = len(text)

        while cursor < text_length:
            window_end = min(cursor + self.max_chars, text_length)
            candidate_end = self._find_break(text, cursor, window_end)
            if candidate_end <= cursor:
                candidate_end = window_end

            raw_chunk = text[cursor:candidate_end]
            if not raw_chunk:
                break

            leading_ws = len(raw_chunk) - len(raw_chunk.lstrip())
            trailing_ws = len(raw_chunk) - len(raw_chunk.rstrip())
            start_offset = cursor + leading_ws
            end_offset = candidate_end - trailing_ws
            chunk_text = text[start_offset:end_offset]

            if len(chunk_text) >= self.min_chars:
                segments.append(
                    SegmentRecord(
                        segment_id=_stable_segment_id(document_id, segment_index, chunk_text),
                        workspace_id=workspace_id,
                        document_id=document_id,
                        segment_index=segment_index,
                        text=chunk_text,
                        start_offset=start_offset,
                        end_offset=end_offset,
                        token_count=_token_count(chunk_text),
                        checksum=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                        created_at=created_at,
                    )
                )
                segment_index += 1

            if candidate_end >= text_length:
                break

            next_cursor = max(end_offset - self.overlap_chars, cursor + 1)
            cursor = min(next_cursor, text_length)

        if not segments:
            whole_text = text.strip()
            start_offset = text.find(whole_text)
            end_offset = start_offset + len(whole_text)
            segments.append(
                SegmentRecord(
                    segment_id=_stable_segment_id(document_id, 0, whole_text),
                    workspace_id=workspace_id,
                    document_id=document_id,
                    segment_index=0,
                    text=whole_text,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    token_count=_token_count(whole_text),
                    checksum=hashlib.sha256(whole_text.encode("utf-8")).hexdigest(),
                    created_at=created_at,
                )
            )

        return segments

    def _find_break(self, text: str, start: int, window_end: int) -> int:
        """Choose a deterministic break point near the end of a window."""
        if window_end >= len(text):
            return window_end

        lower_bound = min(start + self.min_chars, window_end)
        break_markers: Iterable[str] = ("\n\n", "\n", ". ", "; ", " ")
        for marker in break_markers:
            position = text.rfind(marker, lower_bound, window_end)
            if position != -1:
                return position + len(marker)
        return window_end
