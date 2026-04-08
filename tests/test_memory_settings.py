"""Tests for the typed settings model used by the new service core."""

from __future__ import annotations

from pathlib import Path

from mempalace.infrastructure.settings import MemorySettings
from mempalace.interfaces.runtime import parse_datetime


def test_settings_load_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "workspace_id: sample",
                "storage:",
                f"  base_dir: {tmp_path / 'runtime'}",
                f"  metadata_path: {tmp_path / 'runtime' / 'memory.sqlite3'}",
                "ingestion:",
                "  default_room_name: misc",
                "retrieval:",
                "  default_limit: 7",
                "  keyword_weight: 0.7",
                "  semantic_weight: 0.3",
            ]
        ),
        encoding="utf-8",
    )

    settings = MemorySettings.from_yaml(config_path)
    assert settings.workspace_id == "sample"
    assert settings.ingestion.default_room_name == "misc"
    assert settings.retrieval.default_limit == 7
    assert settings.retrieval.keyword_weight == 0.7
    assert settings.retrieval.semantic_weight == 0.3


def test_settings_ensure_directories_creates_runtime_paths(tmp_path: Path) -> None:
    settings = MemorySettings.from_mapping(
        {
            "storage": {
                "base_dir": str(tmp_path / "runtime"),
                "metadata_path": str(tmp_path / "runtime" / "memory.sqlite3"),
            }
        }
    )

    settings.ensure_directories()
    assert (tmp_path / "runtime").exists()


def test_parse_datetime_can_expand_end_of_day_for_date_inputs() -> None:
    parsed = parse_datetime("2025-12-31", end_of_day_if_date=True)

    assert parsed is not None
    assert parsed.isoformat() == "2025-12-31T23:59:59.999999+00:00"
