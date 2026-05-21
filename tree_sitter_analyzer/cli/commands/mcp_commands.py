#!/usr/bin/env python3
"""MCP-equivalent CLI command handlers."""

import asyncio
import json
import os
from collections.abc import Callable, Mapping
from typing import Any

from tree_sitter_analyzer.cli.commands.mcp_command_helpers import (
    McpCommandSpec,
    build_mcp_tool_args,
    find_selected_mcp_command,
    validate_mcp_command_args,
)

# These imports look unused — they're consumed via ``globals()`` inside
# :func:`_get_tool_class` so that tests can monkeypatch the names at
# module level — see ``tests/unit/cli/test_mcp_commands.py``.
# noqa codes keep refactor-cleaner / autoflake / ruff from stripping them.
from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool  # noqa: F401
from tree_sitter_analyzer.mcp.tools.batch_search_tool import (
    BatchSearchTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.build_project_index_tool import (
    BuildProjectIndexTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.call_graph_tool import (
    CodeGraphCallTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
    ChangeImpactTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.check_tools_tool import (
    CheckToolsTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
    CodePatternsTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
    DependencyAnalysisTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool  # noqa: F401
from tree_sitter_analyzer.mcp.tools.modification_guard_tool import (
    ModificationGuardTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.parser_readiness_tool import (
    ParserReadinessTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.project_health_tool import (
    ProjectHealthTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
    ProjectOverviewTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
    RefactoringSuggestionsTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
    RouteDetectorTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
    SafeToEditTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.smart_context_tool import (
    SmartContextTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import (
    SymbolLineageTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
    TraceImpactTool,  # noqa: F401
)

_DEPENDENCY_FILE_SCOPED_MODES = {"blast_radius", "file_deps"}
_DEPENDENCY_MODE_ALIASES = {"full": "summary"}


def _normalize_dependency_mode(mode: str | None) -> str:
    return _DEPENDENCY_MODE_ALIASES.get(mode or "summary", mode or "summary")


def _dependency_mode_requires_file(args: Any) -> bool:
    return (
        _normalize_dependency_mode(getattr(args, "dependencies", None))
        in _DEPENDENCY_FILE_SCOPED_MODES
    )


def _maybe_add_language(tool_args: dict[str, Any], args: Any) -> dict[str, Any]:
    """Forward ``--language`` from CLI args into the MCP tool's args dict.

    O8 (round-30 dogfood): the CLI used to drop ``--language`` for tools
    like ``--refactor`` so the MCP-side mismatch gate never fired. This
    helper copies the value across only when the user actually passed
    one — keeping the auto-detect path untouched for callers that omit
    the flag.
    """
    language = getattr(args, "language", None)
    if isinstance(language, str) and language.strip():
        tool_args["language"] = language
    return tool_args


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
    """Build tool args for --detect-routes, omitting empty optional keys.

    M4 (round-26 dogfood): when the user passes a positional path to
    ``--detect-routes`` (e.g. ``tree-sitter-analyzer --detect-routes
    /tmp/file.py``), the path used to be silently dropped. The tool would
    scan the project root and report ``total_routes=0`` regardless of the
    nonsense path — agents read this as "the file you asked about has no
    routes" when in reality the file was never scanned.

    Now we treat a positional path as an implicit ``--detect-routes-file``
    *only when* the path exists and is a file. A non-existent path raises
    ``ValueError`` so the dispatcher's error envelope fires (matching
    ``--file-health`` / ``--code-patterns`` / ``--safe-to-edit``). A
    directory raises ``ValueError`` with a hint pointing at
    ``--detect-routes-mode all`` or ``--roots`` for project-wide scans.
    """
    import os as _os

    mode = getattr(args, "detect_routes_mode", "summary") or "summary"
    framework = getattr(args, "detect_routes_framework", "all") or "all"
    tool_args: dict[str, Any] = {
        "mode": mode,
        "framework": framework,
        "output_format": output_format,
    }
    url_pattern = getattr(args, "detect_routes_url", None)
    if url_pattern:
        tool_args["url_pattern"] = url_pattern
    file_path = getattr(args, "detect_routes_file", None)
    positional_path = getattr(args, "file_path", None)

    # If the user passed an explicit ``--detect-routes-file`` we honour
    # that as before. Otherwise, treat the positional ``file_path`` as
    # an implicit file argument — but validate it instead of silently
    # falling through to a project-root scan.
    candidate = file_path if file_path else positional_path
    if candidate:
        if not _os.path.exists(candidate):
            raise ValueError(f"file not found: {candidate}")
        if _os.path.isdir(candidate):
            raise ValueError(
                f"path is a directory: {candidate} — use "
                "--detect-routes-mode all for a project-wide scan, "
                "or pass an individual file"
            )
        if not _os.path.isfile(candidate):
            raise ValueError(f"not a regular file: {candidate}")
        tool_args["file_path"] = candidate
        # Auto-promote to ``mode=file`` when the user supplied a file
        # path but left ``--detect-routes-mode`` at the default. Keeps
        # the experience consistent with ``--file-health <path>``.
        if mode == "summary":
            tool_args["mode"] = "file"
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
    import json
    from pathlib import Path

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


MCP_COMMAND_SPECS: tuple[McpCommandSpec, ...] = (
    McpCommandSpec(
        flag_name="file_health",
        tool_attr="FileHealthTool",
        label="File health check",
        required_file_error="--file-health requires a file path",
        # O3 (round-30 dogfood): forward ``--language`` so the tool's
        # strict mismatch gate can refuse e.g. ``--file-health foo.py
        # --language java``.
        build_tool_args=lambda args, output_format: _maybe_add_language(
            {
                "file_path": args.file_path,
                "output_format": output_format,
            },
            args,
        ),
    ),
    McpCommandSpec(
        flag_name="project_health",
        tool_attr="ProjectHealthTool",
        label="Project health check",
        build_tool_args=lambda args, output_format: {
            "min_grade": getattr(args, "min_grade", "D"),
            "max_files": getattr(args, "max_files", 30),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="overview",
        tool_attr="ProjectOverviewTool",
        label="Project overview",
        build_tool_args=lambda args, output_format: {
            "include_health": True,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="safe_to_edit",
        tool_attr="SafeToEditTool",
        label="Safe to edit",
        required_file_error="--safe-to-edit requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "edit_type": getattr(args, "edit_type", "refactor") or "refactor",
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="change_impact",
        tool_attr="ChangeImpactTool",
        label="Change impact analysis",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "change_impact_mode", "diff") or "diff",
            "pr_url": getattr(args, "pr_url", "") or "",
            "include_tests": bool(getattr(args, "change_impact_include_tests", True)),
            "output_format": output_format,
            "scope_paths": getattr(args, "change_impact_scope", None) or [],
            "agent_summary_only": bool(getattr(args, "agent_summary_only", False)),
        },
    ),
    McpCommandSpec(
        flag_name="parser_readiness",
        tool_attr="ParserReadinessTool",
        label="Parser readiness advisor",
        build_tool_args=_build_parser_readiness_tool_args,
    ),
    McpCommandSpec(
        flag_name="dependencies",
        tool_attr="DependencyAnalysisTool",
        label="Dependency analysis",
        required_file_error=(
            "--dependencies requires a file path for file_deps and blast_radius modes"
        ),
        requires_file=_dependency_mode_requires_file,
        build_tool_args=_build_dependency_tool_args,
    ),
    McpCommandSpec(
        flag_name="refactor",
        tool_attr="RefactoringSuggestionsTool",
        label="Refactoring suggestions",
        required_file_error="--refactor requires a file path",
        # O8 (round-30 dogfood): forward ``--language`` so the tool's
        # strict mismatch gate can refuse e.g. ``--refactor foo.py
        # --language java`` instead of silently returning verdict=SAFE.
        build_tool_args=lambda args, output_format: _maybe_add_language(
            {
                "file_path": args.file_path,
                "output_format": output_format,
            },
            args,
        ),
    ),
    McpCommandSpec(
        flag_name="smart_context",
        tool_attr="SmartContextTool",
        label="Smart context",
        required_file_error="--smart-context requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="symbol_lineage",
        tool_attr="SymbolLineageTool",
        label="Symbol lineage and impact preview",
        # M12: ``--symbol-lineage SYMBOL`` is a value-bearing flag —
        # treat ``--symbol-lineage ""`` as selected (not "no command")
        # so the dispatcher emits a canonical validation envelope
        # instead of falling through to the file-analysis crash path.
        value_arg_name="symbol_lineage",
        required_value_error=(
            "--symbol-lineage requires a non-empty symbol name (got empty string)"
        ),
        build_tool_args=lambda args, output_format: {
            "symbol": getattr(args, "symbol_lineage", "") or "",
            "max_depth": getattr(args, "max_depth", 3),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="code_patterns",
        tool_attr="CodePatternsTool",
        label="Code pattern and anti-pattern detection",
        required_file_error="--code-patterns requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "categories": getattr(args, "code_patterns_categories", None) or ["all"],
            "severity_threshold": getattr(args, "severity_threshold", "info") or "info",
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="call_graph",
        tool_attr="CodeGraphCallTool",
        label="Function-level call graph (CodeGraph parity)",
        # ``--call-graph <mode>`` uses ``nargs="?"`` with ``const="summary"``
        # in argument_parser_builder.py. argparse stores the chosen mode
        # in ``args.call_graph`` (no explicit ``dest=``), so the dispatcher
        # must read ``call_graph`` — not ``call_graph_mode`` (G1).
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "call_graph", "summary") or "summary",
            "function_name": getattr(args, "call_graph_function", None),
            "file_path": getattr(args, "call_graph_file", None),
            "depth": getattr(args, "call_graph_depth", 5),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="ast_cache",
        tool_attr="ASTCacheTool",
        label="Pre-indexed AST cache (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "ast_cache_mode", "stats") or "stats",
            "file_path": getattr(args, "file_path", None),
            "query": getattr(args, "ast_cache_query", None),
            "language": getattr(args, "ast_cache_language", None),
            "max_files": getattr(args, "ast_cache_max_files", 5000),
            "force": bool(getattr(args, "ast_cache_force", False)),
        },
    ),
    McpCommandSpec(
        flag_name="detect_routes",
        tool_attr="RouteDetectorTool",
        label="Framework route detection (CodeGraph parity)",
        build_tool_args=_build_detect_routes_tool_args,
    ),
    McpCommandSpec(
        flag_name="trace_impact",
        tool_attr="TraceImpactTool",
        label="Trace symbol impact (callers + usages across project)",
        build_tool_args=_build_trace_impact_tool_args,
    ),
    McpCommandSpec(
        flag_name="check_tools",
        tool_attr="CheckToolsTool",
        label="Check fd / ripgrep availability",
        build_tool_args=_build_check_tools_tool_args,
    ),
    McpCommandSpec(
        flag_name="build_project_index",
        tool_attr="BuildProjectIndexTool",
        label="Rebuild persistent project index",
        build_tool_args=_build_build_project_index_tool_args,
    ),
    McpCommandSpec(
        flag_name="modification_guard",
        tool_attr="ModificationGuardTool",
        label="Pre-modification safety check (symbol-level)",
        build_tool_args=_build_modification_guard_tool_args,
    ),
    McpCommandSpec(
        flag_name="batch_search",
        tool_attr="BatchSearchTool",
        label="Run 2-10 ripgrep searches in parallel",
        build_tool_args=_build_batch_search_tool_args,
    ),
)


def _classify_error_type(exc: BaseException) -> str:
    """Classify an exception for the ``error_type`` envelope field.

    J2: agents on the other end of ``--format json`` need a coarse
    bucket so they can decide between "fix my input" vs "report a bug".
    ``ValueError`` is by far the most common path-validation failure
    (the security validator and path resolver both raise it), and
    ``FileNotFoundError`` / generic ``OSError`` is the other half of the
    validation surface. Anything else is treated as internal — agents
    should surface those to a human.
    """
    if isinstance(exc, ValueError | FileNotFoundError | OSError):
        return "validation"
    return "internal"


_SUMMARY_LINE_MAX_LEN = 80


def _summary_line_reason(exc: BaseException) -> str:
    """O6 (round-30 dogfood): the human-readable reason for a summary line.

    Pre-O6 the envelope's ``summary_line`` rendered ``error — ValueError``
    — the Python class name, not the actionable message. Agents that
    only read the headline saw no signal about *what* failed. Now we
    prefer ``str(exc)`` (the same text the ``error`` field exposes) and
    fall back to the class name when the exception has no message.

    The headline budget is small (~80 chars) so multi-sentence messages
    are truncated with ``...``; the full message stays available on
    the ``error`` field for callers that want the long form.
    """
    message = str(exc).strip()
    if not message:
        return type(exc).__name__
    if len(message) > _SUMMARY_LINE_MAX_LEN:
        return message[: _SUMMARY_LINE_MAX_LEN - 3].rstrip() + "..."
    return message


def _build_error_envelope(
    flag_name: str,
    label: str,
    exc: BaseException,
    echo_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct a canonical error envelope for a failed MCP CLI command.

    Mirrors the success-envelope shape (``success``, ``summary_line``,
    ``agent_summary``) so a programmatic consumer can use the same
    parser for success and failure cases.

    ``echo_fields`` (N6, round-28 dogfood): per-command identifier fields
    to mirror onto the response root so the failure envelope carries the
    same context as the success envelope. For ``--dependencies`` this is
    ``{"mode": "<requested>"}`` so the caller sees their requested mode
    even when validation failed *before* any tool-level mode handling.
    Canonical envelope keys (``success``, ``error``, ``error_type``,
    ``summary_line``, ``agent_summary``) are never overwritten.

    O6 (round-30 dogfood): ``summary_line`` now embeds the actual error
    reason (``str(exc)``) instead of the Python exception class name.
    The ``error`` field already carried the actionable text; agents
    that only read the headline now see the same signal.
    """
    err_type = _classify_error_type(exc)
    exc_name = type(exc).__name__
    message = str(exc) or exc_name
    reason = _summary_line_reason(exc)
    envelope: dict[str, Any] = {
        "success": False,
        "error_type": err_type,
        "error": message,
        "summary_line": f"{flag_name}: error — {reason}",
        # r37ah (dogfood): top-level verdict mirror so CLI envelope gate
        # accepts MCP-bridged error responses (r37u contract). Without
        # this, ``--batch-search`` / ``--detect-routes`` / others that
        # route through this builder emitted verdict=None on the
        # validation-error path even though agent_summary.verdict='ERROR'
        # was set.
        "verdict": "ERROR",
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": f"{flag_name}: error — {reason}",
            "next_step": "Fix the input and retry.",
            "label": label,
        },
    }
    if echo_fields:
        for key, value in echo_fields.items():
            if value is None or value == "":
                continue
            # Don't let echoes stomp on canonical envelope keys.
            envelope.setdefault(key, value)
    return envelope


def _collect_echo_fields(spec: McpCommandSpec, args: Any) -> dict[str, Any]:
    """Collect identifier fields to echo into a failure envelope.

    N6 (round-28 dogfood): the success path for ``--dependencies`` echoes
    ``mode: <requested>`` so callers can branch on the requested analysis
    mode. The validation-error path used to drop ``mode`` entirely,
    leaving callers with no signal about what they requested. Mirror the
    same field set onto the error envelope.

    Other commands can grow their own echo fields here without touching
    the envelope builder. Keep this conservative — only echo fields the
    caller can directly use to retry.
    """
    echo: dict[str, Any] = {}
    if spec.flag_name == "dependencies":
        # Normalise via the same alias table the tool uses so a caller
        # who requested ``mode=full`` and got a validation error still
        # sees ``mode: summary`` in the response — matching what the
        # success path echoes.
        from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
            DependencyAnalysisTool,
        )

        raw_mode = getattr(args, "dependencies", None) or "summary"
        echo["mode"] = DependencyAnalysisTool._normalize_mode(raw_mode)
    return echo


def _emit_error_envelope(
    flag_name: str,
    label: str,
    exc: BaseException,
    output_format: str,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    echo_fields: Mapping[str, Any] | None = None,
) -> int:
    """Print a format-respecting error envelope and return exit code 1.

    J2: when the user asked for ``--format json`` (or toon), an
    unhandled error in the tool layer used to bypass the envelope and
    drop a plain-text ``ERROR: ...`` line, leaving agents with no
    parseable response. Now we honour the requested format: JSON when
    ``output_format == 'json'``, TOON envelope (best-effort, falls
    back to JSON on encoder failure) when ``output_format == 'toon'``,
    and the original plain-text message in every other case.
    """
    envelope = _build_error_envelope(flag_name, label, exc, echo_fields)
    if output_format == "json":
        print(json.dumps(envelope, ensure_ascii=False))
        return 1
    if output_format == "toon":
        try:
            from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

            print(ToonFormatter().format(envelope))
        except Exception:  # noqa: BLE001 — degrade to JSON if TOON unavailable
            print(json.dumps(envelope, ensure_ascii=False))
        return 1
    output_error_fn(f"{label} failed: {exc}")
    return 1


def _run_tool(
    args: Any,
    spec: McpCommandSpec,
    tool_cls: Callable[..., Any],
    tool_args: Mapping[str, Any] | None,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    output_format_fn: Callable[[], str],
) -> int:
    """Helper: instantiate tool, run execute(), print output.

    ``tool_args=None`` defers argument construction to inside the
    ``try``/``except`` below so that a ``ValueError`` raised by the
    spec's ``build_tool_args`` callback (e.g. M4 path-validation in
    ``_build_detect_routes_tool_args``) is converted into a structured
    error envelope rather than bubbling out as an uncaught traceback.
    """
    output_format = output_format_fn()
    try:
        if tool_args is None:
            tool_args = build_mcp_tool_args(args, spec, output_format)
        project_root = getattr(args, "project_root", None) or os.getcwd()
        tool = tool_cls(project_root=project_root)
        result: dict[str, Any] = asyncio.run(tool.execute(dict(tool_args)))
        if output_format == "toon":
            print(result.get("toon_content", ""))
        else:
            output_json_fn(result)
        return 0 if result.get("success", False) else 1
    except Exception as e:
        # J2: every ``except Exception`` in this module must respect the
        # caller's requested format. The contract test
        # ``TestJ2ErrorEnvelopeOnJsonFormat`` enforces this for both
        # path-validation and tool-internal failures.
        # N6: pass per-command echo fields (e.g. dependencies ``mode``)
        # so the failure envelope mirrors the success-path identifier.
        return _emit_error_envelope(
            spec.flag_name,
            spec.label,
            e,
            output_format,
            output_json_fn,
            output_error_fn,
            echo_fields=_collect_echo_fields(spec, args),
        )


# ARCH-A2: declare which tool-class names this module exposes for the
# CLI. The set is used by the contract test to verify every
# MCP_COMMAND_SPECS entry resolves. Lookup itself goes through the
# module namespace (``globals()``) so monkeypatching at module level —
# the standard pattern used by tests in tests/unit/cli/test_mcp_commands.py
# — keeps working. A snapshot dict would freeze references at import
# time and quietly break those tests.
_TOOL_CLASS_NAMES: frozenset[str] = frozenset(
    {
        "FileHealthTool",
        "ParserReadinessTool",
        "ProjectHealthTool",
        "ProjectOverviewTool",
        "SafeToEditTool",
        "ChangeImpactTool",
        "DependencyAnalysisTool",
        "RefactoringSuggestionsTool",
        "SmartContextTool",
        "SymbolLineageTool",
        "CodePatternsTool",
        "CodeGraphCallTool",
        "ASTCacheTool",
        "RouteDetectorTool",
        "TraceImpactTool",
        "CheckToolsTool",
        "BuildProjectIndexTool",
        "ModificationGuardTool",
        "BatchSearchTool",
    }
)


def _get_tool_class(tool_attr: str) -> Callable[..., Any]:
    """Resolve a tool class by its command spec attribute name.

    Looks the class up in the module's own namespace (``globals()``) so
    tests that monkeypatch ``mcp_commands.FileHealthTool`` etc. see the
    substituted class — a frozen dict would defeat that pattern.
    """
    if tool_attr not in _TOOL_CLASS_NAMES:
        raise KeyError(f"Unknown MCP tool: {tool_attr}")
    cls = globals().get(tool_attr)
    if cls is None:
        raise KeyError(
            f"Tool name {tool_attr!r} is declared in _TOOL_CLASS_NAMES but "
            "is not bound in this module."
        )
    return cls  # type: ignore[no-any-return]


def _format_aware_error_sink(
    flag_name: str,
    label: str,
    output_format: str,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    echo_fields: Mapping[str, Any] | None = None,
) -> Callable[[str], None]:
    """Return a ``output_error_fn`` that respects the requested format.

    J2: ``validate_mcp_command_args`` reports pre-execution failures
    (e.g. missing ``--file-path`` for ``--dependencies blast_radius``)
    via the same plain-text sink. When the caller asked for JSON or
    TOON, we wrap the sink so the failure surfaces as a structured
    envelope instead of an unparseable ``ERROR: ...`` line.

    N6 (round-28): ``echo_fields`` mirrors per-command identifiers
    (e.g. dependencies ``mode``) onto the validation-error envelope so
    callers see what they requested even when the request never reached
    the tool.
    """

    def _sink(message: str) -> None:
        if output_format in {"json", "toon"}:
            _emit_error_envelope(
                flag_name,
                label,
                ValueError(message),
                output_format,
                output_json_fn,
                output_error_fn,
                echo_fields=echo_fields,
            )
        else:
            output_error_fn(message)

    return _sink


def handle_mcp_commands(
    args: Any,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    output_format_fn: Callable[[], str],
) -> int | None:
    """Handle MCP-equivalent CLI commands. Returns exit code or None if not handled."""
    spec = find_selected_mcp_command(args, MCP_COMMAND_SPECS)
    if spec is None:
        return None

    output_format = output_format_fn()
    # N6: collect per-command echo fields once so both the pre-execution
    # validator and the tool-execution exception path return identical
    # context (e.g. ``mode: file_deps`` on a dependencies failure).
    echo_fields = _collect_echo_fields(spec, args)
    validate_sink = _format_aware_error_sink(
        spec.flag_name,
        spec.label,
        output_format,
        output_json_fn,
        output_error_fn,
        echo_fields=echo_fields,
    )
    if not validate_mcp_command_args(args, spec, validate_sink):
        return 1

    # M4 (round-26): pass ``tool_args=None`` so any ``ValueError`` raised
    # inside ``spec.build_tool_args`` (e.g. detect_routes path validation)
    # is caught by the ``_run_tool`` error envelope rather than escaping
    # as an uncaught traceback.
    return _run_tool(
        args,
        spec,
        _get_tool_class(spec.tool_attr),
        None,
        output_json_fn,
        output_error_fn,
        output_format_fn,
    )
