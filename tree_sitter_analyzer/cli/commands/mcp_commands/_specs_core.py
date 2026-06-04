"""Core MCP command specs: health, analysis, navigation, and graph basics."""

from __future__ import annotations

from tree_sitter_analyzer.cli.commands.mcp_command_helpers import McpCommandSpec

from ....mcp.tools._call_tree import DEFAULT_MAX_NODES as _DEFAULT_TREE_MAX_NODES
from ....mcp.tools.symbol_search_tool import (
    DEFAULT_SYMBOL_SEARCH_LIMIT as _DEFAULT_SYMBOL_SEARCH_LIMIT,
)
from ._builders import (
    _build_change_impact_tool_args,
    _build_dependency_tool_args,
    _build_detect_routes_tool_args,
    _build_parser_readiness_tool_args,
    _dependency_mode_requires_file,
)

_CORE_SPECS: tuple[McpCommandSpec, ...] = (
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
        # agent_summary_only flipped to default-True in v1.12 (was 145 KB
        # of JSON, agents had to add --agent-summary-only every time).
        # ``--change-impact-full`` is the explicit opt-out; the older
        # ``--agent-summary-only`` is still accepted but is now redundant.
        build_tool_args=_build_change_impact_tool_args,
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
        flag_name="outline",
        tool_attr="GetCodeOutlineTool",
        label="Code outline",
        required_file_error="--outline requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "include_fields": getattr(args, "outline_include_fields", False),
            "include_imports": getattr(args, "outline_include_imports", False),
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
            "mode": getattr(args, "call_graph", "summary") or "summary",
            "function_name": getattr(args, "call_graph_function", None),
            "file_path": getattr(args, "call_graph_file", None),
            "depth": getattr(args, "call_graph_depth", 5),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="callers",
        tool_attr="CodeGraphCallersTool",
        label="Find callers of a function (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "function_name": getattr(args, "callers", ""),
            "file_path": getattr(args, "callers_file", None),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="callees",
        tool_attr="CodeGraphCalleesTool",
        label="Find callees of a function (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "function_name": getattr(args, "callees", ""),
            "file_path": getattr(args, "callees_file", None),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="callee_tree",
        tool_attr="CodeGraphCalleeTreeTool",
        label="Depth-limited nested callee tree (mycelium RFC-0020 parity)",
        build_tool_args=lambda args, output_format: {
            "symbol": getattr(args, "callee_tree", "") or "",
            "file_path": getattr(args, "tree_file", None),
            "max_depth": getattr(args, "tree_max_depth", 3),
            "max_nodes": getattr(args, "tree_max_nodes", _DEFAULT_TREE_MAX_NODES),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="caller_tree",
        tool_attr="CodeGraphCallerTreeTool",
        label="Depth-limited nested caller tree (mycelium RFC-0021 parity)",
        build_tool_args=lambda args, output_format: {
            "symbol": getattr(args, "caller_tree", "") or "",
            "file_path": getattr(args, "tree_file", None),
            "max_depth": getattr(args, "tree_max_depth", 3),
            "max_nodes": getattr(args, "tree_max_nodes", _DEFAULT_TREE_MAX_NODES),
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
            "max_files": getattr(args, "ast_cache_max_files", 20_000),
            "force": bool(getattr(args, "ast_cache_force", False)),
            "include_activation": bool(
                getattr(args, "ast_cache_include_activation", False)
            ),
            "poll_interval": getattr(args, "watch_poll_interval", 5.0),
            "backend": getattr(args, "watch_backend", "poll"),
        },
    ),
    McpCommandSpec(
        flag_name="detect_routes",
        tool_attr="RouteDetectorTool",
        label="Framework route detection (CodeGraph parity)",
        build_tool_args=_build_detect_routes_tool_args,
    ),
    McpCommandSpec(
        flag_name="ast_diff",
        tool_attr="ASTDiffTool",
        label="Structural AST diff (difftastic-level)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "ast_diff_mode", "diff_files") or "diff_files",
            "old_file": getattr(args, "ast_diff_old_file", None),
            "new_file": getattr(args, "ast_diff_new_file", None),
            "old_source": getattr(args, "ast_diff_old_source", None),
            "new_source": getattr(args, "ast_diff_new_source", None),
            "file_path": getattr(args, "ast_diff_file", None),
            "old_ref": getattr(args, "ast_diff_old_ref", "HEAD~1"),
            "new_ref": getattr(args, "ast_diff_new_ref", "HEAD"),
            "language": getattr(args, "ast_diff_language", None),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="symbol_search",
        tool_attr="CodeGraphSymbolSearchTool",
        label="FTS5-powered instant symbol search (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            # Pain #21 (dogfood pass 3): same dest-name bug as #17. --symbol-search QUERY
            # stores into args.symbol_search; reading symbol_search_query was always None
            # so the tool always raised "query is required".
            "query": getattr(args, "symbol_search", "") or "",
            "language": getattr(args, "symbol_search_language", None),
            "kind": getattr(args, "symbol_search_kind", "any") or "any",
            "limit": getattr(args, "symbol_search_limit", _DEFAULT_SYMBOL_SEARCH_LIMIT),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="call_path",
        tool_attr="CodeGraphCallPathTool",
        label="Find execution paths between two functions (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "source_function": getattr(args, "call_path_source", "") or "",
            "target_function": getattr(args, "call_path_target", "") or "",
            "source_file": getattr(args, "call_path_source_file", None),
            "target_file": getattr(args, "call_path_target_file", None),
            "max_depth": getattr(args, "call_path_max_depth", 10),
            "max_paths": getattr(args, "call_path_max_paths", 5),
            "direction": getattr(args, "call_path", "bidirectional") or "bidirectional",
            "output_format": output_format,
        },
    ),
)
