"""Special command handling for the CLI entry point."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

OutputJsonFn = Callable[[dict[str, Any]], None]
OutputMessageFn = Callable[[Any], None]


@dataclass(frozen=True)
class SpecialCommandContext:
    """Runtime dependencies injected by cli_main for testable special commands."""

    asyncio_run: Callable[[Any], Any]
    output_json: OutputJsonFn
    output_error: OutputMessageFn
    output_info: OutputMessageFn
    output_list: OutputMessageFn
    query_loader: Any


def handle_special_commands(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Handle CLI commands that bypass the normal file-analysis command path."""
    handlers: tuple[Callable[[], int | None], ...] = (
        lambda: _handle_agent_skills(args, context),
        lambda: _handle_agent_workflow(args, context),
        lambda: _handle_batch_partial_read(args, context),
        lambda: _handle_health_check(args, context),
        lambda: _handle_batch_metrics(args, context),
        lambda: _handle_mcp_commands(args, context),
        lambda: _validate_partial_read_options(args, context.output_error),
        lambda: _handle_query_language_commands(args, context),
        lambda: _handle_sql_platform_commands(args, context),
    )

    for handler in handlers:
        result = handler()
        if result is not None:
            return result
    return None


def _handle_agent_skills(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Return the project-local agent skill inventory."""
    if not getattr(args, "agent_skills", False):
        return None
    from tree_sitter_analyzer.cli.agent_skills import build_agent_skills_inventory

    project_root = getattr(args, "project_root", None) or os.getcwd()
    result = build_agent_skills_inventory(
        project_root=project_root,
        skills_root=getattr(args, "agent_skills_root", None),
    )
    _print_result(result, args, context.output_json)
    return 0


def _handle_agent_workflow(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Return the SMART workflow pack as a structured CLI response."""
    if not getattr(args, "agent_workflow", False):
        return None
    from tree_sitter_analyzer.cli.agent_workflow import build_agent_workflow_pack

    project_root = getattr(args, "project_root", None) or os.getcwd()
    result = build_agent_workflow_pack(
        project_root=project_root,
        target_path=getattr(args, "file_path", None),
    )
    _print_result(result, args, context.output_json)
    return 0


def _effective_output_format(args: Any) -> str:
    """Return the user-visible output format."""
    fmt = getattr(args, "format", None) or getattr(args, "output_format", "json")
    return str(fmt)


def _tool_output_format(args: Any) -> str:
    """Return the json/toon output format accepted by MCP-equivalent tools."""
    fmt = _effective_output_format(args)
    return "toon" if fmt in {"toon", "text"} else "json"


def _print_result(
    result: dict[str, Any],
    args: Any,
    output_json: OutputJsonFn,
) -> None:
    """Print tool output in the requested visible format.

    r37aq (dogfood): replaced inline ``print(result.get("toon_content", ""))``
    with the shared ``output_toon`` helper. ``--code-patterns`` flagged
    the inline ``print`` as ``AP003``; the helper is the canonical TOON
    output channel (matches ``cli/commands/mcp_commands.py``).
    """
    if _effective_output_format(args) == "toon":
        from tree_sitter_analyzer.output_manager import output_toon

        output_toon(result.get("toon_content", ""))
    else:
        output_json(result)


def _load_requests_payload(args: Any) -> list[dict[str, Any]]:
    """Load batch partial-read requests from inline JSON or a file."""
    if getattr(args, "partial_read_requests_json", None):
        raw = args.partial_read_requests_json
    elif getattr(args, "partial_read_requests_file", None):
        with open(args.partial_read_requests_file, encoding="utf-8") as f:
            raw = f.read()
    else:
        raise ValueError("No batch requests source provided")

    payload = json.loads(raw)
    requests = (
        payload["requests"]
        if isinstance(payload, dict) and "requests" in payload
        else payload
    )
    if not isinstance(requests, list):
        raise ValueError("Batch requests must be a list or {'requests': [...]} JSON")
    return requests


def _load_file_paths(args: Any) -> list[str]:
    """Load and de-duplicate file paths for batch metrics."""
    paths: list[str] = []
    if getattr(args, "file_paths", None):
        paths.extend([str(path) for path in args.file_paths])
    if getattr(args, "files_from", None):
        with open(args.files_from, encoding="utf-8") as f:
            paths.extend(line.strip() for line in f.read().splitlines() if line.strip())

    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path in seen:
            continue
        unique.append(path)
        seen.add(path)
    return unique


def _is_batch_partial_read(args: Any) -> bool:
    """Return True when partial-read batch mode is active."""
    return bool(getattr(args, "partial_read", False)) and bool(
        getattr(args, "partial_read_requests_json", None)
        or getattr(args, "partial_read_requests_file", None)
    )


def _handle_batch_partial_read(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Run the MCP read-partial tool for batch partial-read requests."""
    if not _is_batch_partial_read(args):
        return None
    try:
        from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

        project_root = getattr(args, "project_root", None) or os.getcwd()
        tool = ReadPartialTool(project_root=project_root)
        result = context.asyncio_run(
            tool.execute(
                {
                    "requests": _load_requests_payload(args),
                    "output_format": _tool_output_format(args),
                    "format": "text",
                    "allow_truncate": bool(getattr(args, "allow_truncate", False)),
                    "fail_fast": bool(getattr(args, "fail_fast", False)),
                }
            )
        )
        _print_result(result, args, context.output_json)
        return 0 if result.get("success", False) else 1
    except Exception as exc:
        _emit_cli_error(
            args,
            context,
            "partial_read",
            f"Batch partial read failed: {exc}",
            error_type="runtime",
        )
        return 1


def _handle_health_check(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Run the project health tool for --health-check."""
    if not getattr(args, "health_check", False):
        return None
    try:
        from tree_sitter_analyzer.mcp.tools.project_health_tool import ProjectHealthTool

        project_root = getattr(args, "project_root", None) or os.getcwd()
        tool = ProjectHealthTool(project_root=project_root)
        result = context.asyncio_run(
            tool.execute(
                {
                    "min_grade": getattr(args, "min_grade", "D"),
                    "max_files": getattr(args, "max_files", 30),
                    "output_format": _tool_output_format(args),
                }
            )
        )
        _print_result(result, args, context.output_json)
        return 0 if result.get("success", False) else 1
    except Exception as exc:
        _emit_cli_error(
            args,
            context,
            "health_check",
            f"Project health check failed: {exc}",
            error_type="runtime",
        )
        return 1


def _emit_cli_error(
    args: Any,
    context: SpecialCommandContext,
    flag_name: str,
    message: str,
    *,
    error_type: str = "validation",
) -> None:
    """r37al (dogfood): emit error in JSON envelope when caller asked for JSON.

    Mirrors the MCP-bridged ``_build_error_envelope`` shape used by
    ``mcp_commands.py`` (fixed in r37ah). Without this, CLI commands
    in this module surfaced errors to stderr only — agents using
    ``--format json`` got empty stdout and a non-zero exit code with
    no machine-readable context.
    """
    if _effective_output_format(args) == "json":
        summary_line = f"{flag_name}: error — {message}"
        context.output_json(
            {
                "success": False,
                "error_type": error_type,
                "error": message,
                "summary_line": summary_line,
                "verdict": "ERROR",
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": "Fix the input and retry.",
                    "verdict": "ERROR",
                },
            }
        )
    else:
        context.output_error(message)


def _handle_batch_metrics(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Run the scale-analysis tool for batch metrics mode."""
    if not getattr(args, "metrics_only", False):
        return None
    file_paths = _load_file_paths(args)
    if not file_paths:
        _emit_cli_error(
            args,
            context,
            "metrics_only",
            "--metrics-only requires --file-paths or --files-from",
        )
        return 1
    try:
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        project_root = getattr(args, "project_root", None) or os.getcwd()
        tool = AnalyzeScaleTool(project_root=project_root)
        result = context.asyncio_run(
            tool.execute(
                {
                    "file_paths": file_paths,
                    "metrics_only": True,
                    "output_format": _tool_output_format(args),
                }
            )
        )
        _print_result(result, args, context.output_json)
        return 0 if result.get("success", False) else 1
    except Exception as exc:
        _emit_cli_error(
            args,
            context,
            "metrics_only",
            f"Batch metrics failed: {exc}",
            error_type="runtime",
        )
        return 1


def _handle_mcp_commands(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Delegate MCP-equivalent CLI commands to the command table."""
    from .commands.mcp_commands import handle_mcp_commands

    return handle_mcp_commands(
        args,
        context.output_json,
        context.output_error,
        lambda: _tool_output_format(args),
    )


def _validate_partial_read_options(
    args: Any,
    output_error: OutputMessageFn,
) -> int | None:
    """Validate single-range partial-read options."""
    if not getattr(args, "partial_read", False):
        return None
    if args.start_line is None:
        output_error("--start-line is required")
        return 1
    if args.start_line < 1:
        output_error("--start-line must be 1 or greater")
        return 1
    if args.end_line and args.end_line < args.start_line:
        output_error("--end-line must be greater than or equal to --start-line")
        return 1
    if args.start_column is not None and args.start_column < 0:
        output_error("--start-column must be 0 or greater")
        return 1
    if args.end_column is not None and args.end_column < 0:
        output_error("--end-column must be 0 or greater")
        return 1
    return None


from .output_format import wants_json_output as _wants_json  # noqa: E402


def _handle_query_language_commands(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Handle query-language discovery commands.

    r37aq (dogfood): the project's own ``--code-patterns`` flagged this
    as an 80-line ``long_method`` + ``deep_nesting`` depth-5. Split the
    two ``show_*`` branches into named helpers — same pattern as r37ao
    ``DescribeQueryCommand.execute`` refactor.
    """
    if getattr(args, "show_query_languages", False):
        return _emit_show_query_languages(args, context)
    if getattr(args, "show_common_queries", False):
        return _emit_show_common_queries(args, context)
    return None


def _emit_show_query_languages(
    args: Any,
    context: SpecialCommandContext,
) -> int:
    """Emit ``--show-query-languages`` in the active JSON-or-text format."""
    languages_info = [
        {
            "language": language,
            "query_count": len(
                context.query_loader.list_queries_for_language(language)
            ),
        }
        for language in context.query_loader.list_supported_languages()
    ]
    if _wants_json(args):
        summary_line = (
            f"show_query_languages: {len(languages_info)} languages with query support"
        )
        context.output_json(
            {
                "success": True,
                "languages": languages_info,
                "language_count": len(languages_info),
                "summary_line": summary_line,
                "verdict": "INFO",
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": (
                        "Run --list-queries --language=<name> for that "
                        "language's full query catalogue."
                    ),
                    "verdict": "INFO",
                },
            }
        )
        return 0
    context.output_list(["Languages with query support:"])
    for entry in languages_info:
        context.output_list(
            [f"  {entry['language']:<15} ({entry['query_count']} queries)"]
        )
    return 0


def _emit_show_common_queries(
    args: Any,
    context: SpecialCommandContext,
) -> int:
    """Emit ``--show-common-queries`` in the active JSON-or-text format."""
    common_queries = list(context.query_loader.get_common_queries())
    if _wants_json(args):
        count = len(common_queries)
        summary_line = (
            f"show_common_queries: {count} queries common to multiple languages"
            if count
            else "show_common_queries: 0 common queries found"
        )
        context.output_json(
            {
                "success": True,
                "common_queries": common_queries,
                "query_count": count,
                "summary_line": summary_line,
                "verdict": "INFO",
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": (
                        "Use --query-key <key> --language <lang> to run "
                        "one of these queries."
                    ),
                    "verdict": "INFO",
                },
            }
        )
        return 0
    if common_queries:
        context.output_list("Common queries across multiple languages:")
        for query in common_queries:
            context.output_list(f"  {query}")
    else:
        context.output_info("No common queries found.")
    return 0


def _handle_sql_platform_commands(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Handle SQL platform compatibility commands."""
    if getattr(args, "sql_platform_info", False):
        from .commands.sql_platform_helpers import handle_sql_platform_info

        return handle_sql_platform_info(context.output_list, context.output_json, args)
    if getattr(args, "record_sql_profile", False):
        from .commands.sql_platform_helpers import handle_record_sql_profile

        return handle_record_sql_profile(context.output_info, context.output_error)
    if getattr(args, "compare_sql_profiles", None):
        from .commands.sql_platform_helpers import handle_compare_sql_profiles

        return handle_compare_sql_profiles(
            args.compare_sql_profiles,
            context.output_error,
        )
    return None
