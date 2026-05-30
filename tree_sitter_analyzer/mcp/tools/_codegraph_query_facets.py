"""Facet builders for CodeGraph query results.

Each facet enriches a query result with a specific analysis dimension
(complexity, health, risk, UML, affected tests).
"""

from __future__ import annotations

import os
from typing import Any

from ._codegraph_query_state import _QueryState
from ._codegraph_query_symbols import (
    absolute_path as _absolute_path,
)
from ._codegraph_query_symbols import (
    unique_symbol_files as _unique_symbol_files,
)


def complexity_facet(
    cache: Any, project_root: str, symbols: list[dict[str, Any]], max_files: int
) -> dict[str, Any]:
    try:
        from ...complexity_heatmap import analyze_file_complexity_from_cache
    except Exception as exc:
        return {"status": "missing", "reason": str(exc)}

    entries: list[dict[str, Any]] = []
    for file_path in _unique_symbol_files(symbols)[:max_files]:
        abs_path = _absolute_path(project_root, file_path)
        try:
            functions = analyze_file_complexity_from_cache(cache, abs_path)
        except Exception as exc:
            entries.append({"file": file_path, "status": "error", "error": str(exc)})
            continue
        if not functions:
            entries.append({"file": file_path, "status": "no_functions"})
            continue
        hotspots = sorted(functions, key=lambda item: item.complexity, reverse=True)[:5]
        entries.append(
            {
                "file": file_path,
                "status": "included",
                "function_count": len(functions),
                "max_complexity": max(item.complexity for item in functions),
                "total_complexity": sum(item.complexity for item in functions),
                "hotspots": [
                    {
                        "name": item.name,
                        "line": item.line,
                        "complexity": item.complexity,
                    }
                    for item in hotspots
                ],
            }
        )
    return {"status": "included", "files": entries}


def health_facet(
    project_root: str, symbols: list[dict[str, Any]], max_files: int
) -> dict[str, Any]:
    try:
        from ...health_scorer import HealthScorer
    except Exception as exc:
        return {"status": "missing", "reason": str(exc)}

    scorer = HealthScorer()
    entries: list[dict[str, Any]] = []
    for file_path in _unique_symbol_files(symbols)[:max_files]:
        abs_path = _absolute_path(project_root, file_path)
        try:
            score = scorer.score_file(abs_path, fast_dependencies=True)
        except Exception as exc:
            entries.append({"file": file_path, "status": "error", "error": str(exc)})
            continue
        entries.append(
            {
                "file": file_path,
                "status": "included",
                "total": score.total,
                "grade": score.grade,
                "dimensions": score.dimensions,
            }
        )
    return {"status": "included", "files": entries}


def affected_tests_facet(state: _QueryState) -> dict[str, Any]:
    files = _unique_symbol_files(state.symbols)
    tests = [
        file_path
        for file_path in files
        if "test" in os.path.basename(file_path).lower()
        or "/test" in file_path.replace("\\", "/").lower()
    ]
    return {
        "status": "included" if tests else "missing",
        "files": tests,
        "reason": None if tests else "no test files appeared in the current chain",
    }


def risk_facet(state: _QueryState) -> dict[str, Any]:
    reasons: list[str] = []
    complexity = state.facets.get("complexity", {})
    for entry in complexity.get("files", []):
        max_complexity = int(entry.get("max_complexity") or 0)
        if max_complexity >= 20:
            reasons.append(f"{entry.get('file')}: critical complexity {max_complexity}")
        elif max_complexity >= 11:
            reasons.append(f"{entry.get('file')}: high complexity {max_complexity}")

    health = state.facets.get("health", {})
    for entry in health.get("files", []):
        if entry.get("grade") in {"D", "F"}:
            reasons.append(f"{entry.get('file')}: health grade {entry.get('grade')}")

    caller_edges = sum(len(v) for v in state.relationships["callers"].values())
    if caller_edges >= 10:
        reasons.append(f"fan-in {caller_edges} across current symbols")

    return {
        "status": "included",
        "level": "review" if reasons else "info",
        "reasons": reasons,
    }


def uml_facet(
    state: _QueryState,
    *,
    direction: str,
    max_edges: int,
) -> dict[str, Any]:
    from .codegraph_visualization_hub import query_flow_uml_facet

    return query_flow_uml_facet(
        symbols=state.symbols,
        current=state.current,
        relationships=state.relationships,
        direction=direction,
        max_edges=max_edges,
    )
