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
from .base_tool import (
    BaseMCPTool,
    detect_language_mismatch,
    language_mismatch_error_response,
)
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
                "Concrete refactoring plan for a single file: surfaces "
                "structural smells (god class, long method, deep nesting, "
                "duplicated code) AND anti-patterns / security issues "
                "(eval, bare except, mutable default, SQL-injection-shaped "
                "f-strings) — same detectors as code_patterns, packaged as "
                "actionable extraction targets with helper names, line "
                "ranges, parameters, return types, and (optional) code "
                "skeletons.\n\n"
                "WHEN TO USE:\n"
                "- After file_health flags a file as B/C/D/F grade\n"
                "- Before splitting a god class — get extraction plan first\n"
                "- To find safe-to-extract helpers in a long function\n"
                "- Coupled with safe_to_edit before applying the refactor\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- Just to LIST smells with no extraction plan — use "
                "code_patterns (faster, no skeleton generation)\n"
                "- For a project-wide smell sweep — use file_health on each "
                "weakest file in project_health output\n"
                "- For pure renames — use modification_guard"
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return get_refactoring_tool_schema()

    # Source file reading and analysis
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute refactoring analysis on a source file.

        r37bk (dogfood): tool flagged this at 112 lines. Split into
        argument parse + path validation + language gate + file read +
        suggestion pipeline + envelope finalize. Each phase is now ≤25
        lines. O8 mismatch gate, J9 cross-tool surfacing, M14 language
        echo all preserved.
        """
        file_path = arguments.get("file_path", "")
        explicit_language = arguments.get("language")
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

        mismatch_response = self._check_language_mismatch(
            resolved, file_path, explicit_language, output_format
        )
        if mismatch_response is not None:
            return mismatch_response

        source = self._read_source_or_error(resolved, file_path)
        if isinstance(source, dict):
            return source  # error envelope

        suggestions = self._build_suggestions_for_source(
            resolved, source, include_extractions
        )
        result = build_success_response(
            resolved,
            suggestions,
            max_suggestions,
            include_skeleton,
            project_root=self.project_root,
        )
        self._echo_detected_language(resolved, result)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _check_language_mismatch(
        self,
        resolved: str,
        file_path: str,
        explicit_language: str | None,
        output_format: str,
    ) -> dict[str, Any] | None:
        """O8 gate: reject ``--language java`` on a ``.py`` file."""
        mismatch = detect_language_mismatch(
            resolved,
            explicit_language,
            project_root=self.project_root,
        )
        if not mismatch:
            return None
        response = language_mismatch_error_response(
            tool_name="refactoring_suggestions",
            file_path=file_path,
            warning=mismatch,
        )
        response["output_format"] = output_format
        return response

    def _read_source_or_error(
        self, resolved: str, file_path: str
    ) -> str | dict[str, Any]:
        """Read source text; return an error envelope on failure."""
        try:
            return Path(resolved).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return error_response(
                file_path,
                f"Cannot read file: {e}",
                project_root=self.project_root,
            )

    def _build_suggestions_for_source(
        self,
        resolved: str,
        source: str,
        include_extractions: bool,
    ) -> list[dict[str, Any]]:
        """Run tree-sitter analysis + python bonus + J9 cross-tool surfacing."""
        analysis = extract_elements(resolved, self.project_root)
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
        # J9: bridge anti-patterns + security findings (so refactor and
        # code_patterns no longer disagree on the same input).
        _surface_security_and_anti_patterns(resolved, suggestions, file_path=resolved)
        build_precise_plans(resolved, source, analysis, suggestions)
        return suggestions

    def _echo_detected_language(self, resolved: str, result: dict[str, Any]) -> None:
        """M14 (round-26): echo detected language so callers don't see None."""
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
