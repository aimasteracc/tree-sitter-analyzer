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
from .base_tool import BaseMCPTool, mirror_summary_line
from .utils.parse_validity import is_file_parse_broken
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
                "Pre-edit safety check for a single file: how many other "
                "modules depend on it, which test files cover it, and a "
                "concrete checklist of pre-edit verifications. Returns a "
                "risk_level (SAFE/CAUTION/UNSAFE) plus actionable next "
                "steps. MUST be called before editing any production-facing "
                "file — the built-in Edit tool gives you no visibility into "
                "downstream impact.\n\n"
                "WHEN TO USE:\n"
                "- Before ANY edit to a public-facing module / utility\n"
                "- Before renaming or deleting a function (paired with "
                "modification_guard)\n"
                "- To know which tests must pass after the edit\n"
                "- To check coupling before reorganising a directory\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For a private/internal helper with no external callers "
                "(check via trace_impact first)\n"
                "- To assess CODE QUALITY of the file — use file_health\n"
                "- For symbol-level rename impact — use modification_guard"
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
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

        from ..utils.format_helper import apply_toon_format_to_response

        # M3 (round-26 dogfood): if tree-sitter reports any ERROR node we
        # cannot trust the dependency graph or the health scorer — both
        # walk the AST. Without this gate ``safe_to_edit`` graded
        # ``def broken(:`` as ``risk=safe`` and an agent could happily
        # proceed with "planned changes" against a broken file. The
        # short-circuit envelope keeps the same shape as the success
        # path (file_path / agent_summary / output_format) but pins
        # ``risk=high`` + ``verdict=ERROR`` + ``signal=syntax_error``.
        syntax_response = _syntax_error_response(resolved, file_path, edit_type)
        if syntax_response is not None:
            syntax_response["output_format"] = output_format
            return apply_toon_format_to_response(syntax_response, output_format)

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

        # M14 (round-26): also echo ``language`` on the success path.
        # The syntax-error short-circuit above already echoes it; the
        # success path used to only echo on the dispatcher-routed
        # path, leaving CLI / direct callers with ``language=None``.
        if "language" not in result:
            from ...language_detector import detect_language_from_file

            try:
                detected = detect_language_from_file(
                    resolved, project_root=self.project_root
                )
            except Exception:  # nosec B110 — language detection best-effort
                detected = "unknown"
            if detected and detected != "unknown":
                result["language"] = detected

        # M10 (round-26): mirror top-level ``verdict`` into
        # ``agent_summary.verdict`` so chained agents see the same answer
        # at both surfaces. safe_to_edit historically only set top-level
        # ``verdict`` (SAFE / CAUTION / UNSAFE); ``mirror_summary_line``
        # now propagates it into ``agent_summary``.
        result = mirror_summary_line(result)

        return apply_toon_format_to_response(result, output_format)


def _syntax_error_response(
    resolved: str,
    file_path: str,
    edit_type: str,
) -> dict[str, Any] | None:
    """M3 (round-26): short-circuit when tree-sitter detected syntax errors.

    Returns ``None`` when the file parses cleanly (caller continues with
    the normal dependency + health + test-discovery walk). Otherwise
    returns a risk envelope that matches the success-path shape (so
    downstream consumers don't have to special-case the keys) but pins
    ``risk=high`` and ``risk_level=dangerous`` so any agent reading
    either field sees the same answer.

    Why ``risk_level=dangerous`` not ``safe``: broken syntax means we
    cannot enumerate dependents or score health — every downstream
    walker is going to choke on the partial AST. ``dangerous`` is the
    safest default: an agent must investigate the syntax error before
    editing anything.
    """
    # Detect language locally — safe_to_edit doesn't otherwise know it.
    from ...language_detector import detect_language_from_file

    language = detect_language_from_file(resolved)
    if not language or language == "unknown":
        return None
    if not is_file_parse_broken(resolved, language):
        return None
    summary_line = f"{file_path} signal=syntax_error verdict=ERROR"
    return {
        "success": True,
        "file_path": file_path,
        "edit_type": edit_type,
        "language": language,
        # ``risk_level`` is the canonical safe_to_edit field (cross-tool
        # contract). Use ``dangerous`` because broken syntax blocks the
        # entire downstream walk.
        "risk_level": "dangerous",
        "risk": "dangerous",
        "verdict": "ERROR",
        "signal": "syntax_error",
        # Empty downstream / test lists — we couldn't compute them on a
        # broken tree. ``has_tests=False`` keeps the schema valid.
        "downstream_dependents": [],
        "dependencies": [],
        "test_files": [],
        "has_tests": False,
        "pre_edit_checklist": [
            "Fix syntax errors so the file parses cleanly.",
            "Re-run safe_to_edit after the file parses.",
        ],
        "recommendation": (
            "File fails to parse — tree-sitter reported syntax errors. "
            "Fix syntax before editing further."
        ),
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": ("file fails to parse — fix syntax before further analysis"),
            "verdict": "ERROR",
            "risk": "high",
        },
    }


def _compute_risk(*args: Any, **kwargs: Any) -> tuple[str, list[dict[str, str]]]:
    """Compatibility wrapper for tests and internal imports."""
    return compute_risk(*args, **kwargs)


def _is_init_file(file_path: str) -> bool:
    """Compatibility wrapper for tests and internal imports."""
    return is_init_file(file_path)
