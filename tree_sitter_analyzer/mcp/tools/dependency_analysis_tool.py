#!/usr/bin/env python3
"""
Dependency Analysis MCP Tool

Exposes project_graph.py to AI agents via MCP protocol.
Provides dependency graph queries, blast radius analysis, and cycle detection.
"""

import time
from pathlib import Path
from typing import Any

from ...project_graph import BlastRadius, DependencyGraph
from ...utils import setup_logger
from ._graph_cache_fingerprint import GraphFingerprint, compute_graph_fingerprint
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DependencyAnalysisTool(BaseMCPTool):
    """MCP Tool for project-level dependency analysis."""

    def __init__(self, project_root: str | None = None) -> None:
        self._graph: DependencyGraph | None = None
        # H4 fix: snapshot fingerprint at build time. Compared against a
        # fresh fingerprint on every call so in-place edits invalidate
        # both the instance cache AND, indirectly, DependencyGraph's
        # _global_cache (whose key is now derived from the same fingerprint).
        self._graph_fingerprint: GraphFingerprint | None = None
        self._graph_built_at: float | None = None
        self._cache_invalidated_reason: str | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._graph = None
        self._graph_fingerprint = None
        self._graph_built_at = None
        self._cache_invalidated_reason = None

    def _get_graph(self) -> DependencyGraph:
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        current_fp = compute_graph_fingerprint(self.project_root)
        reason: str | None = None
        if self._graph is None:
            reason = "cold"
        elif self._graph_fingerprint != current_fp:
            reason = self._explain_fingerprint_delta(
                self._graph_fingerprint, current_fp
            )

        if reason is not None:
            self._graph = DependencyGraph(self.project_root)
            self._graph_fingerprint = current_fp
            self._graph_built_at = time.time()
            self._cache_invalidated_reason = reason
        else:
            self._cache_invalidated_reason = None
        assert self._graph is not None  # nosec B101 - just rebuilt above
        return self._graph

    @staticmethod
    def _explain_fingerprint_delta(
        old: GraphFingerprint | None, new: GraphFingerprint
    ) -> str:
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
            "name": "analyze_dependencies",
            "description": (
                "Dependency graph + blast radius. Modes: blast_radius (impact), "
                "file_deps, cycles, summary. No built-in tool provides this. "
                "First call builds the full dep graph (2-5s on medium repos); "
                "subsequent calls within the session reuse the cached graph."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["blast_radius", "file_deps", "cycles", "summary"],
                    "description": "Analysis mode (default: summary)",
                    "default": "summary",
                },
                "file_path": {
                    "type": "string",
                    "description": "Required for blast_radius and file_deps modes. Relative or absolute path.",
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
        mode = arguments.get("mode", "summary")
        if mode in ("blast_radius", "file_deps") and "file_path" not in arguments:
            raise ValueError(f"file_path is required for mode '{mode}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        started = time.perf_counter()
        mode = arguments.get("mode", "summary")
        output_format = arguments.get("output_format", "toon")
        # Cache hit fast-path: ``self._graph`` is built lazily on the first
        # call (2-5s on medium repos) and reused for the rest of the process
        # lifetime — subsequent calls finish in single-digit ms.
        graph = self._get_graph()

        if mode == "summary":
            result = _summary(graph)
        elif mode == "cycles":
            result = _cycles(graph)
        elif mode == "file_deps":
            file_path = arguments["file_path"]
            resolved = self._resolve_file(file_path, graph)
            result = _file_deps(graph, resolved)
        elif mode == "blast_radius":
            file_path = arguments["file_path"]
            resolved = self._resolve_file(file_path, graph)
            br = BlastRadius(graph)
            analysis = br.analyze(resolved)
            result = {
                "success": True,
                "file": resolved,
                "mode": "blast_radius",
                "forward_impact_count": analysis["forward_count"],
                "reverse_dependency_count": analysis["reverse_count"],
                "forward_impact": analysis["forward_impact"],
                "reverse_dependencies": analysis["reverse_dependencies"],
                "recommendation": _blast_recommendation(analysis),
            }
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Attach a one-line headline + next-step hint for LLM consumers.
        # Each mode emits a distinct shape, so build per-mode here.
        _attach_agent_summary(result, mode, graph)

        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        # H4 introspection.
        if self._graph_built_at is not None:
            result["cache_age_s"] = round(time.time() - self._graph_built_at, 3)
        if self._cache_invalidated_reason is not None:
            result["cache_invalidated_reason"] = self._cache_invalidated_reason

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _resolve_file(self, file_path: str, graph: DependencyGraph) -> str:
        """Resolve file_path to a project-relative path that exists in the graph."""
        root = Path(self.project_root or ".")
        fp = Path(file_path)

        # Try direct match
        rel = (
            str(fp)
            if not fp.is_absolute()
            else str(fp.relative_to(root))
            if str(root) in str(fp)
            else str(fp)
        )
        if rel in graph._nodes or any(n.endswith(rel) for n in graph._nodes):
            return rel

        # Try resolving as absolute
        if fp.is_absolute():
            try:
                rel = str(fp.relative_to(root))
                if rel in graph._nodes:
                    return rel
            except ValueError:
                pass

        # Fuzzy: find by filename
        target_name = fp.name
        for node in graph._nodes:
            if Path(node).name == target_name:
                return node

        raise ValueError(
            f"File not found in dependency graph: {file_path}. "
            f"The graph has {len(graph._nodes)} nodes."
        )


def _summary(graph: DependencyGraph) -> dict[str, Any]:
    node_count = len(graph._nodes)
    edge_count = len(graph._edges)

    # Find hub files (most dependents = most relied upon)
    dep_counts = {n: len(graph.dependents_of(n)) for n in graph._nodes}
    hubs = sorted(dep_counts.items(), key=lambda x: -x[1])[:10]

    # Find high-fan-in files (most dependencies = most complex)
    fan_in = {n: len(graph.dependencies_of(n)) for n in graph._nodes}
    high_fan = sorted(fan_in.items(), key=lambda x: -x[1])[:10]

    return {
        "success": True,
        "mode": "summary",
        "node_count": node_count,
        "edge_count": edge_count,
        "top_hub_files": [{"file": f, "dependents": c} for f, c in hubs if c > 0],
        "high_dependency_files": [{"file": f, "deps": c} for f, c in high_fan if c > 0],
        "recommendation": (
            "Use mode='blast_radius' to assess change impact, "
            "or mode='cycles' to find circular dependencies."
        ),
    }


def _cycles(graph: DependencyGraph) -> dict[str, Any]:
    cycles = _deterministic_find_cycles(graph)
    return {
        "success": True,
        "mode": "cycles",
        "cycle_count": len(cycles),
        "cycles": cycles[:20],
        "recommendation": (
            f"Found {len(cycles)} circular dependencies. "
            "These can cause import errors and make refactoring harder."
            if cycles
            else "No circular dependencies detected. Project structure is clean."
        ),
    }


def _deterministic_find_cycles(graph: DependencyGraph) -> list[list[str]]:
    """Enumerate elementary cycles in ``graph`` with a deterministic order.

    H3 fix: ``DependencyGraph.find_cycles`` does a DFS that iterates
    ``graph._nodes`` (a ``set``) and ``graph._deps[node]`` (also a ``set``).
    Set iteration order in CPython depends on ``PYTHONHASHSEED``, so
    different OS-level invocations of the same code on the same project
    produced different enumeration trees and thus a *different number*
    of cycles — the dogfood agent saw ``cycle_count`` flicker 5↔6 across
    runs.

    We re-implement the DFS here with sorted iteration of nodes and
    neighbours. The algorithm matches ``DependencyGraph.find_cycles``
    (back-edge style cycle detection) so the result shape and semantics
    are unchanged; only the enumeration order is now stable. Cycles are
    additionally canonicalised (rotated to start at their lexicographically
    smallest node) and de-duplicated so equivalent cycles discovered from
    different DFS roots collapse to a single entry.
    """
    nodes_sorted = sorted(graph._nodes)
    deps = graph._deps  # dict[str, set[str]]

    visited: set[str] = set()
    stack: list[str] = []
    on_stack: set[str] = set()
    raw_cycles: list[tuple[str, ...]] = []

    def dfs(node: str) -> None:
        visited.add(node)
        stack.append(node)
        on_stack.add(node)

        for neighbor in sorted(deps.get(node, ())):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in on_stack:
                # back-edge → cycle from neighbor down to current
                idx = stack.index(neighbor)
                cycle_nodes = tuple(stack[idx:] + [neighbor])
                raw_cycles.append(cycle_nodes)

        stack.pop()
        on_stack.discard(node)

    for root in nodes_sorted:
        if root not in visited:
            dfs(root)

    # Canonicalise each cycle: rotate the node list (excluding the closing
    # duplicate) to start at its lexicographically smallest element, then
    # re-append the closing node so the on-the-wire format matches the
    # legacy shape (``[a, b, c, a]``). De-dup by canonical key.
    canonical: dict[tuple[str, ...], list[str]] = {}
    for cyc in raw_cycles:
        if len(cyc) < 2:
            continue
        body = list(cyc[:-1])  # drop closing duplicate
        if not body:
            continue
        pivot = min(range(len(body)), key=body.__getitem__)
        rotated = body[pivot:] + body[:pivot]
        key = tuple(rotated)
        if key not in canonical:
            canonical[key] = rotated + [rotated[0]]

    # Sort cycles for stable response ordering (by their canonical key).
    return [canonical[k] for k in sorted(canonical.keys())]


def _file_deps(graph: DependencyGraph, rel_path: str) -> dict[str, Any]:
    deps = graph.dependencies_of(rel_path)
    dependents = graph.dependents_of(rel_path)
    return {
        "success": True,
        "mode": "file_deps",
        "file": rel_path,
        "depends_on": deps,
        "depended_by": dependents,
        "dependency_count": len(deps),
        "dependent_count": len(dependents),
    }


def _blast_recommendation(analysis: dict[str, Any]) -> str:
    forward = analysis["forward_count"]
    reverse = analysis["reverse_count"]
    if forward == 0 and reverse == 0:
        return "Isolated file — changes here have no ripple effect."
    if forward > 20:
        return f"High-impact file — {forward} files will be affected by changes. Test thoroughly."
    if forward > 5:
        return f"Moderate impact — {forward} files depend on this. Verify downstream behavior."
    if forward > 0:
        return f"Low impact — only {forward} file(s) affected. Safe to change with basic testing."
    return "No downstream impact detected."


def _attach_agent_summary(
    result: dict[str, Any], mode: str, graph: DependencyGraph
) -> None:
    """Mutate ``result`` in place to add summary_line + agent_summary.

    Each mode shapes the headline differently:
    - summary: nodes / edges / cycles
    - cycles: N cycles found
    - file_deps: <file> depends_on=N depended_by=N
    - blast_radius: <file> forward=N reverse=N
    """
    if mode == "summary":
        # H3: use the deterministic cycle enumerator so ``summary.cycle_count``
        # stays byte-stable across runs (the underlying
        # ``DependencyGraph.find_cycles`` is DFS-order-sensitive and varies
        # with PYTHONHASHSEED).
        cycle_count = len(_deterministic_find_cycles(graph))
        node_count = result.get("node_count", 0)
        edge_count = result.get("edge_count", 0)
        summary_line = (
            f"summary: {node_count} nodes / {edge_count} edges / {cycle_count} cycles"
        )
        if cycle_count:
            next_step = (
                "analyze_dependencies mode=cycles to enumerate circular dependencies"
            )
        else:
            next_step = "analyze_dependencies mode=blast_radius file_path=<file> to assess change impact"
        result["cycle_count"] = cycle_count
    elif mode == "cycles":
        cycle_count = int(result.get("cycle_count", 0))
        summary_line = f"cycles: {cycle_count} circular dependencies"
        next_step = (
            "break each cycle by extracting shared types or inverting an import"
            if cycle_count
            else "no cycles — proceed with planned refactor"
        )
    elif mode == "file_deps":
        file = result.get("file", "?")
        dep_count = int(result.get("dependency_count", 0))
        ent_count = int(result.get("dependent_count", 0))
        summary_line = (
            f"file_deps {file}: depends_on={dep_count} depended_by={ent_count}"
        )
        next_step = "analyze_dependencies mode=blast_radius for full ripple-effect view"
    elif mode == "blast_radius":
        file = result.get("file", "?")
        forward = int(result.get("forward_impact_count", 0))
        reverse = int(result.get("reverse_dependency_count", 0))
        summary_line = f"blast_radius {file}: forward={forward} reverse={reverse}"
        if forward > 20:
            next_step = (
                "trace_impact on key symbols and run downstream tests before editing"
            )
        elif forward > 5:
            next_step = "verify downstream behavior in the listed forward_impact files"
        elif forward > 0:
            next_step = "run basic tests on the few downstream files"
        else:
            next_step = "isolated file — safe to edit"
    else:
        # Defensive — should not happen because execute validates mode.
        summary_line = f"dependency_analysis mode={mode}"
        next_step = "review the result fields"

    result["summary_line"] = summary_line
    result["agent_summary"] = {
        "summary_line": summary_line,
        "next_step": next_step,
    }
