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
from .base_tool import BaseMCPTool, _canonicalize_verdict, mirror_summary_line

logger = setup_logger(__name__)


# Modes that resolve a specific symbol. When one of these returns zero
# results we treat the response as ``NOT_FOUND`` and steer the caller
# toward symbol_lineage rather than handing them an empty envelope.
_SYMBOL_RESOLVING_MODES = frozenset({"callers", "callees", "chain"})


def _result_is_empty_for_mode(result: dict[str, Any], mode: str) -> bool:
    """Return True when the response represents a not-found lookup.

    Finding F8 only treats the symbol-resolving modes as "not found" —
    a zero-edge ``summary`` on an empty project is a different (and
    not particularly actionable) condition.

    H2 refinement: an indexed leaf function (e.g. a callback registered
    via ``requires_file=_dependency_mode_requires_file``) has zero
    callers/callees but IS in the graph — its envelope must NOT carry
    a ``NOT_FOUND`` verdict, or callers will be told the symbol doesn't
    exist when it plainly does. We require BOTH ``count == 0`` AND
    ``function_indexed`` is falsy before declaring not-found. Older
    responses that don't carry ``function_indexed`` (e.g. legacy
    constructions in tests) keep the prior behaviour — treat absence
    as a not-indexed signal so existing F8 expectations still hold.
    """
    indexed = result.get("function_indexed")
    if mode == "callers":
        if int(result.get("caller_count", 0)) != 0:
            return False
        return not bool(indexed) if indexed is not None else True
    if mode == "callees":
        if int(result.get("callee_count", 0)) != 0:
            return False
        return not bool(indexed) if indexed is not None else True
    if mode == "chain":
        if int(result.get("edge_count", 0)) != 0:
            return False
        return not bool(indexed) if indexed is not None else True
    return False


def _call_graph_summary_line(result: dict[str, Any], mode: str, func: str) -> str:
    """Build the per-mode ``summary_line`` for call_graph responses.

    G2: ``CallGraph.summary()`` returns ``call_edge_count`` / ``function_count``
    (see call_graph.py); the legacy ``edges`` / ``edge_count`` keys never
    land here, so the fallback chain reads the canonical field name last so
    the visible number matches ``call_edge_count``.

    r37ew (dogfood): lifted from ``_attach_call_graph_envelope`` so the
    parent function reads as: build line → ensure agent_summary → mirror.
    """
    if mode == "summary":
        edges = result.get(
            "edges", result.get("edge_count", result.get("call_edge_count", 0))
        )
        nodes = result.get("nodes", result.get("function_count", 0))
        return f"call_graph summary nodes={nodes} edges={edges}"
    if mode == "all_functions":
        return f"call_graph all_functions count={result.get('count', 0)}"
    if mode == "callers":
        return (
            f"call_graph callers function={func} "
            f"caller_count={result.get('caller_count', 0)}"
        )
    if mode == "callees":
        return (
            f"call_graph callees function={func} "
            f"callee_count={result.get('callee_count', 0)}"
        )
    if mode == "chain":
        return (
            f"call_graph chain function={func} "
            f"depth={result.get('depth', 0)} "
            f"edge_count={result.get('edge_count', 0)}"
        )
    if mode == "file_impact":
        return (
            f"call_graph file_impact file={result.get('file', '')} "
            f"functions={result.get('function_count', 0)} "
            f"upstream={result.get('upstream_count', 0)} "
            f"downstream={result.get('downstream_count', 0)}"
        )
    if mode == "functions_in_file":
        return (
            f"call_graph functions_in_file file={result.get('file', '')} "
            f"functions={result.get('function_count', 0)}"
        )
    # Defensive — should not happen because execute validates mode.
    return f"call_graph mode={mode}"  # pragma: no cover


def _apply_call_graph_agent_summary(
    result: dict[str, Any],
    summary_line: str,
    mode: str,
    is_not_found: bool,
) -> None:
    """Populate ``result['agent_summary']`` with next_step + verdict + summary_line.

    Preserves existing agent_summary fields via ``setdefault`` — callers
    that pre-populated specific keys keep them. F8 overlays a NOT_FOUND
    verdict when symbol resolution returned zero hits; the default verdict
    is ``n/a`` for informational responses.
    """
    agent_summary = result.get("agent_summary")
    if not isinstance(agent_summary, dict) or not agent_summary:
        agent_summary = {}
    agent_summary.setdefault("summary_line", summary_line)
    if is_not_found:
        agent_summary.setdefault(
            "next_step",
            "Run symbol_lineage to find similar names, or check spelling.",
        )
        agent_summary.setdefault("verdict", "NOT_FOUND")
        agent_summary.setdefault("risk", "low")
    else:
        agent_summary.setdefault(
            "next_step",
            (
                "Use callers/callees/chain modes to navigate the call graph."
                if mode == "summary"
                else "Drill into a specific function with mode='callers' or 'callees'."
            ),
        )
        # F1 (round-37f7): canonicalize "n/a" → "INFO" so call_graph
        # joins the shared :data:`_LEGAL_VERDICTS` vocabulary. The
        # summary surface is informational (graph navigation, not a
        # safety judgement), so ``INFO`` is the right canonical bucket.
        agent_summary.setdefault("verdict", _canonicalize_verdict("n/a"))
    # F1: defensive normalisation — guard against future regressions
    # where another helper sets a non-canonical verdict before we
    # reach this point. The ``setdefault`` above only kicks in on a
    # missing key; this pass replaces any non-canonical existing one.
    existing_verdict = agent_summary.get("verdict")
    if isinstance(existing_verdict, str):
        agent_summary["verdict"] = _canonicalize_verdict(existing_verdict)
    result["agent_summary"] = agent_summary
    # r37x (envelope ratchet): top-level verdict mirror (r37u contract).
    if isinstance(agent_summary.get("verdict"), str):
        result.setdefault("verdict", agent_summary["verdict"])


def _attach_call_graph_envelope(result: dict[str, Any]) -> None:
    """Populate the canonical agent_summary + summary_line for call_graph.

    Finding 6: round-16b dogfood saw ``agent_summary={}`` and
    ``summary_line=None`` on every call_graph response. Build a compact
    summary keyed off the response mode so the dispatch post-hook can
    mirror ``agent_summary.summary_line`` to the top level.

    Finding F8 (round-17): when ``callers``/``callees``/``chain`` resolve
    to zero hits for a symbol that doesn't exist, agents previously saw
    ``verdict='n/a'`` plus a generic "drill in" next_step — nothing
    actionable. We now overlay a ``NOT_FOUND`` verdict with a concrete
    next_step pointing at ``symbol_lineage`` so the caller has somewhere
    to go.

    r37ew (dogfood): 88→~15 lines. ``_call_graph_summary_line`` builds
    the per-mode headline; ``_apply_call_graph_agent_summary`` populates
    ``agent_summary`` and mirrors ``verdict``; this function is the thin
    orchestrator.
    """
    mode = result.get("mode", "summary")
    func = result.get("function") or ""
    is_not_found = mode in _SYMBOL_RESOLVING_MODES and _result_is_empty_for_mode(
        result, mode
    )

    if is_not_found:
        # F8: prefer a single canonical not-found line regardless of mode.
        summary_line = f"call_graph: symbol '{func}' not found"
    else:
        summary_line = _call_graph_summary_line(result, mode, func)

    result.setdefault("summary_line", summary_line)
    _apply_call_graph_agent_summary(result, summary_line, mode, is_not_found)
    # F8: mirror agent_summary.summary_line to the top level so direct
    # ``await tool.execute(args)`` callers see a non-None summary_line
    # without going through the MCP dispatch post-hook.
    mirror_summary_line(result)


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
                "[ADVANCED — prefer codegraph_callers / codegraph_callees / "
                "codegraph_impact for the 90% case.] "
                "Multi-mode call graph aggregator (CodeGraph parity). "
                "Modes: callers, callees, chain (transitive), summary (stats), "
                "all_functions (list every discovered function), "
                "file_impact, functions_in_file. "
                "Use only when you need a non-default mode (chain/summary/"
                "all_functions/file_impact) — for who-calls-X or what-X-calls, "
                "use the dedicated codegraph_callers / codegraph_callees tools."
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
                    "enum": [
                        "callers",
                        "callees",
                        "chain",
                        "summary",
                        "all_functions",
                        "file_impact",
                        "functions_in_file",
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

    _VALID_MODES = (
        "callers",
        "callees",
        "chain",
        "summary",
        "all_functions",
        "file_impact",
        "functions_in_file",
    )
    _FILE_PATH_MODES = frozenset({"file_impact", "functions_in_file"})

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "summary")
        if mode not in self._VALID_MODES:
            raise ValueError(
                f"Invalid mode '{mode}'; expected one of: "
                f"{', '.join(self._VALID_MODES)}."
            )
        if mode in ("callers", "callees", "chain") and "function_name" not in arguments:
            raise ValueError(f"function_name is required for mode '{mode}'")
        if mode in self._FILE_PATH_MODES and "file_path" not in arguments:
            raise ValueError(f"file_path is required for mode '{mode}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch call-graph queries by ``mode``.

        r37br (dogfood): tool flagged this at 104 lines. Refactor splits
        each mode into a ``_build_*_response`` method. M7 / H2 / H4 /
        Finding 6 contracts preserved exactly.
        """
        self.validate_arguments(arguments)
        started = time.perf_counter()
        mode = arguments.get("mode", "summary")
        output_format = arguments.get("output_format", "toon")
        # Cache hit fast-path: first call builds graph (2-5s on medium
        # repos); subsequent calls finish in ~tens of ms.
        graph = self._get_call_graph()

        if mode == "summary":
            result = {"success": True, "mode": "summary", **graph.summary()}
        elif mode == "all_functions":
            result = self._build_all_functions_response(graph)
        elif mode == "callers":
            result = self._build_callers_response(graph, arguments)
        elif mode == "callees":
            result = self._build_callees_response(graph, arguments)
        elif mode == "chain":
            result = self._build_chain_response(graph, arguments)
        elif mode == "file_impact":
            result = self._build_file_impact_response(graph, arguments)
        elif mode == "functions_in_file":
            result = self._build_functions_in_file_response(graph, arguments)
        else:  # pragma: no cover - validate_arguments rejects unknown modes
            raise ValueError(
                f"Invalid mode '{mode}'; expected one of: "
                f"{', '.join(self._VALID_MODES)}."
            )

        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        # H4 introspection: tell callers when this response came from a
        # rebuilt graph vs a warm reuse.
        if self._call_graph_built_at is not None:
            result["cache_age_s"] = round(time.time() - self._call_graph_built_at, 3)
        if self._cache_invalidated_reason is not None:
            result["cache_invalidated_reason"] = self._cache_invalidated_reason

        # Finding 6: ensure direct execute() callers see non-empty envelope.
        _attach_call_graph_envelope(result)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    @staticmethod
    def _build_all_functions_response(graph: Any) -> dict[str, Any]:
        """M7: mode-named ``all_functions`` key + ``functions`` deprecated alias."""
        funcs = graph.all_functions()
        return {
            "success": True,
            "mode": "all_functions",
            "count": len(funcs),
            "all_functions": funcs,
            "functions": funcs,
        }

    @staticmethod
    def _build_callers_response(
        graph: Any, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Return callers of ``function_name`` with H2 ``function_indexed`` echo."""
        func_name = arguments["function_name"]
        file_path = arguments.get("file_path")
        callers = graph.callers_of(func_name, file_path)
        result: dict[str, Any] = {
            "success": True,
            "mode": "callers",
            "function": func_name,
            "caller_count": len(callers),
            "callers": callers,
            "function_indexed": bool(graph.resolve_targets(func_name, file_path)),
        }
        hint = _maybe_bare_name_hint(graph, func_name, len(callers), "callers")
        if hint:
            result["hint"] = hint
        return result

    @staticmethod
    def _build_callees_response(
        graph: Any, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Return callees of ``function_name`` with H2 ``function_indexed`` echo."""
        func_name = arguments["function_name"]
        file_path = arguments.get("file_path")
        callees = graph.callees_of(func_name, file_path)
        result: dict[str, Any] = {
            "success": True,
            "mode": "callees",
            "function": func_name,
            "callee_count": len(callees),
            "callees": callees,
            "function_indexed": bool(graph.resolve_targets(func_name, file_path)),
        }
        hint = _maybe_bare_name_hint(graph, func_name, len(callees), "callees")
        if hint:
            result["hint"] = hint
        return result

    @staticmethod
    def _build_chain_response(graph: Any, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return the full call-chain DAG up to ``depth``."""
        func_name = arguments["function_name"]
        file_path = arguments.get("file_path")
        depth = arguments.get("depth", 5)
        chain = graph.call_chain(func_name, file_path, depth)
        result: dict[str, Any] = {
            "success": True,
            "mode": "chain",
            "function": func_name,
            "depth": depth,
            "edge_count": len(chain),
            "chain": chain,
            "function_indexed": bool(graph.resolve_targets(func_name, file_path)),
        }
        hint = _maybe_bare_name_hint(graph, func_name, len(chain), "chain")
        if hint:
            result["hint"] = hint
        return result

    @staticmethod
    def _build_file_impact_response(
        graph: Any, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Return upstream/downstream impact summary for a file.

        Wraps :meth:`CallGraph.file_impact` and adds the standard MCP
        envelope fields (``success`` / ``mode``).
        """
        file_path = arguments["file_path"]
        impact = graph.file_impact(file_path)
        return {"success": True, "mode": "file_impact", **impact}

    @staticmethod
    def _build_functions_in_file_response(
        graph: Any, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Return all functions defined in the given file."""
        file_path = arguments["file_path"]
        funcs = graph.functions_in_file(file_path)
        return {
            "success": True,
            "mode": "functions_in_file",
            "file": file_path,
            "function_count": len(funcs),
            "functions": funcs,
        }
