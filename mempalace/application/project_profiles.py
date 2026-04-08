"""Project-local runtime configuration helpers for the service-backed CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml


LOCAL_CONFIG_DIRNAME = ".mempalace"
LOCAL_CONFIG_FILENAME = "config.yaml"
LOCAL_GITIGNORE_FILENAME = ".gitignore"
LOCAL_RUNTIME_DIRNAME = "runtime"
POPULAR_DEVELOPER_EXTENSIONS = [
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".sql",
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".java",
    ".kt",
    ".kts",
    ".swift",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".scala",
    ".sc",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".nu",
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    ".hh",
    ".m",
    ".mm",
    ".cs",
    ".dart",
    ".lua",
    ".proto",
    ".graphql",
    ".gql",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".html",
    ".htm",
    ".xml",
    ".plist",
    ".pbxproj",
    ".entitlements",
    ".gradle",
    ".properties",
    ".dockerignore",
    ".gitignore",
]
POPULAR_DEVELOPER_FILENAMES = [
    "Dockerfile",
    "Containerfile",
    "Makefile",
    "GNUmakefile",
    "Justfile",
    "Procfile",
    "Podfile",
    "Podfile.lock",
    "Gemfile",
    "Gemfile.lock",
    "Brewfile",
    "Rakefile",
    "Fastfile",
    "Package.swift",
    ".env.example",
    ".env.sample",
    ".env.local.example",
    ".envrc",
]

LOCAL_MEMPALACE_GITIGNORE = "\n".join(
    [
        "*",
        "!config.yaml",
        "!.gitignore",
        "",
    ]
)


@dataclass(slots=True)
class ProjectInitResult:
    """Result for project-local runtime initialization."""

    workspace_id: str
    project_dir: str
    local_config_path: str
    storage_dir: str
    metadata_path: str
    gitignore_path: str
    created: bool
    updated: bool


def local_project_dir(project_dir: str | Path) -> Path:
    """Return the local MemPalace directory stored under a project root."""
    return Path(project_dir).expanduser().resolve() / LOCAL_CONFIG_DIRNAME


def local_project_config_path(project_dir: str | Path) -> Path:
    """Return the local config path stored under a project root."""
    return local_project_dir(project_dir) / LOCAL_CONFIG_FILENAME


def local_project_gitignore_path(project_dir: str | Path) -> Path:
    """Return the local MemPalace gitignore path stored under a project root."""
    return local_project_dir(project_dir) / LOCAL_GITIGNORE_FILENAME


def find_nearest_project_config(start: str | Path | None = None) -> Path | None:
    """Search upward from the given path for a local project runtime config."""
    current = Path(start or Path.cwd()).expanduser().resolve()
    candidates = [current]
    candidates.extend(current.parents)
    for directory in candidates:
        candidate = directory / LOCAL_CONFIG_DIRNAME / LOCAL_CONFIG_FILENAME
        if candidate.exists():
            return candidate
    return None


def slugify_workspace_id(value: str) -> str:
    """Convert a project name into a stable workspace identifier."""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "workspace"


def _local_storage_dir(project_dir: Path) -> Path:
    return local_project_dir(project_dir) / LOCAL_RUNTIME_DIRNAME


def _build_config_payload(project_dir: Path, workspace_id: str) -> dict[str, Any]:
    storage_dir = _local_storage_dir(project_dir)
    return {
        "workspace_id": workspace_id,
        "storage": {
            "base_dir": str(storage_dir),
            "metadata_path": str(storage_dir / "metadata.sqlite3"),
            "vector_backend": "sqlite",
        },
        "ingestion": {
            "include_extensions": list(POPULAR_DEVELOPER_EXTENSIONS),
            "include_filenames": list(POPULAR_DEVELOPER_FILENAMES),
        },
        "logging": {
            "level": "INFO",
            "json": True,
        },
    }


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _write_yaml_mapping(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)


def _write_local_gitignore(project_dir: Path) -> Path:
    path = local_project_gitignore_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LOCAL_MEMPALACE_GITIGNORE, encoding="utf-8")
    return path


def initialize_project_runtime(
    project_dir: str | Path,
    *,
    workspace_id: str | None = None,
    force: bool = False,
) -> ProjectInitResult:
    """Create or refresh a project-local runtime config directory."""
    project_path = Path(project_dir).expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise FileNotFoundError(f"Project directory not found: {project_path}")

    config_path = local_project_config_path(project_path)
    created = False
    updated = False

    if config_path.exists() and not force:
        payload = _load_yaml_mapping(config_path)
        resolved_workspace_id = str(payload.get("workspace_id", workspace_id or project_path.name))
    else:
        resolved_workspace_id = slugify_workspace_id(workspace_id or project_path.name)
        payload = _build_config_payload(project_path, resolved_workspace_id)
        created = not config_path.exists()
        updated = config_path.exists()
        _write_yaml_mapping(config_path, payload)

    gitignore_path = _write_local_gitignore(project_path)
    storage = payload.get("storage", {})
    return ProjectInitResult(
        workspace_id=slugify_workspace_id(resolved_workspace_id),
        project_dir=str(project_path),
        local_config_path=str(config_path),
        storage_dir=str(storage.get("base_dir", _local_storage_dir(project_path))),
        metadata_path=str(storage.get("metadata_path", _local_storage_dir(project_path) / "metadata.sqlite3")),
        gitignore_path=str(gitignore_path),
        created=created,
        updated=updated,
    )
