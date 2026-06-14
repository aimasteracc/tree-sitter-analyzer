#!/usr/bin/env python3
"""
CodeGraph Impact MCP Tool — Function-level blast radius analysis.

Standalone query tool that answers "what's the blast radius of changing function X?"
Provides:
- function_impact: Direct + transitive callers/callees, risk assessment for one function
- blast_radius: Aggregate impact for a set of functions (or files), with propagation
- risk_score: Quantified risk assessment (0-100) for modifying a function

Unlike callers/callees tools (direct edges only), this provides transitive reachability,
risk scoring, and multi-function blast radius aggregation.

CodeGraph parity: equivalent to CodeGraph's impact analysis.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from ...call_graph import CachedCallGraph, CallGraph, FunctionRef
from ...utils import setup_logger
from ...utils.test_detection import is_test_file
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_MAX_TRANSITIVE = 200
_MAX_DEPTH = 10
# Wave 1b (audit nav-08): cap the EMITTED caller/callee lists. The full counts
# are kept (direct_*/transitive_*_count), but a hub like create_tool_registry
# otherwise serialises ~70k chars of caller/callee dicts and overflows the
# tool-result token budget. The agent gets a representative head + the true
# counts + a truncation flag; the full list is one callers/callees call away.
_MAX_LISTED = 50


def _partition_refs(
    refs: list[FunctionRef],
) -> tuple[list[FunctionRef], list[FunctionRef]]:
    """Split refs into (production, test) using the canonical is_test_file.

    is_test_file lives in utils/test_detection.py and is path-based only —
    never by symbol name — so a production class named TestRunner is not
    misclassified.
    """
    prod = [r for r in refs if not is_test_file(r.file_path)]
    test = [r for r in refs if is_test_file(r.file_path)]
    return prod, test


def _compute_transitive_callers(
    graph: CallGraph,
    func_name: str,
    file_path: str | None = None,
    max_depth: int = _MAX_DEPTH,
    include_tests: bool = False,
) -> list[dict[str, Any]]:
    targets = graph.resolve_targets(func_name, file_path)
    visited: set[str] = set()
    result: list[dict[str, Any]] = []
    queue: deque[tuple[FunctionRef, int]] = deque((t, 0) for t in targets)

    while queue:
        current, d = queue.popleft()
        if d >= max_depth:
            continue
        for caller in graph.caller_refs_of(current):
            if not include_tests and is_test_file(caller.file_path):
                continue  # filter before to_dict()
            key = caller.qualified_name()
            if key not in visited:
                visited.add(key)
                entry = caller.to_dict()
                entry["distance"] = d + 1
                result.append(entry)
                queue.append((caller, d + 1))
                if len(result) >= _MAX_TRANSITIVE:
                    return result
    return result


def _compute_transitive_callees(
    graph: CallGraph,
    func_name: str,
    file_path: str | None = None,
    max_depth: int = _MAX_DEPTH,
    include_tests: bool = False,
) -> list[dict[str, Any]]:
    targets = graph.resolve_targets(func_name, file_path)
    visited: set[str] = set()
    result: list[dict[str, Any]] = []
    queue: deque[tuple[FunctionRef, int]] = deque((t, 0) for t in targets)

    while queue:
        current, d = queue.popleft()
        if d >= max_depth:
            continue
        for callee in graph.callee_refs_of(current):
            if not include_tests and is_test_file(callee.file_path):
                continue  # filter before to_dict()
            key = callee.qualified_name()
            if key not in visited:
                visited.add(key)
                entry = callee.to_dict()
                entry["distance"] = d + 1
                result.append(entry)
                queue.append((callee, d + 1))
                if len(result) >= _MAX_TRANSITIVE:
                    return result
    return result


def _compute_risk_score(
    graph: CallGraph,
    func_name: str,
    file_path: str | None = None,
    include_tests: bool = False,
) -> dict[str, Any]:
    targets = graph.resolve_targets(func_name, file_path)
    if not targets:
        return {
            "score": 0,
            "level": "unknown",
            "factors": {},
            "tests": {"test_callers_count": 0, "test_callees_count": 0},
        }

    target = targets[0]
    all_callers = graph.caller_refs_of(target)
    all_callees = graph.callee_refs_of(target)
    prod_callers, test_callers = _partition_refs(all_callers)
    prod_callees, test_callees = _partition_refs(all_callees)

    fan_in = len(prod_callers)
    fan_out = len(prod_callees)
    caller_files = {c.file_path for c in prod_callers}
    callee_files = {c.file_path for c in prod_callees}
    cross_file_callers = len(caller_files - {target.file_path})
    cross_file_callees = len(callee_files - {target.file_path})

    score = 0
    factors: dict[str, Any] = {}

    if fan_in >= 10:
        score += 35
    elif fan_in >= 5:
        score += 20
    elif fan_in >= 3:
        score += 10
    factors["fan_in"] = fan_in

    if cross_file_callers >= 5:
        score += 25
    elif cross_file_callers >= 2:
        score += 15
    factors["cross_file_callers"] = cross_file_callers

    if fan_out >= 10:
        score += 20
    elif fan_out >= 5:
        score += 10
    factors["fan_out"] = fan_out

    if cross_file_callees >= 3:
        score += 15
    elif cross_file_callees >= 1:
        score += 5
    factors["cross_file_callees"] = cross_file_callees

    chain = graph.call_chain(func_name, file_path, depth=5)
    max_chain_depth = max((e["depth"] for e in chain), default=0)
    if max_chain_depth >= 4:
        score += 5
    factors["max_chain_depth"] = max_chain_depth

    score = min(score, 100)

    if score >= 60:
        level = "critical"
    elif score >= 40:
        level = "high"
    elif score >= 20:
        level = "medium"
    else:
        level = "low"

    # RFC-0014 Phase A: always surface test counts; lists behind include_tests opt-in.
    tests_bucket: dict[str, Any] = {
        "test_callers_count": len(test_callers),
        "test_callees_count": len(test_callees),
    }
    if include_tests:
        tests_bucket["test_caller_files"] = sorted({r.file_path for r in test_callers})
        tests_bucket["test_callee_files"] = sorted({r.file_path for r in test_callees})

    return {
        "score": score,
        "level": level,
        "factors": factors,
        "function": func_name,
        "file": target.file_path,
        "tests": tests_bucket,
    }


def _blast_radius_for_functions(
    graph: CallGraph,
    function_names: list[str],
    file_path: str | None = None,
    depth: int = 5,
) -> dict[str, Any]:
    all_affected: set[str] = set()
    propagation_chains: list[dict[str, Any]] = []
    files_at_risk: dict[str, set[str]] = {}

    for func_name in function_names:
        targets = graph.resolve_targets(func_name, file_path)
        for target in targets:
            start_key = target.qualified_name()
            all_affected.add(start_key)

            queue: deque[tuple[FunctionRef, int]] = deque([(target, 0)])
            visited: set[str] = {start_key}

            while queue:
                current, d = queue.popleft()
                if d >= depth:
                    continue
                for caller in graph.caller_refs_of(current):
                    key = caller.qualified_name()
                    if key not in visited:
                        visited.add(key)
                        all_affected.add(key)
                        caller_set = files_at_risk.setdefault(caller.file_path, set())
                        caller_set.add(caller.name)
                        from_dict = current.to_dict()
                        to_dict = caller.to_dict()
                        propagation_chains.append(
                            {
                                "from": from_dict,
                                "to": to_dict,
                                "direction": "upstream",
                                "depth": d + 1,
                            }
                        )
                        queue.append((caller, d + 1))

                for callee in graph.callee_refs_of(current):
                    key = callee.qualified_name()
                    if key not in visited:
                        visited.add(key)
                        all_affected.add(key)
                        callee_set = files_at_risk.setdefault(callee.file_path, set())
                        callee_set.add(callee.name)
                        from_dict = current.to_dict()
                        to_dict = callee.to_dict()
                        propagation_chains.append(
                            {
                                "from": from_dict,
                                "to": to_dict,
                                "direction": "downstream",
                                "depth": d + 1,
                            }
                        )
                        queue.append((callee, d + 1))

    return {
        "seed_functions": function_names,
        "total_affected_functions": len(all_affected),
        "total_files_at_risk": len(files_at_risk),
        "files_at_risk": {
            f: sorted(funcs) for f, funcs in sorted(files_at_risk.items())
        },
        "propagation_chains": propagation_chains[:100],
        "propagation_truncated": len(propagation_chains) > 100,
    }


class CodeGraphImpactTool(BaseMCPTool):
    """MCP Tool for function-level blast radius analysis (CodeGraph parity)."""

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

    def get_call_graph(self) -> CallGraph:
        """Public alias for _get_call_graph() — use this instead of accessing _call_graph."""
        return self._get_call_graph()

    @property
    def call_graph_initialized(self) -> bool:
        """True if the call graph has been lazily initialized (i.e. cached)."""
        return self._call_graph is not None

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_impact",
            "description": (
                "PRIMARY for 'what would break if I change X' / 'how risky is "
                "modifying X' — try this FIRST before tracing callers manually. "
                "Function-level blast radius + transitive reachability + 0-100 "
                "risk score (CodeGraph parity). "
                "Modes: function_impact (one function), blast_radius "
                "(aggregate over multiple), risk_score (quantified risk). "
                "Use codegraph_callers/codegraph_callees only when you need the "
                "DIRECT-edge view; this tool walks transitive paths."
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
                    "enum": ["function_impact", "blast_radius", "risk_score"],
                    "description": (
                        "Analysis mode: function_impact (transitive callers/callees), "
                        "blast_radius (multi-function aggregate), "
                        "risk_score (0-100 risk score)"
                    ),
                    "default": "function_impact",
                },
                "function_name": {
                    "type": "string",
                    "description": (
                        "Target function name. Required for function_impact and "
                        "risk_score modes. Also accepted as a singular alias for "
                        "blast_radius (wrap in list automatically)."
                    ),
                },
                "function_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of function names for blast_radius mode. "
                        "Use function_names (plural) for blast_radius; "
                        "function_name (singular) is also accepted and wrapped."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to disambiguate overloaded functions",
                },
                "depth": {
                    "type": "integer",
                    "description": "Max transitive depth (default: 5)",
                    "default": 5,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
                "include_tests": {
                    "type": "boolean",
                    "description": (
                        "Applies to function_impact and risk_score modes only "
                        "(not blast_radius). When true, also return "
                        "test_caller_files and test_callee_files in the tests "
                        "bucket. Counts (test_callers_count, test_callees_count) "
                        "are always present in the tests bucket for those modes."
                    ),
                    "default": False,
                },
            },
            "required": ["mode"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "function_impact")
        if mode in ("function_impact", "risk_score") and not arguments.get(
            "function_name"
        ):
            raise ValueError(f"function_name is required for mode '{mode}'")
        if mode == "blast_radius":
            # Accept function_names (plural) OR function_name (singular alias).
            if not arguments.get("function_names") and not arguments.get(
                "function_name"
            ):
                raise ValueError(
                    "function_names is required for blast_radius mode; "
                    "for file-level dependents use nav action=xref mode=file"
                )
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "function_impact")
        func_name = arguments.get("function_name")
        file_path = arguments.get("file_path")
        depth = arguments.get("depth", 5)
        output_format = arguments.get("output_format", "toon")
        include_tests: bool = bool(arguments.get("include_tests", False))

        graph = self.get_call_graph()
        graph.build()

        if mode == "function_impact":
            if not func_name:
                raise ValueError("function_name required for function_impact mode")
            result = self._function_impact(
                graph, func_name, file_path, depth, include_tests
            )
        elif mode == "blast_radius":
            # #657: accept function_name (singular) as alias — wrap in list.
            func_names: list[str] = arguments.get("function_names") or (
                [arguments["function_name"]] if arguments.get("function_name") else []
            )
            result = _blast_radius_for_functions(graph, func_names, file_path, depth)
        elif mode == "risk_score":
            if not func_name:
                raise ValueError("function_name required for risk_score mode")
            result = _compute_risk_score(graph, func_name, file_path, include_tests)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # pain #10 (dogfood pass 2): codegraph_impact emitted no verdict.
        # Map the embedded risk level (already computed by _compute_risk_score)
        # to the canonical agent-facing vocabulary so the tsa-landing /
        # safe-to-edit gates branch correctly.
        verdict = _impact_verdict(result)
        # blast_radius: if no affected functions were found the seed(s) could
        # not be resolved in the call graph — treat this as NOT_FOUND so agents
        # don't receive "proceed with edit" for an unknown symbol.
        if mode == "blast_radius" and result.get("total_affected_functions", 0) == 0:
            verdict = "NOT_FOUND"
        # #577: uniform agent_summary across all facade actions.
        if mode == "function_impact":
            func = result.get("function") or func_name or "?"
            risk_level = (result.get("risk") or {}).get("level", "unknown")
            summary_line = f"impact: {func!r} risk={risk_level} verdict={verdict}"
        elif mode == "blast_radius":
            total_affected = result.get("total_affected_functions", 0)
            summary_line = f"impact: blast_radius affected_functions={total_affected}"
        else:
            # risk_score
            score = result.get("score", 0)
            level = result.get("level", "unknown")
            summary_line = f"impact: risk_score={score} level={level}"

        if verdict == "NOT_FOUND":
            next_step = (
                "Symbol not found in the call graph. "
                "Check the function name or run index action=auto."
            )
        elif verdict in ("CAUTION", "REVIEW"):
            next_step = (
                "High risk change — trace callers with nav action=callers "
                "and run the listed test files before editing."
            )
        else:
            next_step = (
                "Low risk change — proceed with edit; run nearest test file afterwards."
            )
        response: dict[str, Any] = {
            "success": True,
            "mode": mode,
            "verdict": verdict,
            **result,
            "agent_summary": {
                "summary_line": summary_line,
                "verdict": verdict,
                "next_step": next_step,
            },
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)

    def _function_impact(
        self,
        graph: CallGraph,
        func_name: str,
        file_path: str | None,
        depth: int,
        include_tests: bool = False,
    ) -> dict[str, Any]:
        direct_callers = graph.callers_of(func_name, file_path)
        direct_callees = graph.callees_of(func_name, file_path)
        transitive_callers = _compute_transitive_callers(
            graph, func_name, file_path, max_depth=depth, include_tests=include_tests
        )
        transitive_callees = _compute_transitive_callees(
            graph, func_name, file_path, max_depth=depth, include_tests=include_tests
        )
        risk = _compute_risk_score(
            graph, func_name, file_path, include_tests=include_tests
        )

        caller_files = {c.get("file", "") for c in direct_callers}
        callee_files = {c.get("file", "") for c in direct_callees}
        targets = graph.resolve_targets(func_name, file_path)
        self_file = targets[0].file_path if targets else ""
        cross_file_callers = len(caller_files - {self_file})
        cross_file_callees = len(callee_files - {self_file})

        # Wave 1b (audit nav-08): emit a capped head of each list; the full
        # counts below stay accurate so the agent sees the true blast radius.
        lists_truncated = (
            len(direct_callers) > _MAX_LISTED
            or len(direct_callees) > _MAX_LISTED
            or len(transitive_callers) > _MAX_LISTED
            or len(transitive_callees) > _MAX_LISTED
        )
        out: dict[str, Any] = {
            "function": func_name,
            "file": self_file,
            "direct_callers": direct_callers[:_MAX_LISTED],
            "direct_callees": direct_callees[:_MAX_LISTED],
            "transitive_callers": transitive_callers[:_MAX_LISTED],
            "transitive_callees": transitive_callees[:_MAX_LISTED],
            "direct_caller_count": len(direct_callers),
            "direct_callee_count": len(direct_callees),
            "transitive_caller_count": len(transitive_callers),
            "transitive_callee_count": len(transitive_callees),
            "cross_file_caller_files": cross_file_callers,
            "cross_file_callee_files": cross_file_callees,
            "lists_truncated": lists_truncated,
            "listed_cap": _MAX_LISTED,
            "risk": risk,
        }
        # #658 honest-truncation: flag when the _MAX_TRANSITIVE cap was hit so
        # agents don't report the cap (200) as a precise total.
        if len(transitive_callers) >= _MAX_TRANSITIVE:
            out["transitive_count_is_capped"] = True
        if len(transitive_callees) >= _MAX_TRANSITIVE:
            out["transitive_callee_count_is_capped"] = True
        return out


def _impact_verdict(result: dict[str, Any]) -> str:
    """Map embedded risk level to canonical verdict.

    The shape varies between modes — function_impact embeds a ``risk``
    dict, risk_score IS the risk dict itself, blast_radius has its own
    risk summary. We read whichever shape we got.
    """
    risk = result.get("risk", result)
    level = risk.get("level") if isinstance(risk, dict) else None
    if level == "unknown":
        # _compute_risk_score returns unknown when the symbol isn't in the
        # call graph at all — agents should treat this as NOT_FOUND so they
        # don't act on stale assumptions.
        return "NOT_FOUND"
    if level == "critical":
        # #798: _compute_risk_score emits "critical" (score >= 60) but this
        # mapper had no branch for it, so the highest-blast-radius symbols fell
        # through to INFO and read as "proceed with edit" — a dangerous false
        # green. Map critical to CAUTION (matching the sister _compute_verdict
        # convention) so next_step becomes the high-risk "trace callers" advice.
        return "CAUTION"
    if level == "high":
        return "CAUTION"
    if level == "medium":
        return "REVIEW"
    if level == "low":
        return "INFO"
    # No "level" key (e.g. the blast_radius result shape) keeps the pre-existing
    # INFO fallthrough — changing blast_radius semantics is out of #798 scope.
    return "INFO"
