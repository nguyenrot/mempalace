"""Unit tests for deterministic text segmentation."""

from __future__ import annotations

from mempalace.application.segmentation import TextSegmenter


def test_text_segmenter_preserves_offsets() -> None:
    text = (
        "First paragraph about authentication and retrieval.\n\n"
        "Second paragraph explains how provenance should include document IDs.\n\n"
        "Third paragraph closes with rollout notes and observability requirements."
    )
    segmenter = TextSegmenter(max_chars=90, overlap_chars=15, min_chars=20)

    segments = segmenter.segment_document("workspace", "doc_123", text)

    assert len(segments) >= 2
    for segment in segments:
        assert text[segment.start_offset : segment.end_offset] == segment.text
        assert segment.token_count > 0
