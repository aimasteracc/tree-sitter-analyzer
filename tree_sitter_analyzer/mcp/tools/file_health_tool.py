#!/usr/bin/env python3
"""
File Health MCP Tool

Exposes health_scorer.py to AI agents via MCP protocol.
Returns A-F grades, dimension scores, and specific code smells for single files.
"""

from pathlib import Path
from typing import Any

from ...health_scorer import HealthScorer
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


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
                "SMART Workflow 'Analyze' step: Score code health (A-F grade) for a single file. "
                "Returns weighted scores across 5 dimensions AND specific code smells detected "
                "(God Class, Long Method, Deep Nesting, High Coupling, Missing Docs). "
                "Use to quickly identify files needing refactoring and what exactly to fix."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
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

        resolved = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved).exists():
            raise ValueError(f"File not found: {file_path}")

        scorer = self._get_scorer()
        health = scorer.score_file(resolved)
        smells = _detect_code_smells(resolved, health.dimensions)

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

        # Provide a concrete next action for AI agents
        if health.grade in ("D", "F"):
            result["next_action"] = _suggest_next_action(
                file_path, health.grade, smells
            )

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _detect_code_smells(
    file_path: str, dimensions: dict[str, float]
) -> list[dict[str, Any]]:
    """Detect specific code smells in a file."""
    smells: list[dict[str, Any]] = []

    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return smells

    lines = source.splitlines()
    line_count = len(lines)

    # 1. Oversized file
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

    # 2. Deep nesting detection
    max_indent = 0
    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent > max_indent:
            max_indent = indent
    # Assuming 4-space indentation
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

    # 3. Missing docstrings
    if dimensions.get("comments", 100) < 20:
        smells.append(
            {
                "smell": "missing_documentation",
                "detail": f"Comment ratio: {dimensions.get('comments', 0):.0f}% (recommended > 15%)",
                "severity": "info",
                "fix": "Add docstrings to public classes and functions",
            }
        )

    # 4. High complexity
    if dimensions.get("complexity", 100) < 30:
        smells.append(
            {
                "smell": "high_complexity",
                "detail": f"Complexity score: {dimensions.get('complexity', 0):.0f}/100",
                "severity": "critical"
                if dimensions.get("complexity", 0) < 10
                else "warning",
                "fix": "Break complex functions into smaller, focused ones",
            }
        )

    # 5. Many dependencies (high coupling)
    if dimensions.get("dependencies", 100) < 30:
        smells.append(
            {
                "smell": "high_coupling",
                "detail": f"Dependency score: {dimensions.get('dependencies', 0):.0f}/100",
                "severity": "warning",
                "fix": "Reduce imports — consider dependency injection or facade pattern",
            }
        )

    # 6. Detect potential God Class (many classes or very long class)
    class_count = _count_keyword(lines, ["class "])
    if line_count > 300 and class_count <= 1:
        smells.append(
            {
                "smell": "god_class",
                "detail": f"Single class spanning {line_count} lines",
                "severity": "critical" if line_count > 500 else "warning",
                "fix": "Extract responsibilities into separate classes (Single Responsibility Principle)",
            }
        )

    # 7. Long method detection (by counting consecutive non-blank lines at same indent level)
    long_methods = _find_long_blocks(lines, threshold=50)
    if long_methods:
        for method_name, start, length in long_methods[:3]:
            smells.append(
                {
                    "smell": "long_method",
                    "detail": f"'{method_name}' is ~{length} lines (L{start})",
                    "severity": "critical" if length > 100 else "warning",
                    "fix": "Extract logical sections into separate helper methods",
                }
            )

    # 8. Too many TODO/FIXME/HACK
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

    return smells


def _count_keyword(lines: list[str], keywords: list[str]) -> int:
    return sum(1 for line in lines if any(k in line for k in keywords))


def _find_long_blocks(
    lines: list[str], threshold: int = 50
) -> list[tuple[str, int, int]]:
    """Find long blocks of code (potential long methods/functions)."""
    results: list[tuple[str, int, int]] = []
    in_def = False
    def_name = ""
    def_start = 0
    def_indent = 0
    block_lines = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect function/method definitions
        if stripped.startswith("def ") or stripped.startswith("async def "):
            # Save previous block if it was long
            if in_def and block_lines > threshold:
                results.append((def_name, def_start + 1, block_lines))

            in_def = True
            # Extract function name
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
            # Same or deeper indent = still in the function
            if current_indent > def_indent:
                block_lines += 1
            elif current_indent == def_indent and (
                stripped.startswith("def ")
                or stripped.startswith("async def ")
                or stripped.startswith("class ")
                or stripped.startswith("@")
            ):
                # Hit a new def/class/decorator at same level — end current block
                if block_lines > threshold:
                    results.append((def_name, def_start + 1, block_lines))
                in_def = False
            else:
                block_lines += 1

    # Don't forget the last block
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

    # Add extraction suggestion for long methods
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
    """Suggest a concrete next action for an AI agent to take."""
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
