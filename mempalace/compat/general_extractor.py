"""
general_extractor.py — Extract 5 types of memories (Compat Namespace)
=====================================================================

Thin re-export wrapper for the actual implementation in _legacy_general_extractor.
"""

from mempalace.compat._legacy_general_extractor import (
    DECISION_MARKERS,
    PREFERENCE_MARKERS,
    MILESTONE_MARKERS,
    PROBLEM_MARKERS,
    EMOTION_MARKERS,
    extract_memories,
)

__all__ = [
    "DECISION_MARKERS",
    "PREFERENCE_MARKERS",
    "MILESTONE_MARKERS",
    "PROBLEM_MARKERS",
    "EMOTION_MARKERS",
    "extract_memories",
]
