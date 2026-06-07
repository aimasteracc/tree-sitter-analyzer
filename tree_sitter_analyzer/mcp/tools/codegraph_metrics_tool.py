#!/usr/bin/env python3
"""
CodeGraph Metrics MCP Tool — Aggregated project intelligence dashboard.

Single-call entry point that combines data from all pre-indexed sources
into a unified project card:

  - AST cache: file count, symbol count, language breakdown, FTS5 status
  - Call graph: function count, call edge count, entry points, dead code
  - Complexity: mean/median/max cyclomatic complexity, high-risk files
  - Routes: HTTP endpoint count by framework
  - Health: file grade distribution (A-F), worst files

Agents call this ONCE to get the full picture before drilling into
specific tools. CodeGraph parity: equivalent to CodeGraph's
"Code Intelligence Dashboard".

All data comes from pre-indexed SQLite caches — queries are instant.
Gracefully degrades when indexes don't exist yet (reports what's
available and suggests which tools to run first).
"""

from __future__ import annotations

from typing import Any

from ...utils import setup_logger
from ..utils.auto_index_guard import ensure_indexed
from ._response_builder import build_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphMetricsTool(BaseMCPTool):
    """MCP Tool for aggregated project intelligence metrics."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None

    def _get_cache(self) -> Any:
        if self._cache is not None:
            return self._cache
        # codegraph_metrics is a READ-only metrics surface. Building
        # the AST index synchronously here regularly tripped MCP
        # client timeouts (30-60 s on a 1500-file repo, vs the 30 s
        # default client timeout), surfacing as "tool never returns".
        # Pass ``auto_build=False`` so we return ``None`` immediately
        # when the cache is empty; ``_collect_cache_metrics`` already
        # surfaces the right hint ("Run ast_cache mode=index first")
        # for that path.
        cache = ensure_indexed(self.project_root, auto_build=False)
        if cache is not None:
            self._cache = cache
        return self._cache

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_metrics",
            "description": (
                "Aggregated project intelligence dashboard (CodeGraph parity). "
                "Combines AST cache stats, call graph metrics, complexity distribution, "
                "route counts, and file health into a single project card. "
                "Agents call this once to get the full picture. "
                "All data from pre-indexed caches — instant response. "
                "Suggests which tools to run first if indexes are empty. "
                "No other tool provides cross-domain aggregated metrics."
            ),
            "inputSchema": self.get_tool_schema(),
            # PM-fix: codegraph_metrics READS cache stats only — Class A, not B.
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
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "cache",
                            "call_graph",
                            "complexity",
                            "routes",
                            "health",
                        ],
                    },
                    "description": (
                        "Metric sections to include (default: all). "
                        "Omit sections that are slow or irrelevant."
                    ),
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        sections = arguments.get("sections")
        if sections is not None:
            valid = {"cache", "call_graph", "complexity", "routes", "health"}
            invalid = set(sections) - valid
            if invalid:
                raise ValueError(
                    f"Invalid sections: {invalid}. Must be subset of {valid}"
                )
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        requested = arguments.get("sections") or [
            "cache",
            "call_graph",
            "complexity",
            "routes",
            "health",
        ]
        output_format = arguments.get("output_format", "toon")

        cache = self._get_cache()
        payload: dict[str, Any] = {
            "project_root": self.project_root,
            "cache_indexed": cache is not None,
        }

        if "cache" in requested:
            payload["cache"] = self._collect_cache_metrics(cache)

        if "call_graph" in requested:
            payload["call_graph"] = self._collect_call_graph_metrics(cache)

        if "complexity" in requested:
            payload["complexity"] = self._collect_complexity_metrics(cache)

        if "routes" in requested:
            payload["routes"] = self._collect_route_metrics()

        if "health" in requested:
            payload["health"] = self._collect_health_metrics()

        suggestions = self._build_suggestions(payload)
        if suggestions:
            payload["suggested_next_steps"] = suggestions

        payload["sections_included"] = list(requested)

        result = build_response(verdict="INFO", **payload)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _collect_cache_metrics(self, cache: Any) -> dict[str, Any]:
        if cache is None:
            return {"status": "empty", "hint": "Run ast_cache mode=index first"}
        try:
            stats = cache.get_stats()
            return {
                "status": "indexed",
                "total_files": stats.get("total_files", 0),
                "total_symbols": stats.get("total_symbols", 0),
                "fts5_available": stats.get("fts5_available", False),
                "fts_indexed_symbols": stats.get("fts_indexed_symbols", 0),
                "by_language": stats.get("by_language", {}),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _collect_call_graph_metrics(self, cache: Any) -> dict[str, Any]:
        if cache is None:
            return {
                "status": "empty",
                "hint": "Run ast_cache mode=index first",
                "data_source": "none",
            }
        try:
            from ...call_graph import CachedCallGraph

            assert self.project_root is not None, "project_root required"
            cg = CachedCallGraph(self.project_root, cache=cache)
            cg.build()

            func_dicts = cg.all_functions()
            # NOTE: FunctionRef.to_dict() keys the path under "file" (NOT
            # "file_path"). Reading the wrong key made every function string an
            # empty path "::name" that never matched the real-path call-edge keys
            # below, degenerating to entry_points == dead == total_functions and
            # files_with_functions == 1 (F1 trust-breaker). Keep these keys in
            # sync with FunctionRef.to_dict() in call_graph.py.
            functions: list[str] = [
                f"{f.get('file', '')}::{f.get('name', '')}" for f in func_dicts
            ]
            call_edges: list[tuple[str, str]] = [
                (
                    f"{caller.file_path}::{caller.name}",
                    f"{callee.file_path}::{callee.name}",
                )
                for caller, callee, _line in cg.call_edges()
            ]

            callers_map: dict[str, int] = {}
            callees_map: dict[str, int] = {}
            for caller, callee in call_edges:
                callers_map.setdefault(callee, 0)
                callers_map[callee] += 1
                callees_map.setdefault(caller, 0)
                callees_map[caller] += 1

            entry_points = [f for f in functions if f not in callers_map]
            dead = [
                f for f in functions if f not in callers_map and f not in callees_map
            ]

            top_hubs = sorted(callers_map.items(), key=lambda x: -x[1])[:10]

            files: set[str] = set()
            for func in functions:
                if "::" in func:
                    files.add(func.split("::")[0])

            return {
                "status": "computed",
                "total_functions": len(functions),
                "total_call_edges": len(call_edges),
                "entry_points": len(entry_points),
                "dead_code_candidates": len(dead),
                "top_hub_functions": [{"name": n, "callers": c} for n, c in top_hubs],
                "files_with_functions": len(files),
                "data_source": "ast_cache",
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _collect_complexity_metrics(self, cache: Any) -> dict[str, Any]:
        try:
            from ...complexity_heatmap import analyze_project_heatmap

            assert self.project_root is not None, "project_root required"
            heatmap = analyze_project_heatmap(
                self.project_root,
                max_files=200,
                cache=cache,
            )

            file_heatmaps = heatmap.get("files", {})
            if not file_heatmaps:
                return {"status": "no_data"}

            complexities: list[int] = []
            high_risk_files: list[dict[str, Any]] = []
            risk_bands = {"low": 0, "medium": 0, "high": 0, "very_high": 0}

            for file_path, fh in file_heatmaps.items():
                if isinstance(fh, dict):
                    max_c = fh.get("max_complexity", 0)
                else:
                    max_c = getattr(fh, "max_complexity", 0)
                complexities.append(max_c)
                if max_c <= 5:
                    risk_bands["low"] += 1
                elif max_c <= 10:
                    risk_bands["medium"] += 1
                elif max_c <= 20:
                    risk_bands["high"] += 1
                else:
                    risk_bands["very_high"] += 1
                if max_c > 15:
                    high_risk_files.append({"file": file_path, "complexity": max_c})

            complexities.sort()
            n = len(complexities)
            mean_c = sum(complexities) / n if n > 0 else 0
            median_c = complexities[n // 2] if n > 0 else 0
            max_c = complexities[-1] if complexities else 0

            high_risk_files.sort(key=lambda x: -x["complexity"])
            return {
                "status": "computed",
                "files_analyzed": n,
                "mean_complexity": round(mean_c, 2),
                "median_complexity": median_c,
                "max_complexity": max_c,
                "risk_bands": risk_bands,
                "high_risk_files": high_risk_files[:10],
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _collect_route_metrics(self) -> dict[str, Any]:
        try:
            from ...route_detector import RouteDetector

            assert self.project_root is not None, "project_root required"
            detector = RouteDetector(self.project_root)
            summary = detector.summary()
            return {
                "status": "computed",
                "total_routes": summary.get("total_routes", 0),
                "by_framework": summary.get("by_framework", {}),
                "by_method": summary.get("by_method", {}),
                "route_files": summary.get("file_count", 0),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _collect_health_metrics(self) -> dict[str, Any]:
        try:
            from ...health_scorer import HealthScorer

            assert self.project_root is not None, "project_root required"
            scorer = HealthScorer()
            scores = scorer.score_project(self.project_root)
            if not scores:
                return {"status": "no_data"}

            grade_dist: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
            for info in scores:
                grade = info.grade
                if grade in grade_dist:
                    grade_dist[grade] += 1

            worst = sorted(scores, key=lambda x: x.total)[:5]
            avg_score = sum(s.total for s in scores) / len(scores) if scores else 0

            return {
                "status": "computed",
                "total_files_scored": len(scores),
                "average_score": round(avg_score, 1),
                "grade_distribution": grade_dist,
                "worst_files": [
                    {
                        "file": w.file_path,
                        "score": round(w.total, 1),
                        "grade": w.grade,
                    }
                    for w in worst
                ],
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _build_suggestions(self, result: dict[str, Any]) -> list[str]:
        suggestions: list[str] = []

        cache_info = result.get("cache", {})
        if cache_info.get("status") == "empty":
            suggestions.append(
                "Run ast_cache mode=index to build the pre-indexed cache"
            )
            return suggestions

        cg_info = result.get("call_graph", {})
        if cg_info.get("status") == "computed":
            dead = cg_info.get("dead_code_candidates", 0)
            if dead > 0:
                suggestions.append(
                    f"{dead} dead code candidates found — use codegraph_dead_code for details"
                )

        cx_info = result.get("complexity", {})
        if cx_info.get("status") == "computed":
            vh = cx_info.get("risk_bands", {}).get("very_high", 0)
            if vh > 0:
                suggestions.append(
                    f"{vh} files with very high complexity — use codegraph_complexity_heatmap"
                )

        route_info = result.get("routes", {})
        if (
            route_info.get("status") == "computed"
            and route_info.get("total_routes", 0) > 0
        ):
            suggestions.append(
                f"{route_info['total_routes']} routes detected — use detect_routes for URL→Handler mapping"
            )

        return suggestions
