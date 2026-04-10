"""
cli.py — Command-Line Interface Entry Point
==========================================

This is a thin shim that delegates to:
  - Service runtime commands (interfaces/cli/service_cli.py)
  - Legacy runtime commands (compat/cli.py)

Keeping it here maintains the original entry point `mempalace` or
`python -m mempalace` without breaking anything.

The actual implementations live in the sibling directories.
"""

import argparse
import sys

# Import compat (legacy) commands directly by name to avoid shadowing
from mempalace.compat.cli import (
    cmd_compress,
    cmd_repair,
    cmd_split,
    cmd_wakeup,
    cmd_legacy_init,
    cmd_legacy_mine,
    cmd_legacy_search,
    cmd_legacy_status,
)


CLI_ALIAS_MAP = {
    "workspace-init": "init",
    "ingest-directory": "ingest",
    "mine": "ingest",
    "search-memory": "search",
    "status-health": "status",
}


def _dispatch_legacy_command(argv: list[str]) -> bool:
    """Handle explicit legacy commands outside the primary CLI surface."""
    if not argv:
        return False

    command = argv[0]
    if command not in {"legacy-init", "legacy-mine", "legacy-search", "legacy-status"}:
        return False

    parser = argparse.ArgumentParser(prog=f"mempalace {command}")
    parser.add_argument(
        "--palace",
        default=None,
        help="Where the legacy palace lives (default: from ~/.mempalace/config.json or ~/.mempalace/palace)",
    )

    if command == "legacy-init":
        parser.add_argument("dir", help="Project directory to set up")
        parser.add_argument("--yes", action="store_true", help="Auto-accept all detected entities")
        args = parser.parse_args(argv[1:])
        cmd_legacy_init(args)
        return True

    if command == "legacy-mine":
        parser.add_argument("dir", help="Directory to mine")
        parser.add_argument("--mode", choices=["projects", "convos"], default="projects")
        parser.add_argument("--wing", default=None)
        parser.add_argument("--no-gitignore", action="store_true")
        parser.add_argument("--include-ignored", action="append", default=[])
        parser.add_argument("--agent", default="mempalace")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--extract", choices=["exchange", "general"], default="exchange")
        args = parser.parse_args(argv[1:])
        cmd_legacy_mine(args)
        return True

    if command == "legacy-search":
        parser.add_argument("query", help="What to search for")
        parser.add_argument("--wing", default=None)
        parser.add_argument("--room", default=None)
        parser.add_argument("--results", type=int, default=5)
        args = parser.parse_args(argv[1:])
        cmd_legacy_search(args)
        return True

    args = parser.parse_args(argv[1:])
    cmd_legacy_status(args)
    return True


def main():
    argv = list(sys.argv[1:])
    if argv:
        argv[0] = CLI_ALIAS_MAP.get(argv[0], argv[0])

    if _dispatch_legacy_command(argv):
        return

    parser = argparse.ArgumentParser(
        description="MemPalace — Give your AI a memory. No API key required.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--palace",
        default=None,
        help="Legacy palace path (default: from ~/.mempalace/config.json or ~/.mempalace/palace)",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Create project-local memory runtime in the current repo")
    p_init.add_argument("dir", nargs="?", default=".", help="Project directory to set up")
    p_init.add_argument("--workspace-id", default=None)
    p_init.add_argument("--force", action="store_true")

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest project files into the current repo memory")
    p_ingest.add_argument("dir", nargs="?", default=".")
    p_ingest.add_argument("--mode", choices=["projects", "convos"], default="projects")
    p_ingest.add_argument("--wing", default=None)
    p_ingest.add_argument("--no-gitignore", action="store_true")
    p_ingest.add_argument("--include-ignored", action="append", default=[])
    p_ingest.add_argument("--extract", choices=["exchange", "general"], default="exchange")
    p_ingest.add_argument("--config", default=None)
    p_ingest.add_argument("--workspace", default=None)

    # search
    p_search = sub.add_parser("search", help="Search current project memory with provenance")
    p_search.add_argument("query", help="What to search for")
    p_search.add_argument("--wing", default=None)
    p_search.add_argument("--room", default=None)
    p_search.add_argument("--limit", "--results", dest="limit", type=int, default=5)
    p_search.add_argument("--config", default=None)
    p_search.add_argument("--workspace", default=None)
    p_search.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="hybrid")
    p_search.add_argument("--start-time", default=None)
    p_search.add_argument("--end-time", default=None)
    p_search.add_argument("--filter", action="append", dest="filters", default=[])

    from mempalace.interfaces.cli.service_cli import add_service_cli_parsers

    add_service_cli_parsers(sub)

    # compress
    p_compress = sub.add_parser("compress", help="Compress drawers using AAAK Dialect (~30x reduction)")
    p_compress.add_argument("--wing", default=None)
    p_compress.add_argument("--dry-run", action="store_true")
    p_compress.add_argument("--config", default=None)

    # wake-up
    p_wakeup = sub.add_parser("wake-up", help="Show L0 + L1 wake-up context (~600-900 tokens)")
    p_wakeup.add_argument("--wing", default=None)

    # split
    p_split = sub.add_parser(
        "split",
        help="Split concatenated transcript mega-files into per-session files (run before mine)",
    )
    p_split.add_argument("dir", help="Directory containing transcript files")
    p_split.add_argument("--output-dir", default=None)
    p_split.add_argument("--dry-run", action="store_true")
    p_split.add_argument("--min-sessions", type=int, default=2)

    # repair
    sub.add_parser("repair", help="Rebuild palace vector index from stored data")

    # status
    p_status = sub.add_parser("status", help="Show health and storage counts for current project memory")
    p_status.add_argument("--config", default=None)
    p_status.add_argument("--workspace", default=None)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return

    # Import service commands lazily to keep the dispatch table clean
    from mempalace.interfaces.cli import service_cli as _svc

    dispatch = {
        "init": _svc.cmd_init_project_service,
        "ingest": _svc.cmd_ingest_directory_service,
        "split": cmd_split,
        "search": _svc.cmd_search_memory_service,
        "ingest-chat-history": _svc.cmd_ingest_chat_history_service,
        "ingest-source": _svc.cmd_ingest_source_service,
        "search-time-range": _svc.cmd_search_time_range_service,
        "explain-retrieval": _svc.cmd_explain_retrieval_service,
        "fetch-document": _svc.cmd_fetch_document_service,
        "fetch-evidence": _svc.cmd_fetch_evidence_service,
        "extract-facts": _svc.cmd_extract_facts_service,
        "query-facts": _svc.cmd_query_facts_service,
        "reindex": _svc.cmd_reindex_service,
        "recall-episodes": _svc.cmd_recall_episodes_service,
        "compact-session-context": _svc.cmd_compact_session_context_service,
        "prepare-startup-context": _svc.cmd_prepare_startup_context_service,
        "migrate-legacy": _svc.cmd_migrate_legacy_service,
        "compress": cmd_compress,
        "wake-up": cmd_wakeup,
        "repair": cmd_repair,
        "status": _svc.cmd_status_health_service,
    }

    try:
        dispatch[args.command](args)
    except FileNotFoundError as exc:
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
