#!/usr/bin/env python3
"""
Symbol Lineage / Impact Preview MCP Tool.

Given a symbol name, traces its lineage: definitions, callers, downstream
dependents, and risk assessment. Combines AST-level reference search with
file-level dependency graph analysis for a complete impact preview.

Tells AI agents: "If you change X, here's everything affected."
"""

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
        symbol = arguments["symbol"].strip()
        output_format = arguments.get("output_format", "toon")

        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        root = Path(self.project_root).resolve()
        if not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")

        ref_args = {"symbol": symbol, "output_format": "json"}
        refs_result = await execute_find_references(self.project_root, ref_args)

        definitions = refs_result.get("definitions", [])
        references = refs_result.get("references", [])

        def_files = {d["file"] for d in definitions}
        ref_files = {r["file"] for r in references}
        all_symbol_files = def_files | ref_files

        try:
            graph = DependencyGraph(str(root))
        except Exception:
            graph = None

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
        }

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
