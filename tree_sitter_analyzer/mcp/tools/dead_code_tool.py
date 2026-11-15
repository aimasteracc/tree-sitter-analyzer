#!/usr/bin/env python3
"""
Dead Code Analysis MCP Tool — Transitive dead code, unused imports, unreferenced variables.

Modes:
- **all**: Full analysis (dead functions + unused imports + unreferenced variables)
- **dead_functions**: Transitive dead code detection via call graph flood-fill
- **unused_imports**: Import statements never referenced in their file
- **variables**: File-level variables not referenced by any function

CodeGraph parity: equivalent to CodeGraph's dead code intelligence,
but extends it with transitive analysis and unused import detection.
"""

from typing import Any

from ...dead_code_analyzer import (
    CONFIDENCE_HIGH,
    DeadFunction,
    UnreferencedVariable,
    UnusedImport,
    analyze_dead_code,
)
from ...utils import setup_logger
from ._validators import invalid_enum_error
from .base_tool import BaseMCPTool
from .dead_code_answer import (
    STATUS_FOUND,
    STATUS_NONE_FOUND,
    CertCounts,
    evidence_sentence,
    insufficient_evidence,
    mark_unknown,
    scope_evidence,
)
from .dead_code_answer import under_path as _under_path
from .dead_code_certify import (
    STATUS_CERTIFIED,
    certify_transitive,
    query_name,
    uncertified_entry,
)

logger = setup_logger(__name__)


class CodeGraphDeadCodeTool(BaseMCPTool):
    """MCP Tool for comprehensive dead code analysis (CodeGraph parity)."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_dead_code",
            "description": (
                "Dead code analysis: transitive dead functions, unused imports, "
                "and unreferenced variables. Extends basic orphan detection with "
                "flood-fill from entry points to find entire dead call chains. "
                "No other built-in tool provides transitive dead code analysis."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["all", "dead_functions", "unused_imports", "variables"],
                    "description": (
                        "Analysis mode: 'all' (default) for full analysis, "
                        "'dead_functions' for transitive dead code, "
                        "'unused_imports' for unused import detection, "
                        "'variables' for unreferenced variable detection."
                    ),
                    "default": "all",
                },
                "include_test_files": {
                    "type": "boolean",
                    "description": "Include test files in analysis (default: false)",
                    "default": False,
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Restrict results to functions/imports/variables defined "
                        "under this path prefix, relative to the project root and "
                        "matched on path segments (e.g. 'tree_sitter_analyzer/mcp' "
                        "excludes corpus/ and benchmarks/). Transitive reachability "
                        "is still computed across the whole project; only the "
                        "reported items are scoped."
                    ),
                },
                "max_dead": {
                    "type": "integer",
                    "description": "Max dead function candidates to return (default: 50)",
                    "default": 50,
                },
                "max_imports": {
                    "type": "integer",
                    "description": "Max unused import results (default: 50)",
                    "default": 50,
                },
                "max_variables": {
                    "type": "integer",
                    "description": "Max unreferenced variable results (default: 50)",
                    "default": 50,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json"],
                    "description": "Output format: JSON.",
                    "default": "json",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "all")
        valid_modes = ["all", "dead_functions", "unused_imports", "variables"]
        if mode not in valid_modes:
            raise invalid_enum_error("mode", mode, valid_modes)
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        if not self.project_root:
            return {
                "success": False,
                "error": "Project root not set. Call set_project_path first.",
            }

        mode = arguments.get("mode", "all")
        include_tests = arguments.get("include_test_files", False)
        max_dead = arguments.get("max_dead", 50)
        max_imports = arguments.get("max_imports", 50)
        max_variables = arguments.get("max_variables", 50)
        output_format = arguments.get("output_format", "json")
        path = arguments.get("path") or None

        try:
            result = analyze_dead_code(
                self.project_root,
                include_test_files=include_tests,
                include_unused_imports=mode in ("all", "unused_imports"),
                include_variables=mode in ("all", "variables"),
            )
        except Exception as exc:
            logger.error(f"Dead code analysis failed: {exc}")
            return {
                "success": False,
                "error": f"Analysis failed: {exc}",
            }

        # Scope to a path prefix (#1084) AFTER the transitive analysis, so
        # cross-file reachability stays whole-project but the *reported* items
        # are limited to definitions under ``path``. Applied before any total
        # is computed so every count reflects the scoped set.
        all_dead = list(result.dead_functions)
        if path is not None:
            result.dead_functions = [
                df
                for df in result.dead_functions
                if _under_path(df.function.file_path, path)
            ]
            result.unused_imports = [
                ui for ui in result.unused_imports if _under_path(ui.file, path)
            ]
            result.unreferenced_variables = [
                uv for uv in result.unreferenced_variables if _under_path(uv.file, path)
            ]

        # #1941: a transitive candidate is listed only when nav action=callers
        # certifies it (complete, every caller dead too, no outside supertype).
        candidates_total = len(result.dead_functions)
        cert_section: dict[str, Any] = {}
        if mode in ("all", "dead_functions"):
            result.dead_functions, cert_section = await _certified(
                self.project_root, result.dead_functions, all_dead, max_dead
            )

        # Totals BEFORE the display cap — used for truncation signals.
        total_dead_funcs = len(result.dead_functions)
        low_confidence_dead = sum(
            1 for df in result.dead_functions if df.confidence != CONFIDENCE_HIGH
        )
        total_unused_imports = len(result.unused_imports)
        total_unref_vars = len(result.unreferenced_variables)

        # Apply display caps.
        dead_funcs = result.dead_functions[:max_dead]
        unused_imports = result.unused_imports[:max_imports]
        unref_vars = result.unreferenced_variables[:max_variables]

        # Counts AFTER the display cap — what is actually listed in the response.
        listed_dead = len(dead_funcs)
        listed_imports = len(unused_imports)
        listed_vars = len(unref_vars)
        listed_total = listed_dead + listed_imports + listed_vars

        # Full totals across all categories (for verdict / next_step).
        total_all = total_dead_funcs + total_unused_imports + total_unref_vars

        # Truncation signals: only categories VISIBLE in this mode count
        # (Codex P2: mode=unused_imports strips dead_functions — a truncated
        # flag about an absent list is misinformation).
        dead_visible = mode in ("all", "dead_functions")
        imports_visible = mode in ("all", "unused_imports")
        vars_visible = mode in ("all", "variables")
        dead_truncated = dead_visible and total_dead_funcs > max_dead
        imports_truncated = imports_visible and total_unused_imports > max_imports
        vars_truncated = vars_visible and total_unref_vars > max_variables
        any_truncated = dead_truncated or imports_truncated or vars_truncated

        # Labeled stats — every count is named for what it counts so
        # agents can distinguish the raw total from what is shown.
        labeled_stats: dict[str, Any] = {
            # Honest label (Codex P2): the analyzer's dead set is TRANSITIVE
            # (zero-caller roots PLUS functions only reachable from them,
            # reason=unreachable_from_entry) — not pure zero-caller orphans.
            "total_dead_functions_transitive": total_dead_funcs,
            # filter = transitive reachability; #1941: listed = certified ones.
            "candidates_after_filters": candidates_total,
            "dead_functions_status": STATUS_CERTIFIED,
            "dead_functions_not_certified": cert_section.get("not_certified", 0),
            "dead_functions_unchecked": cert_section.get("unchecked", 0),
            "dead_functions_listed": listed_dead,
            "dead_functions_cap": max_dead,
            "dead_functions_high_confidence": total_dead_funcs - low_confidence_dead,
            "dead_functions_low_confidence": low_confidence_dead,
            "total_unused_imports": total_unused_imports,
            "unused_imports_listed": listed_imports,
            "unused_imports_cap": max_imports,
            "total_unreferenced_variables": total_unref_vars,
            "unreferenced_variables_listed": listed_vars,
            "unreferenced_variables_cap": max_variables,
            "total_functions": result.stats.get("total_functions", 0),
            "total_call_edges": result.stats.get("total_call_edges", 0),
        }

        # #1958: count what the answer covers; with no evidence it is unknown.
        evidence = scope_evidence(
            result.function_files,
            path=path,
            include_tests=include_tests,
            indexed=result.indexed,
        )
        labeled_stats.update(evidence.to_stats())
        insufficient = None
        if dead_visible:
            counts = CertCounts(
                candidates_total, total_dead_funcs, cert_section.get("unchecked", 0)
            )
            insufficient = insufficient_evidence(evidence, counts, self.project_root)

        # Wave 1b (audit health-10): emit an actionable next_step. dead_code
        # previously set none, so the boundary left agent_summary.next_step
        # empty — an agent saw a REVIEW verdict with N findings and no guidance.
        if total_all == 0:
            verdict = "INFO"
            next_step = (
                f"No dead code found among {evidence_sentence(evidence)} in scope."
                if dead_visible
                else "No unused imports or unreferenced variables found in scope."
            )
        else:
            verdict = "REVIEW" if total_all > 20 else "CAUTION"
            if any_truncated:
                parts: list[str] = []
                if dead_truncated:
                    parts.append(
                        f"showing {listed_dead} of {total_dead_funcs} dead functions"
                    )
                if imports_truncated:
                    parts.append(
                        f"showing {listed_imports} of {total_unused_imports} unused imports"
                    )
                if vars_truncated:
                    parts.append(
                        f"showing {listed_vars} of {total_unref_vars} unreferenced variables"
                    )
                truncation_note = "; ".join(parts)
                next_step = (
                    f"Results truncated ({truncation_note}). Raise max_dead / "
                    "max_imports / max_variables or filter by path to see more. "
                    "Static analysis can miss dynamic refs (reflection, plugins, "
                    "__all__). Run edit action=guard on a symbol to confirm zero "
                    "callers before deleting it."
                )
            else:
                next_step = (
                    f"Review the {listed_total} candidate(s) "
                    f"({listed_dead} dead functions, {listed_imports} unused imports, "
                    f"{listed_vars} unreferenced variables) — static analysis can miss "
                    "dynamic refs (reflection, plugins, __all__). Run edit action=guard "
                    "on a symbol to confirm zero callers before deleting it."
                )
            if dead_visible:
                next_step += (
                    f" {total_dead_funcs} certified dead function(s) of "
                    f"{evidence_sentence(evidence)} analyzed."
                )
            if dead_visible and low_confidence_dead:
                next_step += (
                    f" {low_confidence_dead} dead function(s) are confidence=low "
                    "(module path unresolvable, e.g. a hyphenated directory): "
                    "cross-file uses may be missing, so do not delete them on "
                    "this evidence alone."
                )
        not_certified = cert_section.get("not_certified", 0)
        unchecked_dead = cert_section.get("unchecked", 0)
        if dead_visible and (not_certified or unchecked_dead):
            next_step += (
                f" {not_certified} candidate(s) are not certified dead "
                "(possibly_dead_functions names the open callers evidence or the "
                f"outside supertype for each) and {unchecked_dead} were not checked "
                "in the time budget; neither is listed in dead_functions."
            )

        response: dict[str, Any] = {
            "success": True,
            "verdict": verdict,
            "status": STATUS_FOUND if total_all else STATUS_NONE_FOUND,
            "mode": mode,
            "project_root": self.project_root,
            "stats": labeled_stats,
            "truncated": any_truncated,
            "next_step": next_step,
            "dead_functions": [_serialize_dead_function(df) for df in dead_funcs],
            # #1941: candidates the callers evidence does not certify, and why.
            "possibly_dead_functions": cert_section.get("possibly_dead", []),
            "unused_imports": [_serialize_unused_import(ui) for ui in unused_imports],
            "unreferenced_variables": [_serialize_unref_var(uv) for uv in unref_vars],
        }
        if insufficient is not None:
            mark_unknown(response, *insufficient)
            labeled_stats["dead_functions_status"] = response["status"]

        if mode != "all":
            sections_to_keep = {
                "dead_functions": ["dead_functions"],
                "unused_imports": ["unused_imports"],
                "variables": ["unreferenced_variables"],
            }
            keep = sections_to_keep.get(mode, [])
            if "dead_functions" in keep:
                keep = [*keep, "possibly_dead_functions"]
            for key in (
                "dead_functions",
                "possibly_dead_functions",
                "unused_imports",
                "unreferenced_variables",
            ):
                if key not in keep:
                    response.pop(key, None)

        from ..utils.format_helper import apply_output_format_to_response

        return apply_output_format_to_response(response, output_format)


async def _certified(
    project_root: str,
    scoped: list[DeadFunction],
    all_dead: list[DeadFunction],
    cap: int,
) -> tuple[list[DeadFunction], dict[str, Any]]:
    """#1941: the ``scoped`` candidates that the callers evidence certifies dead.

    Every candidate of the project is asked (the scoped ones first), because a
    scoped function called only from an out-of-scope candidate is dead only if
    that caller is. Candidates the budget left unasked are never listed.
    """
    scoped_funcs = [df.function for df in scoped]
    dead, cert = await certify_transitive(
        project_root, scoped_funcs, [df.function for df in all_dead]
    )
    not_certified = [
        uncertified_entry(func, cert, dead)
        for func in scoped_funcs
        if func in cert.verdicts and func not in dead
    ]
    section = {
        "possibly_dead": not_certified[:cap],
        "not_certified": len(not_certified),
        "unchecked": sum(1 for func in scoped_funcs if func not in cert.verdicts),
        "elapsed_seconds": cert.elapsed_seconds,
    }
    return [df for df in scoped if df.function in dead], section


def _serialize_dead_function(df: DeadFunction) -> dict[str, Any]:
    return {
        "name": df.function.name,
        "qualified_name": query_name(df.function),
        "file": df.function.file_path,
        "line": df.function.start_line,
        "end_line": df.function.end_line,
        "language": df.function.language,
        "reason": df.reason,
        "dead_callee_count": len(df.dead_callees),
        "dead_callees": df.dead_callees[:10],
        # #1790：``low`` 表示文件的模块路径无法解析，来自其他文件的调用 / 引用可能缺失，
        # 不能据此删除。
        "confidence": df.confidence,
        "confidence_reason": df.confidence_reason,
    }


def _serialize_unused_import(ui: UnusedImport) -> dict[str, Any]:
    return {
        "file": ui.file,
        "line": ui.line,
        "import_text": ui.import_text,
        "unused_names": ui.unused_names,
    }


def _serialize_unref_var(uv: UnreferencedVariable) -> dict[str, Any]:
    return {
        "file": uv.file,
        "name": uv.name,
        "line": uv.line,
        "language": uv.language,
    }
