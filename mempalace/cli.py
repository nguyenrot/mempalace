"""
cli.py — Command-Line Interface Entry Point
==========================================

Delegates to service runtime commands (interfaces/cli/service_cli.py).
Legacy commands have been removed in v1.0.
"""

import argparse
import sys


CLI_ALIAS_MAP = {
    "workspace-init": "init",
    "ingest-directory": "ingest",
    "mine": "ingest",
    "search-memory": "search",
    "status-health": "status",
}


def main():
    argv = list(sys.argv[1:])
    if argv:
        argv[0] = CLI_ALIAS_MAP.get(argv[0], argv[0])

    parser = argparse.ArgumentParser(
        description="MemPalace — Give your AI a memory. No API key required.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    # status
    p_status = sub.add_parser("status", help="Show health and storage counts for current project memory")
    p_status.add_argument("--config", default=None)
    p_status.add_argument("--workspace", default=None)

    from mempalace.interfaces.cli.service_cli import add_service_cli_parsers

    add_service_cli_parsers(sub)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return

    # Import service commands lazily
    from mempalace.interfaces.cli import service_cli as _svc

    dispatch = {
        "init": _svc.cmd_init_project_service,
        "ingest": _svc.cmd_ingest_directory_service,
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
        "status": _svc.cmd_status_health_service,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return

    try:
        handler(args)
    except FileNotFoundError as exc:
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
