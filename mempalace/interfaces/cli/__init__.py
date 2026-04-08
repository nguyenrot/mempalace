"""CLI interface helpers for the service-backed core."""

from .service_cli import (
    add_service_cli_parsers,
    cmd_compact_session_context_service,
    cmd_explain_retrieval_service,
    cmd_fetch_evidence_service,
    cmd_fetch_document_service,
    cmd_ingest_directory_service,
    cmd_ingest_source_service,
    cmd_prepare_startup_context_service,
    cmd_recall_episodes_service,
    cmd_reindex_service,
    cmd_search_memory_service,
    cmd_search_time_range_service,
    cmd_status_health_service,
)

__all__ = [
    "add_service_cli_parsers",
    "cmd_compact_session_context_service",
    "cmd_explain_retrieval_service",
    "cmd_fetch_evidence_service",
    "cmd_fetch_document_service",
    "cmd_ingest_directory_service",
    "cmd_ingest_source_service",
    "cmd_prepare_startup_context_service",
    "cmd_recall_episodes_service",
    "cmd_reindex_service",
    "cmd_search_memory_service",
    "cmd_search_time_range_service",
    "cmd_status_health_service",
]
