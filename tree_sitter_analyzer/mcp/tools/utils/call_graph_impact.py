#!/usr/bin/env python3
"""Call-graph-aware function-level change impact analysis.

Enriches the file-level change impact with function-level precision from the
call graph.  When a file changes, this module identifies:

* **Upstream callers** — functions in *other* files that call into the changed
  file (who is affected by this change).
* **Downstream callees** — functions the changed file calls in other files
  (what this change depends on).
* **Function-level risk** — high fan-in functions (called by many) get elevated
  risk because changing them has wider blast radius.

This is the key CodeGraph-differentiator: file-level dependency graphs only
know *that* A imports B, not *which functions* in A depend on *which
functions* in B.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ....ast_cache import ASTCache
from ....call_graph import CachedCallGraph, CallGraph

logger = logging.getLogger(__name__)

_MAX_FUNCTIONS_PER_FILE = 30
_MAX_UPSTREAM = 50
_MAX_DOWNSTREAM = 50


@dataclass
class FunctionImpact:
    name: str
    file: str
    line: int
    upstream_callers: list[dict[str, Any]] = field(default_factory=list)
    downstream_callees: list[dict[str, Any]] = field(default_factory=list)
    fan_in: int = 0
    fan_out: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "fan_in": self.fan_in,
            "fan_out": self.fan_out,
        }
        if self.upstream_callers:
            d["upstream_callers"] = self.upstream_callers[:_MAX_UPSTREAM]
        if self.downstream_callees:
            d["downstream_callees"] = self.downstream_callees[:_MAX_DOWNSTREAM]
        return d


@dataclass
class CallGraphImpactResult:
    functions_analyzed: int = 0
    total_upstream: int = 0
    total_downstream: int = 0
    high_risk_functions: list[str] = field(default_factory=list)
    cross_file_callers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    cross_file_callees: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    function_impacts: list[dict[str, Any]] = field(default_factory=list)
    affected_functions_by_file: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "functions_analyzed": self.functions_analyzed,
            "total_upstream_callers": self.total_upstream,
            "total_downstream_callees": self.total_downstream,
            "high_risk_functions": self.high_risk_functions[:20],
            "cross_file_callers": self.cross_file_callers,
            "cross_file_callees": self.cross_file_callees,
            "function_impacts": self.function_impacts[:_MAX_FUNCTIONS_PER_FILE],
            "affected_functions_by_file": self.affected_functions_by_file,
        }


def _build_call_graph(project_root: str) -> CallGraph | None:
    try:
        cache = ASTCache(project_root)
        stats = cache.get_stats()
        cg: CallGraph
        if stats.get("total_files", 0) > 0:
            cg = CachedCallGraph(project_root, cache=cache)
        else:
            cache.close()
            cg = CallGraph(project_root)
        cg.build()
        return cg
    except Exception:
        try:
            cg = CallGraph(project_root)
            cg.build()
            return cg
        except Exception:
            logger.debug("call graph build failed for %s", project_root, exc_info=True)
            return None


def compute_call_graph_impact(
    project_root: str,
    changed_files: list[str],
) -> CallGraphImpactResult | None:
    if not changed_files:
        return None

    cg = _build_call_graph(project_root)
    if cg is None:
        return None

    result = CallGraphImpactResult()
    changed_set = set(changed_files)
    all_funcs = cg.all_functions()
    funcs_by_file: dict[str, list[dict[str, Any]]] = {}
    for func in all_funcs:
        fp = func.get("file", "")
        funcs_by_file.setdefault(fp, []).append(func)

    for changed_file in changed_files:
        file_funcs = funcs_by_file.get(changed_file, [])
        if not file_funcs:
            continue

        for func in file_funcs[:_MAX_FUNCTIONS_PER_FILE]:
            func_name = func["name"]
            func_line = func.get("line", 0)

            callers = cg.callers_of(func_name, file_path=changed_file)
            cross_file_callers = [
                c for c in callers if c.get("file", "") not in changed_set
            ]

            callees = cg.callees_of(func_name, file_path=changed_file)
            cross_file_callees = [
                c for c in callees if c.get("file", "") not in changed_set
            ]

            impact = FunctionImpact(
                name=func_name,
                file=changed_file,
                line=func_line,
                upstream_callers=cross_file_callers,
                downstream_callees=cross_file_callees,
                fan_in=len(callers),
                fan_out=len(callees),
            )

            result.functions_analyzed += 1
            result.total_upstream += len(cross_file_callers)
            result.total_downstream += len(cross_file_callees)

            if cross_file_callers:
                result.cross_file_callers.setdefault(changed_file, []).extend(
                    cross_file_callers[:10]
                )
                for caller in cross_file_callers:
                    caller_file = caller.get("file", "")
                    caller_name = caller.get("name", "")
                    result.affected_functions_by_file.setdefault(
                        caller_file, []
                    ).append(f"{caller_name} -> {func_name}")

            if cross_file_callees:
                result.cross_file_callees.setdefault(changed_file, []).extend(
                    cross_file_callees[:10]
                )

            if impact.fan_in >= 5:
                result.high_risk_functions.append(
                    f"{changed_file}:{func_name} (fan_in={impact.fan_in})"
                )

            result.function_impacts.append(impact.to_dict())

    return result
