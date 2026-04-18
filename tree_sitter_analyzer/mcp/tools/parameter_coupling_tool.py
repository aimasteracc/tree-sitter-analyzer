#!/usr/bin/env python3
"""
Parameter Coupling Tool — MCP Tool

Analyzes function parameter coupling across codebases to identify
functions with too many parameters and Data Clumps.

Supports: Python, JavaScript/TypeScript, Java, Go
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.parameter_coupling import (
    CouplingResult,
    ParameterCouplingAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ParameterCouplingTool(BaseMCPTool):
    """
    MCP tool for analyzing function parameter coupling.

    Detects functions with excessive parameters and Data Clumps
    (groups of functions sharing the same parameter sets).
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "parameter_coupling",
            "description": (
                "Analyze function parameter coupling in your codebase. "
                "\n\n"
                "Supported Languages:\n"
                "- Python: functions, methods, constructors\n"
                "- JavaScript/TypeScript: functions, methods, arrow functions\n"
                "- Java: methods, constructors\n"
                "- Go: functions, methods\n"
                "\n"
                "Detects:\n"
                "- Functions with too many parameters (>5 by default)\n"
                "- Data Clumps: groups of functions sharing the same parameters\n"
                "- Parameter type complexity\n"
                "\n"
                "WHEN TO USE:\n"
                "- To identify refactoring candidates (Extract Parameter Object)\n"
                "- Before code review to flag coupling hotspots\n"
                "- As part of architecture quality checks\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For complexity scoring (use cognitive_complexity)\n"
                "- For import analysis (use import_sanitizer)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "If provided, analyzes only this file."
                        ),
                    },
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory. "
                            "If provided without file_path, scans entire project."
                        ),
                    },
                    "max_params": {
                        "type": "integer",
                        "description": (
                            "Maximum acceptable parameter count. "
                            "Functions exceeding this are flagged. Default: 5."
                        ),
                    },
                    "min_clump_size": {
                        "type": "integer",
                        "description": (
                            "Minimum number of shared parameters to consider "
                            "a Data Clump. Default: 3."
                        ),
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default) or json",
                        "enum": ["toon", "json"],
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        project_root = arguments.get(
            "project_root", self.project_root or ""
        )
        max_params = arguments.get("max_params", 5)
        min_clump_size = arguments.get("min_clump_size", 3)
        output_format = arguments.get("format", "toon")

        if not file_path and not project_root:
            return {
                "error": "Either file_path or project_root must be provided",
                "format": output_format,
            }

        analyzer = ParameterCouplingAnalyzer(
            max_params=max_params,
            min_clump_size=min_clump_size,
        )

        if file_path:
            result = analyzer.analyze_file(file_path)
        else:
            result = analyzer.analyze_directory(project_root)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: CouplingResult) -> dict[str, Any]:
        return {
            "total_functions": result.total_functions,
            "total_parameters": result.total_parameters,
            "avg_params_per_function": result.avg_params_per_function,
            "high_param_functions": [
                {
                    "name": f.name,
                    "file": f.file_path,
                    "line": f.line_number,
                    "param_count": f.param_count,
                    "element_type": f.element_type,
                    "parameters": [
                        {
                            "name": p.name,
                            "type": p.type_annotation,
                            "default": p.default_value,
                            "variadic": p.is_variadic,
                            "optional": p.is_optional,
                        }
                        for p in f.parameters
                    ],
                }
                for f in result.high_param_functions
            ],
            "data_clumps": [
                {
                    "shared_params": sorted(c.param_names),
                    "function_count": c.function_count,
                    "similarity": round(c.similarity, 3),
                    "functions": [
                        {
                            "name": f.name,
                            "file": f.file_path,
                            "line": f.line_number,
                        }
                        for f in c.functions
                    ],
                }
                for c in result.data_clumps
            ],
            "warnings": result.get_warnings(),
        }

    def _format_toon(self, result: CouplingResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Parameter Coupling Analysis")
        lines.append(f"Total functions: {result.total_functions}")
        lines.append(f"Total parameters: {result.total_parameters}")
        lines.append(f"Avg params/function: {result.avg_params_per_function:.1f}")

        if result.high_param_functions:
            lines.append("")
            lines.append(f"High-Parameter Functions (>{5}):")
            for func in result.high_param_functions:
                lines.append(
                    f"  [{func.element_type}] {func.name} "
                    f"({Path(func.file_path).name}:{func.line_number}) "
                    f"- {func.param_count} params"
                )
                for p in func.parameters:
                    type_str = f": {p.type_annotation}" if p.type_annotation else ""
                    default_str = f" = {p.default_value}" if p.default_value else ""
                    variadic_str = "..." if p.is_variadic else ""
                    lines.append(f"    {variadic_str}{p.name}{type_str}{default_str}")

        if result.data_clumps:
            lines.append("")
            lines.append("Data Clumps:")
            for clump in result.data_clumps:
                params_str = ", ".join(sorted(clump.param_names))
                lines.append(
                    f"  [{clump.function_count} functions] "
                    f"shared: [{params_str}]"
                )
                for func in clump.functions:
                    lines.append(
                        f"    {func.name} "
                        f"({Path(func.file_path).name}:{func.line_number})"
                    )

        if not result.high_param_functions and not result.data_clumps:
            lines.append("")
            lines.append("No parameter coupling issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "total_parameters": result.total_parameters,
            "high_param_count": len(result.high_param_functions),
            "data_clump_count": len(result.data_clumps),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", "")
        if not file_path and not project_root:
            raise ValueError("Either file_path or project_root must be provided")

        return True
