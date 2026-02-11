"""
Code Intelligence MCP Tool — Expose ProjectCodeMap intelligence via MCP.

Provides a single unified tool with action-based routing:
- scan: Scan project and build code map
- trace_calls: Bidirectional call flow tracing
- impact: Modification impact analysis
- gather_context: LLM context capture engine
- dead_code: List dead (unreachable) code
- hot_spots: List most-referenced symbols

Scan results are cached per project path to avoid redundant re-scanning.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from tree_sitter_analyzer_v2.core.code_map import (
    CodeMapResult,
    ProjectCodeMap,
)
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

_VALID_ACTIONS = frozenset({
    "scan", "trace_calls", "impact", "gather_context",
    "dead_code", "hot_spots", "inheritance", "refactorings", "code_smells",
    "change_risk", "mermaid", "snapshot", "test_audit",
})


class CodeIntelligenceTool(BaseTool):
    """
    MCP tool for project-level code intelligence.

    Scans an entire codebase and provides:
    - Full symbol index with call relationships
    - Bidirectional call flow tracing
    - Modification impact analysis with risk levels
    - LLM context capture with token budgets
    - Dead code detection (decorator-aware)
    - Hot spot identification
    """

    def __init__(self) -> None:
        """Initialize with empty cache and pre-built dispatch table."""
        self._mapper = ProjectCodeMap()
        self._cached_result: CodeMapResult | None = None
        self._cached_project: str | None = None
        # S4-5: build dispatch table once (not on every execute() call)
        self._dispatch: dict[str, Any] = {
            "trace_calls": self._handle_trace_calls,
            "impact": self._handle_impact,
            "gather_context": self._handle_gather_context,
            "dead_code": self._handle_dead_code,
            "hot_spots": self._handle_hot_spots,
            "inheritance": self._handle_inheritance,
            "refactorings": self._handle_refactorings,
            "code_smells": self._handle_code_smells,
            "change_risk": self._handle_change_risk,
            "mermaid": self._handle_mermaid,
            "snapshot": self._handle_snapshot,
            "test_audit": self._handle_test_audit,
        }

    def get_name(self) -> str:
        return "code_intelligence"

    def get_description(self) -> str:
        return (
            "Project-level code intelligence: scan a codebase to build a full code map, "
            "then trace call flows, analyze modification impact, gather LLM context, "
            "detect dead code, and find hot spots. "
            "Supports Python, Java, TypeScript. Results in TOON format for minimal token usage."
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": sorted(_VALID_ACTIONS),
                    "description": (
                        "Action to perform: "
                        "'scan' = build code map, "
                        "'trace_calls' = call flow for a function, "
                        "'impact' = impact analysis for a symbol, "
                        "'gather_context' = capture code context for LLM, "
                        "'dead_code' = list unreachable functions, "
                        "'hot_spots' = list most-referenced symbols, "
                        "'inheritance' = trace class inheritance chain, "
                        "'refactorings' = suggest code refactorings, "
                        "'code_smells' = detect anti-patterns, "
                        "'change_risk' = assess risk of file changes, "
                        "'mermaid' = generate dependency/inheritance graph, "
                        "'snapshot' = compact project overview with token economics, "
                        "'test_audit' = audit test architecture coverage"
                    ),
                },
                "project_path": {
                    "type": "string",
                    "description": "Root directory of the project to scan (required for 'scan', optional otherwise if already scanned)",
                },
                "name": {
                    "type": "string",
                    "description": "Function/symbol name for trace_calls and impact actions",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for gather_context action",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Token budget for gather_context (default: 4000)",
                    "default": 4000,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max depth for trace_calls (default: 1)",
                    "default": 1,
                },
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File extensions to scan (default: ['.py', '.java', '.ts', '.js'])",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max items to return for dead_code and hot_spots (default: 50)",
                    "default": 50,
                },
            },
            "required": ["action"],
        }

    def _build_dispatch_table(self) -> dict[str, Any]:
        """Build callable dispatch table (action -> bound method).

        Uses actual callables instead of string method names to prevent
        typo bugs and enable IDE rename-refactoring.
        Note: 'scan' is handled directly in execute() before dispatch.
        """
        return {
            "trace_calls": self._handle_trace_calls,
            "impact": self._handle_impact,
            "gather_context": self._handle_gather_context,
            "dead_code": self._handle_dead_code,
            "hot_spots": self._handle_hot_spots,
            "inheritance": self._handle_inheritance,
            "refactorings": self._handle_refactorings,
            "code_smells": self._handle_code_smells,
            "change_risk": self._handle_change_risk,
            "mermaid": self._handle_mermaid,
            "snapshot": self._handle_snapshot,
            "test_audit": self._handle_test_audit,
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the code intelligence action via callable dispatch."""
        action = arguments.get("action")
        if not action:
            return self._error("Missing required parameter: action", error_code="INVALID_ARGUMENT")
        if action not in _VALID_ACTIONS:
            return self._error(f"Invalid action: {action}. Valid: {sorted(_VALID_ACTIONS)}", error_code="INVALID_ARGUMENT")

        try:
            project_path = arguments.get("project_path")
            extensions = arguments.get("extensions")

            # Handle scan explicitly (needs project_path, no prior cache needed)
            if action == "scan":
                if not project_path:
                    return self._error("project_path is required for scan action", error_code="INVALID_ARGUMENT")
                self._do_scan(project_path, extensions)
                return self._handle_scan()

            # Ensure project is scanned for non-scan actions
            if project_path and project_path != self._cached_project:
                self._do_scan(project_path, extensions)
            elif self._cached_result is None:
                if project_path:
                    self._do_scan(project_path, extensions)
                else:
                    return self._error("No project scanned. Provide project_path or run 'scan' first.", error_code="INVALID_ARGUMENT")

            # Callable dispatch: look up handler from pre-built table
            handler = self._dispatch.get(action)
            if handler:
                logger.debug("Dispatching action=%s", action)
                return handler(arguments)

            return self._error(f"Unhandled action: {action}", error_code="INVALID_ARGUMENT")
        except Exception as e:
            logger.error("Action %s failed: %s", action, e, exc_info=True)
            return self._error(str(e), error_code="INTERNAL_ERROR")

    def _do_scan(
        self, project_path: str, extensions: list[str] | None = None
    ) -> None:
        """Run ProjectCodeMap.scan and cache the result.

        Raises:
            ValueError: If project_path does not exist or is not a directory.
        """
        resolved = Path(project_path).resolve()
        if not resolved.is_dir():
            raise ValueError(f"project_path is not a valid directory: {project_path}")
        exts = extensions or [".py", ".java", ".ts", ".js"]
        self._cached_result = self._mapper.scan(str(resolved), extensions=exts)
        self._cached_project = project_path

    def _result(self) -> CodeMapResult:
        """Get cached result (guaranteed non-None by caller)."""
        if self._cached_result is None:
            raise RuntimeError("No scan result cached — call scan first")
        return self._cached_result

    # ── Action handlers ──

    def _handle_scan(self) -> dict[str, Any]:
        r = self._result()
        return {
            "success": True,
            "total_files": r.total_files,
            "total_symbols": r.total_symbols,
            "total_classes": r.total_classes,
            "total_functions": r.total_functions,
            "total_lines": r.total_lines,
            "entry_points": len(r.entry_points),
            "dead_code_count": len(r.dead_code),
            "hot_spots_count": len(r.hot_spots),
            "toon": r.to_toon(),
        }

    def _handle_trace_calls(self, args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("name", "")
        if not name:
            return self._error("name is required for trace_calls", error_code="INVALID_ARGUMENT")
        max_depth = args.get("max_depth", 1)
        flow = self._result().trace_call_flow(name, max_depth=max_depth)
        return {
            "success": True,
            "callers_count": len(flow.callers),
            "callees_count": len(flow.callees),
            "toon": flow.to_toon(),
        }

    def _handle_impact(self, args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("name", "")
        if not name:
            return self._error("name is required for impact", error_code="INVALID_ARGUMENT")
        impact = self._result().impact_analysis(name)
        return {
            "success": True,
            "blast_radius": impact.blast_radius,
            "affected_files": len(impact.affected_files),
            "risk_level": impact.risk_level,
            "depth": impact.depth,
            "toon": impact.to_toon(),
        }

    def _handle_gather_context(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query", "")
        if not query:
            return self._error("query is required for gather_context", error_code="INVALID_ARGUMENT")
        max_tokens = args.get("max_tokens", 4000)
        ctx = self._result().gather_context(query, max_tokens=max_tokens)
        return {
            "success": True,
            "matched_symbols": len(ctx.matched_symbols),
            "code_sections": len(ctx.code_sections),
            "total_tokens": ctx.total_tokens,
            "toon": ctx.to_toon(),
        }

    def _handle_dead_code(self, args: dict[str, Any]) -> dict[str, Any]:
        r = self._result()
        limit = args.get("limit", 50)
        all_dead = r.dead_code
        shown = all_dead[:limit]
        lines: list[str] = [f"DEAD_CODE ({len(all_dead)} total):"]
        for sym in shown:
            lines.append(f"  {sym.kind} {sym.name} ({sym.file}:L{sym.line_start})")
        return {
            "success": True,
            "dead_count": len(all_dead),
            "shown": len(shown),
            "toon": "\n".join(lines),
        }

    def _handle_hot_spots(self, args: dict[str, Any]) -> dict[str, Any]:
        r = self._result()
        limit = args.get("limit", 50)
        all_spots = r.hot_spots
        shown = all_spots[:limit]
        lines: list[str] = [f"HOT_SPOTS ({len(all_spots)} total):"]
        for sym, count in shown:
            lines.append(f"  {sym.name} ({sym.file}:L{sym.line_start}) refs={count}")
        return {
            "success": True,
            "count": len(all_spots),
            "shown": len(shown),
            "toon": "\n".join(lines),
        }

    def _handle_inheritance(self, args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("name", "")
        if not name:
            return self._error("name is required for inheritance", error_code="INVALID_ARGUMENT")
        chain = self._result().trace_inheritance(name)
        return {
            "success": True,
            "ancestors_count": len(chain.ancestors),
            "descendants_count": len(chain.descendants),
            "toon": chain.to_toon(),
        }

    def _handle_refactorings(self, args: dict[str, Any]) -> dict[str, Any]:
        suggestions = self._result().suggest_refactorings()
        limit = args.get("limit", 50)
        shown = suggestions[:limit]
        lines: list[str] = [f"REFACTORING_SUGGESTIONS ({len(suggestions)} total):"]
        for s in shown:
            lines.append(f"  {s.to_toon()}")
        return {
            "success": True,
            "count": len(suggestions),
            "shown": len(shown),
            "toon": "\n".join(lines),
        }

    def _handle_code_smells(self, args: dict[str, Any]) -> dict[str, Any]:
        smells = self._result().detect_code_smells()
        limit = args.get("limit", 50)
        shown = smells[:limit]
        lines: list[str] = [f"CODE_SMELLS ({len(smells)} total):"]
        for s in shown:
            lines.append(f"  {s.to_toon()}")
        return {
            "success": True,
            "count": len(smells),
            "shown": len(shown),
            "toon": "\n".join(lines),
        }

    def _handle_change_risk(self, args: dict[str, Any]) -> dict[str, Any]:
        changed_files = args.get("changed_files", [])
        if not changed_files:
            return self._error("changed_files is required", error_code="INVALID_ARGUMENT")
        report = self._result().assess_change_risk(changed_files)
        return {
            "success": True,
            "risk_level": report.risk_level,
            "affected_files_count": len(report.affected_files),
            "affected_symbols_count": len(report.affected_symbols),
            "toon": report.to_toon(),
        }

    def _handle_mermaid(self, args: dict[str, Any]) -> dict[str, Any]:
        kind = args.get("kind", "dependencies")
        mermaid = self._result().to_mermaid(kind=kind)
        return {
            "success": True,
            "kind": kind,
            "mermaid": mermaid,
        }

    def _handle_snapshot(self, args: dict[str, Any]) -> dict[str, Any]:
        r = self._result()
        eco = r.token_economics()
        return {
            "success": True,
            "snapshot": r.project_snapshot(),
            "token_economics": eco,
            "symbol_index": r.symbol_index(),
        }

    def _handle_test_audit(self, args: dict[str, Any]) -> dict[str, Any]:
        test_roots = args.get("test_roots", [])
        report = self._result().audit_test_architecture(
            test_roots=test_roots if test_roots else None
        )
        return {
            "success": True,
            "file_coverage_percent": report.coverage_percent,
            "symbol_coverage_percent": report.symbol_coverage_percent,
            "total_source_symbols": report.total_source_symbols,
            "tested_symbols": report.tested_symbols,
            "untested_files_count": len(report.untested_files),
            "untested_tools_count": len(report.untested_tools),
            "total_test_functions": report.total_test_functions,
            "missing_layers": report.missing_layers,
            "import_matched_count": len(report.import_matched),
            "thin_tests_count": sum(
                1 for c in report.test_quality.values() if c <= 1
            ),
            "toon": report.to_toon(),
        }
