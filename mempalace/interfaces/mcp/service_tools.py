"""MCP tools backed by the refactored service core."""

from __future__ import annotations

from mempalace.domain.models import SearchMode, SearchRequest
from mempalace.interfaces.runtime import build_platform, parse_datetime, to_primitive


def tool_status_health_service(config_path: str = None, workspace_id: str = None):
    """Return service-runtime health and storage counts."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    return to_primitive(platform.health())


def tool_ingest_directory_service(
    directory: str,
    mode: str = "projects",
    extract_mode: str = "exchange",
    wing: str = None,
    respect_gitignore: bool = True,
    include_ignored: list[str] | None = None,
    config_path: str = None,
    workspace_id: str = None,
):
    """Ingest a directory through the service-backed runtime."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.ingest_directory(
        directory,
        mode=mode,
        extract_mode=extract_mode,
        wing_override=wing,
        respect_gitignore=respect_gitignore,
        include_ignored=include_ignored,
    )
    return to_primitive(result)


def tool_ingest_source_service(
    path: str,
    mode: str = "projects",
    extract_mode: str = "exchange",
    wing: str = None,
    config_path: str = None,
    workspace_id: str = None,
):
    """Ingest one explicit source file through the service-backed runtime."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.ingest_source(
        path,
        mode=mode,
        extract_mode=extract_mode,
        wing_override=wing,
    )
    return to_primitive(result)


def tool_migrate_legacy_service(
    palace_path: str,
    collection_name: str = "mempalace_drawers",
    config_path: str = None,
    workspace_id: str = None,
):
    """Import a legacy Chroma palace through the service-backed runtime."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.migrate_legacy_palace(palace_path, collection_name=collection_name)
    return to_primitive(result)


def tool_extract_facts_service(
    document_id: str = None,
    config_path: str = None,
    workspace_id: str = None,
):
    """Extract deterministic structured facts through the service-backed runtime."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.extract_facts(document_id=document_id)
    return to_primitive(result)


def tool_query_facts_service(
    query: str = None,
    subject: str = None,
    predicate: str = None,
    object_text: str = None,
    limit: int = 20,
    config_path: str = None,
    workspace_id: str = None,
):
    """Query structured facts through the service-backed runtime."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.query_facts(
        query=query,
        subject=subject,
        predicate=predicate,
        object_text=object_text,
        limit=limit,
    )
    return to_primitive(result)


def tool_fetch_evidence_trail_service(
    fact_id: str = None,
    segment_id: str = None,
    document_id: str = None,
    neighbor_count: int = 1,
    config_path: str = None,
    workspace_id: str = None,
):
    """Fetch a provenance trail around a fact, segment, or document."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.fetch_evidence_trail(
        fact_id=fact_id,
        segment_id=segment_id,
        document_id=document_id,
        neighbor_count=neighbor_count,
    )
    return to_primitive(result)


def tool_search_memory_service(
    query: str,
    limit: int = 5,
    mode: str = "hybrid",
    start_time: str = None,
    end_time: str = None,
    wing: str = None,
    room: str = None,
    filters: dict[str, str] | None = None,
    config_path: str = None,
    workspace_id: str = None,
):
    """Search memory through the service-backed runtime."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    exact_filters = dict(filters or {})
    if wing:
        exact_filters["wing"] = wing
    if room:
        exact_filters["room"] = room
    request = SearchRequest(
        workspace_id=platform.settings.workspace_id,
        query=query,
        mode=SearchMode(mode),
        limit=limit,
        start_time=parse_datetime(start_time),
        end_time=parse_datetime(end_time, end_of_day_if_date=True),
        filters=exact_filters,
    )
    response = platform.search_request(request)
    return to_primitive(response)


def tool_search_time_range_service(
    query: str,
    start_time: str,
    end_time: str,
    limit: int = 5,
    mode: str = "hybrid",
    config_path: str = None,
    workspace_id: str = None,
):
    """Search memory through an explicit time range."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    response = platform.search_by_time_range(
        query,
        start_time=parse_datetime(start_time),
        end_time=parse_datetime(end_time, end_of_day_if_date=True),
        mode=SearchMode(mode),
        limit=limit,
    )
    return to_primitive(response)


def tool_explain_retrieval_service(
    query: str,
    limit: int = 5,
    mode: str = "hybrid",
    start_time: str = None,
    end_time: str = None,
    wing: str = None,
    room: str = None,
    filters: dict[str, str] | None = None,
    config_path: str = None,
    workspace_id: str = None,
):
    """Return the inspectable retrieval payload used by the service runtime."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    exact_filters = dict(filters or {})
    if wing:
        exact_filters["wing"] = wing
    if room:
        exact_filters["room"] = room
    response = platform.explain_retrieval(
        query,
        mode=SearchMode(mode),
        limit=limit,
        start_time=parse_datetime(start_time),
        end_time=parse_datetime(end_time, end_of_day_if_date=True),
        filters=exact_filters,
    )
    return to_primitive(response)


def tool_fetch_document_service(
    document_id: str,
    config_path: str = None,
):
    """Fetch one document and its segments from the service-backed runtime."""
    platform = build_platform(config_path=config_path)
    document = platform.fetch_document(document_id)
    if document is None:
        return {"error": "Document not found", "document_id": document_id}
    return to_primitive(
        {
            "document": document,
            "segments": platform.fetch_document_segments(document_id),
        }
    )


def tool_reindex_service(
    document_id: str = None,
    config_path: str = None,
    workspace_id: str = None,
):
    """Rebuild vector entries from stored segments."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.reindex(document_id=document_id)
    return to_primitive(result)


def tool_recall_episodes_service(
    query: str = None,
    start_time: str = None,
    end_time: str = None,
    limit: int = 5,
    config_path: str = None,
    workspace_id: str = None,
):
    """Recall recent or query-matched episodes."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.recall_episodes(
        query=query,
        start_time=parse_datetime(start_time),
        end_time=parse_datetime(end_time, end_of_day_if_date=True),
        limit=limit,
    )
    return to_primitive(result)


def tool_compact_session_context_service(
    query: str = None,
    start_time: str = None,
    end_time: str = None,
    evidence_limit: int = 5,
    fact_limit: int = 5,
    episode_limit: int = 3,
    max_chars: int = 4000,
    config_path: str = None,
    workspace_id: str = None,
):
    """Assemble a compact agent-ready context block."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.compact_session_context(
        query=query,
        start_time=parse_datetime(start_time),
        end_time=parse_datetime(end_time, end_of_day_if_date=True),
        evidence_limit=evidence_limit,
        fact_limit=fact_limit,
        episode_limit=episode_limit,
        max_chars=max_chars,
    )
    return to_primitive(result)


def tool_prepare_startup_context_service(
    agent_name: str = "assistant",
    query: str = None,
    evidence_limit: int = 6,
    fact_limit: int = 6,
    episode_limit: int = 4,
    max_chars: int = 6000,
    config_path: str = None,
    workspace_id: str = None,
):
    """Prepare startup context for an agent entering the workspace."""
    platform = build_platform(config_path=config_path, workspace_id=workspace_id)
    result = platform.prepare_startup_context(
        agent_name=agent_name,
        query=query,
        evidence_limit=evidence_limit,
        fact_limit=fact_limit,
        episode_limit=episode_limit,
        max_chars=max_chars,
    )
    return to_primitive(result)
