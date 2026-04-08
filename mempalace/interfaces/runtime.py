"""Shared runtime helpers for service-backed interfaces."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any

from mempalace.api import LocalMemoryPlatform
from mempalace.application.project_profiles import find_nearest_project_config
from mempalace.infrastructure.settings import MemorySettings


def load_settings(config_path: str | None = None, workspace_id: str | None = None) -> MemorySettings:
    """Load settings from YAML when present, otherwise use defaults."""
    if config_path:
        settings = MemorySettings.from_yaml(config_path)
    else:
        local_config = find_nearest_project_config()
        if local_config and local_config.exists():
            settings = MemorySettings.from_yaml(local_config)
        else:
            raise FileNotFoundError(
                "No local MemPalace config found. Run 'mempalace workspace-init' in the project first "
                "or pass --config explicitly."
            )

    if workspace_id:
        settings.workspace_id = workspace_id
    return settings


def build_platform(config_path: str | None = None, workspace_id: str | None = None) -> LocalMemoryPlatform:
    """Create a service-backed local memory platform instance."""
    settings = load_settings(config_path=config_path, workspace_id=workspace_id)
    return LocalMemoryPlatform.from_settings(settings)


def parse_datetime(value: str | None, *, end_of_day_if_date: bool = False) -> datetime | None:
    """Parse an ISO-8601 date or datetime string."""
    if not value:
        return None

    normalized = value.strip()
    has_time_component = "T" in normalized or " " in normalized
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo:
            return parsed
        if not has_time_component and end_of_day_if_date:
            return datetime.combine(parsed.date(), time.max, tzinfo=timezone.utc)
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        parsed_date = date.fromisoformat(normalized)
        clock = time.max if end_of_day_if_date else datetime.min.time()
        return datetime.combine(
            parsed_date,
            clock,
            tzinfo=timezone.utc,
        )


def to_primitive(value: Any) -> Any:
    """Convert dataclasses and typed values into JSON-serializable structures."""
    if is_dataclass(value):
        return to_primitive(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_primitive(item) for item in value]
    return value


def dumps_json(value: Any) -> str:
    """Serialize runtime objects to pretty JSON."""
    return json.dumps(to_primitive(value), indent=2, ensure_ascii=True)
