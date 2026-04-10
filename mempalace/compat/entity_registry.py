"""
entity_registry.py — Persistent personal entity registry (Compat Namespace)
=========================================================================

Thin re-export wrapper for the actual implementation in _legacy_entity_registry.
"""

from mempalace.compat._legacy_entity_registry import (
    COMMON_ENGLISH_WORDS,
    EntityRegistry,
)

__all__ = ["COMMON_ENGLISH_WORDS", "EntityRegistry"]
