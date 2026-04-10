"""
entity_detector.py — Auto-detect people and projects (Compat Namespace)
======================================================================

Thin re-export wrapper for the actual implementation in _legacy_entity_detector.
"""

from mempalace.compat._legacy_entity_detector import (
    PERSON_VERB_PATTERNS,
    PRONOUN_PATTERNS,
    DIALOGUE_PATTERNS,
    PROJECT_VERB_PATTERNS,
    detect_entities,
    scan_for_detection,
    confirm_entities,
)

__all__ = [
    "PERSON_VERB_PATTERNS",
    "PRONOUN_PATTERNS",
    "DIALOGUE_PATTERNS",
    "PROJECT_VERB_PATTERNS",
    "detect_entities",
    "scan_for_detection",
    "confirm_entities",
]
