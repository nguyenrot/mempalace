"""
miner.py — ChromaDB-backed file miner (Compat Namespace)
========================================================

Thin re-export wrapper for the actual implementation in _legacy_miner.
"""

from mempalace.compat._legacy_miner import (
    GitignoreMatcher,
    chunk_text,
    detect_room,
    file_already_mined,
    get_collection,
    is_exact_force_include,
    is_force_included,
    is_gitignored,
    load_config,
    load_gitignore_matcher,
    mine,
    normalize_include_paths,
    process_file,
    scan_project,
    should_skip_dir,
    status,
)

__all__ = [
    "GitignoreMatcher",
    "chunk_text",
    "detect_room",
    "file_already_mined",
    "get_collection",
    "is_exact_force_include",
    "is_force_included",
    "is_gitignored",
    "load_config",
    "load_gitignore_matcher",
    "mine",
    "normalize_include_paths",
    "process_file",
    "scan_project",
    "should_skip_dir",
    "status",
]
