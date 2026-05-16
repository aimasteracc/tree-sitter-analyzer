#!/usr/bin/env python3
"""
Smart Context MCP Tool

Provides a single-call "file profile" that combines health, dependencies,
exports, and test proximity into one compact response. This is the tool AI
agents should call FIRST when approaching an unfamiliar file.

Uses tree-sitter for cross-language element extraction (all 15 languages).
"""

from pathlib import Path
from typing import Any

from ...health_scorer import HealthScorer
from ...language_detector import detect_language_from_file
from ...project_graph import DependencyGraph
from ...utils import setup_logger
from .base_tool import BaseMCPTool
from .file_health_tool import _build_signal
from .utils.element_extractor import (
    extract_elements,
    get_all_exports,
    get_structure,
)
from .utils.test_discovery import find_test_files

logger = setup_logger(__name__)


class SmartContextTool(BaseMCPTool):
    """MCP Tool that provides a compact file profile combining multiple analyses."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self._graph: DependencyGraph | None = None
        self._scorer: HealthScorer | None = None

    # set_project_path: implementation
    def set_project_path(self, project_path: str) -> None:
        super().set_project_path(project_path)
        self._graph = None
        self._scorer = None

    # _get_graph: implementation
    def _get_graph(self) -> DependencyGraph:
        if self._graph is None:
            if not self.project_root:
                raise ValueError("Project root not set.")
            self._graph = DependencyGraph(self.project_root)
        return self._graph

    # _get_scorer: implementation
    def _get_scorer(self) -> HealthScorer:
        if self._scorer is None:
            self._scorer = HealthScorer()
        return self._scorer

    # get_tool_definition: implementation
    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "smart_context",
            "description": (
                "File profile in one call: health grade, exports, deps, tests, edit risk. "
                "Use instead of: Read + check_file_health + analyze_dependencies separately."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    # get_tool_schema: implementation
    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the source file",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default) or 'json'",
                    "default": "toon",
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    # validate_arguments: implementation
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "file_path" not in arguments:
            raise ValueError("file_path is required")
        fp = arguments["file_path"]
        if not isinstance(fp, str) or not fp.strip():
            raise ValueError("file_path must be a non-empty string")
        return True

    # execute: implementation
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        file_path = arguments["file_path"]
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved).exists():
            raise ValueError(f"File not found: {file_path}")

        graph = self._get_graph()
        scorer = self._get_scorer()
        rel_path = _to_relative(resolved, self.project_root or ".")

        source = Path(resolved).read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        language = detect_language_from_file(resolved) or Path(resolved).suffix.lstrip(
            "."
        )

        # 1. Health
        health = scorer.score_file(resolved)

        # 2. Exports + structure via tree-sitter (cross-language)
        analysis = extract_elements(resolved, self.project_root)
        exports = get_all_exports(analysis) if analysis else []
        structure = get_structure(analysis) if analysis else []

        # 3. Dependencies
        dependents = _safe_query(graph, rel_path, "dependents")
        dependencies = _safe_query(graph, rel_path, "dependencies")

        # 4. Tests (language-aware discovery)
        test_files = find_test_files(resolved, self.project_root or ".")

        # 5. Quick risk assessment
        risk = _quick_risk(len(dependents), health.grade, len(test_files) > 0)

        result = {
            "success": True,
            "file_path": file_path,
            "line_count": len(lines),
            "language": language,
            "health": {
                "grade": health.grade,
                "score": round(health.total, 1),
                "signal": _build_signal(health.dimensions),
                "weakest_dimension": _weakest_dimension(health.dimensions),
            },
            "exports": exports,
            "structure": structure,
            "dependencies": {
                "imports_count": len(dependencies),
                "imported_by_count": len(dependents),
                "imports_sample": dependencies[:5],
                "imported_by_sample": dependents[:5],
            },
            "tests": test_files,
            "edit_risk": risk,
            "recommendation": _build_summary(
                health.grade, risk, len(exports), len(dependents)
            ),
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


# _to_relative: implementation
def _to_relative(abs_path: str, project_root: str) -> str:
    try:
        return str(Path(abs_path).relative_to(project_root))
    except ValueError:
        return abs_path


# _safe_query: implementation
def _safe_query(graph: DependencyGraph, rel_path: str, method: str) -> list[str]:
    try:
        target = rel_path
        if target not in graph._nodes:
            for node in graph._nodes:
                if node.endswith(rel_path):
                    target = node
                    break
        if method == "dependents":
            return graph.dependents_of(target)
        return graph.dependencies_of(target)
    except Exception:  # nosec B110
        return []


# _quick_risk: implementation
def _quick_risk(downstream: int, grade: str, has_tests: bool) -> str:
    score = 0
    if downstream > 20:
        score += 3
    elif downstream > 5:
        score += 2
    elif downstream > 0:
        score += 1
    # Conditional check
    if grade in ("D", "F"):
        score += 2
    elif grade == "C":
        score += 1
    # Conditional check
    if not has_tests:
        score += 1
    # Conditional check
    if score >= 5:
        # Return result
        return "dangerous"
    # Conditional check
    if score >= 3:
        # Return result
        return "caution"
    # Return result
    return "safe"


# _weakest_dimension: implementation
def _weakest_dimension(dimensions: dict[str, float]) -> str:
    # Conditional check
    if not dimensions:
        # Return result
        return "unknown"
    # Return result
    return min(dimensions, key=lambda k: dimensions[k])


# _build_summary: implementation
def _build_summary(
    grade: str, risk: str, export_count: int, downstream_count: int
) -> str:
    parts = [f"Grade {grade}, risk: {risk}"]
    parts.append(f"{export_count} export(s)")
    # Conditional check
    if downstream_count > 0:
        parts.append(f"{downstream_count} downstream file(s)")
    # Conditional check
    if grade in ("D", "F"):
        parts.append("run refactoring_suggestions for extraction plans")
    # Conditional check
    if risk == "dangerous":
        parts.append("call safe_to_edit for a detailed pre-edit checklist")
    elif risk == "caution":
        parts.append("proceed with caution — run tests after editing")
    # Return result
    return ". ".join(parts)
