"""Filesystem scanning with deterministic .gitignore handling."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class GitignoreMatcher:
    """Lightweight matcher for one directory's `.gitignore` rules."""

    base_dir: Path
    rules: list[dict[str, object]]

    @classmethod
    def from_dir(cls, dir_path: Path) -> "GitignoreMatcher | None":
        gitignore_path = dir_path / ".gitignore"
        if not gitignore_path.is_file():
            return None

        try:
            lines = gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None

        rules: list[dict[str, object]] = []
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("\\#") or line.startswith("\\!"):
                line = line[1:]
            elif line.startswith("#"):
                continue

            negated = line.startswith("!")
            if negated:
                line = line[1:]

            anchored = line.startswith("/")
            if anchored:
                line = line.lstrip("/")

            dir_only = line.endswith("/")
            if dir_only:
                line = line.rstrip("/")

            if not line:
                continue

            rules.append(
                {
                    "pattern": line,
                    "anchored": anchored,
                    "dir_only": dir_only,
                    "negated": negated,
                }
            )

        if not rules:
            return None
        return cls(base_dir=dir_path, rules=rules)

    def matches(self, path: Path, *, is_dir: bool | None = None) -> bool | None:
        """Return ignore decision for a path relative to this matcher, if any."""
        try:
            relative = path.relative_to(self.base_dir).as_posix().strip("/")
        except ValueError:
            return None

        if not relative:
            return None

        ignored: bool | None = None
        for rule in self.rules:
            if self._rule_matches(rule, relative=relative, is_dir=path.is_dir() if is_dir is None else is_dir):
                ignored = not bool(rule["negated"])
        return ignored

    def _rule_matches(self, rule: dict[str, object], *, relative: str, is_dir: bool) -> bool:
        pattern = str(rule["pattern"])
        parts = relative.split("/")
        pattern_parts = pattern.split("/")

        if bool(rule["dir_only"]):
            target_parts = parts if is_dir else parts[:-1]
            if not target_parts:
                return False
            if bool(rule["anchored"]) or len(pattern_parts) > 1:
                return self._match_from_root(target_parts, pattern_parts)
            return any(fnmatch.fnmatch(part, pattern) for part in target_parts)

        if bool(rule["anchored"]) or len(pattern_parts) > 1:
            return self._match_from_root(parts, pattern_parts)
        return any(fnmatch.fnmatch(part, pattern) for part in parts)

    def _match_from_root(self, target_parts: list[str], pattern_parts: list[str]) -> bool:
        def matches(path_index: int, pattern_index: int) -> bool:
            if pattern_index == len(pattern_parts):
                return True
            if path_index == len(target_parts):
                return all(part == "**" for part in pattern_parts[pattern_index:])

            pattern_part = pattern_parts[pattern_index]
            if pattern_part == "**":
                return matches(path_index, pattern_index + 1) or matches(path_index + 1, pattern_index)

            if not fnmatch.fnmatch(target_parts[path_index], pattern_part):
                return False
            return matches(path_index + 1, pattern_index + 1)

        return matches(0, 0)


def normalize_include_paths(include_ignored: Iterable[str] | None) -> set[str]:
    """Normalize include override paths into project-relative POSIX strings."""
    normalized: set[str] = set()
    for raw_path in include_ignored or ():
        candidate = str(raw_path).strip().strip("/")
        if candidate:
            normalized.add(Path(candidate).as_posix())
    return normalized


def is_force_included(path: Path, project_root: Path, include_paths: set[str]) -> bool:
    """Return true when a path or one of its ancestors/descendants is explicitly included."""
    if not include_paths:
        return False

    try:
        relative = path.relative_to(project_root).as_posix().strip("/")
    except ValueError:
        return False
    if not relative:
        return False

    for include_path in include_paths:
        if relative == include_path:
            return True
        if relative.startswith(f"{include_path}/"):
            return True
        if include_path.startswith(f"{relative}/"):
            return True
    return False


def is_exact_force_include(path: Path, project_root: Path, include_paths: set[str]) -> bool:
    """Return true when a file exactly matches an include override."""
    if not include_paths:
        return False
    try:
        relative = path.relative_to(project_root).as_posix().strip("/")
    except ValueError:
        return False
    return relative in include_paths


def _is_gitignored(path: Path, matchers: list[GitignoreMatcher], *, is_dir: bool) -> bool:
    ignored = False
    for matcher in matchers:
        decision = matcher.matches(path, is_dir=is_dir)
        if decision is not None:
            ignored = decision
    return ignored


def scan_files(
    project_root: str | Path,
    *,
    include_extensions: set[str],
    skip_directories: set[str],
    skip_filenames: set[str],
    respect_gitignore: bool = True,
    include_ignored: Iterable[str] | None = None,
) -> list[Path]:
    """Return readable files while respecting `.gitignore` and include overrides."""
    resolved_root = Path(project_root).expanduser().resolve()
    include_paths = normalize_include_paths(include_ignored)
    matcher_cache: dict[Path, GitignoreMatcher | None] = {}
    active_matchers: list[GitignoreMatcher] = []
    files: list[Path] = []

    for root, dirs, filenames in os.walk(resolved_root):
        root_path = Path(root)

        if respect_gitignore:
            active_matchers = [
                matcher
                for matcher in active_matchers
                if root_path == matcher.base_dir or matcher.base_dir in root_path.parents
            ]
            if root_path not in matcher_cache:
                matcher_cache[root_path] = GitignoreMatcher.from_dir(root_path)
            current_matcher = matcher_cache[root_path]
            if current_matcher is not None:
                active_matchers.append(current_matcher)

        dirs[:] = [
            dirname
            for dirname in dirs
            if is_force_included(root_path / dirname, resolved_root, include_paths)
            or dirname not in skip_directories
        ]
        if respect_gitignore and active_matchers:
            dirs[:] = [
                dirname
                for dirname in dirs
                if is_force_included(root_path / dirname, resolved_root, include_paths)
                or not _is_gitignored(root_path / dirname, active_matchers, is_dir=True)
            ]

        for filename in filenames:
            path = root_path / filename
            force_include = is_force_included(path, resolved_root, include_paths)
            exact_force_include = is_exact_force_include(path, resolved_root, include_paths)

            if not force_include and filename in skip_filenames:
                continue
            if path.suffix.lower() not in include_extensions and not exact_force_include:
                continue
            if respect_gitignore and active_matchers and not force_include:
                if _is_gitignored(path, active_matchers, is_dir=False):
                    continue
            files.append(path)

    return sorted(files)
