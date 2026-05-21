# Refactoring suggestions with precise extraction targets
#!/usr/bin/env python3
"""
Refactoring Suggestions MCP Tool

Analyzes files and returns concrete, actionable refactoring suggestions
with exact function names, line ranges, extraction targets, and code skeletons.

Uses tree-sitter for cross-language element extraction (all 15 languages),
with Python-AST enhanced analysis (nesting, params, static detection) as bonus.
"""

from pathlib import Path
from typing import Any

from ...utils import setup_logger
from ._refactoring_plan_builder import build_precise_plans
from .base_tool import BaseMCPTool
from .code_patterns_tool import _detect_anti_patterns, _detect_security
from .utils.element_extractor import extract_elements
from .utils.refactoring_suggestions_helpers import (
    build_success_response,
    error_response,
    get_refactoring_tool_schema,
)
from .utils.refactoring_suggestions_python import python_bonus_analysis
from .utils.refactoring_suggestions_treesitter import analyze_treesitter_patterns

logger = setup_logger(__name__)

_PATTERN_RULES: list[dict[str, Any]] = [
    {
        "id": "P001",
        # Pattern rules for code smell detection
        "name": "god_file",
        "severity": "critical",
        "threshold": 800,
        "message": "File exceeds {threshold} lines ({actual} lines). Split by responsibility.",
    },
    {
        "id": "P002",
        "name": "long_function",
        "severity": "major",
        "threshold": 50,
        "message": "Function '{name}' is {actual} lines (>{threshold}). Extract sub-operations.",
    },
    {
        "id": "P003",
        "name": "deep_nesting",
        "severity": "major",
        "threshold": 4,
        "message": "Function '{name}' has {actual} levels of nesting (>{threshold}). Flatten with early returns or guard clauses.",
    },
    {
        "id": "P004",
        "name": "too_many_params",
        "severity": "minor",
        "threshold": 5,
        "message": "Function '{name}' has {actual} parameters (>{threshold}). Introduce a parameter object.",
    },
]

_EXTRACTABLE_PATTERNS: list[dict[str, Any]] = [
    {
        # Extractable patterns for refactoring suggestions
        "id": "E001",
        "name": "extract_method",
        "detect": "block_after_assignment",
        "message": "Lines {start}-{end} in '{function}' compute a value then use it once. Extract as a helper function.",
    },
    {
        "id": "E002",
        "name": "extract_class",
        "detect": "methods_with_common_prefix",
        "message": "Methods {methods} in '{class_name}' share prefix '{prefix}'. Extract a new class.",
    },
    {
        "id": "E003",
        "name": "move_to_helpers",
        "detect": "pure_function_in_class",
        "message": "Method '{method}' in '{class_name}' doesn't use self. Move to module-level helper.",
    },
    {
        "id": "E004",
        "name": "reduce_class_size",
        "detect": "large_class",
        "threshold": 15,
        "message": "Class '{name}' has {actual} methods (>{threshold}). Consider splitting responsibilities.",
    },
]


class RefactoringSuggestionsTool(BaseMCPTool):
    """MCP Tool that provides concrete refactoring suggestions for source files."""

    # Tool definition and schema
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "refactoring_suggestions",
            "description": (
                "Refactoring plan with precise extraction targets. "
                "Returns helper names, line ranges, params, returns, code skeletons. "
                "No built-in tool provides this."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return get_refactoring_tool_schema()

    # Source file reading and analysis
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute refactoring analysis on a source file."""
        file_path = arguments.get("file_path", "")
        max_suggestions = arguments.get("max_suggestions", 10)
        include_extractions = arguments.get("include_extractions", True)
        include_skeleton = arguments.get("include_skeleton", False)
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        if not resolved:
            return error_response(
                file_path,
                "File not found or outside project boundary",
                project_root=self.project_root,
            )

        try:
            source = Path(resolved).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return error_response(
                file_path,
                f"Cannot read file: {e}",
                project_root=self.project_root,
            )

        analysis = extract_elements(resolved, self.project_root)
        # Tree-sitter based pattern analysis
        suggestions = analyze_treesitter_patterns(
            source,
            analysis,
            include_extractions,
            _PATTERN_RULES,
            _EXTRACTABLE_PATTERNS,
            resolved,
        )

        ext = Path(resolved).suffix.lower()
        if ext == ".py" and analysis:
            python_bonus_analysis(
                source,
                suggestions,
                include_extractions,
                _PATTERN_RULES,
                _EXTRACTABLE_PATTERNS,
            )

        # J9 (round-22): bridge anti-patterns + security findings into the
        # refactor suggestion stream. Before this, a file containing
        # ``def f(x=[])``, ``except:``, and ``eval(...)`` returned
        # ``refactor=clean`` while ``code_patterns`` flagged 4 findings on
        # the same file — agents that ran refactor first shipped the bugs.
        # The structural detectors above only catch length / nesting /
        # large-class smells; anti-patterns + security live in their own
        # module. We pull from the same helpers ``code_patterns`` uses so
        # the two tools no longer disagree on the same input.
        _surface_security_and_anti_patterns(resolved, suggestions, file_path=file_path)

        build_precise_plans(resolved, source, analysis, suggestions)

        result = build_success_response(
            resolved,
            suggestions,
            max_suggestions,
            include_skeleton,
            project_root=self.project_root,
        )

        # M14 (round-26): echo the detected language. ``refactor`` and
        # ``file_health`` previously returned ``language: None`` on a
        # ``.ts`` file even though both apply TypeScript-specific
        # analysis — agents that cross-checked ``analyze_scale`` saw a
        # contradiction. Detect once here (best-effort: detector
        # failures must not block the suggestion stream).
        from ...language_detector import detect_language_from_file

        try:
            detected_language = detect_language_from_file(
                resolved, project_root=self.project_root
            )
        except Exception:  # nosec B110 — language detection is best-effort
            detected_language = "unknown"
        if (
            detected_language
            and detected_language != "unknown"
            and "language" not in result
        ):
            result["language"] = detected_language

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    # Input validation - fail fast with clear error messages
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate file_path argument."""
        file_path = arguments.get("file_path", "")
        if not file_path or not isinstance(file_path, str):
            raise ValueError("file_path is required and must be a string")
        return True


def _surface_security_and_anti_patterns(
    resolved: str,
    suggestions: list[dict[str, Any]],
    *,
    file_path: str,
) -> None:
    """J9: append code_patterns findings as refactor suggestions.

    The refactor tool used to only emit *structural* suggestions (long
    method, deep nesting, god class). On a file like::

        def f(x=[]):
            return x
        try: pass
        except: pass
        eval("1+1")

    every structural threshold passes (the file is 5 lines, no nesting,
    no class) so the tool happily returned ``refactor=clean`` —
    misleading because ``code_patterns`` flagged the same file as
    UNSAFE with 2 critical findings. An agent chaining
    ``--refactor`` first would have shipped the bugs.

    We pull from the same module-level helpers that ``code_patterns``
    uses so both tools see exactly the same findings. The shape is
    normalised to the refactor suggestion contract: severity values are
    mapped (critical→critical, warning→major, info→minor) so the
    existing ``_agent_risk`` and severity-counting logic keeps working
    without special casing.
    """
    from ...language_detector import detect_language_from_file

    try:
        language = detect_language_from_file(resolved)
    except Exception:  # nosec B110 — language detection is best-effort
        return

    if not language:
        return

    findings: list[dict[str, Any]] = []
    try:
        findings.extend(_detect_security(resolved, language))
    except Exception:  # nosec B110 — detector failure must not block refactor
        pass
    try:
        findings.extend(_detect_anti_patterns(resolved, language))
    except Exception:  # nosec B110 — detector failure must not block refactor
        pass

    if not findings:
        return

    # Severity mapping: code_patterns uses ``critical/warning/info``;
    # refactor's downstream logic uses ``critical/major/minor``. Keep
    # the ordering parallel so ``_agent_risk`` still produces
    # ``high`` for any critical finding.
    severity_map = {"critical": "critical", "warning": "major", "info": "minor"}

    for finding in findings:
        sev_raw = str(finding.get("severity") or "info")
        sev = severity_map.get(sev_raw, "minor")
        category = str(finding.get("category") or "")
        finding_id = str(finding.get("id") or finding.get("type") or "unknown")
        finding_type = str(finding.get("type") or finding_id)
        message = str(finding.get("message") or finding_type)
        line = finding.get("line")
        # Priority pulls criticals above structural suggestions but
        # leaves room (100) for the god-file pattern. ``code_patterns``
        # already attaches a severity ordering — mirror it here so the
        # most dangerous finding sorts to the top of the response.
        priority = 85 if sev == "critical" else (60 if sev == "major" else 40)
        suggestion: dict[str, Any] = {
            "type": "anti_pattern" if category == "anti_patterns" else "security",
            "id": finding_id,
            "name": finding_type,
            "pattern": finding_type,
            "severity": sev,
            "message": message,
            "priority_score": priority,
            "source": "code_patterns",
            "category": category,
        }
        if isinstance(line, int):
            suggestion["line_range"] = {"start": line, "end": line}
        suggestions.append(suggestion)

    # Side-effect documented: callers receive the augmented list in
    # place. The display ``file_path`` is unused here — kept in the
    # signature so future severity-weighting can echo it back.
    _ = file_path
