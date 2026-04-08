"""Unit tests for project-local runtime profile helpers."""

from __future__ import annotations

from pathlib import Path

import yaml

from mempalace.application.project_profiles import (
    find_nearest_project_config,
    initialize_project_runtime,
    local_project_config_path,
    local_project_gitignore_path,
)


def test_initialize_project_runtime_creates_local_config_and_gitignore(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = initialize_project_runtime(project_dir)

    assert result.workspace_id == "project"
    assert Path(result.local_config_path) == local_project_config_path(project_dir)
    assert Path(result.gitignore_path) == local_project_gitignore_path(project_dir)
    assert Path(result.local_config_path).exists()
    assert Path(result.gitignore_path).exists()
    payload = yaml.safe_load(Path(result.local_config_path).read_text(encoding="utf-8"))
    assert payload["workspace_id"] == "project"
    assert payload["storage"]["metadata_path"].endswith(".mempalace/runtime/metadata.sqlite3")


def test_find_nearest_project_config_searches_parents(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    nested_dir = project_dir / "src" / "feature"
    nested_dir.mkdir(parents=True)
    initialize_project_runtime(project_dir, workspace_id="workspace_demo")

    discovered = find_nearest_project_config(nested_dir)

    assert discovered == local_project_config_path(project_dir)
