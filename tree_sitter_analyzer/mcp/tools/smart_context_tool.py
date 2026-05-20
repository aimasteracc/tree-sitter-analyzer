#!/usr/bin/env python3
"""
Smart Context MCP Tool

Provides a single-call "file profile" that combines health, dependencies,
exports, and test proximity into one compact response. This is the tool AI
agents should call FIRST when approaching an unfamiliar file.

Uses tree-sitter for cross-language element extraction (all 15 languages).
"""

import shlex
from dataclasses import dataclass
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


@dataclass(frozen=True)
class SmartContextProfile:
    file_path: str
    line_count: int
    language: str
    health: Any
    exports: list[dict[str, Any]]
    structure: list[dict[str, Any]]
    dependencies: list[str]
    dependents: list[str]
    test_files: list[str]
    risk: str


@dataclass(frozen=True)
class AgentSummaryInput:
    file_path: str
    grade: str
    score: float
    weakest: str
    risk: str
    export_count: int
    downstream_count: int
    test_files: list[str]


class SmartContextTool(BaseMCPTool):
    """MCP Tool that provides a compact file profile combining multiple analyses."""

    def __init__(self, project_root: str | None = None) -> None:
        self._graph: DependencyGraph | None = None
        self._scorer: HealthScorer | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
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
        profile = self._build_profile(file_path)
        result = _build_smart_context_result(profile)
        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    # _build_profile: implementation
    def _build_profile(self, file_path: str) -> SmartContextProfile:
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

        health = scorer.score_file(resolved)
        analysis = extract_elements(resolved, self.project_root)
        exports = get_all_exports(analysis) if analysis else []
        structure = get_structure(analysis) if analysis else []
        dependents = _safe_query(graph, rel_path, "dependents")
        dependencies = _safe_query(graph, rel_path, "dependencies")
        test_files = find_test_files(resolved, self.project_root or ".")
        risk = _quick_risk(len(dependents), health.grade, len(test_files) > 0)
        return SmartContextProfile(
            file_path=file_path,
            line_count=len(lines),
            language=language,
            health=health,
            exports=exports,
            structure=structure,
            dependencies=dependencies,
            dependents=dependents,
            test_files=test_files,
            risk=risk,
        )


# _to_relative: implementation
def _to_relative(abs_path: str, project_root: str) -> str:
    try:
        return str(Path(abs_path).relative_to(project_root))
    except ValueError:
        return abs_path


# _safe_query: implementation
def _safe_query(graph: DependencyGraph, rel_path: str, method: str) -> list[str]:
    try:
        target = _resolve_graph_node(graph, rel_path)
        if method == "dependents":
            return graph.dependents_of(target)
        return graph.dependencies_of(target)
    except Exception:  # nosec B110
        return []


# _resolve_graph_node: implementation
def _resolve_graph_node(graph: DependencyGraph, rel_path: str) -> str:
    if rel_path in graph._nodes:
        return rel_path
    return next((node for node in graph._nodes if node.endswith(rel_path)), rel_path)


# _build_smart_context_result: implementation
def _build_smart_context_result(profile: SmartContextProfile) -> dict[str, Any]:
    grade = profile.health.grade
    score = round(profile.health.total, 1)
    weakest = _weakest_dimension(profile.health.dimensions)
    summary_input = AgentSummaryInput(
        file_path=profile.file_path,
        grade=grade,
        score=score,
        weakest=weakest,
        risk=profile.risk,
        export_count=len(profile.exports),
        downstream_count=len(profile.dependents),
        test_files=profile.test_files,
    )
    return {
        "success": True,
        "file_path": profile.file_path,
        "line_count": profile.line_count,
        "language": profile.language,
        "health": {
            "grade": grade,
            "score": score,
            "signal": _build_signal(profile.health.dimensions),
            "weakest_dimension": weakest,
        },
        "agent_summary": _build_agent_summary(summary_input),
        "exports": profile.exports,
        "structure": profile.structure,
        "dependencies": {
            "imports_count": len(profile.dependencies),
            "imported_by_count": len(profile.dependents),
            "imports_sample": profile.dependencies[:5],
            "imported_by_sample": profile.dependents[:5],
        },
        "tests": profile.test_files,
        "edit_risk": profile.risk,
        "recommendation": _build_summary(
            grade, profile.risk, len(profile.exports), len(profile.dependents)
        ),
    }


# _build_agent_summary: implementation
def _build_agent_summary(context: AgentSummaryInput) -> dict[str, Any]:
    quoted_path = shlex.quote(context.file_path)
    focused_test_command = _focused_test_command(context.test_files)
    verification_command = focused_test_command or (
        "uv run python -m tree_sitter_analyzer "
        f"{quoted_path} --file-health --format json"
    )
    return {
        "risk": context.risk,
        "grade": context.grade,
        "score": context.score,
        "next_step": _agent_next_step(
            file_path=context.file_path,
            grade=context.grade,
            risk=context.risk,
            has_tests=bool(context.test_files),
        ),
        "verification_command": verification_command,
        "focused_test_command": focused_test_command,
        "safe_to_edit_command": (
            "uv run python -m tree_sitter_analyzer "
            f"{quoted_path} --safe-to-edit --format json"
        ),
        "change_impact_command": (
            "uv run python -m tree_sitter_analyzer --change-impact "
            f"--change-impact-scope {quoted_path} --format json"
        ),
        "stop_condition": _agent_stop_condition(
            verification_command, context.test_files
        ),
        "weakest_dimension": context.weakest,
        "exports_count": context.export_count,
        "downstream_count": context.downstream_count,
    }


# _focused_test_command: implementation
def _focused_test_command(test_files: list[str]) -> str:
    if not test_files:
        return ""
    quoted_tests = shlex.join(test_files[:5])
    return f"uv run pytest {quoted_tests} -q"


# _agent_next_step: implementation
def _agent_next_step(
    *,
    file_path: str,
    grade: str,
    risk: str,
    has_tests: bool,
) -> str:
    quoted_path = shlex.quote(file_path)
    if risk == "dangerous":
        return (
            "Run safe-to-edit before modifying this file: "
            f"uv run python -m tree_sitter_analyzer {quoted_path} "
            "--safe-to-edit --format json"
        )
    if grade in {"D", "F"}:
        return (
            "Run refactoring suggestions before editing: "
            f"uv run python -m tree_sitter_analyzer {quoted_path} "
            "--refactor --format json"
        )
    if not has_tests:
        return "Find or add a focused test before making behavior changes."
    return "Make a focused edit, then run the nearby tests and scoped change-impact."


# _agent_stop_condition: implementation
def _agent_stop_condition(verification_command: str, test_files: list[str]) -> str:
    if test_files:
        return (
            f"{verification_command} passes and scoped change-impact matches the edit."
        )
    return "File-health is reviewed and a focused test plan is selected before editing."


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
        return "dangerous"
    # Conditional check
    if score >= 3:
        return "caution"
    return "safe"


# _weakest_dimension: implementation
def _weakest_dimension(dimensions: dict[str, float]) -> str:
    # Conditional check
    if not dimensions:
        return "unknown"
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
    return ". ".join(parts)
