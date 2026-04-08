"""Deterministic project manifest loading and room classification."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _normalize_slug(value: str) -> str:
    """Convert a project or room label into a stable lowercase slug."""
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized or "general"


@dataclass(slots=True, frozen=True)
class ProjectRoomDefinition:
    """Room definition loaded from a project manifest."""

    name: str
    description: str | None = None
    keywords: tuple[str, ...] = ()

    def all_tokens(self) -> tuple[str, ...]:
        """Return the normalized room name and keywords used for matching."""
        tokens = {_normalize_slug(self.name)}
        tokens.update(_normalize_slug(keyword) for keyword in self.keywords if keyword.strip())
        return tuple(sorted(token for token in tokens if token))


@dataclass(slots=True, frozen=True)
class ProjectManifest:
    """Normalized project routing manifest."""

    wing: str
    rooms: tuple[ProjectRoomDefinition, ...]
    manifest_path: str | None = None
    default_room_name: str = "general"


@dataclass(slots=True, frozen=True)
class ProjectClassification:
    """Classification output for one project file."""

    wing: str
    room: str
    strategy: str
    matched_token: str | None = None


@dataclass(slots=True)
class ProjectClassifier:
    """Classify project files into deterministic wing and room metadata."""

    project_root: Path
    manifest: ProjectManifest
    room_index: dict[str, ProjectRoomDefinition] = field(init=False)

    def __post_init__(self) -> None:
        self.room_index = {room.name: room for room in self.manifest.rooms}

    @classmethod
    def from_project_root(
        cls,
        project_root: str | Path,
        *,
        manifest_filenames: list[str],
        default_room_name: str = "general",
        wing_override: str | None = None,
    ) -> "ProjectClassifier":
        """Build a classifier from a project root and optional manifest files."""
        resolved_root = Path(project_root).expanduser().resolve()
        manifest_path = next(
            (resolved_root / name for name in manifest_filenames if (resolved_root / name).is_file()),
            None,
        )
        manifest = load_project_manifest(
            resolved_root,
            manifest_path=manifest_path,
            default_room_name=default_room_name,
            wing_override=wing_override,
        )
        return cls(project_root=resolved_root, manifest=manifest)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        manifest_filenames: list[str],
        default_room_name: str = "general",
        wing_override: str | None = None,
    ) -> "ProjectClassifier":
        """Build a classifier by resolving the nearest project root for a file or directory."""
        resolved_path = Path(path).expanduser().resolve()
        project_root = find_project_root(resolved_path, manifest_filenames=manifest_filenames)
        return cls.from_project_root(
            project_root,
            manifest_filenames=manifest_filenames,
            default_room_name=default_room_name,
            wing_override=wing_override,
        )

    def classify(self, file_path: str | Path, content: str) -> ProjectClassification:
        """Classify one project file into a wing and room."""
        resolved_path = Path(file_path).expanduser().resolve()
        relative_path = resolved_path.relative_to(self.project_root).as_posix().lower()
        filename = resolved_path.stem.lower()
        content_lower = content[:2000].lower()
        path_parts = relative_path.split("/")

        for part in path_parts[:-1]:
            for room in self.manifest.rooms:
                for token in room.all_tokens():
                    if part == token or token in part or part in token:
                        return ProjectClassification(
                            wing=self.manifest.wing,
                            room=room.name,
                            strategy="path_token",
                            matched_token=token,
                        )

        for room in self.manifest.rooms:
            for token in room.all_tokens():
                if token in filename or filename in token:
                    return ProjectClassification(
                        wing=self.manifest.wing,
                        room=room.name,
                        strategy="filename_token",
                        matched_token=token,
                    )

        scores: dict[str, int] = defaultdict(int)
        token_matches: dict[str, str] = {}
        for room in self.manifest.rooms:
            for token in room.all_tokens():
                count = content_lower.count(token)
                if count > 0:
                    scores[room.name] += count
                    token_matches.setdefault(room.name, token)

        if scores:
            best_room = max(scores, key=scores.get)
            if scores[best_room] > 0:
                return ProjectClassification(
                    wing=self.manifest.wing,
                    room=best_room,
                    strategy="content_keyword",
                    matched_token=token_matches.get(best_room),
                )

        return ProjectClassification(
            wing=self.manifest.wing,
            room=self.manifest.default_room_name,
            strategy="default_room",
            matched_token=None,
        )

    def is_manifest_file(self, file_path: str | Path) -> bool:
        """Return true when the file is the active project manifest."""
        if self.manifest.manifest_path is None:
            return False
        return Path(file_path).expanduser().resolve().as_posix() == self.manifest.manifest_path


def load_project_manifest(
    project_root: str | Path,
    *,
    manifest_path: Path | None,
    default_room_name: str = "general",
    wing_override: str | None = None,
) -> ProjectManifest:
    """Load and normalize a project manifest, falling back to deterministic defaults."""
    resolved_root = Path(project_root).expanduser().resolve()
    payload: dict[str, object] = {}

    if manifest_path is not None:
        with manifest_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

    rooms_payload = payload.get("rooms", []) if isinstance(payload, dict) else []
    rooms = [_normalize_room_definition(item) for item in rooms_payload if isinstance(item, dict)]

    default_room = _normalize_slug(default_room_name)
    if not any(room.name == default_room for room in rooms):
        rooms.append(
            ProjectRoomDefinition(
                name=default_room,
                description="Files that do not match a named room.",
                keywords=(),
            )
        )

    if not rooms:
        rooms = [ProjectRoomDefinition(name=default_room, description="All project files.", keywords=())]

    payload_wing = payload.get("wing") if isinstance(payload, dict) else None
    wing = _normalize_slug(str(wing_override or payload_wing or resolved_root.name))
    return ProjectManifest(
        wing=wing,
        rooms=tuple(rooms),
        manifest_path=manifest_path.as_posix() if manifest_path is not None else None,
        default_room_name=default_room,
    )


def find_project_root(path: str | Path, *, manifest_filenames: list[str]) -> Path:
    """Resolve the nearest ancestor containing a project manifest, else use the file parent."""
    resolved_path = Path(path).expanduser().resolve()
    current = resolved_path if resolved_path.is_dir() else resolved_path.parent
    candidates = [current, *current.parents]
    for candidate in candidates:
        if any((candidate / name).is_file() for name in manifest_filenames):
            return candidate
    return current


def _normalize_room_definition(payload: dict[str, object]) -> ProjectRoomDefinition:
    """Normalize a raw room mapping from YAML into a typed room definition."""
    room_name = _normalize_slug(str(payload.get("name", "general")))
    keywords_payload = payload.get("keywords", [])
    if isinstance(keywords_payload, str):
        keywords = (keywords_payload,)
    elif isinstance(keywords_payload, list):
        keywords = tuple(str(item) for item in keywords_payload)
    else:
        keywords = ()
    return ProjectRoomDefinition(
        name=room_name,
        description=str(payload.get("description")) if payload.get("description") is not None else None,
        keywords=tuple(_normalize_slug(keyword) for keyword in keywords if str(keyword).strip()),
    )
