#!/usr/bin/env python3
"""
CodeGraph Dependency Matrix MCP Tool — Module coupling analysis.

Computes a bidirectional coupling matrix between all project modules using
import edges and call edges from the pre-indexed AST cache. Identifies
tightly-coupled module pairs that are refactoring targets.

Modes:
  summary       — project-wide coupling statistics
  matrix        — full coupling matrix (all pairs with score > 0)
  hotspots      — top-K most coupled module pairs
  file          — coupling entries for a specific file
  unstable      — modules with instability >= threshold (likely to change)

CodeGraph parity: equivalent to CodeGraph Pro's dependency-coupling-matrix.
"""

from typing import Any

from ...dependency_matrix import DependencyMatrix
from ...utils import setup_logger
from ._validators import invalid_enum_error
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphDependencyMatrixTool(BaseMCPTool):
    """MCP Tool for module coupling analysis via dependency matrix."""

    def __init__(self, project_root: str | None = None) -> None:
        self._dm: DependencyMatrix | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._dm = None

    def _get_matrix(self) -> DependencyMatrix:
        if self._dm is None:
            if not self.project_root:
                raise ValueError("Project root not set.")
            self._dm = DependencyMatrix(self.project_root)
        return self._dm

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_dependency_matrix",
            "description": (
                "Module coupling analysis from pre-indexed AST cache. "
                "Modes: summary (stats), matrix (all pairs), hotspots (top-K), "
                "file (coupling for one file), unstable (high-instability modules). "
                "Requires ast_cache index. "
                "No other tool provides pairwise module coupling scores."
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
                        "summary",
                        "matrix",
                        "hotspots",
                        "file",
                        "unstable",
                    ],
                    "description": "Operation mode (default: summary)",
                    "default": "summary",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path (required for mode=file)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of top coupled pairs for hotspots (default: 10)",
                    "default": 10,
                },
                "threshold": {
                    "type": "number",
                    "description": "Instability threshold for unstable mode (default: 0.7)",
                    "default": 0.7,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format (default: toon)",
                    "default": "toon",
                },
            },
            "required": ["mode"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "summary")
        valid = ["summary", "matrix", "hotspots", "file", "unstable"]
        if mode not in valid:
            raise invalid_enum_error("mode", mode, valid)
        if mode == "file" and not arguments.get("file_path"):
            raise ValueError("file_path is required for mode='file'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "summary")
        output_format = arguments.get("output_format", "toon")
        dm = self._get_matrix()

        if mode == "summary":
            result = {
                "success": True,
                "verdict": "INFO",
                "mode": "summary",
                **dm.summary(),
            }

        elif mode == "matrix":
            dm_result = dm.build()
            result = {
                "success": True,
                "verdict": "INFO",
                "mode": "matrix",
                "module_count": len(dm_result.modules),
                "coupling_pairs": [e.to_dict() for e in dm_result.coupling_pairs],
            }

        elif mode == "hotspots":
            top_k = arguments.get("top_k", 10)
            hotspots = dm.most_coupled(top_k=top_k)
            result = {
                "success": True,
                "verdict": "CAUTION"
                if any(e.score >= 10 for e in hotspots)
                else "INFO",
                "mode": "hotspots",
                "top_k": top_k,
                "hotspots": [e.to_dict() for e in hotspots],
            }

        elif mode == "file":
            file_path = arguments["file_path"]
            resolved = self.resolve_and_validate_file_path(file_path)
            dm_result = dm.build()
            rel = resolved
            if not rel:
                rel = file_path
            related: list[dict[str, Any]] = []
            for entry in dm_result.coupling_pairs:
                if entry.file_a == rel or entry.file_b == rel:
                    other = entry.file_b if entry.file_a == rel else entry.file_a
                    related.append(
                        {
                            "file": other,
                            "import_count": entry.import_count,
                            "call_count": entry.call_count,
                            "coupling_score": entry.score,
                        }
                    )
            related.sort(key=lambda x: x["coupling_score"], reverse=True)
            result = {
                "success": True,
                "verdict": "CAUTION"
                if any(r["coupling_score"] >= 10 for r in related)
                else "INFO",
                "mode": "file",
                "file": file_path,
                "coupled_module_count": len(related),
                "coupled_modules": related,
            }

        elif mode == "unstable":
            threshold = arguments.get("threshold", 0.7)
            unstable = dm.unstable_modules(threshold=threshold)
            result = {
                "success": True,
                "verdict": "CAUTION" if unstable else "INFO",
                "mode": "unstable",
                "threshold": threshold,
                "unstable_count": len(unstable),
                "unstable_modules": [s.to_dict() for s in unstable],
            }

        else:
            result = {
                "success": False,
                "error": f"Unknown mode: {mode}",
                "verdict": "ERROR",
            }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)
