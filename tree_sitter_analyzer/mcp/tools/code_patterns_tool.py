#!/usr/bin/env python3
"""
Code Patterns / Anti-Pattern Detection MCP Tool.

Unified pattern detection combining code smells, security issues, refactoring
patterns, and LLM anti-patterns into a single agent-friendly API.

Tells AI agents: "Here are the problems in this file and how to fix them."
"""

from pathlib import Path
from typing import Any

from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool
from .security_scanner import detect_security_issues
from .utils.file_health_smells import detect_code_smells

logger = setup_logger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "File to scan for patterns",
        },
        "categories": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["smells", "security", "anti_patterns", "all"],
            },
            "default": ["all"],
            "description": "Pattern categories to detect",
        },
        "severity_threshold": {
            "type": "string",
            "enum": ["info", "warning", "critical"],
            "default": "info",
            "description": "Minimum severity to report",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
    },
    "required": ["file_path"],
    "additionalProperties": False,
}

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


class CodePatternsTool(BaseMCPTool):
    """Detect code patterns, anti-patterns, and security issues in a file."""

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "code_patterns",
            "description": (
                "Detect anti-patterns, code smells, and security issues in a file. "
                "Categories: smells (god_class, long_method, deep_nesting), "
                "security (sql_injection, hardcoded_secret, eval_usage), "
                "anti_patterns (mutable_defaults, bare_except, print_statements). "
                "Use BEFORE editing to know what to fix."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("file_path"):
            raise ValueError("file_path is required")
        cats = arguments.get("categories", ["all"])
        valid = {"smells", "security", "anti_patterns", "all"}
        for c in cats:
            if c not in valid:
                raise ValueError(f"Unknown category: {c}")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments["file_path"]
        categories = arguments.get("categories", ["all"])
        severity_threshold = arguments.get("severity_threshold", "info")
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved).is_file():
            raise ValueError(f"Not a file: {file_path}")

        min_sev = _SEVERITY_ORDER.get(severity_threshold, 0)

        from ...language_detector import detect_language_from_file

        language = detect_language_from_file(resolved, project_root=self.project_root)

        all_patterns: list[dict[str, Any]] = []

        scan_all = "all" in categories

        if scan_all or "smells" in categories:
            all_patterns.extend(_detect_smells(resolved, language))

        if scan_all or "security" in categories:
            all_patterns.extend(_detect_security(resolved, language))

        if scan_all or "anti_patterns" in categories:
            all_patterns.extend(_detect_anti_patterns(resolved, language))

        filtered = [
            p for p in all_patterns if _SEVERITY_ORDER.get(p.get("severity"), 0) >= min_sev
        ]
        filtered.sort(key=lambda p: _SEVERITY_ORDER.get(p.get("severity"), 0), reverse=True)

        by_category: dict[str, list[dict[str, Any]]] = {}
        for p in filtered:
            cat = p["category"]
            by_category.setdefault(cat, []).append(p)

        response: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "language": language,
            "total_patterns": len(filtered),
            "patterns": filtered[:50],
            "by_category": {k: len(v) for k, v in by_category.items()},
            "summary": _build_summary(filtered),
            "smart_workflow_hint": (
                f"Found {len(filtered)} pattern(s) in {file_path}. "
                + (
                    "Critical issues found — fix these first. "
                    if any(p["severity"] == "critical" for p in filtered)
                    else "Review warnings and decide which to address. "
                )
                + "Use refactoring_suggestions for concrete fix recipes."
            ),
        }

        return apply_toon_format_to_response(response, output_format)


def _detect_smells(file_path: str, language: str) -> list[dict[str, Any]]:
    try:
        smells = detect_code_smells(file_path, language)
    except Exception:
        return []

    patterns: list[dict[str, Any]] = []
    for smell in smells:
        sev = "info"
        if smell.get("critical"):
            sev = "critical"
        elif smell.get("severity") in ("warning", "major"):
            sev = "warning"
        patterns.append(
            {
                "id": smell.get("id", smell.get("type", "unknown")),
                "category": "smells",
                "type": smell.get("type", ""),
                "severity": sev,
                "message": smell.get("message", ""),
                "line": smell.get("line"),
            }
        )
    return patterns


def _detect_security(file_path: str, language: str) -> list[dict[str, Any]]:
    try:
        issues = detect_security_issues(file_path, language)
    except Exception:
        return []

    patterns: list[dict[str, Any]] = []
    for issue in issues:
        patterns.append(
            {
                "id": issue.get("id", issue.get("type", "unknown")),
                "category": "security",
                "type": issue.get("type", ""),
                "severity": "critical" if issue.get("type") in (
                    "hardcoded_secret", "sql_injection", "shell_injection",
                ) else "warning",
                "message": issue.get("message", ""),
                "line": issue.get("line"),
            }
        )
    return patterns


def _detect_anti_patterns(file_path: str, language: str) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []

    try:
        content = Path(file_path).read_text(errors="replace")
    except Exception:
        return patterns

    lines = content.splitlines()

    if language == "python":
        _check_python_anti_patterns(lines, patterns)
    elif language in ("javascript", "typescript"):
        _check_js_anti_patterns(lines, patterns)
    elif language == "java":
        _check_java_anti_patterns(lines, patterns)

    return patterns


def _check_python_anti_patterns(
    lines: list[str], patterns: list[dict[str, Any]]
) -> None:
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        if "=" in stripped and any(
            f"={t}" in stripped
            for t in ("[]", "{},", "set()", "[],")
        ):
            if "def " in lines[max(0, i - 5) : i][-1] or any(
                "def " in ln for ln in lines[max(0, i - 10) : i]
            ):
                patterns.append(
                    {
                        "id": "AP001",
                        "category": "anti_patterns",
                        "type": "mutable_default_argument",
                        "severity": "critical",
                        "message": "Mutable default argument — shared across calls",
                        "line": i,
                    }
                )

        if stripped.startswith("except:") and "except:" == stripped:
            patterns.append(
                {
                    "id": "AP002",
                    "category": "anti_patterns",
                    "type": "bare_except",
                    "severity": "warning",
                    "message": "Bare except catches everything including KeyboardInterrupt",
                    "line": i,
                }
            )

        if "print(" in stripped and not stripped.startswith("#"):
            in_def = any(
                "def " in ln for ln in lines[max(0, i - 30) : i]
            )
            if in_def:
                patterns.append(
                    {
                        "id": "AP003",
                        "category": "anti_patterns",
                        "type": "print_in_production",
                        "severity": "info",
                        "message": "Use logging instead of print()",
                        "line": i,
                    }
                )


def _check_js_anti_patterns(
    lines: list[str], patterns: list[dict[str, Any]]
) -> None:
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "var " in stripped and not stripped.startswith("//"):
            patterns.append(
                {
                    "id": "AP010",
                    "category": "anti_patterns",
                    "type": "var_usage",
                    "severity": "info",
                    "message": "Use const/let instead of var",
                    "line": i,
                }
            )
        if "== " in stripped or " !=" in stripped:
            if "===" not in stripped and "!==" not in stripped:
                patterns.append(
                    {
                        "id": "AP011",
                        "category": "anti_patterns",
                        "type": "loose_equality",
                        "severity": "warning",
                        "message": "Use === instead of == for strict comparison",
                        "line": i,
                    }
                )


def _check_java_anti_patterns(
    lines: list[str], patterns: list[dict[str, Any]]
) -> None:
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "System.out.println" in stripped and not stripped.startswith("//"):
            patterns.append(
                {
                    "id": "AP020",
                    "category": "anti_patterns",
                    "type": "system_out_println",
                    "severity": "info",
                    "message": "Use a logging framework instead of System.out",
                    "line": i,
                }
            )
        if "e.printStackTrace()" in stripped:
            patterns.append(
                {
                    "id": "AP021",
                    "category": "anti_patterns",
                    "type": "print_stacktrace",
                    "severity": "warning",
                    "message": "Use proper logging instead of printStackTrace()",
                    "line": i,
                }
            )


def _build_summary(patterns: list[dict[str, Any]]) -> str:
    if not patterns:
        return "No patterns detected."

    critical = sum(1 for p in patterns if p["severity"] == "critical")
    warning = sum(1 for p in patterns if p["severity"] == "warning")
    info = sum(1 for p in patterns if p["severity"] == "info")

    parts: list[str] = []
    if critical:
        parts.append(f"{critical} critical")
    if warning:
        parts.append(f"{warning} warning")
    if info:
        parts.append(f"{info} info")

    return f"Patterns: {', '.join(parts)}. Total: {len(patterns)}."
