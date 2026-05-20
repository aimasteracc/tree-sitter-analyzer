#!/usr/bin/env python3
"""MCP-equivalent CLI command handlers."""

import asyncio
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
from tree_sitter_analyzer.mcp.tools.call_graph_tool import (
    CodeGraphCallTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
    ChangeImpactTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
    CodePatternsTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
    DependencyAnalysisTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool  # noqa: F401
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


MCP_COMMAND_SPECS: tuple[McpCommandSpec, ...] = (
    McpCommandSpec(
        flag_name="file_health",
        tool_attr="FileHealthTool",
        label="File health check",
        required_file_error="--file-health requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "output_format": output_format,
        },
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
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "output_format": output_format,
        },
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
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "call_graph_mode", "summary") or "summary",
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
)


def _run_tool(
    args: Any,
    tool_cls: Callable[..., Any],
    tool_args: Mapping[str, Any],
    label: str,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    output_format_fn: Callable[[], str],
) -> int:
    """Helper: instantiate tool, run execute(), print output."""
    try:
        project_root = getattr(args, "project_root", None) or os.getcwd()
        tool = tool_cls(project_root=project_root)
        result: dict[str, Any] = asyncio.run(tool.execute(dict(tool_args)))
        fmt = output_format_fn()
        if fmt == "toon":
            print(result.get("toon_content", ""))
        else:
            output_json_fn(result)
        return 0 if result.get("success", False) else 1
    except Exception as e:
        output_error_fn(f"{label} failed: {e}")
        return 1


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

    if not validate_mcp_command_args(args, spec, output_error_fn):
        return 1

    output_format = output_format_fn()
    return _run_tool(
        args,
        _get_tool_class(spec.tool_attr),
        build_mcp_tool_args(args, spec, output_format),
        spec.label,
        output_json_fn,
        output_error_fn,
        output_format_fn,
    )
