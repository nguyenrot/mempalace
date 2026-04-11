"""Conversation export discovery across known tools and locations.

This module helps users avoid manually tracking down chat export paths by
scanning well-known directories for popular AI chat tools.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from mempalace.infrastructure.settings import ConversationSettings, ConversationSource


@dataclass(slots=True)
class DiscoveredExport:
    """A discovered chat export directory or file."""

    tool: str  # e.g., "claude_desktop", "cursor", "chatgpt"
    path: Path
    file_count: int  # number of candidate chat files
    detected_by: str  # which known location matched


# Known default locations for various AI chat tools
# Keys should match conversation.tool values in ConversationSource
KNOWN_LOCATIONS: dict[str, list[str]] = {
    "claude_desktop": [
        "~/.config/claude/",
        "~/.config/Claude/",
        "~/Library/Application Support/Claude/",
        "~/Library/Application Support/claude/",
    ],
    "cursor": [
        "~/.cursor/chat_history/",
        "~/.config/cursor/chat_history/",
    ],
    "chatgpt": [
        "~/Downloads/",
        "~/Documents/ChatGPT_Exports/",
        "~/Documents/chatgpt/",
    ],
    "claude_code": [
        "~/.claude/chat_history/",
        "~/.claude/history/",
    ],
}


def discover_chat_exports(
    sources: list[ConversationSource] | None = None,
    extra_paths: list[str | Path] | None = None,
) -> list[DiscoveredExport]:
    """Discover available chat exports from known locations and configured sources.

    Args:
        sources: Optional list of configured conversation sources from settings.
        extra_paths: Additional paths to scan (from CLI flags, etc.).

    Returns:
        List of discovered exports, sorted by tool and path.
    """
    discovered: list[DiscoveredExport] = []

    # 1. Scan configured sources from mempalace.yaml
    if sources:
        for src in sources:
            p = Path(src.path).expanduser()
            if p.exists():
                count = _count_chat_files(p, src.tool)
                if count > 0:
                    discovered.append(
                        DiscoveredExport(
                            tool=src.tool,
                            path=p,
                            file_count=count,
                            detected_by="config",
                        )
                    )

    # 2. Scan known default locations
    for tool, locations in KNOWN_LOCATIONS.items():
        for loc in locations:
            p = Path(loc).expanduser()
            if p.exists():
                count = _count_chat_files(p, tool)
                if count > 0:
                    # Avoid duplicates: if path already discovered via config, skip
                    if not any(d.path == p for d in discovered):
                        discovered.append(
                            DiscoveredExport(
                                tool=tool,
                                path=p,
                                file_count=count,
                                detected_by=f"known:{loc}",
                            )
                        )

    # 3. Scan extra paths from CLI
    if extra_paths:
        for extra in extra_paths:
            p = Path(extra).expanduser()
            if p.exists():
                # Tool unknown, mark as "custom"
                count = _count_chat_files(p, "custom")
                if count > 0:
                    discovered.append(
                        DiscoveredExport(
                            tool="custom",
                            path=p,
                            file_count=count,
                            detected_by="cli",
                        )
                    )

    # Sort by tool then path for consistent output
    discovered.sort(key=lambda d: (d.tool, str(d.path)))
    return discovered


def _count_chat_files(path: Path, tool: str) -> int:
    """Count candidate chat export files in a directory.

    Different tools have different file extensions and patterns.
    """
    if not path.is_dir():
        # Single file case: if the path itself looks like a chat export
        if _is_chat_file(path, tool):
            return 1
        return 0

    # Known file patterns per tool (extensions without dot)
    patterns: dict[str, list[str]] = {
        "claude_desktop": ["json"],  # Claude exports are JSON
        "cursor": ["json", "md", "txt"],
        "chatgpt": ["json", "csv", "txt"],
        "claude_code": ["json", "txt", "md"],
        "custom": ["json", "md", "txt", "csv"],
    }

    exts = patterns.get(tool, patterns["custom"])
    count = 0
    try:
        for ext in exts:
            # Use glob pattern like "*.json"
            count += len(list(path.glob(f"*.{ext}")))
    except (PermissionError, OSError):
        pass
    return count


def _is_chat_file(path: Path, tool: str) -> bool:
    """Heuristic to detect if a single file is a chat export."""
    if not path.is_file():
        return False
    # Simple check: extension matches known patterns
    ext = path.suffix.lower().lstrip(".")
    known_exts = {
        "claude_desktop": {"json"},
        "cursor": {"json", "md", "txt"},
        "chatgpt": {"json", "csv", "txt"},
        "claude_code": {"json", "txt", "md"},
    }
    return ext in known_exts.get(tool, {"json", "md", "txt", "csv"})


def format_discovery_for_display(discovered: list[DiscoveredExport]) -> str:
    """Format discovered exports as user-readable text."""
    if not discovered:
        return "No chat exports discovered. Use --path to specify a location."

    lines = ["Discovered chat exports:", ""]
    for d in discovered:
        lines.append(f"  [{d.tool}] {d.path}")
        lines.append(f"      Files: {d.file_count}")
        lines.append(f"      Source: {d.detected_by}")
        lines.append("")
    return "\n".join(lines)
