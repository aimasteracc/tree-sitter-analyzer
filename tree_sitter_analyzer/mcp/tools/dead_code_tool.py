#!/usr/bin/env python3
"""
Dead Code Analysis MCP Tool — Transitive dead code, unused imports, unreferenced variables.

Modes:
- **all**: Full analysis (dead functions + unused imports + unreferenced variables)
- **dead_functions**: Transitive dead code detection via call graph flood-fill
- **unused_imports**: Import statements never referenced in their file
- **variables**: File-level variables not referenced by any function

CodeGraph parity: equivalent to CodeGraph's dead code intelligence,
but extends it with transitive analysis and unused import detection.
"""

from typing import Any

from ...dead_code_analyzer import (
    DeadFunction,
    UnreferencedVariable,
    UnusedImport,
    analyze_dead_code,
)
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphDeadCodeTool(BaseMCPTool):
    """MCP Tool for comprehensive dead code analysis (CodeGraph parity)."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_dead_code",
            "description": (
                "Dead code analysis: transitive dead functions, unused imports, "
                "and unreferenced variables. Extends basic orphan detection with "
                "flood-fill from entry points to find entire dead call chains. "
                "No other built-in tool provides transitive dead code analysis."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["all", "dead_functions", "unused_imports", "variables"],
                    "description": (
                        "Analysis mode: 'all' (default) for full analysis, "
                        "'dead_functions' for transitive dead code, "
                        "'unused_imports' for unused import detection, "
                        "'variables' for unreferenced variable detection."
                    ),
                    "default": "all",
                },
                "include_test_files": {
                    "type": "boolean",
                    "description": "Include test files in analysis (default: false)",
                    "default": False,
                },
                "max_dead": {
                    "type": "integer",
                    "description": "Max dead function candidates to return (default: 50)",
                    "default": 50,
                },
                "max_imports": {
                    "type": "integer",
                    "description": "Max unused import results (default: 50)",
                    "default": 50,
                },
                "max_variables": {
                    "type": "integer",
                    "description": "Max unreferenced variable results (default: 50)",
                    "default": 50,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format (default: toon)",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "all")
        if mode not in ("all", "dead_functions", "unused_imports", "variables"):
            raise ValueError(f"Invalid mode: {mode}")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        if not self.project_root:
            return {
                "success": False,
                "error": "Project root not set. Call set_project_path first.",
            }

        mode = arguments.get("mode", "all")
        include_tests = arguments.get("include_test_files", False)
        max_dead = arguments.get("max_dead", 50)
        max_imports = arguments.get("max_imports", 50)
        max_variables = arguments.get("max_variables", 50)
        output_format = arguments.get("output_format", "toon")

        try:
            result = analyze_dead_code(
                self.project_root,
                include_test_files=include_tests,
                include_unused_imports=mode in ("all", "unused_imports"),
                include_variables=mode in ("all", "variables"),
            )
        except Exception as exc:
            logger.error(f"Dead code analysis failed: {exc}")
            return {
                "success": False,
                "error": f"Analysis failed: {exc}",
            }

        dead_funcs = result.dead_functions[:max_dead]
        unused_imports = result.unused_imports[:max_imports]
        unref_vars = result.unreferenced_variables[:max_variables]

        total_issues = len(dead_funcs) + len(unused_imports) + len(unref_vars)

        if total_issues == 0:
            verdict = "INFO"
        elif total_issues > 20:
            verdict = "REVIEW"
        else:
            verdict = "CAUTION"

        response: dict[str, Any] = {
            "success": True,
            "verdict": verdict,
            "mode": mode,
            "project_root": self.project_root,
            "stats": result.stats,
            "dead_functions": [
                _serialize_dead_function(df) for df in dead_funcs
            ],
            "unused_imports": [
                _serialize_unused_import(ui) for ui in unused_imports
            ],
            "unreferenced_variables": [
                _serialize_unref_var(uv) for uv in unref_vars
            ],
        }

        if mode != "all":
            sections_to_keep = {
                "dead_functions": ["dead_functions"],
                "unused_imports": ["unused_imports"],
                "variables": ["unreferenced_variables"],
            }
            keep = sections_to_keep.get(mode, [])
            for key in ("dead_functions", "unused_imports", "unreferenced_variables"):
                if key not in keep:
                    response.pop(key, None)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)


def _serialize_dead_function(df: DeadFunction) -> dict[str, Any]:
    return {
        "name": df.function.name,
        "file": df.function.file_path,
        "line": df.function.start_line,
        "end_line": df.function.end_line,
        "language": df.function.language,
        "reason": df.reason,
        "dead_callee_count": len(df.dead_callees),
        "dead_callees": df.dead_callees[:10],
    }


def _serialize_unused_import(ui: UnusedImport) -> dict[str, Any]:
    return {
        "file": ui.file,
        "line": ui.line,
        "import_text": ui.import_text,
        "unused_names": ui.unused_names,
    }


def _serialize_unref_var(uv: UnreferencedVariable) -> dict[str, Any]:
    return {
        "file": uv.file,
        "name": uv.name,
        "line": uv.line,
        "language": uv.language,
    }
