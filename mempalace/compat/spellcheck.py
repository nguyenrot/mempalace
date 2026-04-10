"""
spellcheck.py — Spell-correct user messages (Compat Namespace)
=============================================================

Thin re-export wrapper for the actual implementation in _legacy_spellcheck.
"""

from mempalace.compat._legacy_spellcheck import spellcheck_user_text

__all__ = ["spellcheck_user_text"]
