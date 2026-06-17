#!/usr/bin/env python3
"""
CodeGraph Complexity Heatmap MCP Tool — Cyclomatic complexity analysis.

Computes McCabe-style cyclomatic complexity per function and produces a
project-wide heatmap with risk bands (low/medium/high/critical).

Modes:
  - project: Full project heatmap with hotspots and risk distribution
  - file:    Per-file complexity breakdown
  - function: Complexity for a specific function (requires function_name)

CodeGraph parity: equivalent to CodeGraph's complexity analysis / code heatmap.
"""

from __future__ import annotations

import os
from typing import Any

from ...complexity_heatmap import (
    RISK_BANDS,
    _risk_band,
    analyze_file_complexity,
    analyze_project_heatmap,
)
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_error, build_response
from ._validators import invalid_enum_error
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphComplexityHeatmapTool(BaseMCPTool):
    """MCP Tool for cyclomatic complexity heatmap (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None

    def _get_cache(self) -> Any | None:
        if self._cache is not None:
            return self._cache
        if not self.project_root:
            return None
        try:
            from ...ast_cache import ASTCache

            cache = ASTCache(self.project_root)
            stats = cache.get_stats()
            if stats.get("total_files", 0) > 0:
                self._cache = cache
                return cache
            cache.close()
        except Exception:
            pass
        return None

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_complexity_heatmap",
            "description": (
                "Cyclomatic complexity heatmap per function + project-wide analysis "
                "(CodeGraph parity). Ranks functions by complexity, identifies hotspots, "
                "and produces risk distribution (low 1-5, medium 6-10, high 11-20, critical 20+). "
                "Modes: project (full heatmap), file (single file), function (named function). "
                "No other tool provides complexity-based risk analysis."
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
                    "enum": ["project", "file", "function"],
                    "description": (
                        "project=full project heatmap, "
                        "file=per-file breakdown (requires file_path), "
                        "function=specific function (requires function_name)"
                    ),
                    "default": "project",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path for file/function mode (relative to project root)",
                },
                "function_name": {
                    "type": "string",
                    "description": "Function name to look up (for function mode)",
                },
                "language": {
                    "type": "string",
                    "description": "Filter by language (e.g. 'python', 'javascript')",
                },
                "directory": {
                    "type": "string",
                    "description": "Filter to a subdirectory (for project mode)",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Max files to scan in project mode (default: 200)",
                    "default": 200,
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
        mode = arguments.get("mode", "project")
        valid_modes = ["project", "file", "function"]
        if mode not in valid_modes:
            raise invalid_enum_error("mode", mode, valid_modes)
        if mode in ("file", "function") and not arguments.get("file_path"):
            raise ValueError(f"file_path required for {mode} mode")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "project")
        output_format = arguments.get("output_format", "toon")

        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        if mode == "project":
            result = self._execute_project(arguments)
        elif mode == "file":
            result = self._execute_file(arguments)
        else:
            result = self._execute_function(arguments)

        return apply_toon_format_to_response(result, output_format)

    def _execute_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self.project_root is not None, "project_root required"
        language = arguments.get("language")
        directory = arguments.get("directory")
        # The MCP boundary can deliver numeric params as strings (e.g. "200").
        # Coerce so ``len(results) >= max_files`` in _collect_source_files never
        # hits ``int >= str`` (matches the int() pattern in _call_tree_tool).
        max_files = int(arguments.get("max_files", 200))
        cache = self._get_cache()

        heatmap = analyze_project_heatmap(
            project_root=self.project_root,
            language_filter=language,
            directory_filter=directory,
            max_files=max_files,
            cache=cache,
        )

        if cache is not None:
            heatmap["data_source"] = "ast_cache"

        high_count = heatmap["risk_distribution"].get("high", 0)
        critical_count = heatmap["risk_distribution"].get("critical", 0)

        if critical_count > 0:
            verdict = "REVIEW"
        elif high_count > 5:
            verdict = "REVIEW"
        elif heatmap["total_functions"] == 0:
            verdict = "NOT_FOUND"
        else:
            verdict = "INFO"

        heatmap["risk_bands"] = {k: f"{v[0]}-{v[1]}" for k, v in RISK_BANDS.items()}
        return build_response(verdict=verdict, mode="project", **heatmap)

    def _execute_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self.project_root is not None, "project_root required"
        file_path = arguments["file_path"]
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.project_root, file_path)

        if not os.path.isfile(file_path):
            return build_error(
                error=f"File not found: {file_path}", verdict="NOT_FOUND"
            )

        from ...project_graph import _language_from_ext

        language = arguments.get("language") or _language_from_ext(file_path)
        if not language:
            return build_error(
                error=f"Unsupported language for: {file_path}",
                verdict="NOT_FOUND",
            )

        functions = self._analyze_file_cached(file_path, language)
        rel_path = os.path.relpath(file_path, self.project_root)

        total_cc = sum(f.complexity for f in functions)
        max_cc = max((f.complexity for f in functions), default=0)
        avg_cc = round(total_cc / len(functions), 2) if functions else 0.0

        has_high = any(f.complexity > 10 for f in functions)
        verdict = "REVIEW" if has_high else "INFO"

        return build_response(
            verdict=verdict,
            mode="file",
            file=rel_path,
            language=language,
            function_count=len(functions),
            total_complexity=total_cc,
            average_complexity=avg_cc,
            max_complexity=max_cc,
            functions=[
                {
                    "name": f.name,
                    "line": f.line,
                    "end_line": f.end_line,
                    "complexity": f.complexity,
                    "risk": _risk_band(f.complexity),
                    "class": f.class_name,
                    "decision_points": f.decision_points,
                }
                for f in sorted(functions, key=lambda x: x.complexity, reverse=True)
            ],
        )

    def _execute_function(self, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self.project_root is not None, "project_root required"
        file_path = arguments["file_path"]
        function_name = arguments.get("function_name", "")
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.project_root, file_path)

        if not os.path.isfile(file_path):
            return build_error(
                error=f"File not found: {file_path}", verdict="NOT_FOUND"
            )

        from ...project_graph import _language_from_ext

        language = arguments.get("language") or _language_from_ext(file_path)
        if not language:
            return build_error(
                error=f"Unsupported language for: {file_path}",
                verdict="NOT_FOUND",
            )

        functions = self._analyze_file_cached(file_path, language)
        matches = [f for f in functions if f.name == function_name]

        if not matches:
            return build_error(
                error=(
                    f"Function '{function_name}' not found in "
                    f"{os.path.relpath(file_path, self.project_root)}"
                ),
                verdict="NOT_FOUND",
                available_functions=[f.name for f in functions],
            )

        f = max(matches, key=lambda x: x.complexity)
        return build_response(
            verdict="REVIEW" if f.complexity > 10 else "INFO",
            mode="function",
            file=os.path.relpath(file_path, self.project_root),
            language=language,
            name=f.name,
            line=f.line,
            end_line=f.end_line,
            complexity=f.complexity,
            risk=_risk_band(f.complexity),
            **{"class": f.class_name},
            decision_points=f.decision_points,
        )

    def _analyze_file_cached(self, file_path: str, language: str) -> list[Any]:
        cache = self._get_cache()
        if cache is not None:
            from ...complexity_heatmap import analyze_file_complexity_from_cache

            return analyze_file_complexity_from_cache(cache, file_path)
        return analyze_file_complexity(file_path, language)
