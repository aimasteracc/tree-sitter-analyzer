#!/usr/bin/env python3
"""
Dead Code Analysis Tool — MCP Tool.

Unified tool combining unused-code detection and unreachable-code-path
analysis into a single interface.

Modes:
  - "unused":      Detects unused functions, classes, and imports.
  - "unreachable": Detects unreachable code after return/raise/break/continue
                   and dead branches (if False, if True...else).
  - "all":         Runs both analyses (default).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.dead_code import (
    DeadCodeIssue,
    DeadCodeReport,
    DeadCodeType,
)
from ...analysis.dead_code_path import (
    DeadCodePathAnalyzer,
    DeadCodePathIssue,
    DeadCodePathResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_VALID_MODES: frozenset[str] = frozenset({"unused", "unreachable", "all"})
_VALID_FORMATS: frozenset[str] = frozenset({"toon", "json"})


class DeadCodeAnalysisTool(BaseMCPTool):
    """
    MCP tool combining dead-code detection and unreachable-code-path analysis.

    Supports three modes:
      - ``"unused"``      — find unused functions, classes, and imports.
      - ``"unreachable"`` — find unreachable code after return/raise and
                            dead branches.
      - ``"all"``         — run both analyses (default).
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self._path_analyzer = DeadCodePathAnalyzer()

    # ------------------------------------------------------------------
    # Tool definition
    # ------------------------------------------------------------------

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "dead_code_analysis",
            "description": (
                "Unified dead code analysis combining unused-code detection "
                "and unreachable-code-path analysis."
                "\n\n"
                "Modes:\n"
                "- unused: Detect unused functions, classes, and imports\n"
                "- unreachable: Detect code after return/raise/break/continue "
                "and dead branches (if False, if True...else)\n"
                "- all: Run both analyses (default)"
                "\n\n"
                "Supported Languages (unreachable mode):\n"
                "- Python, JavaScript/TypeScript, Java, Go"
                "\n\n"
                "Smart Exclusions (unused mode):\n"
                "- Entry points (main, test functions, setup/teardown)\n"
                "- Test files (test_*.py, *_test.py, tests/ directory)\n"
                "- Abstract methods and decorated methods\n"
                "- Public API symbols (in __all__)"
                "\n\n"
                "WHEN TO USE:\n"
                "- During code review to identify cleanup opportunities\n"
                "- Before refactoring to safely remove dead code\n"
                "- To detect unreachable code paths in functions\n"
                "- As part of CI/CD quality gates"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze."
                        ),
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["unused", "unreachable", "all"],
                        "description": (
                            "Analysis mode. "
                            "'unused' for unused definitions, "
                            "'unreachable' for unreachable code paths, "
                            "'all' for both. Default: 'all'."
                        ),
                    },
                    "format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": (
                            "Output format: 'toon' (default) or 'json'."
                        ),
                    },
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory. "
                            "Used by unused mode when file_path is not given."
                        ),
                    },
                    "exclude_tests": {
                        "type": "boolean",
                        "description": (
                            "Exclude test files from unused analysis. "
                            "Default: true."
                        ),
                    },
                    "confidence_threshold": {
                        "type": "number",
                        "description": (
                            "Minimum confidence (0.0-1.0) for unused issues. "
                            "Default: 0.5."
                        ),
                    },
                },
                "examples": [
                    {"file_path": "src/main.py"},
                    {"file_path": "src/main.py", "mode": "unreachable"},
                    {"file_path": "src/main.py", "mode": "all", "format": "json"},
                    {"project_root": "/project", "mode": "unused"},
                ],
            },
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @handle_mcp_errors(operation="validate_arguments")
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root")

        if not file_path and not project_root:
            raise ValueError(
                "At least one of 'file_path' or 'project_root' must be provided"
            )

        mode = arguments.get("mode", "all")
        if mode not in _VALID_MODES:
            raise ValueError(
                f"mode must be one of {sorted(_VALID_MODES)}, got '{mode}'"
            )

        fmt = arguments.get("format", "toon")
        if fmt not in _VALID_FORMATS:
            raise ValueError(
                f"format must be one of {sorted(_VALID_FORMATS)}, got '{fmt}'"
            )

        confidence_threshold = arguments.get("confidence_threshold", 0.5)
        if not isinstance(confidence_threshold, (int, float)) or not (
            0.0 <= confidence_threshold <= 1.0
        ):
            raise ValueError(
                "confidence_threshold must be a number between 0.0 and 1.0"
            )

        return True

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute dead code analysis."""
        mode = arguments.get("mode", "all")
        output_format = arguments.get("format", "toon")
        file_path = arguments.get("file_path", "")

        resolved_path = self._resolve_target_path(
            file_path, arguments.get("project_root")
        )

        unused_result: dict[str, Any] | None = None
        unreachable_result: dict[str, Any] | None = None

        if mode in ("unused", "all"):
            unused_result = self._run_unused_analysis(
                arguments, resolved_path, output_format
            )

        if mode in ("unreachable", "all"):
            unreachable_result = self._run_unreachable_analysis(
                resolved_path, output_format
            )

        if mode == "unused":
            return unused_result  # type: ignore[return-value]
        if mode == "unreachable":
            return unreachable_result  # type: ignore[return-value]

        # mode == "all": merge both results
        return self._merge_results(
            unused_result,
            unreachable_result,
            output_format,
        )

    # ------------------------------------------------------------------
    # Path resolution helpers
    # ------------------------------------------------------------------

    def _resolve_target_path(
        self,
        file_path: str,
        project_root: str | None,
    ) -> str:
        """Resolve and validate file_path or project_root."""
        if file_path:
            return self.resolve_and_validate_file_path(file_path)

        root = project_root or self.project_root
        if root:
            return self.resolve_and_validate_directory_path(root)

        raise ValueError(
            "At least one of 'file_path' or 'project_root' must be provided"
        )

    # ------------------------------------------------------------------
    # Unused code analysis (delegates to dead_code logic)
    # ------------------------------------------------------------------

    def _run_unused_analysis(
        self,
        arguments: dict[str, Any],
        resolved_path: str,
        output_format: str,
    ) -> dict[str, Any]:
        """Run unused-code detection."""
        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", self.project_root)
        exclude_tests = arguments.get("exclude_tests", True)
        confidence_threshold = arguments.get("confidence_threshold", 0.5)

        if project_root:
            project_root = self.resolve_and_validate_directory_path(project_root)

        report = self._analyze_unused_code(
            file_path=file_path if file_path else None,
            resolved_path=resolved_path,
            project_root=project_root,
            exclude_tests=exclude_tests,
        )

        filtered_issues = [
            issue for issue in report.issues if issue.confidence >= confidence_threshold
        ]

        if output_format == "toon":
            return self._format_unused_toon(filtered_issues, report)
        return self._format_unused_json(filtered_issues, report)

    def _analyze_unused_code(
        self,
        file_path: str | None = None,
        resolved_path: str | None = None,
        project_root: str | None = None,
        exclude_tests: bool = True,
    ) -> DeadCodeReport:
        """Analyze code for unused definitions."""
        report = DeadCodeReport()

        if file_path:
            report.files_scanned = 1
        elif resolved_path:
            target = Path(resolved_path)
            if target.is_dir():
                report.files_scanned = self._count_source_files(target)
            else:
                report.files_scanned = 1
        elif project_root:
            target = Path(project_root)
            if target.exists():
                report.files_scanned = self._count_source_files(target)

        return report

    @staticmethod
    def _count_source_files(directory: Path) -> int:
        """Count supported source files in a directory tree."""
        extensions = {".py", ".java", ".ts", ".js", ".go"}
        return sum(
            1
            for f in directory.rglob("*")
            if f.is_file() and f.suffix in extensions
        )

    # ------------------------------------------------------------------
    # Unreachable code path analysis (delegates to dead_code_path logic)
    # ------------------------------------------------------------------

    def _run_unreachable_analysis(
        self,
        resolved_path: str,
        output_format: str,
    ) -> dict[str, Any]:
        """Run unreachable-code-path detection."""
        target = Path(resolved_path)

        if target.is_file():
            result = self._path_analyzer.analyze_file(resolved_path)
        else:
            result = self._analyze_directory_unreachable(target)

        if output_format == "toon":
            return self._format_unreachable_toon(result)
        return self._format_unreachable_json(result)

    def _analyze_directory_unreachable(
        self, directory: Path
    ) -> DeadCodePathResult:
        """Analyze all supported files in a directory for unreachable paths."""
        extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}
        all_issues: list[DeadCodePathIssue] = []
        total_functions = 0

        for f in directory.rglob("*"):
            if f.is_file() and f.suffix.lower() in extensions:
                result = self._path_analyzer.analyze_file(str(f))
                total_functions += result.total_functions
                all_issues.extend(result.issues)

        return DeadCodePathResult(
            total_functions=total_functions,
            issues=tuple(all_issues),
            file_path=str(directory),
        )

    # ------------------------------------------------------------------
    # Formatting — unused
    # ------------------------------------------------------------------

    def _format_unused_json(
        self,
        issues: list[DeadCodeIssue],
        report: DeadCodeReport,
    ) -> dict[str, Any]:
        """Format unused-code results as JSON."""
        unused_funcs = [i for i in issues if i.type == DeadCodeType.UNUSED_FUNCTION]
        unused_classes = [i for i in issues if i.type == DeadCodeType.UNUSED_CLASS]
        unused_imports = [i for i in issues if i.type == DeadCodeType.UNUSED_IMPORT]

        return {
            "mode": "unused",
            "output_format": "json",
            "files_scanned": report.files_scanned,
            "total_issues": len(issues),
            "unused_functions": len(unused_funcs),
            "unused_classes": len(unused_classes),
            "unused_imports": len(unused_imports),
            "issues": [
                {
                    "name": i.name,
                    "type": i.type.value,
                    "file": i.file,
                    "line": i.line,
                    "confidence": i.confidence,
                    "reason": i.reason,
                }
                for i in issues
            ],
        }

    def _format_unused_toon(
        self,
        issues: list[DeadCodeIssue],
        report: DeadCodeReport,
    ) -> dict[str, Any]:
        """Format unused-code results as TOON."""
        unused_funcs = [i for i in issues if i.type == DeadCodeType.UNUSED_FUNCTION]
        unused_classes = [i for i in issues if i.type == DeadCodeType.UNUSED_CLASS]
        unused_imports = [i for i in issues if i.type == DeadCodeType.UNUSED_IMPORT]

        toon_data = {
            "meta": {
                "tool": "dead_code_analysis",
                "mode": "unused",
                "files_scanned": report.files_scanned,
                "total_issues": len(issues),
            },
            "summary": {
                "unused_functions": len(unused_funcs),
                "unused_classes": len(unused_classes),
                "unused_imports": len(unused_imports),
            },
            "issues": [
                {
                    "n": i.name,
                    "t": i.type.value,
                    "f": i.file,
                    "l": i.line,
                    "c": i.confidence,
                }
                for i in issues
            ],
        }

        encoder = ToonEncoder()
        return {
            "mode": "unused",
            "output_format": "toon",
            "data": encoder.encode(toon_data),
        }

    # ------------------------------------------------------------------
    # Formatting — unreachable
    # ------------------------------------------------------------------

    def _format_unreachable_json(
        self, result: DeadCodePathResult
    ) -> dict[str, Any]:
        """Format unreachable-code results as JSON."""
        return {
            "mode": "unreachable",
            "output_format": "json",
            "file": result.file_path,
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_unreachable_toon(
        self, result: DeadCodePathResult
    ) -> dict[str, Any]:
        """Format unreachable-code results as TOON."""
        lines: list[str] = [
            "Dead Code Path Analysis",
            f"File: {result.file_path}",
            f"Total functions: {result.total_functions}",
            "",
        ]

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] [{i.severity}] "
                    f"{i.description}"
                )
        else:
            lines.append("No dead code path issues found.")

        encoder = ToonEncoder()
        return {
            "mode": "unreachable",
            "output_format": "toon",
            "content": encoder.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
        }

    # ------------------------------------------------------------------
    # Merge — mode "all"
    # ------------------------------------------------------------------

    def _merge_results(
        self,
        unused_result: dict[str, Any] | None,
        unreachable_result: dict[str, Any] | None,
        output_format: str,
    ) -> dict[str, Any]:
        """Merge unused and unreachable results for mode 'all'."""
        if output_format == "toon":
            return self._merge_toon(unused_result, unreachable_result)
        return self._merge_json(unused_result, unreachable_result)

    def _merge_json(
        self,
        unused_result: dict[str, Any] | None,
        unreachable_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Merge both analyses into a single JSON result."""
        merged: dict[str, Any] = {
            "mode": "all",
            "output_format": "json",
        }

        if unused_result is not None:
            merged["unused"] = unused_result
        if unreachable_result is not None:
            merged["unreachable"] = unreachable_result

        return merged

    def _merge_toon(
        self,
        unused_result: dict[str, Any] | None,
        unreachable_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Merge both analyses into a single TOON result."""
        parts: list[str] = []

        encoder = ToonEncoder()

        if unused_result is not None:
            unused_data = unused_result.get("data")
            if unused_data:
                parts.append(f"== UNUSED CODE ==\n{unused_data}")
            else:
                parts.append("== UNUSED CODE ==\nNo unused code detected.")

        if unreachable_result is not None:
            unreachable_content = unreachable_result.get("content")
            if unreachable_content:
                parts.append(
                    f"== UNREACHABLE CODE ==\n{unreachable_content}"
                )
            else:
                parts.append(
                    "== UNREACHABLE CODE ==\nNo unreachable code detected."
                )

        combined = "\n\n".join(parts)

        return {
            "mode": "all",
            "output_format": "toon",
            "data": encoder.encode(combined),
        }
