"""
config.py — Legacy Config (Compat Namespace)
============================================

Thin re-export wrapper: imports the actual implementation from compat level,
then re-exports it at the old `mempalace.config` path for backward compat.

All the actual logic lives in `mempalace.compat._legacy_config`.
"""

# Re-export from the compat-namespaced version so that code importing
# `from mempalace.config import MempalaceConfig` continues to work.
from mempalace.compat._legacy_config import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_HALL_KEYWORDS,
    DEFAULT_PALACE_PATH,
    DEFAULT_TOPIC_WINGS,
    MempalaceConfig,
)

__all__ = [
    "DEFAULT_COLLECTION_NAME",
    "DEFAULT_HALL_KEYWORDS",
    "DEFAULT_PALACE_PATH",
    "DEFAULT_TOPIC_WINGS",
    "MempalaceConfig",
]
