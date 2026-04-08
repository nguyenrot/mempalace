#!/usr/bin/env python3
"""
MemPalace — Give your AI a memory. No API key required.

Project-local memory flow:
  1. mempalace init                      (create .mempalace/ in the current repo)
  2. mempalace ingest                    (index code, docs, and notes)
  3. mempalace ingest-chat-history ...   (optional: add AI chat exports)
  4. mempalace search "query"            (search with provenance)

Commands:
    mempalace init [dir]                  Create project-local memory runtime
    mempalace ingest [dir]                Ingest project files into local memory
    mempalace ingest-chat-history [dir]   Ingest AI chat exports
    mempalace search "query"              Search memory with provenance
    mempalace status                      Show health for the current project memory
    mempalace ingest-source <file>        Ingest one file into local memory
    mempalace search-time-range "query"   Search inside a time window
    mempalace explain-retrieval "query"   Return inspectable retrieval payload
    mempalace fetch-document <id>         Fetch one document
    mempalace fetch-evidence              Fetch a provenance trail
    mempalace extract-facts               Extract deterministic structured facts
    mempalace query-facts                 Query structured facts
    mempalace reindex                     Rebuild vector entries from stored segments
    mempalace recall-episodes             Recall recent or query-matched episodes
    mempalace compact-session-context     Build compact agent context
    mempalace prepare-startup-context     Prepare startup context for an agent
    mempalace migrate-legacy <palace>     Import a legacy Chroma palace into the new runtime

Compatibility aliases still work:
    mempalace workspace-init
    mempalace split <dir>                 Split concatenated mega-files into per-session files
    mempalace ingest-directory
    mempalace search-memory
    mempalace status-health
    mempalace wake-up                     Show L0 + L1 wake-up context
    mempalace wake-up --wing my_app       Wake-up for a specific project

Examples:
    mempalace init
    mempalace ingest
    mempalace ingest-chat-history ~/exports/claude
    mempalace search "why did we switch to GraphQL"
    mempalace status
"""

import os
import sys
import argparse
from pathlib import Path

from .config import MempalaceConfig


def cmd_legacy_init(args):
    import json
    from pathlib import Path
    from .entity_detector import scan_for_detection, detect_entities, confirm_entities
    from .room_detector_local import detect_rooms_local

    # Pass 1: auto-detect people and projects from file content
    print(f"\n  Scanning for entities in: {args.dir}")
    files = scan_for_detection(args.dir)
    if files:
        print(f"  Reading {len(files)} files...")
        detected = detect_entities(files)
        total = len(detected["people"]) + len(detected["projects"]) + len(detected["uncertain"])
        if total > 0:
            confirmed = confirm_entities(detected, yes=getattr(args, "yes", False))
            # Save confirmed entities to <project>/entities.json for the miner
            if confirmed["people"] or confirmed["projects"]:
                entities_path = Path(args.dir).expanduser().resolve() / "entities.json"
                with open(entities_path, "w") as f:
                    json.dump(confirmed, f, indent=2)
                print(f"  Entities saved: {entities_path}")
        else:
            print("  No entities detected — proceeding with directory-based rooms.")

    # Pass 2: detect rooms from folder structure
    detect_rooms_local(project_dir=args.dir, yes=getattr(args, "yes", False))
    MempalaceConfig().init()


def cmd_legacy_mine(args):
    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    include_ignored = []
    for raw in args.include_ignored or []:
        include_ignored.extend(part.strip() for part in raw.split(",") if part.strip())

    if args.mode == "convos":
        from .convo_miner import mine_convos

        mine_convos(
            convo_dir=args.dir,
            palace_path=palace_path,
            wing=args.wing,
            agent=args.agent,
            limit=args.limit,
            dry_run=args.dry_run,
            extract_mode=args.extract,
        )
    else:
        from .miner import mine

        mine(
            project_dir=args.dir,
            palace_path=palace_path,
            wing_override=args.wing,
            agent=args.agent,
            limit=args.limit,
            dry_run=args.dry_run,
            respect_gitignore=not args.no_gitignore,
            include_ignored=include_ignored,
        )


def cmd_legacy_search(args):
    from .searcher import search, SearchError

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    try:
        search(
            query=args.query,
            palace_path=palace_path,
            wing=args.wing,
            room=args.room,
            n_results=args.results,
        )
    except SearchError:
        sys.exit(1)


def cmd_wakeup(args):
    """Show L0 (identity) + L1 (essential story) — the wake-up context."""
    from .layers import MemoryStack

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    stack = MemoryStack(palace_path=palace_path)

    text = stack.wake_up(wing=args.wing)
    tokens = len(text) // 4
    print(f"Wake-up text (~{tokens} tokens):")
    print("=" * 50)
    print(text)


def cmd_split(args):
    """Split concatenated transcript mega-files into per-session files."""
    from .split_mega_files import main as split_main
    import sys

    # Rebuild argv for split_mega_files argparse
    argv = ["--source", args.dir]
    if args.output_dir:
        argv += ["--output-dir", args.output_dir]
    if args.dry_run:
        argv.append("--dry-run")
    if args.min_sessions != 2:
        argv += ["--min-sessions", str(args.min_sessions)]

    old_argv = sys.argv
    sys.argv = ["mempalace split"] + argv
    try:
        split_main()
    finally:
        sys.argv = old_argv


def cmd_legacy_status(args):
    from .miner import status

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path
    status(palace_path=palace_path)


def cmd_ingest_directory(args):
    from .interfaces.cli.service_cli import cmd_ingest_directory_service

    cmd_ingest_directory_service(args)


def cmd_ingest_chat_history(args):
    from .interfaces.cli.service_cli import cmd_ingest_chat_history_service

    cmd_ingest_chat_history_service(args)


def cmd_search_memory(args):
    from .interfaces.cli.service_cli import cmd_search_memory_service

    cmd_search_memory_service(args)


def cmd_ingest_source(args):
    from .interfaces.cli.service_cli import cmd_ingest_source_service

    cmd_ingest_source_service(args)


def cmd_search_time_range(args):
    from .interfaces.cli.service_cli import cmd_search_time_range_service

    cmd_search_time_range_service(args)


def cmd_explain_retrieval(args):
    from .interfaces.cli.service_cli import cmd_explain_retrieval_service

    cmd_explain_retrieval_service(args)


def cmd_fetch_document(args):
    from .interfaces.cli.service_cli import cmd_fetch_document_service

    cmd_fetch_document_service(args)


def cmd_extract_facts(args):
    from .interfaces.cli.service_cli import cmd_extract_facts_service

    cmd_extract_facts_service(args)


def cmd_query_facts(args):
    from .interfaces.cli.service_cli import cmd_query_facts_service

    cmd_query_facts_service(args)


def cmd_fetch_evidence(args):
    from .interfaces.cli.service_cli import cmd_fetch_evidence_service

    cmd_fetch_evidence_service(args)


def cmd_reindex(args):
    from .interfaces.cli.service_cli import cmd_reindex_service

    cmd_reindex_service(args)


def cmd_recall_episodes(args):
    from .interfaces.cli.service_cli import cmd_recall_episodes_service

    cmd_recall_episodes_service(args)


def cmd_compact_session_context(args):
    from .interfaces.cli.service_cli import cmd_compact_session_context_service

    cmd_compact_session_context_service(args)


def cmd_prepare_startup_context(args):
    from .interfaces.cli.service_cli import cmd_prepare_startup_context_service

    cmd_prepare_startup_context_service(args)


def cmd_status_health(args):
    from .interfaces.cli.service_cli import cmd_status_health_service

    cmd_status_health_service(args)


def cmd_migrate_legacy(args):
    from .interfaces.cli.service_cli import cmd_migrate_legacy_service

    cmd_migrate_legacy_service(args)


def cmd_workspace_init(args):
    from .interfaces.cli.service_cli import cmd_init_project_service

    cmd_init_project_service(args)


def cmd_init(args):
    cmd_workspace_init(args)


def cmd_ingest(args):
    cmd_ingest_directory(args)


def cmd_search(args):
    cmd_search_memory(args)


def cmd_status(args):
    cmd_status_health(args)


def cmd_repair(args):
    """Rebuild palace vector index from SQLite metadata."""
    import chromadb
    import shutil

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path

    if not os.path.isdir(palace_path):
        print(f"\n  No palace found at {palace_path}")
        return

    print(f"\n{'=' * 55}")
    print("  MemPalace Repair")
    print(f"{'=' * 55}\n")
    print(f"  Palace: {palace_path}")

    # Try to read existing drawers
    try:
        client = chromadb.PersistentClient(path=palace_path)
        col = client.get_collection("mempalace_drawers")
        total = col.count()
        print(f"  Drawers found: {total}")
    except Exception as e:
        print(f"  Error reading palace: {e}")
        print("  Cannot recover — palace may need to be re-mined from source files.")
        return

    if total == 0:
        print("  Nothing to repair.")
        return

    # Extract all drawers in batches
    print("\n  Extracting drawers...")
    batch_size = 5000
    all_ids = []
    all_docs = []
    all_metas = []
    offset = 0
    while offset < total:
        batch = col.get(limit=batch_size, offset=offset, include=["documents", "metadatas"])
        all_ids.extend(batch["ids"])
        all_docs.extend(batch["documents"])
        all_metas.extend(batch["metadatas"])
        offset += batch_size
    print(f"  Extracted {len(all_ids)} drawers")

    # Backup and rebuild
    backup_path = palace_path + ".backup"
    if os.path.exists(backup_path):
        shutil.rmtree(backup_path)
    print(f"  Backing up to {backup_path}...")
    shutil.copytree(palace_path, backup_path)

    print("  Rebuilding collection...")
    client.delete_collection("mempalace_drawers")
    new_col = client.create_collection("mempalace_drawers")

    filed = 0
    for i in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[i : i + batch_size]
        batch_docs = all_docs[i : i + batch_size]
        batch_metas = all_metas[i : i + batch_size]
        new_col.add(documents=batch_docs, ids=batch_ids, metadatas=batch_metas)
        filed += len(batch_ids)
        print(f"  Re-filed {filed}/{len(all_ids)} drawers...")

    print(f"\n  Repair complete. {filed} drawers rebuilt.")
    print(f"  Backup saved at {backup_path}")
    print(f"\n{'=' * 55}\n")


def cmd_compress(args):
    """Compress drawers in a wing using AAAK Dialect."""
    import chromadb
    from .dialect import Dialect

    palace_path = os.path.expanduser(args.palace) if args.palace else MempalaceConfig().palace_path

    # Load dialect (with optional entity config)
    config_path = args.config
    if not config_path:
        for candidate in ["entities.json", os.path.join(palace_path, "entities.json")]:
            if os.path.exists(candidate):
                config_path = candidate
                break

    if config_path and os.path.exists(config_path):
        dialect = Dialect.from_config(config_path)
        print(f"  Loaded entity config: {config_path}")
    else:
        dialect = Dialect()

    # Connect to palace
    try:
        client = chromadb.PersistentClient(path=palace_path)
        col = client.get_collection("mempalace_drawers")
    except Exception:
        print(f"\n  No palace found at {palace_path}")
        print("  Run: mempalace init <dir> then mempalace mine <dir>")
        sys.exit(1)

    # Query drawers in batches to avoid SQLite variable limit (~999)
    where = {"wing": args.wing} if args.wing else None
    _BATCH = 500
    docs, metas, ids = [], [], []
    offset = 0
    while True:
        try:
            kwargs = {"include": ["documents", "metadatas"], "limit": _BATCH, "offset": offset}
            if where:
                kwargs["where"] = where
            batch = col.get(**kwargs)
        except Exception as e:
            if not docs:
                print(f"\n  Error reading drawers: {e}")
                sys.exit(1)
            break
        batch_docs = batch.get("documents", [])
        if not batch_docs:
            break
        docs.extend(batch_docs)
        metas.extend(batch.get("metadatas", []))
        ids.extend(batch.get("ids", []))
        offset += len(batch_docs)
        if len(batch_docs) < _BATCH:
            break

    if not docs:
        wing_label = f" in wing '{args.wing}'" if args.wing else ""
        print(f"\n  No drawers found{wing_label}.")
        return

    print(
        f"\n  Compressing {len(docs)} drawers"
        + (f" in wing '{args.wing}'" if args.wing else "")
        + "..."
    )
    print()

    total_original = 0
    total_compressed = 0
    compressed_entries = []

    for doc, meta, doc_id in zip(docs, metas, ids):
        compressed = dialect.compress(doc, metadata=meta)
        stats = dialect.compression_stats(doc, compressed)

        total_original += stats["original_chars"]
        total_compressed += stats["compressed_chars"]

        compressed_entries.append((doc_id, compressed, meta, stats))

        if args.dry_run:
            wing_name = meta.get("wing", "?")
            room_name = meta.get("room", "?")
            source = Path(meta.get("source_file", "?")).name
            print(f"  [{wing_name}/{room_name}] {source}")
            print(
                f"    {stats['original_tokens']}t -> {stats['compressed_tokens']}t ({stats['ratio']:.1f}x)"
            )
            print(f"    {compressed}")
            print()

    # Store compressed versions (unless dry-run)
    if not args.dry_run:
        try:
            comp_col = client.get_or_create_collection("mempalace_compressed")
            for doc_id, compressed, meta, stats in compressed_entries:
                comp_meta = dict(meta)
                comp_meta["compression_ratio"] = round(stats["ratio"], 1)
                comp_meta["original_tokens"] = stats["original_tokens"]
                comp_col.upsert(
                    ids=[doc_id],
                    documents=[compressed],
                    metadatas=[comp_meta],
                )
            print(
                f"  Stored {len(compressed_entries)} compressed drawers in 'mempalace_compressed' collection."
            )
        except Exception as e:
            print(f"  Error storing compressed drawers: {e}")
            sys.exit(1)

    # Summary
    ratio = total_original / max(total_compressed, 1)
    orig_tokens = Dialect.count_tokens("x" * total_original)
    comp_tokens = Dialect.count_tokens("x" * total_compressed)
    print(f"  Total: {orig_tokens:,}t -> {comp_tokens:,}t ({ratio:.1f}x compression)")
    if args.dry_run:
        print("  (dry run -- nothing stored)")


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
        epilog=__doc__,
    )
    parser.add_argument(
        "--palace",
        default=None,
        help="Where the palace lives (default: from ~/.mempalace/config.json or ~/.mempalace/palace)",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Create project-local memory runtime in the current repo")
    p_init.add_argument(
        "dir",
        nargs="?",
        default=".",
        help="Project directory to set up (default: current directory)",
    )
    p_init.add_argument(
        "--workspace-id",
        default=None,
        help="Optional explicit workspace identifier for the service runtime",
    )
    p_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing local service runtime config",
    )
    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest project files into the current repo memory")
    p_ingest.add_argument("dir", nargs="?", default=".", help="Directory to ingest (default: current directory)")
    p_ingest.add_argument(
        "--mode",
        choices=["projects", "convos"],
        default="projects",
        help="Ingest mode: 'projects' for code/docs (default), 'convos' for chat exports",
    )
    p_ingest.add_argument("--wing", default=None, help="Optional workspace wing override")
    p_ingest.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Don't respect .gitignore files when scanning project files",
    )
    p_ingest.add_argument(
        "--include-ignored",
        action="append",
        default=[],
        help="Always scan these project-relative paths even if ignored; repeat or pass comma-separated paths",
    )
    p_ingest.add_argument(
        "--extract",
        choices=["exchange", "general"],
        default="exchange",
        help="Extraction strategy for convos mode: 'exchange' (default) or 'general' (5 memory types)",
    )
    p_ingest.add_argument(
        "--config",
        default=None,
        help="YAML config for service runtime ingest",
    )
    p_ingest.add_argument(
        "--workspace",
        default=None,
        help="Workspace override for service runtime ingest",
    )
    # search
    p_search = sub.add_parser("search", help="Search current project memory with provenance")
    p_search.add_argument("query", help="What to search for")
    p_search.add_argument("--wing", default=None, help="Limit to one project")
    p_search.add_argument("--room", default=None, help="Limit to one room")
    p_search.add_argument("--limit", "--results", dest="limit", type=int, default=5, help="Number of results")
    p_search.add_argument(
        "--config",
        default=None,
        help="YAML config for search",
    )
    p_search.add_argument(
        "--workspace",
        default=None,
        help="Workspace override for search",
    )
    p_search.add_argument(
        "--mode",
        choices=["keyword", "semantic", "hybrid"],
        default="hybrid",
        help="Retrieval mode",
    )
    p_search.add_argument(
        "--start-time",
        default=None,
        help="Optional start time for search",
    )
    p_search.add_argument(
        "--end-time",
        default=None,
        help="Optional end time for search",
    )
    p_search.add_argument(
        "--filter",
        action="append",
        dest="filters",
        default=[],
        help="Exact metadata filter in key=value form; may be repeated",
    )
    from .interfaces.cli.service_cli import add_service_cli_parsers

    add_service_cli_parsers(sub)

    # compress
    p_compress = sub.add_parser(
        "compress", help="Compress drawers using AAAK Dialect (~30x reduction)"
    )
    p_compress.add_argument("--wing", default=None, help="Wing to compress (default: all wings)")
    p_compress.add_argument(
        "--dry-run", action="store_true", help="Preview compression without storing"
    )
    p_compress.add_argument(
        "--config", default=None, help="Entity config JSON (e.g. entities.json)"
    )

    # wake-up
    p_wakeup = sub.add_parser("wake-up", help="Show L0 + L1 wake-up context (~600-900 tokens)")
    p_wakeup.add_argument("--wing", default=None, help="Wake-up for a specific project/wing")

    # split
    p_split = sub.add_parser(
        "split",
        help="Split concatenated transcript mega-files into per-session files (run before mine)",
    )
    p_split.add_argument("dir", help="Directory containing transcript files")
    p_split.add_argument(
        "--output-dir",
        default=None,
        help="Write split files here (default: same directory as source files)",
    )
    p_split.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be split without writing files",
    )
    p_split.add_argument(
        "--min-sessions",
        type=int,
        default=2,
        help="Only split files containing at least N sessions (default: 2)",
    )

    # repair
    sub.add_parser(
        "repair",
        help="Rebuild palace vector index from stored data (fixes segfaults after corruption)",
    )

    # status
    p_status = sub.add_parser("status", help="Show health and storage counts for current project memory")
    p_status.add_argument("--config", default=None, help="YAML config for current project memory")
    p_status.add_argument("--workspace", default=None, help="Workspace override for current project memory")
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return

    dispatch = {
        "init": cmd_init,
        "ingest": cmd_ingest,
        "split": cmd_split,
        "search": cmd_search,
        "ingest-chat-history": cmd_ingest_chat_history,
        "ingest-source": cmd_ingest_source,
        "search-time-range": cmd_search_time_range,
        "explain-retrieval": cmd_explain_retrieval,
        "fetch-document": cmd_fetch_document,
        "fetch-evidence": cmd_fetch_evidence,
        "extract-facts": cmd_extract_facts,
        "query-facts": cmd_query_facts,
        "reindex": cmd_reindex,
        "recall-episodes": cmd_recall_episodes,
        "compact-session-context": cmd_compact_session_context,
        "prepare-startup-context": cmd_prepare_startup_context,
        "migrate-legacy": cmd_migrate_legacy,
        "compress": cmd_compress,
        "wake-up": cmd_wakeup,
        "repair": cmd_repair,
        "status": cmd_status,
    }
    try:
        dispatch[args.command](args)
    except FileNotFoundError as exc:
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
