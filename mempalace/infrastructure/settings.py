"""Typed configuration models for the refactored memory core."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class StorageSettings:
    """Persistent storage settings."""

    base_dir: str = "~/.mempalace/runtime"
    metadata_path: str = "~/.mempalace/runtime/metadata.sqlite3"
    vector_backend: str = "sqlite"

    def resolved_base_dir(self) -> Path:
        """Return the expanded base directory."""
        return Path(self.base_dir).expanduser().resolve()

    def resolved_metadata_path(self) -> Path:
        """Return the expanded metadata database path."""
        return Path(self.metadata_path).expanduser().resolve()


@dataclass(slots=True)
class SegmenterSettings:
    """Document segmentation configuration."""

    max_chars: int = 900
    overlap_chars: int = 120
    min_chars: int = 80


@dataclass(slots=True)
class IngestionSettings:
    """Source discovery settings for the default filesystem importer."""

    include_extensions: list[str] = field(
        default_factory=lambda: [
            ".md",
            ".txt",
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".sql",
        ]
    )
    skip_directories: list[str] = field(
        default_factory=lambda: [
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "env",
            "dist",
            "build",
            ".next",
            "coverage",
            ".mempalace",
            ".ruff_cache",
            ".mypy_cache",
            ".pytest_cache",
            ".cache",
            ".tox",
            ".nox",
            ".idea",
            ".vscode",
            ".ipynb_checkpoints",
            ".eggs",
            "htmlcov",
            "target",
        ]
    )
    skip_filenames: list[str] = field(
        default_factory=lambda: [
            ".gitignore",
            "package-lock.json",
        ]
    )
    include_filenames: list[str] = field(
        default_factory=lambda: [
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
    )
    conversation_extensions: list[str] = field(
        default_factory=lambda: [
            ".txt",
            ".md",
            ".json",
            ".jsonl",
        ]
    )
    project_manifest_filenames: list[str] = field(
        default_factory=lambda: [
            "mempalace.yaml",
            "mempalace.yml",
            "mempal.yaml",
            "mempal.yml",
        ]
    )
    default_room_name: str = "general"


@dataclass(slots=True)
class RetrievalSettings:
    """Retrieval weighting and defaults."""

    default_limit: int = 5
    keyword_weight: float = 0.6
    semantic_weight: float = 0.4


@dataclass(slots=True)
class LoggingSettings:
    """Structured logging configuration."""

    level: str = "INFO"
    json: bool = True


@dataclass(slots=True)
class MemorySettings:
    """Top-level application settings."""

    workspace_id: str = "default"
    storage: StorageSettings = field(default_factory=StorageSettings)
    segmenter: SegmenterSettings = field(default_factory=SegmenterSettings)
    ingestion: IngestionSettings = field(default_factory=IngestionSettings)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MemorySettings":
        """Load settings from a YAML file."""
        with Path(path).expanduser().open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "MemorySettings":
        """Construct settings from a plain mapping."""
        return cls(
            workspace_id=payload.get("workspace_id", "default"),
            storage=StorageSettings(**payload.get("storage", {})),
            segmenter=SegmenterSettings(**payload.get("segmenter", {})),
            ingestion=IngestionSettings(**payload.get("ingestion", {})),
            retrieval=RetrievalSettings(**payload.get("retrieval", {})),
            logging=LoggingSettings(**payload.get("logging", {})),
        )

    def ensure_directories(self) -> None:
        """Create required local directories."""
        self.storage.resolved_base_dir().mkdir(parents=True, exist_ok=True)
        self.storage.resolved_metadata_path().parent.mkdir(parents=True, exist_ok=True)
