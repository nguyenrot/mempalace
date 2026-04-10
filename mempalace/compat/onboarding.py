"""
onboarding.py — First-run setup (Compat Namespace)
================================================

Thin re-export wrapper for the actual implementation in _legacy_onboarding.
"""

from mempalace.compat._legacy_onboarding import (
    DEFAULT_WINGS,
    EntityRegistry,
    detect_entities,
    scan_for_detection,
    quick_setup,
    run_onboarding,
)

__all__ = [
    "DEFAULT_WINGS",
    "EntityRegistry",
    "detect_entities",
    "scan_for_detection",
    "quick_setup",
    "run_onboarding",
]
