"""
split_mega_files.py — Split concatenated transcript files (Compat Namespace)
============================================================================

Thin re-export wrapper for the actual implementation in _legacy_split_mega_files.
"""

from mempalace.compat._legacy_split_mega_files import main

__all__ = ["main"]
