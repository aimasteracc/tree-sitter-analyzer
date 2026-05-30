"""Extended MCP command specs: codegraph intelligence, UML, and advanced commands."""

from __future__ import annotations

from tree_sitter_analyzer.cli.commands.mcp_command_helpers import McpCommandSpec

from ._builders import (
    _build_batch_search_tool_args,
    _build_build_project_index_tool_args,
    _build_check_tools_tool_args,
    _build_code_similarity_tool_args,
    _build_codegraph_explore_tool_args,
    _build_codegraph_query_tool_args,
    _build_codegraph_status_tool_args,
    _build_decision_journal_tool_args,
    _build_modification_guard_tool_args,
    _build_trace_impact_tool_args,
    _build_uml_tool_args,
)

_EXTENDED_SPECS: tuple[McpCommandSpec, ...] = (
    McpCommandSpec(
        flag_name="codegraph_overview",
        tool_attr="CodeGraphOverviewTool",
        label="Project-wide call graph intelligence (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "max_entry_points": getattr(
                args, "codegraph_overview_max_entry_points", 30
            ),
            "max_hubs": getattr(args, "codegraph_overview_max_hubs", 20),
            "max_dead": getattr(args, "codegraph_overview_max_dead", 20),
            "max_coupled_files": getattr(args, "codegraph_overview_max_coupled", 15),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="symbol_resolve",
        tool_attr="CodeGraphSymbolResolveTool",
        label="Go-to-definition and find-all-references (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "symbol": getattr(args, "symbol_resolve", ""),
            "mode": getattr(args, "symbol_resolve_mode", "resolve") or "resolve",
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_impact",
        tool_attr="CodeGraphImpactTool",
        label="Function blast radius analysis (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_impact_mode", "function_impact")
            or "function_impact",
            # Pain #17 (dogfood pass 3): --codegraph-impact FUNCTION argparse
            # dest is ``codegraph_impact``, not ``codegraph_impact_function``.
            # Reading the wrong attr meant function_name was always None and
            # the tool always raised at CLI invocation.
            "function_name": getattr(args, "codegraph_impact", None),
            "function_names": getattr(args, "codegraph_impact_functions", None),
            "file_path": getattr(args, "codegraph_impact_file", None),
            "depth": getattr(args, "codegraph_impact_depth", 5),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_navigate",
        tool_attr="CodeGraphNavigateTool",
        label="Unified symbol navigation: go-to-def + references + call hierarchy",
        build_tool_args=lambda args, output_format: {
            "symbol": getattr(args, "codegraph_navigate", ""),
            "mode": getattr(args, "codegraph_navigate_mode", "full") or "full",
            "file_path": getattr(args, "codegraph_navigate_file", None),
            "depth": getattr(args, "codegraph_navigate_depth", 2),
            "output_format": output_format,
        },
    ),
    # CodeGraph parity gap-closure (2026-05-24): codegraph_status is a thin
    # facade returning index health in one call (was: 3-4 separate calls to
    # ast_cache + auto_index + check_tools). Bare boolean flag.
    McpCommandSpec(
        flag_name="codegraph_status",
        tool_attr="CodeGraphStatusTool",
        label="Index health at-a-glance (CodeGraph parity)",
        build_tool_args=_build_codegraph_status_tool_args,
    ),
    # CodeGraph parity gap-closure (2026-05-24): codegraph_explore replaces
    # ~8 chained codegraph_node / analyze_code_structure calls with one
    # capped batch fetch. Value-bearing flag: --codegraph-explore "QUERY".
    McpCommandSpec(
        flag_name="codegraph_explore",
        tool_attr="CodeGraphExploreTool",
        label="Bulk-fetch N related symbols' source + relationship map",
        build_tool_args=_build_codegraph_explore_tool_args,
    ),
    McpCommandSpec(
        flag_name="codegraph_query",
        tool_attr="CodeGraphQueryTool",
        label="jQuery-style chained code graph query",
        build_tool_args=_build_codegraph_query_tool_args,
    ),
    McpCommandSpec(
        flag_name="ast_path",
        tool_attr="CodeGraphASTPathTool",
        label="AST path/scope navigation (CodeGraph parity)",
        required_file_error="--ast-path requires a file path",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "ast_path_mode", "scope") or "scope",
            "file_path": args.file_path,
            "line": getattr(args, "ast_path_line", None),
            "max_depth": getattr(args, "ast_path_max_depth", 3),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="semantic_classify",
        tool_attr="SemanticClassifyTool",
        label="Semantic change classification",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "semantic_classify_mode", "classify_file")
            or "classify_file",
            "file_path": getattr(args, "file_path", None),
            "old_ref": getattr(args, "semantic_classify_old_ref", "HEAD~1"),
            "new_ref": getattr(args, "semantic_classify_new_ref", "HEAD"),
            "language": getattr(args, "semantic_classify_language", None),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="pr_review",
        tool_attr="CodeGraphPRReviewTool",
        label="AI-powered PR review: AST diff + semantic + call graph",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "pr_review", "diff") or "diff",
            "pr_url": getattr(args, "pr_review_url", "") or "",
            "include_call_graph": True,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="import_graph",
        tool_attr="CodeGraphImportGraphTool",
        label="File-level import dependency graph (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "import_graph_mode", "summary") or "summary",
            "file_path": getattr(args, "import_graph_file", None)
            or getattr(args, "file_path", None),
            "max_depth": getattr(args, "import_graph_max_depth", 10),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="dead_code",
        tool_attr="CodeGraphDeadCodeTool",
        label="Dead code analysis: transitive dead functions, unused imports, unreferenced variables",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "dead_code_mode", "all") or "all",
            "include_test_files": bool(getattr(args, "dead_code_include_tests", False)),
            "max_dead": getattr(args, "dead_code_max", 50) or 50,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="doc_sync",
        tool_attr="DocSyncTool",
        label="Doc-sync: scan markdown docs for stale file-path references",
        build_tool_args=lambda args, output_format: {
            "doc_patterns": getattr(args, "doc_sync_patterns", None) or None,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="code_similarity",
        tool_attr="CodeGraphSimilarityTool",
        label="AST-structural clone detection: finds duplicate and near-duplicate functions (CodeGraph parity)",
        build_tool_args=_build_code_similarity_tool_args,
    ),
    McpCommandSpec(
        flag_name="codegraph_sitemap",
        tool_attr="CodeGraphSitemapTool",
        label="Hierarchical project code map: directory→file→class→function (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_sitemap_mode", "full") or "full",
            "language": getattr(args, "codegraph_sitemap_language", None),
            "directory": getattr(args, "codegraph_sitemap_directory", None),
            "max_files": getattr(args, "codegraph_sitemap_max_files", 200),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_xref",
        tool_attr="CodeGraphXRefTool",
        label="Instant cross-reference: definition + callers + callees + import deps (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_xref_mode", "symbol") or "symbol",
            "symbol": getattr(args, "codegraph_xref", ""),
            "file_path": getattr(args, "codegraph_xref_file", None),
            "include_callers": bool(getattr(args, "codegraph_xref_callers", True)),
            "include_callees": bool(getattr(args, "codegraph_xref_callees", True)),
            "include_imports": bool(getattr(args, "codegraph_xref_imports", True)),
            "include_file_deps": bool(getattr(args, "codegraph_xref_file_deps", True)),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_complexity_heatmap",
        tool_attr="CodeGraphComplexityHeatmapTool",
        label="Cyclomatic complexity heatmap with risk bands (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_complexity_heatmap", "project")
            or "project",
            "file_path": getattr(args, "codegraph_complexity_file", None),
            "function_name": getattr(args, "codegraph_complexity_function", None),
            "language": getattr(args, "codegraph_complexity_language", None),
            "directory": getattr(args, "codegraph_complexity_directory", None),
            "max_files": getattr(args, "codegraph_complexity_max_files", 200),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="class_hierarchy",
        tool_attr="ClassHierarchyTool",
        label="Class inheritance hierarchy analysis: subclasses, superclasses, impact (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "class_hierarchy_mode", "summary") or "summary",
            "class_name": getattr(args, "class_hierarchy_class", None),
            "max_depth": getattr(args, "class_hierarchy_depth", 10),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="class_inspect",
        tool_attr="ClassInspectTool",
        label="Inspect a class: list defined methods with override detection",
        build_tool_args=lambda args, output_format: {
            "class_name": getattr(args, "class_inspect", None) or "",
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="dependency_matrix",
        tool_attr="CodeGraphDependencyMatrixTool",
        label="Module coupling analysis: pairwise scores, hotspots, unstable modules (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "dependency_matrix_mode", "summary") or "summary",
            "file_path": getattr(args, "dependency_matrix_file", None),
            "top_k": getattr(args, "dependency_matrix_top_k", 10),
            "threshold": getattr(args, "dependency_matrix_threshold", 0.7),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_visualize",
        tool_attr="CodeGraphVisualizeTool",
        label="Mermaid call graph visualization (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_visualize_mode", "full") or "full",
            "file_path": getattr(args, "codegraph_visualize_file", None),
            "function": getattr(args, "codegraph_visualize_function", None),
            "depth": getattr(args, "codegraph_visualize_depth", 3),
            "max_edges": getattr(args, "codegraph_visualize_max_edges", 150),
            "direction": getattr(args, "codegraph_visualize_direction", "TD") or "TD",
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="uml",
        tool_attr="CodeGraphUMLTool",
        label="UML Mermaid export: class, package, component, sequence diagrams",
        build_tool_args=_build_uml_tool_args,
    ),
    # consolidated-only dispatchers ported during merge of feat/autonomous-dev
    McpCommandSpec(
        flag_name="trace_impact",
        tool_attr="TraceImpactTool",
        label="Trace symbol impact (callers + usages across project)",
        build_tool_args=_build_trace_impact_tool_args,
    ),
    McpCommandSpec(
        flag_name="check_tools",
        tool_attr="CheckToolsTool",
        label="Check whether fd and ripgrep are installed",
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
        label="Pre-modification safety guard for a symbol",
        build_tool_args=_build_modification_guard_tool_args,
    ),
    McpCommandSpec(
        flag_name="decision_journal",
        tool_attr="DecisionJournalTool",
        label="Decision journal (record/get/search/supersede)",
        build_tool_args=_build_decision_journal_tool_args,
    ),
    McpCommandSpec(
        flag_name="batch_search",
        tool_attr="BatchSearchTool",
        label="Batch ripgrep search (2-10 queries via JSON file)",
        build_tool_args=_build_batch_search_tool_args,
    ),
)
