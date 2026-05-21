#!/usr/bin/env python3
"""
Symbol Lineage / Impact Preview MCP Tool.

Given a symbol name, traces its lineage: definitions, callers, downstream
dependents, and risk assessment. Combines AST-level reference search with
file-level dependency graph analysis for a complete impact preview.

Tells AI agents: "If you change X, here's everything affected."
"""

import copy
import time
from pathlib import Path
from typing import Any

from ...project_graph import BlastRadius, DependencyGraph
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool
from .query_symbol_search import execute_find_references

logger = setup_logger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {
            "type": "string",
            "description": "Symbol name to trace lineage for",
        },
        "max_depth": {
            "type": "integer",
            "default": 3,
            "description": "Max dependency graph traversal depth (1-5)",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
    },
    "required": ["symbol"],
    "additionalProperties": False,
}


class SymbolLineageTool(BaseMCPTool):
    """Trace symbol lineage: definitions, references, file-level downstream impact."""

    def __init__(self, project_root: str | None = None) -> None:
        # Lazy graph + per-symbol response cache. Built on the first call,
        # reset on project_root rebind via _on_project_root_changed.
        self._dep_graph: DependencyGraph | None = None
        self._symbol_cache: dict[tuple[str, int], dict[str, Any]] = {}
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        # ARCH-A4 hook: invalidate every per-project cache when rebinding.
        self._dep_graph = None
        self._symbol_cache = {}

    def _get_dep_graph(self) -> DependencyGraph | None:
        """Return cached dependency graph, building it on first use.

        Returns ``None`` if graph construction fails (keeps the tool usable
        with reduced fidelity — downstream/upstream stay empty).
        """
        if self._dep_graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            try:
                self._dep_graph = DependencyGraph(str(self.project_root))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"DependencyGraph build failed: {exc}")
                return None
        return self._dep_graph

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "symbol_lineage",
            "description": (
                "Symbol lineage: definition → callers → downstream files → risk. "
                "Shows what breaks if you change a symbol. "
                "Combines AST references with file dependency graph. "
                "SLOW: traverses AST references plus the full dependency graph "
                "(5-15s per symbol on medium repos). Cache via project_index."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        symbol = arguments.get("symbol", "").strip()
        if not symbol:
            raise ValueError("symbol is required")
        max_depth = arguments.get("max_depth", 3)
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 5:
            raise ValueError("max_depth must be 1-5")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        symbol = arguments["symbol"].strip()
        max_depth = int(arguments.get("max_depth", 3))
        output_format = arguments.get("output_format", "toon")

        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        root = Path(self.project_root).resolve()
        if not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")

        # Per-symbol response cache: this tool does an expensive cross-file
        # walk (rglob + 500x engine.analyze) even with the analysis cache
        # warm. The same (symbol, max_depth) pair is asked for repeatedly
        # by orchestrators, so cache the deep-copied response.
        cache_key = (symbol, max_depth)
        cached = self._symbol_cache.get(cache_key)
        if cached is not None:
            result = copy.deepcopy(cached)
            result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
            result["from_cache"] = True
            return apply_toon_format_to_response(result, output_format)

        ref_args = {"symbol": symbol, "output_format": "json"}
        refs_result = await execute_find_references(self.project_root, ref_args)

        definitions = refs_result.get("definitions", [])
        references = refs_result.get("references", [])

        def_files = {d["file"] for d in definitions}
        ref_files = {r["file"] for r in references}
        all_symbol_files = def_files | ref_files

        # Use the instance-cached graph (built lazily on first call,
        # invalidated on project_root rebind via _on_project_root_changed).
        graph = self._get_dep_graph()

        downstream: dict[str, Any] = {}
        upstream: dict[str, Any] = {}
        if graph:
            for f in all_symbol_files:
                if f not in graph._nodes:
                    continue
                br = BlastRadius(graph)
                fwd = br.forward(f)
                if fwd:
                    downstream[f] = sorted(fwd)
                rev = br.reverse(f)
                if rev:
                    upstream[f] = sorted(rev)

        all_downstream_files: set[str] = set()
        for files in downstream.values():
            all_downstream_files.update(files)

        all_upstream_files: set[str] = set()
        for files in upstream.values():
            all_upstream_files.update(files)

        risk = _assess_risk(
            len(definitions), len(references), len(all_downstream_files)
        )

        test_files = sorted(
            f for f in (all_downstream_files | all_symbol_files) if _is_test_file(f)
        )

        # One-line headline + next-step hint for LLM consumers.
        summary_line = (
            f"{symbol} defs={len(definitions)} refs={len(references)} "
            f"downstream={len(all_downstream_files)} risk={risk['level']}"
        )
        # Verdict mirrors trace_impact / safe_to_edit vocabulary so an agent
        # can chain decisions across tools.
        risk_to_verdict = {
            "high": "UNSAFE",
            "medium": "CAUTION",
            "low": "SAFE",
            "unknown": "n/a",
        }
        verdict = risk_to_verdict.get(risk["level"], "n/a")
        if risk["level"] == "high":
            next_step = (
                "trace_impact and run listed test files before changing signature"
            )
        elif risk["level"] == "medium":
            next_step = "review callers in listed files, then run downstream tests"
        elif risk["level"] == "low":
            next_step = "proceed with edit, run nearest test file"
        else:
            next_step = "verify symbol name — no definitions found"

        response: dict[str, Any] = {
            "success": True,
            "symbol": symbol,
            "definitions": definitions[:20],
            "definition_count": len(definitions),
            "references": references[:30],
            "reference_count": len(references),
            "files_containing_symbol": sorted(all_symbol_files),
            "downstream_files": sorted(all_downstream_files)[:50],
            "downstream_file_count": len(all_downstream_files),
            "upstream_files": sorted(all_upstream_files)[:20],
            "upstream_file_count": len(all_upstream_files),
            "test_files_to_run": test_files[:20],
            "test_file_count": len(test_files),
            "risk": risk,
            "smart_workflow_hint": (
                f"Symbol '{symbol}' has {risk['level']} change risk "
                f"({len(references)} refs, {len(all_downstream_files)} downstream files). "
                f"{'Run the listed test files before committing.' if test_files else 'No test files detected.'} "
                "Use analyze_change_impact after editing for git-diff level detail."
            ),
            "summary_line": summary_line,
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": next_step,
                "verdict": verdict,
            },
        }

        # Stash a deep-copy so subsequent identical lookups skip the
        # cross-file walk + dep-graph traversal. The cache is keyed on
        # (symbol, max_depth) and reset on project_root rebind.
        self._symbol_cache[cache_key] = copy.deepcopy(response)

        response["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        response["from_cache"] = False

        return apply_toon_format_to_response(response, output_format)


def _assess_risk(
    def_count: int, ref_count: int, downstream_count: int
) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []

    if def_count == 0:
        return {"level": "unknown", "score": 0, "reasons": ["Symbol not found"]}

    if def_count > 1:
        score += 1
        reasons.append(f"Multiple definitions ({def_count})")

    if ref_count > 20:
        score += 3
        reasons.append(f"Many references ({ref_count})")
    elif ref_count > 5:
        score += 2
        reasons.append(f"Moderate references ({ref_count})")
    elif ref_count > 0:
        score += 1
        reasons.append(f"Few references ({ref_count})")

    if downstream_count > 10:
        score += 3
        reasons.append(f"Wide blast radius ({downstream_count} downstream files)")
    elif downstream_count > 3:
        score += 2
        reasons.append(f"Moderate blast radius ({downstream_count} downstream files)")
    elif downstream_count > 0:
        score += 1
        reasons.append(f"Small blast radius ({downstream_count} downstream files)")

    if score <= 2:
        level = "low"
    elif score <= 5:
        level = "medium"
    else:
        level = "high"

    return {"level": level, "score": score, "reasons": reasons}


def _is_test_file(rel_path: str) -> bool:
    lower = rel_path.lower()
    parts = Path(lower).parts
    return (
        "test" in parts[-1]
        or "tests" in parts
        or "test" in parts
        or parts[-1].startswith("test_")
        or parts[-1].endswith("_test.py")
        or parts[-1].endswith("_test.js")
        or parts[-1].endswith("test.java")
        or parts[-1].endswith("test.go")
    )
