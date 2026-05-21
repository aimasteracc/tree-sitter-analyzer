#!/usr/bin/env python3
"""
CodeGraph Call Graph MCP Tool

Exposes bidirectional function-level call tracking via MCP protocol.
Provides callers_of, callees_of, call_chain, and summary queries.
CodeGraph parity: equivalent to codegraph_callers / codegraph_callees.
"""

import time
from typing import Any

from ...call_graph import CallGraph
from ...utils import setup_logger
from ._graph_cache_fingerprint import GraphFingerprint, compute_graph_fingerprint
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


def _maybe_bare_name_hint(
    graph: CallGraph, func_name: str, hit_count: int, mode: str
) -> str | None:
    """Return a hint string when a qualified ``Class.method`` lookup returns
    zero hits but the bare ``method`` name would have matched something.

    Returns ``None`` when there's no useful hint (already non-zero hits,
    or func_name is not qualified, or the bare name also has zero hits).
    """
    if hit_count > 0:
        return None
    if (
        "." not in func_name
        or ":" in func_name
        or "/" in func_name
        or "\\" in func_name
    ):
        return None
    _, _, suffix = func_name.rpartition(".")
    if not suffix:
        return None
    try:
        if mode == "callers":
            alt = graph.callers_of(suffix)
        elif mode == "callees":
            alt = graph.callees_of(suffix)
        else:  # chain
            alt = graph.call_chain(suffix)
    except Exception:
        return None
    if not alt:
        return None
    return (
        f"0 hits for qualified name '{func_name}'. The bare name '{suffix}' "
        f"would match {len(alt)} {mode} (across all classes). Re-run with "
        f"function_name='{suffix}' to see them, or pass file_path= to "
        f"disambiguate."
    )


class CodeGraphCallTool(BaseMCPTool):
    """MCP Tool for function-level call graph analysis."""

    def __init__(self, project_root: str | None = None) -> None:
        self._call_graph: CallGraph | None = None
        # H4 fix: fingerprint snapshotted when the graph was built.
        # Compared against a fresh fingerprint on every _get_call_graph()
        # to detect in-place edits that don't change the directory mtime.
        self._call_graph_fingerprint: GraphFingerprint | None = None
        self._call_graph_built_at: float | None = None
        self._cache_invalidated_reason: str | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._call_graph = None
        self._call_graph_fingerprint = None
        self._call_graph_built_at = None
        self._cache_invalidated_reason = None

    def _get_call_graph(self) -> CallGraph:
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        current_fp = compute_graph_fingerprint(self.project_root)
        reason: str | None = None
        if self._call_graph is None:
            reason = "cold"
        elif self._call_graph_fingerprint != current_fp:
            reason = self._explain_fingerprint_delta(
                self._call_graph_fingerprint, current_fp
            )

        if reason is not None:
            self._call_graph = CallGraph(self.project_root)
            self._call_graph.build()
            self._call_graph_fingerprint = current_fp
            self._call_graph_built_at = time.time()
            self._cache_invalidated_reason = reason
        else:
            # Warm reuse — clear any prior invalidation reason so the next
            # response stays quiet about it.
            self._cache_invalidated_reason = None
        assert self._call_graph is not None  # nosec B101 - just rebuilt above
        return self._call_graph

    @staticmethod
    def _explain_fingerprint_delta(
        old: GraphFingerprint | None, new: GraphFingerprint
    ) -> str:
        """Best-effort human-readable reason the cache was invalidated."""
        if old is None:
            return "cold"
        if old.file_count != new.file_count:
            delta = new.file_count - old.file_count
            return (
                f"file_count_changed ({delta:+d}, {old.file_count}->{new.file_count})"
            )
        if old.max_mtime_ns != new.max_mtime_ns:
            return "source_modified"
        return "unknown"

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_call_graph",
            "description": (
                "Function-level call graph (CodeGraph parity). Modes: "
                "callers (who calls X), callees (what does X call), "
                "chain (transitive call chain), summary (stats), "
                "all_functions (list all discovered functions). "
                "No other built-in tool provides function-level call tracking. "
                "First call on a project builds the full graph (2-5s on "
                "medium repos); subsequent calls within the session are fast."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [
                        "callers",
                        "callees",
                        "chain",
                        "summary",
                        "all_functions",
                    ],
                    "description": "Query mode (default: summary)",
                    "default": "summary",
                },
                "function_name": {
                    "type": "string",
                    "description": "Target function name (required for callers, callees, chain modes)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to disambiguate overloaded functions",
                },
                "depth": {
                    "type": "integer",
                    "description": "Max traversal depth for chain mode (default: 5)",
                    "default": 5,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    _VALID_MODES = ("callers", "callees", "chain", "summary", "all_functions")

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "summary")
        if mode not in self._VALID_MODES:
            raise ValueError(
                f"Invalid mode '{mode}'; expected one of: "
                f"{', '.join(self._VALID_MODES)}."
            )
        if mode in ("callers", "callees", "chain") and "function_name" not in arguments:
            raise ValueError(f"function_name is required for mode '{mode}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        started = time.perf_counter()
        mode = arguments.get("mode", "summary")
        output_format = arguments.get("output_format", "toon")
        # Cache hit fast-path: the first call builds the graph (2-5s on
        # medium repos); every subsequent call within the same process
        # reuses ``self._call_graph`` and finishes in tens of ms.
        graph = self._get_call_graph()

        if mode == "summary":
            result = {"success": True, "mode": "summary", **graph.summary()}
        elif mode == "all_functions":
            funcs = graph.all_functions()
            result = {
                "success": True,
                "mode": "all_functions",
                "count": len(funcs),
                "functions": funcs,
            }
        elif mode == "callers":
            func_name = arguments["function_name"]
            file_path = arguments.get("file_path")
            callers = graph.callers_of(func_name, file_path)
            result = {
                "success": True,
                "mode": "callers",
                "function": func_name,
                "caller_count": len(callers),
                "callers": callers,
            }
            hint = _maybe_bare_name_hint(graph, func_name, len(callers), "callers")
            if hint:
                result["hint"] = hint
        elif mode == "callees":
            func_name = arguments["function_name"]
            file_path = arguments.get("file_path")
            callees = graph.callees_of(func_name, file_path)
            result = {
                "success": True,
                "mode": "callees",
                "function": func_name,
                "callee_count": len(callees),
                "callees": callees,
            }
            hint = _maybe_bare_name_hint(graph, func_name, len(callees), "callees")
            if hint:
                result["hint"] = hint
        elif mode == "chain":
            func_name = arguments["function_name"]
            file_path = arguments.get("file_path")
            depth = arguments.get("depth", 5)
            chain = graph.call_chain(func_name, file_path, depth)
            result = {
                "success": True,
                "mode": "chain",
                "function": func_name,
                "depth": depth,
                "edge_count": len(chain),
                "chain": chain,
            }
            hint = _maybe_bare_name_hint(graph, func_name, len(chain), "chain")
            if hint:
                result["hint"] = hint
        else:  # pragma: no cover - validate_arguments rejects unknown modes
            raise ValueError(
                f"Invalid mode '{mode}'; expected one of: "
                f"{', '.join(self._VALID_MODES)}."
            )

        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        # H4 introspection: tell callers when this response came from a
        # rebuilt graph vs a warm reuse, so AI agents can reason about
        # whether they're seeing post-edit state.
        if self._call_graph_built_at is not None:
            result["cache_age_s"] = round(time.time() - self._call_graph_built_at, 3)
        if self._cache_invalidated_reason is not None:
            result["cache_invalidated_reason"] = self._cache_invalidated_reason

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)
