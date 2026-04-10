"""
layers.py — 4-Layer Memory Stack (Compat Namespace)
=================================================

Thin re-export wrapper for the actual implementation in _legacy_layers.
"""

from mempalace.compat._legacy_layers import (
    Layer0,
    Layer1,
    Layer2,
    Layer3,
    MemoryStack,
)

__all__ = ["Layer0", "Layer1", "Layer2", "Layer3", "MemoryStack"]
