"""Service-backed CLI commands for the refactored memory core."""

from __future__ import annotations

import argparse
import sys

from mempalace.application.project_profiles import (
    ProjectInitResult,
    initialize_project_runtime,
)
from mempalace.domain.models import (
    CompactedSessionContext,
    EvidenceTrail,
    FactExtractionResult,
    FactRecord,
    IngestionResult,
    MigrationResult,
    ReindexResult,
    SearchMode,
    SearchRequest,
    SearchResponse,
    StartupContext,
)
from mempalace.interfaces.runtime import build_platform, dumps_json, parse_datetime


def _add_runtime_args(parser: argparse.ArgumentParser, *, include_workspace: bool = True) -> None:
    """Attach runtime-selection arguments to a parser."""
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config for the service-backed local runtime",
    )
    if include_workspace:
        parser.add_argument(
            "--workspace",
            default=None,
            help="Workspace override for the service-backed runtime",
        )


def add_service_cli_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register service-backed CLI commands."""
    ingest_chat_parser = subparsers.add_parser(
        "ingest-chat-history",
        help="Ingest AI chat exports using the service-backed runtime",
    )
    ingest_chat_parser.add_argument(
        "dir",
        nargs="?",
        default=".",
        help="Directory containing chat exports (default: current directory)",
    )
    ingest_chat_parser.add_argument(
        "--extract",
        choices=["exchange", "general"],
        default="exchange",
        help="Conversation extraction mode (default: exchange)",
    )
    _add_runtime_args(ingest_chat_parser)

    ingest_source_parser = subparsers.add_parser(
        "ingest-source",
        help="Ingest one explicit file through the new service-backed runtime",
    )
    ingest_source_parser.add_argument("path", help="File to ingest")
    ingest_source_parser.add_argument(
        "--wing",
        default=None,
        help="Optional wing override for project ingestion",
    )
    ingest_source_parser.add_argument(
        "--mode",
        choices=["projects", "convos"],
        default="projects",
        help="Ingest mode for the service-backed runtime",
    )
    ingest_source_parser.add_argument(
        "--extract",
        choices=["exchange", "general"],
        default="exchange",
        help="Conversation extraction mode when --mode convos",
    )
    _add_runtime_args(ingest_source_parser)

    fetch_parser = subparsers.add_parser(
        "fetch-document",
        help="Fetch a document and its segments from the new service-backed runtime",
    )
    fetch_parser.add_argument("document_id", help="Document ID to fetch")
    _add_runtime_args(fetch_parser, include_workspace=False)

    extract_facts_parser = subparsers.add_parser(
        "extract-facts",
        help="Extract deterministic structured facts from the service-backed runtime",
    )
    extract_facts_parser.add_argument(
        "--document-id",
        default=None,
        help="Optional document ID to restrict extraction to one document",
    )
    _add_runtime_args(extract_facts_parser)

    query_facts_parser = subparsers.add_parser(
        "query-facts",
        help="Query structured facts from the service-backed runtime",
    )
    query_facts_parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Optional free-text query over subject, predicate, and object",
    )
    query_facts_parser.add_argument("--subject", default=None, help="Exact subject match")
    query_facts_parser.add_argument("--predicate", default=None, help="Exact predicate match")
    query_facts_parser.add_argument("--object", dest="object_text", default=None, help="Exact object match")
    query_facts_parser.add_argument("--limit", type=int, default=20, help="Maximum facts to return")
    _add_runtime_args(query_facts_parser)

    evidence_parser = subparsers.add_parser(
        "fetch-evidence",
        help="Fetch a provenance trail around a fact, segment, or document",
    )
    evidence_parser.add_argument("--fact-id", default=None, help="Exact fact ID")
    evidence_parser.add_argument("--segment-id", default=None, help="Exact segment ID")
    evidence_parser.add_argument("--document-id", default=None, help="Exact document ID")
    evidence_parser.add_argument(
        "--neighbor-count",
        type=int,
        default=1,
        help="How many neighboring segments to include on each side",
    )
    _add_runtime_args(evidence_parser)

    explain_parser = subparsers.add_parser(
        "explain-retrieval",
        help="Run retrieval and return the inspectable response payload",
    )
    explain_parser.add_argument("query", help="Search query")
    explain_parser.add_argument(
        "--mode",
        choices=["keyword", "semantic", "hybrid"],
        default="hybrid",
        help="Retrieval mode (default: hybrid)",
    )
    explain_parser.add_argument("--limit", type=int, default=5, help="Maximum number of results")
    explain_parser.add_argument("--start-time", default=None, help="Optional inclusive start time in ISO format")
    explain_parser.add_argument("--end-time", default=None, help="Optional inclusive end time in ISO format")
    explain_parser.add_argument("--wing", default=None, help="Optional exact-match wing filter")
    explain_parser.add_argument("--room", default=None, help="Optional exact-match room filter")
    explain_parser.add_argument(
        "--filter",
        action="append",
        dest="filters",
        default=[],
        help="Exact metadata filter in key=value form; may be repeated",
    )
    _add_runtime_args(explain_parser)

    time_search_parser = subparsers.add_parser(
        "search-time-range",
        help="Search memory within an explicit inclusive time range",
    )
    time_search_parser.add_argument("query", help="Search query")
    time_search_parser.add_argument("--start-time", required=True, help="Inclusive start time in ISO format")
    time_search_parser.add_argument("--end-time", required=True, help="Inclusive end time in ISO format")
    time_search_parser.add_argument(
        "--mode",
        choices=["keyword", "semantic", "hybrid"],
        default="hybrid",
        help="Retrieval mode (default: hybrid)",
    )
    time_search_parser.add_argument("--limit", type=int, default=5, help="Maximum number of results")
    _add_runtime_args(time_search_parser)

    reindex_parser = subparsers.add_parser(
        "reindex",
        help="Rebuild vector entries from stored segments",
    )
    reindex_parser.add_argument(
        "--document-id",
        default=None,
        help="Optional document ID to restrict reindexing to one document",
    )
    _add_runtime_args(reindex_parser)

    episodes_parser = subparsers.add_parser(
        "recall-episodes",
        help="Recall recent or query-matched episodes from stored documents",
    )
    episodes_parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Optional query to find relevant episodes",
    )
    episodes_parser.add_argument("--start-time", default=None, help="Optional inclusive start time in ISO format")
    episodes_parser.add_argument("--end-time", default=None, help="Optional inclusive end time in ISO format")
    episodes_parser.add_argument("--limit", type=int, default=5, help="Maximum episodes to return")
    _add_runtime_args(episodes_parser)

    compact_parser = subparsers.add_parser(
        "compact-session-context",
        help="Assemble a compact agent-ready context block",
    )
    compact_parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Optional query focus for context compaction",
    )
    compact_parser.add_argument("--start-time", default=None, help="Optional inclusive start time in ISO format")
    compact_parser.add_argument("--end-time", default=None, help="Optional inclusive end time in ISO format")
    compact_parser.add_argument("--evidence-limit", type=int, default=5, help="Maximum evidence items")
    compact_parser.add_argument("--fact-limit", type=int, default=5, help="Maximum fact items")
    compact_parser.add_argument("--episode-limit", type=int, default=3, help="Maximum episode items")
    compact_parser.add_argument("--max-chars", type=int, default=4000, help="Maximum context size in characters")
    _add_runtime_args(compact_parser)

    startup_parser = subparsers.add_parser(
        "prepare-startup-context",
        help="Prepare startup context for an agent entering the workspace",
    )
    startup_parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Optional query focus for startup context",
    )
    startup_parser.add_argument("--agent-name", default="assistant", help="Agent name label")
    startup_parser.add_argument("--evidence-limit", type=int, default=6, help="Maximum evidence items")
    startup_parser.add_argument("--fact-limit", type=int, default=6, help="Maximum fact items")
    startup_parser.add_argument("--episode-limit", type=int, default=4, help="Maximum episode items")
    startup_parser.add_argument("--max-chars", type=int, default=6000, help="Maximum startup context size")
    _add_runtime_args(startup_parser)

    migrate_parser = subparsers.add_parser(
        "migrate-legacy",
        help="Import a legacy Chroma palace into the new service-backed runtime",
    )
    migrate_parser.add_argument("palace_path", help="Path to the legacy Chroma palace directory")
    migrate_parser.add_argument(
        "--collection",
        default="mempalace_drawers",
        help="Legacy Chroma collection name (default: mempalace_drawers)",
    )
    _add_runtime_args(migrate_parser)


def build_exact_filters(args: argparse.Namespace) -> dict[str, str]:
    """Build exact-match metadata filters from CLI arguments."""
    filters: dict[str, str] = {}
    for raw in getattr(args, "filters", []) or []:
        if "=" not in raw:
            raise ValueError(f"Invalid filter '{raw}'. Expected key=value.")
        key, value = raw.split("=", 1)
        if not key.strip() or not value.strip():
            raise ValueError(f"Invalid filter '{raw}'. Expected key=value.")
        filters[key.strip()] = value.strip()

    wing = getattr(args, "wing", None)
    room = getattr(args, "room", None)
    if wing:
        filters["wing"] = wing
    if room:
        filters["room"] = room
    return filters


def build_search_request_from_args(args: argparse.Namespace) -> SearchRequest:
    """Construct a search request from parsed CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return SearchRequest(
        workspace_id=platform.settings.workspace_id,
        query=args.query,
        mode=SearchMode(args.mode),
        limit=args.limit,
        start_time=parse_datetime(args.start_time),
        end_time=parse_datetime(args.end_time, end_of_day_if_date=True),
        filters=build_exact_filters(args),
    )


def run_search_memory_service(args: argparse.Namespace) -> SearchResponse:
    """Execute a service-backed search from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    request = SearchRequest(
        workspace_id=platform.settings.workspace_id,
        query=args.query,
        mode=SearchMode(args.mode),
        limit=args.limit,
        start_time=parse_datetime(args.start_time),
        end_time=parse_datetime(args.end_time, end_of_day_if_date=True),
        filters=build_exact_filters(args),
    )
    return platform.search_request(request)


def run_status_health_service(args: argparse.Namespace) -> dict[str, object]:
    """Return health information for the service-backed runtime."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.health()


def run_init_project_service(args: argparse.Namespace) -> ProjectInitResult:
    """Initialize a project-scoped service runtime config."""
    return initialize_project_runtime(
        args.dir,
        workspace_id=getattr(args, "workspace_id", None),
        force=getattr(args, "force", False),
    )


def run_ingest_directory_service(args: argparse.Namespace) -> IngestionResult:
    """Execute a service-backed directory ingest from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    include_ignored: list[str] = []
    for raw in getattr(args, "include_ignored", []) or []:
        include_ignored.extend(part.strip() for part in raw.split(",") if part.strip())
    return platform.ingest_directory(
        args.dir,
        mode=args.mode,
        extract_mode=args.extract,
        wing_override=getattr(args, "wing", None),
        respect_gitignore=not getattr(args, "no_gitignore", False),
        include_ignored=include_ignored,
    )


def run_ingest_chat_history_service(args: argparse.Namespace) -> IngestionResult:
    """Execute chat-history ingest using the service-backed runtime."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.ingest_directory(
        args.dir,
        mode="convos",
        extract_mode=args.extract,
    )


def run_ingest_source_service(args: argparse.Namespace) -> IngestionResult:
    """Execute a service-backed single-source ingest from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.ingest_source(
        args.path,
        mode=args.mode,
        extract_mode=args.extract,
        wing_override=getattr(args, "wing", None),
    )


def run_migrate_legacy_service(args: argparse.Namespace) -> MigrationResult:
    """Execute a legacy Chroma migration through the service runtime."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.migrate_legacy_palace(args.palace_path, collection_name=args.collection)


def run_extract_facts_service(args: argparse.Namespace) -> FactExtractionResult:
    """Execute deterministic fact extraction from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.extract_facts(document_id=args.document_id)


def run_query_facts_service(args: argparse.Namespace) -> tuple[FactRecord, ...]:
    """Query structured facts from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.query_facts(
        query=args.query,
        subject=args.subject,
        predicate=args.predicate,
        object_text=args.object_text,
        limit=args.limit,
    )


def run_fetch_evidence_service(args: argparse.Namespace) -> EvidenceTrail:
    """Fetch a provenance trail from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.fetch_evidence_trail(
        fact_id=args.fact_id,
        segment_id=args.segment_id,
        document_id=args.document_id,
        neighbor_count=args.neighbor_count,
    )


def run_explain_retrieval_service(args: argparse.Namespace) -> SearchResponse:
    """Run retrieval and return the inspectable response payload."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.explain_retrieval(
        args.query,
        mode=SearchMode(args.mode),
        limit=args.limit,
        start_time=parse_datetime(args.start_time),
        end_time=parse_datetime(args.end_time, end_of_day_if_date=True),
        filters=build_exact_filters(args),
    )


def run_search_time_range_service(args: argparse.Namespace) -> SearchResponse:
    """Search within an explicit inclusive time window."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.search_by_time_range(
        args.query,
        start_time=parse_datetime(args.start_time),
        end_time=parse_datetime(args.end_time, end_of_day_if_date=True),
        mode=SearchMode(args.mode),
        limit=args.limit,
    )


def run_reindex_service(args: argparse.Namespace) -> ReindexResult:
    """Reindex vector entries from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.reindex(document_id=args.document_id)


def run_recall_episodes_service(args: argparse.Namespace):
    """Recall episodes from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.recall_episodes(
        query=args.query,
        start_time=parse_datetime(args.start_time),
        end_time=parse_datetime(args.end_time, end_of_day_if_date=True),
        limit=args.limit,
    )


def run_compact_session_context_service(args: argparse.Namespace) -> CompactedSessionContext:
    """Build a compact session context from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.compact_session_context(
        query=args.query,
        start_time=parse_datetime(args.start_time),
        end_time=parse_datetime(args.end_time, end_of_day_if_date=True),
        evidence_limit=args.evidence_limit,
        fact_limit=args.fact_limit,
        episode_limit=args.episode_limit,
        max_chars=args.max_chars,
    )


def run_prepare_startup_context_service(args: argparse.Namespace) -> StartupContext:
    """Build startup context from CLI arguments."""
    platform = build_platform(config_path=args.config, workspace_id=args.workspace)
    return platform.prepare_startup_context(
        agent_name=args.agent_name,
        query=args.query,
        evidence_limit=args.evidence_limit,
        fact_limit=args.fact_limit,
        episode_limit=args.episode_limit,
        max_chars=args.max_chars,
    )


def render_ingestion_result(result: IngestionResult) -> str:
    """Render a human-readable ingestion summary."""
    lines = []
    lines.append("")
    lines.append("=" * 55)
    lines.append("  Service Runtime Ingest")
    lines.append("=" * 55)
    lines.append(f"  Workspace:         {result.workspace_id}")
    lines.append(f"  Run ID:            {result.run_id}")
    lines.append(f"  Source type:       {result.source_type}")
    lines.append(f"  Files seen:        {result.files_seen}")
    lines.append(f"  Files read:        {result.files_read}")
    lines.append(f"  Documents written: {result.documents_written}")
    lines.append(f"  Documents updated: {result.documents_updated}")
    lines.append(f"  Documents skipped: {result.documents_skipped}")
    lines.append(f"  Segments written:  {result.segments_written}")
    if result.errors:
        lines.append(f"  Errors:            {len(result.errors)}")
    lines.append("")
    lines.append("  Files:")
    for file_result in result.file_results:
        document_id = file_result.document_id or "-"
        reason = f" ({file_result.reason})" if file_result.reason else ""
        lines.append(
            f"    {file_result.status:8} {file_result.uri} -> {document_id} +{file_result.segments_written}{reason}"
        )
    lines.append("")
    lines.append("=" * 55)
    lines.append("")
    return "\n".join(lines)


def render_project_init_result(result: ProjectInitResult) -> str:
    """Render a human-readable project initialization summary."""
    lines = []
    lines.append("")
    lines.append("=" * 55)
    lines.append("  Service Runtime Init")
    lines.append("=" * 55)
    lines.append(f"  Workspace:      {result.workspace_id}")
    lines.append(f"  Project:        {result.project_dir}")
    lines.append(f"  Local config:   {result.local_config_path}")
    lines.append(f"  Storage dir:    {result.storage_dir}")
    lines.append(f"  Metadata path:  {result.metadata_path}")
    lines.append(f"  Gitignore:      {result.gitignore_path}")
    lines.append(f"  Created:        {'yes' if result.created else 'no'}")
    lines.append(f"  Updated:        {'yes' if result.updated else 'no'}")
    lines.append("")
    lines.append("  Next:")
    lines.append("    mempalace ingest")
    lines.append("    mempalace ingest-chat-history /path/to/exports")
    lines.append("")
    return "\n".join(lines)


def render_migration_result(result: MigrationResult) -> str:
    """Render a human-readable migration summary."""
    lines = []
    lines.append("")
    lines.append("=" * 55)
    lines.append("  Service Runtime Legacy Migration")
    lines.append("=" * 55)
    lines.append(f"  Workspace:         {result.workspace_id}")
    lines.append(f"  Run ID:            {result.run_id}")
    lines.append(f"  Source type:       {result.source_type}")
    lines.append(f"  Drawers seen:      {result.drawers_seen}")
    lines.append(f"  Drawers migrated:  {result.drawers_migrated}")
    lines.append(f"  Drawers skipped:   {result.drawers_skipped}")
    lines.append(f"  Segments written:  {result.segments_written}")
    if result.errors:
        lines.append(f"  Errors:            {len(result.errors)}")
    lines.append("")
    lines.append("  Drawers:")
    for drawer_result in result.drawer_results:
        document_id = drawer_result.document_id or "-"
        reason = f" ({drawer_result.reason})" if drawer_result.reason else ""
        source_file = drawer_result.legacy_source_file or drawer_result.legacy_drawer_id
        lines.append(f"    {drawer_result.status:8} {source_file} -> {document_id}{reason}")
    lines.append("")
    lines.append("=" * 55)
    lines.append("")
    return "\n".join(lines)


def render_fact_extraction_result(result: FactExtractionResult) -> str:
    """Render a human-readable fact extraction summary."""
    lines = []
    lines.append("")
    lines.append("=" * 55)
    lines.append("  Service Runtime Fact Extraction")
    lines.append("=" * 55)
    lines.append(f"  Workspace:           {result.workspace_id}")
    lines.append(f"  Documents seen:      {result.documents_seen}")
    lines.append(f"  Documents processed: {result.documents_processed}")
    lines.append(f"  Facts written:       {result.facts_written}")
    lines.append(f"  Entities written:    {result.entities_written}")
    if result.errors:
        lines.append(f"  Errors:              {len(result.errors)}")
    lines.append("")
    lines.append("  Documents:")
    for document_result in result.document_results:
        reason = f" ({document_result.reason})" if document_result.reason else ""
        lines.append(
            f"    {document_result.status:9} {document_result.document_id} facts={document_result.facts_written} entities={document_result.entities_written}{reason}"
        )
    lines.append("")
    lines.append("=" * 55)
    lines.append("")
    return "\n".join(lines)


def render_search_response(response: SearchResponse) -> str:
    """Render a human-readable search response."""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append(f'  Service Results for: "{response.request.query}"')
    lines.append(f"  Workspace: {response.request.workspace_id}")
    lines.append(f"  Mode: {response.plan.mode.value}")
    lines.append("=" * 60)
    lines.append("")

    if not response.results:
        lines.append("  No results found.")
        lines.append("")
        return "\n".join(lines)

    for index, result in enumerate(response.results, start=1):
        lines.append(f"  [{index}] {result.document_title}")
        lines.append(f"      Source: {result.source_uri}")
        lines.append(f"      Score:  {result.scores.combined:.3f}")
        lines.append(f"      Why:    {result.retrieval_reason}")
        if result.timestamp:
            lines.append(f"      Time:   {result.timestamp.isoformat()}")
        lines.append("")
        for line in result.excerpt.strip().splitlines():
            lines.append(f"      {line}")
        lines.append("")
        lines.append(f"  {'─' * 56}")

    lines.append("")
    return "\n".join(lines)


def render_status_health(health: dict[str, object]) -> str:
    """Render a human-readable health summary."""
    counts = dict(health.get("counts", {}))
    lines = []
    lines.append("")
    lines.append("=" * 55)
    lines.append("  Service Runtime Status")
    lines.append("=" * 55)
    lines.append(f"  Workspace:      {health.get('workspace_id', 'unknown')}")
    lines.append(f"  Metadata path:  {health.get('metadata_path', '')}")
    lines.append(f"  Vector backend: {health.get('vector_backend', '')}")
    lines.append("")
    lines.append("  Counts:")
    for key in ("workspaces", "sources", "documents", "segments", "facts", "entities", "ingestion_runs"):
        lines.append(f"    {key:14} {counts.get(key, 0)}")
    lines.append("")
    lines.append("=" * 55)
    lines.append("")
    return "\n".join(lines)


def cmd_ingest_directory_service(args: argparse.Namespace) -> None:
    """Ingest a directory and print the structured result."""
    print(dumps_json(run_ingest_directory_service(args)))


def cmd_ingest_chat_history_service(args: argparse.Namespace) -> None:
    """Ingest chat history and print the structured result."""
    print(dumps_json(run_ingest_chat_history_service(args)))


def cmd_ingest_source_service(args: argparse.Namespace) -> None:
    """Ingest one source file and print the structured result."""
    print(dumps_json(run_ingest_source_service(args)))


def cmd_search_memory_service(args: argparse.Namespace) -> None:
    """Search memory using the retrieval service and print JSON."""
    response = run_search_memory_service(args)
    print(dumps_json(response))


def cmd_fetch_document_service(args: argparse.Namespace) -> None:
    """Fetch one document and its segments and print JSON."""
    platform = build_platform(config_path=args.config)
    document = platform.fetch_document(args.document_id)
    if document is None:
        print(dumps_json({"error": "Document not found", "document_id": args.document_id}))
        sys.exit(1)

    payload = {
        "document": document,
        "segments": platform.fetch_document_segments(args.document_id),
    }
    print(dumps_json(payload))


def cmd_status_health_service(args: argparse.Namespace) -> None:
    """Show health and record counts for the service-backed runtime."""
    print(dumps_json(run_status_health_service(args)))


def cmd_init_project_service(args: argparse.Namespace) -> None:
    """Initialize a project runtime config and print a readable summary."""
    print(render_project_init_result(run_init_project_service(args)))


def cmd_migrate_legacy_service(args: argparse.Namespace) -> None:
    """Migrate a legacy Chroma palace and print JSON."""
    print(dumps_json(run_migrate_legacy_service(args)))


def cmd_extract_facts_service(args: argparse.Namespace) -> None:
    """Extract deterministic facts and print JSON."""
    print(dumps_json(run_extract_facts_service(args)))


def cmd_query_facts_service(args: argparse.Namespace) -> None:
    """Query structured facts and print JSON."""
    print(dumps_json(run_query_facts_service(args)))


def cmd_fetch_evidence_service(args: argparse.Namespace) -> None:
    """Fetch an evidence trail and print JSON."""
    print(dumps_json(run_fetch_evidence_service(args)))


def cmd_explain_retrieval_service(args: argparse.Namespace) -> None:
    """Explain retrieval by returning the full search payload."""
    print(dumps_json(run_explain_retrieval_service(args)))


def cmd_search_time_range_service(args: argparse.Namespace) -> None:
    """Search memory within a time range and print JSON."""
    print(dumps_json(run_search_time_range_service(args)))


def cmd_reindex_service(args: argparse.Namespace) -> None:
    """Reindex stored vectors and print JSON."""
    print(dumps_json(run_reindex_service(args)))


def cmd_recall_episodes_service(args: argparse.Namespace) -> None:
    """Recall episodes and print JSON."""
    print(dumps_json(run_recall_episodes_service(args)))


def cmd_compact_session_context_service(args: argparse.Namespace) -> None:
    """Compact session context and print JSON."""
    print(dumps_json(run_compact_session_context_service(args)))


def cmd_prepare_startup_context_service(args: argparse.Namespace) -> None:
    """Prepare startup context and print JSON."""
    print(dumps_json(run_prepare_startup_context_service(args)))
