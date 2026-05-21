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
from .utils.safe_to_edit_helpers import (
    SafeToEditContext,
    is_init_file,
)
from .utils.safe_to_edit_helpers import (
    build_safe_to_edit_result as _build_safe_to_edit_result,
)
from .utils.safe_to_edit_risk import compute_risk

logger = setup_logger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
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


class SafeToEditTool(BaseMCPTool):
    """MCP Tool that assesses how safe it is to edit a specific file."""

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
        # Conditional check
        if self._scorer is None:
            self._scorer = HealthScorer()
        return self._scorer

    # get_tool_definition: implementation
    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "safe_to_edit",
            "description": (
                "MUST call before editing files. Returns risk_level (safe/caution/dangerous), "
                "downstream deps, test files, pre-edit checklist. "
                "No built-in tool provides this."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    # get_tool_schema: implementation
    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    # validate_arguments: implementation
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        # Conditional check
        if "file_path" not in arguments:
            raise ValueError("file_path is required")
        fp = arguments["file_path"]
        # Conditional check
        if not isinstance(fp, str) or not fp.strip():
            raise ValueError("file_path must be a non-empty string")
        return True

    # execute: implementation
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        file_path = arguments["file_path"]
        edit_type = arguments.get("edit_type", "refactor")
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        # Conditional check
        if not Path(resolved).exists():
            raise ValueError(f"File not found: {file_path}")

        result = _build_safe_to_edit_result(
            SafeToEditContext(
                file_path=file_path,
                edit_type=edit_type,
                resolved_path=resolved,
                project_root=self.project_root or ".",
                graph=self._get_graph(),
                scorer=self._get_scorer(),
            )
        )
        # Echo the requested output_format so agents can audit envelope
        # parity without re-reading their own call site.
        result["output_format"] = output_format

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _compute_risk(*args: Any, **kwargs: Any) -> tuple[str, list[dict[str, str]]]:
    """Compatibility wrapper for tests and internal imports."""
    return compute_risk(*args, **kwargs)


def _is_init_file(file_path: str) -> bool:
    """Compatibility wrapper for tests and internal imports."""
    return is_init_file(file_path)
