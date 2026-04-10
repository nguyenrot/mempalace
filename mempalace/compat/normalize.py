"""
normalize.py — Chat export normalizer (Compat Namespace)
========================================================

Thin re-export wrapper for the actual implementation in _legacy_normalize.
"""

from mempalace.compat._legacy_normalize import normalize

__all__ = ["normalize"]
