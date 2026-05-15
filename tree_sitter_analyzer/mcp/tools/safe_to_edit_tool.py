#!/usr/bin/env python3
"""
Safe-to-Edit MCP Tool

Answers the question AI agents ask most: "Can I safely modify this file?"

Combines dependency analysis, health scoring, and test proximity to produce
a risk assessment with specific warnings and a concrete pre-edit checklist.
"""

from pathlib import Path
from typing import Any

from ...health_scorer import HealthScorer
from ...project_graph import DependencyGraph
from ...utils import setup_logger
from .base_tool import BaseMCPTool
from .utils.test_discovery import find_test_files

logger = setup_logger(__name__)


class SafeToEditTool(BaseMCPTool):
    """MCP Tool that assesses how safe it is to edit a specific file."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self._graph: DependencyGraph | None = None
        self._scorer: HealthScorer | None = None

    def set_project_path(self, project_path: str) -> None:
        super().set_project_path(project_path)
        self._graph = None
        self._scorer = None

    def _get_graph(self) -> DependencyGraph:
        if self._graph is None:
            if not self.project_root:
                raise ValueError("Project root not set.")
            self._graph = DependencyGraph(self.project_root)
        return self._graph

    def _get_scorer(self) -> HealthScorer:
        if self._scorer is None:
            self._scorer = HealthScorer()
        return self._scorer

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "safe_to_edit",
            "description": (
                "Call BEFORE editing: returns risk_level (safe/caution/dangerous), "
                "affected files, test coverage hints, pre-edit checklist."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file you plan to edit",
                },
                "edit_type": {
                    "type": "string",
                    "enum": ["refactor", "add_feature", "fix_bug", "rename"],
                    "description": "Type of edit planned (affects risk assessment)",
                    "default": "refactor",
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

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "file_path" not in arguments:
            raise ValueError("file_path is required")
        fp = arguments["file_path"]
        if not isinstance(fp, str) or not fp.strip():
            raise ValueError("file_path must be a non-empty string")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        file_path = arguments["file_path"]
        edit_type = arguments.get("edit_type", "refactor")
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved).exists():
            raise ValueError(f"File not found: {file_path}")

        graph = self._get_graph()
        scorer = self._get_scorer()

        rel_path = _to_relative(resolved, self.project_root or ".")

        # 1. Dependency analysis — how many files depend on this one?
        dependents = _safe_dependents(graph, rel_path)
        deps = _safe_dependencies(graph, rel_path)

        # 2. Blast radius
        forward_count = len(dependents)

        # 3. Health score
        health = scorer.score_file(resolved)

        # 4. Test proximity — are there co-located tests?
        test_files = find_test_files(resolved, self.project_root or ".")
        has_tests = len(test_files) > 0

        # 5. Compute risk
        risk, risk_factors = _compute_risk(
            forward_count=forward_count,
            dep_count=len(deps),
            health_grade=health.grade,
            has_tests=has_tests,
            edit_type=edit_type,
            is_init_file=_is_init_file(resolved),
        )

        result = {
            "success": True,
            "file_path": file_path,
            "risk_level": risk,
            "risk_factors": risk_factors,
            "health_grade": health.grade,
            "health_score": health.total,
            "downstream_files": dependents[:20],
            "downstream_count": forward_count,
            "dependencies": deps[:10],
            "dependency_count": len(deps),
            "test_files_nearby": test_files,
            "pre_edit_checklist": _build_checklist(
                risk, forward_count, has_tests, test_files, edit_type
            ),
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _to_relative(abs_path: str, project_root: str) -> str:
    try:
        return str(Path(abs_path).relative_to(project_root))
    except ValueError:
        return abs_path


def _safe_dependents(graph: DependencyGraph, rel_path: str) -> list[str]:
    try:
        if rel_path in graph._nodes:
            return graph.dependents_of(rel_path)
        # fuzzy match
        for node in graph._nodes:
            if node.endswith(rel_path):
                return graph.dependents_of(node)
    except Exception:  # nosec B110 — graph lookup failure returns empty list
        pass
    return []


def _safe_dependencies(graph: DependencyGraph, rel_path: str) -> list[str]:
    try:
        if rel_path in graph._nodes:
            return graph.dependencies_of(rel_path)
        for node in graph._nodes:
            if node.endswith(rel_path):
                return graph.dependencies_of(node)
    except Exception:  # nosec B110 — graph lookup failure returns empty list
        pass
    return []


def _is_init_file(file_path: str) -> bool:
    return Path(file_path).name == "__init__.py"


def _compute_risk(
    forward_count: int,
    dep_count: int,
    health_grade: str,
    has_tests: bool,
    edit_type: str,
    is_init_file: bool,
) -> tuple[str, list[dict[str, str]]]:
    """Compute risk level and contributing factors."""
    factors: list[dict[str, str]] = []
    score = 0

    # Downstream impact
    if forward_count > 20:
        score += 3
        factors.append(
            {
                "factor": "high_downstream",
                "detail": f"{forward_count} files depend on this — high blast radius",
                "severity": "dangerous",
            }
        )
    elif forward_count > 5:
        score += 2
        factors.append(
            {
                "factor": "moderate_downstream",
                "detail": f"{forward_count} files depend on this",
                "severity": "caution",
            }
        )
    elif forward_count > 0:
        score += 1
        factors.append(
            {
                "factor": "low_downstream",
                "detail": f"{forward_count} file(s) depend on this",
                "severity": "info",
            }
        )

    # Health grade — fragile files are riskier to edit
    if health_grade in ("D", "F"):
        score += 2
        factors.append(
            {
                "factor": "poor_health",
                "detail": f"Grade {health_grade} — file already has issues, edits may compound them",
                "severity": "caution",
            }
        )
    elif health_grade in ("C",):
        score += 1
        factors.append(
            {
                "factor": "fair_health",
                "detail": f"Grade {health_grade} — moderate technical debt",
                "severity": "info",
            }
        )

    # Test coverage
    if not has_tests:
        score += 2
        factors.append(
            {
                "factor": "no_tests",
                "detail": "No nearby test files found — changes won't be automatically verified",
                "severity": "caution",
            }
        )
    else:
        factors.append(
            {
                "factor": "has_tests",
                "detail": "Nearby test files found — run them before and after editing",
                "severity": "good",
            }
        )

    # __init__.py is a package boundary
    if is_init_file:
        score += 2
        factors.append(
            {
                "factor": "init_file",
                "detail": "Editing __init__.py affects package exports and all importers",
                "severity": "caution",
            }
        )

    # Edit type adjustments
    if edit_type == "rename":
        score += 2
        factors.append(
            {
                "factor": "rename_risk",
                "detail": "Rename requires updating all importers — use find_and_grep first",
                "severity": "caution",
            }
        )
    elif edit_type == "refactor" and forward_count > 5:
        score += 1
        factors.append(
            {
                "factor": "refactor_risk",
                "detail": "Refactoring a widely-imported file — keep the public API stable",
                "severity": "caution",
            }
        )

    # High dependency count means complex interactions
    if dep_count > 10:
        score += 1
        factors.append(
            {
                "factor": "high_dependencies",
                "detail": f"File imports {dep_count} modules — complex interaction surface",
                "severity": "info",
            }
        )

    # Determine risk level
    if score >= 6:
        risk = "dangerous"
    elif score >= 3:
        risk = "caution"
    else:
        risk = "safe"

    return risk, factors


def _build_checklist(
    risk: str,
    downstream_count: int,
    has_tests: bool,
    test_files: list[str],
    edit_type: str,
) -> list[str]:
    """Build a pre-edit checklist for the AI agent."""
    items: list[str] = []

    if risk == "dangerous":
        items.append(
            "1. HIGH RISK — consider breaking changes into smaller, atomic edits"
        )
    elif risk == "caution":
        items.append("1. MODERATE RISK — proceed with caution, test after each change")
    else:
        items.append("1. LOW RISK — file is relatively safe to edit")

    if has_tests:
        items.append(f"2. Run existing tests FIRST: pytest {' '.join(test_files[:3])}")
        items.append("3. Run same tests AFTER editing to catch regressions")
    else:
        items.append("2. No tests found nearby — write tests BEFORE editing (TDD)")
        items.append("3. Run full test suite after editing to catch side effects")

    if downstream_count > 0:
        items.append(
            f"4. {downstream_count} downstream file(s) — verify imports still resolve"
        )

    if edit_type == "rename":
        items.append(
            "5. After rename: run find_and_grep(old_name) to find all references"
        )

    if edit_type == "refactor":
        items.append("5. Keep public API signatures unchanged during refactor")

    return items
