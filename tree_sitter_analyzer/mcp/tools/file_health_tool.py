#!/usr/bin/env python3
"""
File Health MCP Tool

Exposes health_scorer.py to AI agents via MCP protocol.
Returns A-F grades, dimension scores, and specific code smells for single files.

Uses tree-sitter for cross-language element extraction (all 15 languages).
"""

import re
from pathlib import Path
from typing import Any

from ...health_scorer import HealthScorer
from ...utils import setup_logger
from .base_tool import BaseMCPTool
from .security_scanner import detect_security_issues
from .utils.element_extractor import extract_elements, get_classes, get_functions

logger = setup_logger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Path to the source file to score",
        },
        "language": {
            "type": "string",
            "description": "Programming language (optional, auto-detected)",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "description": "Output format: 'toon' (default, token-efficient) or 'json'",
            "default": "toon",
        },
    },
    "required": ["file_path"],
    "additionalProperties": False,
}


class FileHealthTool(BaseMCPTool):
    """MCP Tool for file-level code health scoring with code smell detection."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self._scorer: HealthScorer | None = None

    def set_project_path(self, project_path: str) -> None:
        super().set_project_path(project_path)
        self._scorer = None

    def _get_scorer(self) -> HealthScorer:
        if self._scorer is None:
            self._scorer = HealthScorer()
        return self._scorer

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "check_file_health",
            "description": (
                "File health A-F grade with code smells + security scan. "
                "NOT reading code — gives risk assessment. "
                "Returns: 5 dimension scores, smells, fix suggestions."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

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
        output_format = arguments.get("output_format", "toon")
        language = arguments.get("language")

        resolved = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved).exists():
            raise ValueError(f"File not found: {file_path}")

        if not language:
            from ...language_detector import detect_language_from_file

            language = detect_language_from_file(
                resolved, project_root=self.project_root
            )
            if language == "unknown":
                language = None

        scorer = self._get_scorer()
        health = scorer.score_file(resolved)

        analysis = extract_elements(resolved, self.project_root)

        smells = _detect_code_smells(resolved, health.dimensions, analysis, language)

        result = {
            "success": True,
            "file_path": file_path,
            "grade": health.grade,
            "total_score": health.total,
            "dimensions": health.dimensions,
            "code_smells": smells,
            "smell_count": len(smells),
            "recommendation": _build_recommendation(
                health.grade, health.dimensions, smells
            ),
        }

        if health.grade in ("D", "F"):
            result["next_action"] = _suggest_next_action(
                file_path, health.grade, smells
            )
            plan = _build_extraction_plan(file_path, smells, resolved, analysis)
            if plan:
                result["extraction_plan"] = plan

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _detect_code_smells(
    file_path: str,
    dimensions: dict[str, float],
    analysis: Any,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Detect specific code smells using tree-sitter elements."""
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lines = source.splitlines()
    line_count = len(lines)
    smells: list[dict[str, Any]] = []

    _check_oversized_file(smells, line_count)
    _check_deep_nesting(smells, lines)
    _check_dimension_smells(smells, dimensions)
    _check_element_smells(smells, lines, line_count, analysis)
    _check_technical_debt(smells, lines)

    if language:
        sec_issues = detect_security_issues(source, language)
        for issue in sec_issues[:10]:
            smells.append(
                {
                    "smell": f"security:{issue['issue']}",
                    "detail": f"{issue['description']} (line {issue['lines'][0]})",
                    "severity": issue["severity"],
                    "fix": "Move secrets to env vars / use parameterized queries / avoid eval()",
                }
            )

    return smells


def _check_oversized_file(smells: list[dict[str, Any]], line_count: int) -> None:
    if line_count > 500:
        severity = "critical" if line_count > 1000 else "warning"
        smells.append(
            {
                "smell": "oversized_file",
                "detail": f"{line_count} lines (recommended < 300)",
                "severity": severity,
                "fix": "Split into smaller, focused modules",
            }
        )


def _check_deep_nesting(smells: list[dict[str, Any]], lines: list[str]) -> None:
    max_indent = 0
    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent > max_indent:
            max_indent = indent
    max_nesting = max_indent // 4
    if max_nesting > 4:
        smells.append(
            {
                "smell": "deep_nesting",
                "detail": f"Max nesting depth: {max_nesting} (recommended < 4)",
                "severity": "critical" if max_nesting > 6 else "warning",
                "fix": "Extract nested logic into helper functions or use early returns",
            }
        )


def _check_dimension_smells(
    smells: list[dict[str, Any]], dimensions: dict[str, float]
) -> None:
    if dimensions.get("comments", 100) < 20:
        smells.append(
            {
                "smell": "missing_documentation",
                "detail": f"Comment ratio: {dimensions.get('comments', 0):.0f}% (recommended > 15%)",
                "severity": "info",
                "fix": "Add docstrings to public classes and functions",
            }
        )

    complexity = dimensions.get("complexity", 100)
    if complexity < 30:
        smells.append(
            {
                "smell": "high_complexity",
                "detail": f"Complexity score: {complexity:.0f}/100",
                "severity": "critical" if complexity < 10 else "warning",
                "fix": "Break complex functions into smaller, focused ones",
            }
        )

    deps = dimensions.get("dependencies", 100)
    if deps < 30:
        smells.append(
            {
                "smell": "high_coupling",
                "detail": f"Dependency score: {deps:.0f}/100",
                "severity": "warning",
                "fix": "Reduce imports — consider dependency injection or facade pattern",
            }
        )


def _check_element_smells(
    smells: list[dict[str, Any]],
    lines: list[str],
    line_count: int,
    analysis: Any,
) -> None:
    if analysis:
        classes = get_classes(analysis)
        functions = get_functions(analysis)

        if line_count > 300 and len(classes) <= 1:
            smells.append(
                {
                    "smell": "god_class",
                    "detail": f"Single class spanning {line_count} lines",
                    "severity": "critical" if line_count > 500 else "warning",
                    "fix": "Extract responsibilities into separate classes (Single Responsibility Principle)",
                }
            )

        for func in functions:
            if func["lines"] > 50:
                smells.append(
                    {
                        "smell": "long_method",
                        "detail": f"'{func['name']}' is {func['lines']} lines (L{func['line']})",
                        "severity": "critical" if func["lines"] > 100 else "warning",
                        "fix": "Extract logical sections into separate helper methods",
                    }
                )
    else:
        long_methods = _find_long_blocks_heuristic(lines, threshold=50)
        for method_name, start, length in long_methods[:3]:
            smells.append(
                {
                    "smell": "long_method",
                    "detail": f"'{method_name}' is ~{length} lines (L{start})",
                    "severity": "critical" if length > 100 else "warning",
                    "fix": "Extract logical sections into separate helper methods",
                }
            )


def _check_technical_debt(smells: list[dict[str, Any]], lines: list[str]) -> None:
    todo_count = sum(
        1
        for line in lines
        if any(k in line.upper() for k in ("TODO", "FIXME", "HACK", "XXX"))
        and not line.strip().startswith("#!")
        and not line.strip().startswith("# type:")
    )
    if todo_count > 5:
        smells.append(
            {
                "smell": "technical_debt",
                "detail": f"{todo_count} TODO/FIXME/HACK markers",
                "severity": "info",
                "fix": "Resolve or create issues for outstanding TODOs",
            }
        )


def _find_long_blocks_heuristic(
    lines: list[str], threshold: int = 50
) -> list[tuple[str, int, int]]:
    """Fallback long block detection using indentation heuristics."""
    results: list[tuple[str, int, int]] = []
    in_def = False
    def_name = ""
    def_start = 0
    def_indent = 0
    block_lines = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("def ") or stripped.startswith("async def "):
            if in_def and block_lines > threshold:
                results.append((def_name, def_start + 1, block_lines))
            in_def = True
            after_def = stripped.split("def ", 1)[-1] if "def " in stripped else ""
            def_name = after_def.split("(")[0].strip() if after_def else f"block_{i}"
            def_start = i
            def_indent = len(line) - len(line.lstrip())
            block_lines = 1
            continue

        if in_def:
            if not stripped:
                block_lines += 1
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent > def_indent:
                block_lines += 1
            elif current_indent == def_indent and (
                stripped.startswith("def ")
                or stripped.startswith("async def ")
                or stripped.startswith("class ")
                or stripped.startswith("@")
            ):
                if block_lines > threshold:
                    results.append((def_name, def_start + 1, block_lines))
                in_def = False
            else:
                block_lines += 1

    if in_def and block_lines > threshold:
        results.append((def_name, def_start + 1, block_lines))

    results.sort(key=lambda x: -x[2])
    return results


def _build_recommendation(
    grade: str,
    dimensions: dict[str, float],
    smells: list[dict[str, Any]],
) -> str:
    if grade in ("A", "B") and not smells:
        return "File is in good shape. No immediate action needed."
    if not smells:
        worst = min(dimensions, key=lambda k: dimensions[k], default="")
        return f"Overall grade {grade} — weakest dimension is '{worst}'. Consider targeted improvement."

    critical = [s for s in smells if s["severity"] == "critical"]
    warnings = [s for s in smells if s["severity"] == "warning"]
    parts = [f"Grade {grade}"]
    if critical:
        parts.append(
            f"{len(critical)} critical: {', '.join(s['smell'] for s in critical)}"
        )
    if warnings:
        parts.append(
            f"{len(warnings)} warning(s): {', '.join(s['smell'] for s in warnings)}"
        )

    long_methods = [s for s in smells if s["smell"] == "long_method"]
    if long_methods:
        names = [s["detail"].split("'")[1] for s in long_methods if "'" in s["detail"]]
        if names:
            parts.append(
                f"Extract: {', '.join(names[:3])} into standalone functions in a new module"
            )

    return ". ".join(parts) + ". Focus on critical items first."


def _suggest_next_action(
    file_path: str,
    grade: str,
    smells: list[dict[str, Any]],
) -> str:
    long_methods = [s for s in smells if s["smell"] == "long_method"]
    if long_methods:
        names = [s["detail"].split("'")[1] for s in long_methods if "'" in s["detail"]]
        if names:
            return (
                f"Extract {', '.join(names[:2])} into a new module, "
                f"then call check_file_health(file_path='{file_path}') to verify improvement"
            )

    oversized = any(s["smell"] == "oversized_file" for s in smells)
    if oversized:
        return (
            f"Call analyze_code_structure(file_path='{file_path}', format='table') "
            f"to identify extraction targets, then split into focused modules"
        )

    return (
        "Review code_smells above and apply suggested fixes, "
        "then re-run check_file_health to track improvement"
    )


def _build_extraction_plan(
    file_path: str,
    smells: list[dict[str, Any]],
    resolved_path: str,
    analysis: Any,
) -> dict[str, Any] | None:
    """Build a structured extraction plan for D/F grade files."""
    long_methods = [s for s in smells if s["smell"] == "long_method"]
    if not long_methods:
        return None

    targets = []
    for s in long_methods[:3]:
        detail = s.get("detail", "")
        name = detail.split("'")[1] if "'" in detail else "unknown"
        line_match = re.search(r"\(L(\d+)\)", detail)
        start_line = int(line_match.group(1)) if line_match else 0
        end_line = _find_function_end_line(resolved_path, start_line, analysis)
        targets.append(
            {
                "method": name,
                "start_line": start_line,
                "end_line": end_line,
                "priority": "critical" if s.get("severity") == "critical" else "normal",
            }
        )

    stem = Path(file_path).stem
    parent = str(Path(file_path).parent)
    new_module = f"{parent}/_{stem}_helpers.py" if parent else f"_{stem}_helpers.py"

    return {
        "target_file": file_path,
        "new_module": new_module,
        "methods_to_extract": targets,
        "steps": [
            f"1. Read {file_path} with extract_code_section",
            f"2. Create {new_module} with extracted methods as standalone functions",
            f"3. Add delegates in {file_path} calling the new module",
            "4. Run tests to verify zero regressions",
            f"5. Re-run check_file_health(file_path='{file_path}')",
        ],
    }


def _find_function_end_line(file_path: str, start_line: int, analysis: Any) -> int:
    """Find the end line of a function using tree-sitter elements, with fallback."""
    # Primary: use tree-sitter extracted elements
    if analysis:
        functions = get_functions(analysis)
        for func in functions:
            if func["line"] == start_line:
                return func["end_line"]  # type: ignore[no-any-return]

    # Fallback: indentation-based
    try:
        lines = (
            Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        )
        if start_line - 1 >= len(lines):
            return start_line

        base_indent = len(lines[start_line - 1]) - len(lines[start_line - 1].lstrip())
        for i in range(start_line, len(lines)):
            stripped = lines[i].strip()
            if not stripped:
                continue
            current_indent = len(lines[i]) - len(lines[i].lstrip())
            if current_indent <= base_indent and stripped:
                return i
        return len(lines)
    except Exception:  # nosec B110
        return start_line
