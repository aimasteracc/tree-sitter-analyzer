#!/usr/bin/env python3
"""
Code Similarity MCP Tool — AST-structural clone detection.

Finds duplicate and near-duplicate code using tree-sitter AST fingerprints.
Detects structural clones (same AST shape) and textual clones (copy-paste
with renamed identifiers).

CodeGraph parity: equivalent to CodeGraph's clone detection intelligence.
No other built-in tool provides AST-based similarity analysis.
"""

from typing import Any

from ...code_similarity import analyze_code_similarity
from ...utils import setup_logger
from ._validators import invalid_enum_error
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphSimilarityTool(BaseMCPTool):
    """MCP Tool for AST-structural clone detection (CodeGraph parity)."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_similarity",
            "description": (
                "AST-structural clone detection: finds duplicate and near-duplicate "
                "functions using tree-sitter fingerprints. Detects structural clones "
                "(same AST shape, different names) and textual clones (copy-paste). "
                "No other tool provides AST-based similarity analysis. "
                "Default response is a summary map (files, line ranges, similarity "
                "scores — no code bodies). Pass include_bodies=true to include "
                "code snippets in each function entry."
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
                    "enum": ["all", "structural", "textual"],
                    "description": (
                        "Detection mode: 'all' (default) for both, "
                        "'structural' for AST shape clones, "
                        "'textual' for normalized text clones."
                    ),
                    "default": "all",
                },
                "min_lines": {
                    "type": "integer",
                    "description": "Minimum function body lines to consider (default: 5)",
                    "default": 5,
                },
                "min_group_size": {
                    "type": "integer",
                    "description": "Minimum clone group size to report (default: 2)",
                    "default": 2,
                },
                "limit": {
                    "type": "integer",
                    "description": "Alias for max_groups in facade mode (default: 20)",
                    "default": 20,
                },
                "max_groups": {
                    "type": "integer",
                    "description": "Maximum similarity groups to return (default: 20)",
                    "default": 20,
                },
                "use_cache": {
                    "type": "boolean",
                    "description": "Use pre-indexed AST cache for instant detection (default: true)",
                    "default": True,
                },
                "include_bodies": {
                    "type": "boolean",
                    "description": (
                        "Include code snippets in each function entry (default: false). "
                        "By default the response is a summary map (files, line ranges, "
                        "similarity scores only). Set include_bodies=true to add code "
                        "body snippets — this substantially increases response size."
                    ),
                    "default": False,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format (default: toon)",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "all")
        valid_modes = ["all", "structural", "textual"]
        if mode not in valid_modes:
            raise invalid_enum_error("mode", mode, valid_modes)
        return True

    @staticmethod
    def _coerce_positive_int(value: Any, name: str, default: int) -> int:
        """Return a strict positive integer, accepting int/whole-float/string forms."""
        if value is None:
            return default
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a positive integer, got bool {value!r}")
        if isinstance(value, int):
            candidate = value
        elif isinstance(value, float):
            if value != int(value):
                raise ValueError(
                    f"{name} must be a positive integer, got float {value!r}"
                )
            candidate = int(value)
        elif isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError(f"{name} must be a positive integer, got {value!r}")
            try:
                candidate = int(value)
            except ValueError as exc:
                raise ValueError(
                    f"{name} must be a positive integer, got {value!r}"
                ) from exc
        else:
            raise ValueError(f"{name} must be a positive integer, got {value!r}")

        if candidate < 1:
            raise ValueError(f"{name} must be a positive integer, got {candidate!r}")
        return candidate

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        if not self.project_root:
            return {
                "success": False,
                "error": "Project root not set. Call set_project_path first.",
            }

        mode = arguments.get("mode", "all")
        min_lines = self._coerce_positive_int(
            arguments.get("min_lines"), "min_lines", 5
        )
        min_group_size = self._coerce_positive_int(
            arguments.get("min_group_size"), "min_group_size", 2
        )
        source_max_groups = arguments.get("max_groups", arguments.get("limit", 20))
        max_groups = self._coerce_positive_int(
            source_max_groups,
            "max_groups",
            20,
        )
        use_cache = arguments.get("use_cache", True)
        include_bodies = arguments.get("include_bodies", False)
        output_format = arguments.get("output_format", "toon")

        try:
            result = analyze_code_similarity(
                self.project_root,
                mode=mode,
                min_lines=min_lines,
                min_group_size=min_group_size,
                max_groups=max_groups,
                use_cache=use_cache,
            )
        except Exception as exc:
            logger.error(f"Code similarity analysis failed: {exc}")
            return {
                "success": False,
                "error": f"Analysis failed: {exc}",
            }

        total_groups = len(result.groups)
        total_clones = result.stats.get("total_clone_instances", 0)

        if total_groups == 0:
            verdict = "INFO"
        elif total_clones > 50:
            verdict = "REVIEW"
        else:
            verdict = "CAUTION"

        response: dict[str, Any] = {
            "success": True,
            "verdict": verdict,
            "project_root": self.project_root,
            "stats": result.stats,
            "groups": [g.to_dict(include_bodies=include_bodies) for g in result.groups],
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)
