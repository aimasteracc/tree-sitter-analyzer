"""Tool-args builder functions for MCP-bridged CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEPENDENCY_FILE_SCOPED_MODES = {"blast_radius", "file_deps"}
_DEPENDENCY_MODE_ALIASES = {"full": "summary"}


def _normalize_dependency_mode(mode: str | None) -> str:
    return _DEPENDENCY_MODE_ALIASES.get(mode or "summary", mode or "summary")


def _dependency_mode_requires_file(args: Any) -> bool:
    return (
        _normalize_dependency_mode(getattr(args, "dependencies", None))
        in _DEPENDENCY_FILE_SCOPED_MODES
    )


def _build_dependency_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    mode = _normalize_dependency_mode(getattr(args, "dependencies", None))
    tool_args = {
        "mode": mode,
        "output_format": output_format,
    }
    if mode in _DEPENDENCY_FILE_SCOPED_MODES:
        tool_args["file_path"] = args.file_path
    return tool_args


def _build_detect_routes_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --detect-routes, omitting empty optional keys."""
    tool_args: dict[str, Any] = {
        "mode": getattr(args, "detect_routes_mode", "summary") or "summary",
        "framework": getattr(args, "detect_routes_framework", "all") or "all",
        "output_format": output_format,
    }
    url_pattern = getattr(args, "detect_routes_url", None)
    if url_pattern:
        tool_args["url_pattern"] = url_pattern
    file_path = getattr(args, "detect_routes_file", None)
    if file_path:
        tool_args["file_path"] = file_path
    return tool_args


def _build_parser_readiness_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for parser-readiness CLI alias and flag modes."""
    return {
        "language": getattr(args, "parser_readiness_language", None)
        or getattr(args, "file_path", None),
        "include_supported": bool(
            getattr(args, "parser_readiness_include_supported", False)
        ),
        "output_format": output_format,
    }


def _build_trace_impact_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --trace-impact, omitting empty optional keys.

    The TraceImpactTool schema does not accept ``output_format``, so the
    dispatcher must not forward it here — callers receive JSON envelopes
    by default and can post-process to TOON via the ``toon_content`` field
    if the tool produces one.
    """
    tool_args: dict[str, Any] = {
        "symbol": getattr(args, "trace_impact_symbol", "") or "",
    }
    file_path = getattr(args, "trace_impact_file", None) or getattr(
        args, "file_path", None
    )
    if file_path:
        tool_args["file_path"] = file_path
    roots = getattr(args, "trace_impact_roots", None)
    if roots:
        tool_args["project_root"] = roots
    return tool_args


def _build_batch_search_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --batch-search (T2 round-37d parity fix).

    BatchSearchTool's schema is ``{queries: array<{pattern, roots?, ...}>}``.
    The CLI accepts a JSON file with the queries array (a single CLI flag
    cannot encode a list of dicts cleanly). Validation, schema strictness,
    and the 2-10 queries cap are enforced by the tool itself.

    ``output_format`` is not on the schema (additionalProperties: false),
    so we don't forward it — the CLI's format handler emits the response
    in the requested format after the tool returns.
    """
    del output_format  # BatchSearchTool currently ignores output_format
    queries_path = getattr(args, "batch_search_queries_json", None)
    if not queries_path:
        raise ValueError(
            "--batch-search requires --batch-search-queries-json PATH "
            "pointing to a JSON array of query objects"
        )

    try:
        text = Path(queries_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"Cannot read batch_search queries file '{queries_path}': {exc}"
        ) from exc
    try:
        queries = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"--batch-search-queries-json '{queries_path}' is not valid JSON: {exc}"
        ) from exc
    if not isinstance(queries, list):
        raise ValueError(
            f"--batch-search-queries-json '{queries_path}' must contain a JSON array"
        )
    return {"queries": queries}


def _build_modification_guard_tool_args(
    args: Any, output_format: str
) -> dict[str, Any]:
    """Build tool args for --modification-guard (T1 round-37c parity fix).

    Schema requires ``symbol`` + ``modification_type``; ``file_path`` is
    optional. ModificationGuardTool's schema does not accept
    ``output_format`` (same as trace_impact / check_tools /
    build_project_index — see R4), so we don't forward it. The CLI's
    own format handler still emits the response in the requested format
    after the tool returns.
    """
    del output_format  # ModificationGuardTool currently ignores output_format
    symbol = getattr(args, "modification_guard_symbol", None) or ""
    mod_type = getattr(args, "modification_guard_type", None) or ""
    tool_args: dict[str, Any] = {
        "symbol": symbol,
        "modification_type": mod_type,
    }
    file_path = getattr(args, "modification_guard_file", None) or getattr(
        args, "file_path", None
    )
    if file_path:
        tool_args["file_path"] = file_path
    return tool_args


def _build_decision_journal_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --decision-journal (r37fG CLI-MCP parity).

    Mirrors DecisionJournalTool's four-mode schema. Only forwards the
    fields the chosen mode actually needs so the contract test matrix
    can drive the tool with the minimum viable argument shape.
    """
    mode = getattr(args, "decision_journal_mode", "search") or "search"
    tool_args: dict[str, Any] = {"mode": mode, "output_format": output_format}
    if mode == "record":
        if (title := getattr(args, "decision_journal_title", None)) is not None:
            tool_args["title"] = title
        if (rationale := getattr(args, "decision_journal_rationale", None)) is not None:
            tool_args["rationale"] = rationale
        if (verdict := getattr(args, "decision_journal_verdict", None)) is not None:
            tool_args["verdict"] = verdict
        if (tags := getattr(args, "decision_journal_tags", None)) is not None:
            tool_args["tags"] = tags
    elif mode == "get":
        if (rec_id := getattr(args, "decision_journal_id", None)) is not None:
            tool_args["id"] = rec_id
    elif mode == "search":
        if (query := getattr(args, "decision_journal_query", None)) is not None:
            tool_args["query"] = query
        if (vf := getattr(args, "decision_journal_verdict_filter", None)) is not None:
            tool_args["verdict_filter"] = vf
        tool_args["limit"] = int(getattr(args, "decision_journal_limit", 20) or 20)
    elif mode == "supersede":
        if (rec_id := getattr(args, "decision_journal_id", None)) is not None:
            tool_args["id"] = rec_id
        if (new_id := getattr(args, "decision_journal_new_id", None)) is not None:
            tool_args["new_id"] = new_id
    return tool_args


def _build_check_tools_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --check-tools.

    The CheckToolsTool schema accepts no input properties (only checks
    whether fd/rg are available), so we forward an empty dict.
    """
    del args, output_format  # CheckToolsTool takes no inputs
    return {}


def _build_build_project_index_tool_args(
    args: Any, output_format: str
) -> dict[str, Any]:
    """Build tool args for --build-project-index.

    Mirrors :class:`BuildProjectIndexTool`'s schema — ``roots`` (list of
    directories) and ``add_notes`` (string). ``output_format`` is not on
    the schema so we omit it.
    """
    del output_format  # BuildProjectIndexTool currently ignores output_format
    tool_args: dict[str, Any] = {}
    roots = getattr(args, "build_project_index_roots", None)
    if roots:
        tool_args["roots"] = roots
    notes = getattr(args, "build_project_index_notes", None)
    if notes:
        tool_args["add_notes"] = notes
    return tool_args


def _build_change_impact_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    tool_args = {
        "mode": getattr(args, "change_impact_mode", "diff") or "diff",
        "pr_url": getattr(args, "pr_url", "") or "",
        "include_tests": bool(getattr(args, "change_impact_include_tests", True)),
        "output_format": output_format,
        "scope_paths": getattr(args, "change_impact_scope", None) or [],
        "scope_mode": getattr(args, "change_impact_scope_mode", "report") or "report",
        "agent_summary_only": not bool(getattr(args, "change_impact_full", False)),
        "compact_only": bool(getattr(args, "compact_toon", False)),
    }
    # Always pass resource_profile explicitly so the MCP tool's fallback default
    # ("local_low_impact" for MCP callers) never silently overrides the CLI path.
    tool_args["resource_profile"] = (
        getattr(args, "change_impact_resource_profile", "default") or "default"
    )
    return tool_args


def _build_codegraph_status_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    return {
        "include_lag": not bool(getattr(args, "codegraph_status_no_lag", False)),
        "output_format": output_format,
    }


def _build_codegraph_explore_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    return {
        "query": getattr(args, "codegraph_explore", "") or "",
        "maxFiles": getattr(args, "codegraph_explore_max_files", 12),
        "maxSymbols": getattr(args, "codegraph_explore_max_symbols", 20),
        "includeCode": not bool(getattr(args, "codegraph_explore_outline_only", False)),
        "output_format": output_format,
    }


def _build_codegraph_query_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    return {
        "query": getattr(args, "codegraph_query", "") or "",
        "max_symbols": getattr(args, "codegraph_query_max_symbols", 20),
        "max_files": getattr(args, "codegraph_query_max_files", 8),
        "include_code": not bool(getattr(args, "codegraph_query_outline_only", False)),
        "compact": bool(getattr(args, "codegraph_query_compact", False)),
        "output_format": output_format,
    }


def _build_code_similarity_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    return {
        "mode": getattr(args, "code_similarity_mode", "all") or "all",
        "min_lines": getattr(args, "code_similarity_min_lines", 5) or 5,
        "min_group_size": getattr(args, "code_similarity_min_group", 2) or 2,
        "max_groups": getattr(args, "code_similarity_max_groups", 20) or 20,
        "use_cache": not bool(getattr(args, "code_similarity_no_cache", False)),
        "include_bodies": bool(getattr(args, "code_similarity_include_bodies", False)),
        "output_format": output_format,
    }


def _build_uml_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    tool_args: dict[str, Any] = {
        "diagram": getattr(args, "uml", "class") or "class",
        "source": getattr(args, "uml_source", None),
        "target": getattr(args, "uml_target", None),
        "max_edges": getattr(args, "uml_max_edges", 80),
        "max_depth": getattr(args, "uml_max_depth", 8),
        "max_paths": getattr(args, "uml_max_paths", 3),
        "package_depth": getattr(args, "uml_package_depth", 2),
        "include_external_bases": not bool(
            getattr(args, "uml_no_external_bases", False)
        ),
        "output_format": output_format,
    }
    # P1 scoping params (RFC-0015): only forward when provided
    file_path = getattr(args, "uml_file_path", None)
    if file_path:
        tool_args["file_path"] = file_path
    class_name = getattr(args, "uml_class_name", None)
    if class_name:
        tool_args["class_name"] = class_name
    if getattr(args, "uml_include_tests", False):
        tool_args["include_tests"] = True
    # P2 params (RFC-0015): activity + state diagrams
    function_name = getattr(args, "uml_function", None)
    if function_name:
        tool_args["function_name"] = function_name
    max_nodes = getattr(args, "uml_max_nodes", None)
    if max_nodes is not None:
        tool_args["max_nodes"] = max_nodes
    return tool_args
