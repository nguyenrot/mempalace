"""Tests for service-runtime filesystem scanning and .gitignore handling."""

from __future__ import annotations

from pathlib import Path

from mempalace.application.filesystem_scan import scan_files


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _scan(project_root: Path, **kwargs) -> list[str]:
    files = scan_files(
        project_root,
        include_extensions={".py", ".md", ".json"},
        skip_directories={".git", ".pytest_cache"},
        skip_filenames={".gitignore"},
        **kwargs,
    )
    return sorted(path.relative_to(project_root).as_posix() for path in files)


def test_scan_files_respects_gitignore(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "ignored.py\ndocs/\n")
    _write(tmp_path / "src" / "app.py", "print('hello')\n")
    _write(tmp_path / "ignored.py", "print('skip')\n")
    _write(tmp_path / "docs" / "guide.md", "# Guide\n")

    assert _scan(tmp_path, respect_gitignore=True, include_ignored=None) == ["src/app.py"]


def test_scan_files_can_include_ignored_paths(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "docs/\n")
    _write(tmp_path / "docs" / "guide.md", "# Guide\n")

    assert _scan(tmp_path, respect_gitignore=True, include_ignored=["docs"]) == ["docs/guide.md"]


def test_scan_files_can_disable_gitignore(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "docs/\n")
    _write(tmp_path / "docs" / "guide.md", "# Guide\n")

    assert _scan(tmp_path, respect_gitignore=False, include_ignored=None) == ["docs/guide.md"]
