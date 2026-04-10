"""
dialect.py — AAAK Structured Symbolic Summary Format (Compat Namespace)
======================================================================

Thin re-export wrapper for the actual implementation in _legacy_dialect.
"""

from mempalace.compat._legacy_dialect import Dialect

__all__ = ["Dialect"]
