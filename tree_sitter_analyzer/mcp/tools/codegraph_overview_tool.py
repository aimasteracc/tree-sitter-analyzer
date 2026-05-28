#!/usr/bin/env python3
"""
CodeGraph Overview MCP Tool — API surface analysis.

Provides project-wide call graph intelligence:
- Entry points: functions with zero callers (public API surface)
- Dead code: functions that nobody calls and that call nobody
- Hub functions: functions called by many others (high fan-in)
- Call depth distribution: how deep call chains go
- Module coupling: which files have the most cross-file calls

CodeGraph parity: equivalent to CodeGraph's code intelligence overview.
"""

from typing import Any, cast

from ...call_graph import CachedCallGraph, CallGraph
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_HUB_CALLER_FILE_SAMPLE_LIMIT = 25


class CodeGraphOverviewTool(BaseMCPTool):
    """MCP Tool for project-wide call graph intelligence (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._call_graph: CallGraph | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._call_graph = None

    def _try_get_cache(self) -> Any:
        try:
            from ...ast_cache import ASTCache

            if self.project_root is None:
                return None
            cache = ASTCache(self.project_root)
            stats = cache.get_stats()
            if stats.get("total_files", 0) > 0:
                return cache
            cache.close()
        except Exception:  # nosec B110
            pass
        return None

    def _get_call_graph(self) -> CallGraph:
        if self._call_graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            cache = self._try_get_cache()
            if cache is not None:
                self._call_graph = CachedCallGraph(self.project_root, cache=cache)
            else:
                self._call_graph = CallGraph(self.project_root)
        return self._call_graph

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_overview",
            "description": (
                "Project-wide call graph intelligence (CodeGraph parity). "
                "Identifies entry points (public API), dead code, hub functions, "
                "call depth distribution, and module coupling. "
                "No other built-in tool provides API surface analysis."
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
                "max_entry_points": {
                    "type": "integer",
                    "description": "Max entry points to list (default: 30)",
                    "default": 30,
                },
                "max_hubs": {
                    "type": "integer",
                    "description": "Max hub functions to list (default: 20)",
                    "default": 20,
                },
                "max_dead": {
                    "type": "integer",
                    "description": "Max dead code candidates to list (default: 20)",
                    "default": 20,
                },
                "max_coupled_files": {
                    "type": "integer",
                    "description": "Max coupled files to list (default: 15)",
                    "default": 15,
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

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        max_entry_points = arguments.get("max_entry_points", 30)
        max_hubs = arguments.get("max_hubs", 20)
        max_dead = arguments.get("max_dead", 20)
        max_coupled_files = arguments.get("max_coupled_files", 15)
        output_format = arguments.get("output_format", "toon")

        graph = self._get_call_graph()
        graph.build()

        entry_points = _find_entry_points(graph, max_entry_points)
        hubs = _find_hub_functions(graph, max_hubs)
        dead_code = _find_dead_code(graph, max_dead)
        depth_dist = _compute_depth_distribution(graph)
        coupling = _compute_module_coupling(graph, max_coupled_files)

        summary = graph.summary()

        # Pain #18 (dogfood pass 3): codegraph_overview emitted no verdict.
        # REVIEW when there is significant dead code (signals project debt),
        # NOT_FOUND for an empty graph, INFO otherwise.
        fn_count = summary.get("function_count", 0)
        dead_count = len(dead_code)
        if fn_count == 0:
            verdict = "NOT_FOUND"
        elif dead_count > 10:
            verdict = "REVIEW"
        else:
            verdict = "INFO"

        result: dict[str, Any] = {
            "success": True,
            "verdict": verdict,
            "project_root": self.project_root,
            "summary": {
                "function_count": summary.get("function_count", 0),
                "call_edge_count": summary.get("call_edge_count", 0),
                "file_count": summary.get("file_count", 0),
                "entry_point_count": len(entry_points),
                "dead_code_count": len(dead_code),
                "max_call_depth": depth_dist.get("max_depth", 0),
            },
            "entry_points": entry_points,
            "hub_functions": hubs,
            "dead_code": dead_code,
            "call_depth_distribution": depth_dist,
            "module_coupling": coupling,
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _find_entry_points(graph: CallGraph, limit: int) -> list[dict[str, Any]]:
    """Functions with zero callers = public API surface."""
    entry_points = []
    for func in graph.function_refs():
        callers = graph.caller_refs_of(func)
        if not callers:
            entry_points.append(
                {
                    "name": func.name,
                    "file": func.file_path,
                    "line": func.start_line,
                    "language": func.language,
                    "callee_count": len(graph.callee_refs_of(func)),
                }
            )
    entry_points.sort(
        key=lambda x: (-cast(int, x["callee_count"]), cast(str, x["name"]))
    )
    return entry_points[:limit]


def _find_hub_functions(graph: CallGraph, limit: int) -> list[dict[str, Any]]:
    """Functions called by many others (high fan-in)."""
    candidates: list[tuple[int, str, Any]] = []
    for func in graph.function_refs():
        callers = graph.caller_refs_of(func)
        if len(callers) >= 3:
            candidates.append((len(callers), func.name, func))

    candidates.sort(key=lambda x: (-x[0], x[1]))
    hubs = []
    for caller_count, _name, func in candidates[:limit]:
        caller_files = sorted({c.file_path for c in graph.caller_refs_of(func)})
        hubs.append(
            {
                "name": func.name,
                "file": func.file_path,
                "line": func.start_line,
                "caller_count": caller_count,
                "caller_file_count": len(caller_files),
                "caller_files": caller_files[:_HUB_CALLER_FILE_SAMPLE_LIMIT],
                "caller_files_truncated": len(caller_files)
                > _HUB_CALLER_FILE_SAMPLE_LIMIT,
            }
        )
    return hubs


def _find_dead_code(graph: CallGraph, limit: int) -> list[dict[str, Any]]:
    """Functions with zero callers AND zero callees (dead code candidates)."""
    dead = []
    for func in graph.function_refs():
        callers = graph.caller_refs_of(func)
        callees = graph.callee_refs_of(func)
        if not callers and not callees:
            dead.append(
                {
                    "name": func.name,
                    "file": func.file_path,
                    "line": func.start_line,
                    "language": func.language,
                }
            )
    dead.sort(key=lambda x: (x["file"], x["name"]))
    return dead[:limit]


def _compute_depth_distribution(graph: CallGraph) -> dict[str, Any]:
    """Compute a bounded call depth distribution across all functions.

    Large monorepos can contain hundreds of thousands of call edges. Keep this
    pass linear by memoizing per function reference and by capping at the
    public distribution bucket limit.
    """
    func_depths: dict[str, int] = {}
    memo: dict[Any, int] = {}
    visiting: set[Any] = set()
    depth_cap = 10
    capped = False

    def _chain_depth(func: Any) -> int:
        nonlocal capped
        if func in memo:
            return memo[func]
        if func in visiting:
            return 0

        visiting.add(func)
        max_child = 0
        for callee in graph.callee_refs_of(func):
            child_depth = 1 + _chain_depth(callee)
            if child_depth > max_child:
                max_child = child_depth
            if max_child >= depth_cap:
                max_child = depth_cap
                capped = True
                break
        visiting.remove(func)
        memo[func] = max_child
        return max_child

    for func in graph.function_refs():
        d = _chain_depth(func)
        func_depths[func.qualified_name()] = d

    if not func_depths:
        return {
            "max_depth": 0,
            "distribution": {},
            "avg_depth": 0.0,
            "depth_cap": depth_cap,
            "capped": False,
        }

    max_depth = max(func_depths.values())
    dist: dict[str, int] = {}
    for d in func_depths.values():
        level = min(d, 10)
        label = f"depth_{level}" if level < 10 else "depth_10+"
        dist[label] = dist.get(label, 0) + 1

    return {
        "max_depth": max_depth,
        "avg_depth": round(sum(func_depths.values()) / len(func_depths), 2),
        "distribution": dict(sorted(dist.items())),
        "depth_cap": depth_cap,
        "capped": capped,
    }


def _compute_module_coupling(graph: CallGraph, limit: int) -> list[dict[str, Any]]:
    """Files with the most cross-file calls (high coupling)."""
    file_coupling: dict[str, dict[str, int]] = {}
    for caller in graph.function_refs():
        caller_file = caller.file_path
        for callee in graph.callee_refs_of(caller):
            callee_file = callee.file_path
            if caller_file == callee_file:
                continue
            if caller_file not in file_coupling:
                file_coupling[caller_file] = {}
            file_coupling[caller_file][callee_file] = (
                file_coupling[caller_file].get(callee_file, 0) + 1
            )

    result = []
    for src, targets in file_coupling.items():
        total_calls = sum(targets.values())
        result.append(
            {
                "file": src,
                "outgoing_calls": total_calls,
                "target_files": len(targets),
                "top_targets": sorted(targets.items(), key=lambda x: -x[1])[:5],
            }
        )
    result.sort(key=lambda x: -cast(int, x["outgoing_calls"]))
    return result[:limit]
