#!/usr/bin/env python3
"""
Java Pattern Analysis Tool — MCP Tool

Analyzes Java-specific patterns: Lambda expressions, Stream API chains,
and Spring annotations. Uses regex-based extraction for patterns
not easily captured by tree-sitter queries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.java_patterns import (
    analyze_java_patterns,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class JavaPatternAnalysisTool(BaseMCPTool):
    """
    MCP tool for analyzing Java-specific patterns.

    Detects Lambda expressions, Stream API call chains, and Spring
    framework annotations. Provides insights into functional
    programming patterns and framework usage.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "java_patterns",
            "description": (
                "Analyze Java-specific patterns in source files. "
                "\n\n"
                "Patterns Detected:\n"
                "- Lambda Expressions: functional code blocks with method references\n"
                "- Stream API Chains: .stream().filter().map().collect() patterns\n"
                "- Spring Annotations: @Component, @Service, @Repository, @Controller, etc.\n"
                "\n"
                "WHEN TO USE:\n"
                "- Understanding functional programming adoption in Java code\n"
                "- Identifying Stream API usage patterns and potential optimizations\n"
                "- Analyzing Spring framework component structure\n"
                "- Finding lambda expressions that could be extracted to methods\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For non-Java files (use generic query tools instead)\n"
                "- For syntax error detection (use analyze_code_structure instead)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific Java file to analyze. "
                            "If provided, analyzes only this file."
                        ),
                    },
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory. "
                            "If provided without file_path, scans all Java files."
                        ),
                    },
                    "pattern_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Filter to specific pattern types. "
                            "Options: 'lambda', 'stream', 'spring'. Default: all types."
                        ),
                    },
                    "include_code_snippets": {
                        "type": "boolean",
                        "description": (
                            "Include code snippets in results. "
                            "Default: true."
                        ),
                    },
                },
                "examples": [
                    {"file_path": "src/main/java/com/example/Service.java"},
                    {"project_root": "/project", "pattern_types": ["lambda", "stream"]},
                    {"project_root": "/project", "pattern_types": ["spring"]},
                ],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path")
        if file_path is not None and not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        project_root = arguments.get("project_root")
        if project_root is not None and not isinstance(project_root, str):
            raise ValueError("project_root must be a string")

        pattern_types = arguments.get("pattern_types")
        if pattern_types is not None:
            if not isinstance(pattern_types, list):
                raise ValueError("pattern_types must be an array")
            valid_types = {"lambda", "stream", "spring"}
            for pt in pattern_types:
                if pt not in valid_types:
                    raise ValueError(
                        f"Invalid pattern type '{pt}'. Valid: {valid_types}"
                    )

        include_code_snippets = arguments.get("include_code_snippets")
        if include_code_snippets is not None and not isinstance(include_code_snippets, bool):
            raise ValueError("include_code_snippets must be a boolean")

        return True

    @handle_mcp_errors("java_patterns")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        file_path = arguments.get("file_path")
        project_root_arg = arguments.get("project_root")
        pattern_types = arguments.get("pattern_types")
        include_snippets = arguments.get("include_code_snippets", True)

        # Determine project root
        root = project_root_arg or self.project_root or str(Path.cwd())

        # Validate file path if provided
        if file_path:
            resolved = self.resolve_and_validate_file_path(file_path)
            # Use parent as project root for single file analysis
            root = str(Path(resolved).parent)
            file_path = str(Path(resolved).relative_to(root))
        else:
            root = self.resolve_and_validate_directory_path(root)

        # Helper function to read file content
        def _read_file_content(path: str) -> str:
            full_path = Path(root) / path
            try:
                return full_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return ""

        # Run analysis
        if file_path:
            content = _read_file_content(file_path)
            if not content:
                return {
                    "success": False,
                    "error": f"Could not read file: {file_path}",
                }
            result = analyze_java_patterns(content)
            lambdas = result.lambdas if self._should_include("lambda", pattern_types) else []
            streams = result.stream_chains if self._should_include("stream", pattern_types) else []
            springs = result.spring_components if self._should_include("spring", pattern_types) else []
            files_analyzed = [file_path]
        else:
            # Find all Java files
            java_files = []
            for ext in [".java"]:
                for path in Path(root).rglob(f"*{ext}"):
                    # Skip common non-source directories
                    parts = path.parts
                    skip_dirs = {
                        "node_modules", ".git", "vendor", "__pycache__",
                        "build", "dist", "target", ".venv",
                    }
                    if skip_dirs.intersection(parts):
                        continue
                    java_files.append(str(path.relative_to(root)))

            lambdas = []
            streams = []
            springs = []

            for java_file in java_files:
                content = _read_file_content(java_file)
                if content:
                    result = analyze_java_patterns(content)
                    if self._should_include("lambda", pattern_types):
                        lambdas.extend(result.lambdas)
                    if self._should_include("stream", pattern_types):
                        streams.extend(result.stream_chains)
                    if self._should_include("spring", pattern_types):
                        springs.extend(result.spring_components)

            files_analyzed = java_files

        # Format results
        response: dict[str, Any] = {
            "success": True,
            "files_analyzed": len(files_analyzed),
            "patterns": {},
        }

        if self._should_include("lambda", pattern_types):
            response["patterns"]["lambdas"] = {
                "total": len(lambdas),
                "expressions": [
                    {
                        "file": file_path if file_path else "<unknown>",
                        "line": lambda_info.line,
                        "text": lambda_info.raw if include_snippets else None,
                        "parameters": lambda_info.parameters,
                        "has_typed_params": lambda_info.has_typed_params,
                        "method_references": list(lambda_info.method_references),
                        "body_preview": (lambda_info.body[:50] + "...") if len(lambda_info.body) > 50 else lambda_info.body if include_snippets else None,
                    }
                    for lambda_info in lambdas
                ],
            }

        if self._should_include("stream", pattern_types):
            response["patterns"]["streams"] = {
                "total": len(streams),
                "chains": [
                    {
                        "file": file_path if file_path else "<unknown>",
                        "line": stream_info.line,
                        "text": stream_info.raw if include_snippets else None,
                        "operations": list(stream_info.operations),
                        "method_refs": list(stream_info.method_refs),
                        "is_terminal": stream_info.is_terminal,
                        "chain_length": len(stream_info.operations),
                    }
                    for stream_info in streams
                ],
            }

        if self._should_include("spring", pattern_types):
            response["patterns"]["spring_components"] = {
                "total": len(springs),
                "components": [
                    {
                        "file": file_path if file_path else "<unknown>",
                        "line": spring_info.line,
                        "annotation": spring_info.annotation,
                        "class_name": spring_info.class_name,
                        "is_primary": spring_info.is_primary,
                    }
                    for spring_info in springs
                ],
            }

        if response["files_analyzed"] == 0:
            response["message"] = "No Java files found to analyze."

        return response

    def _should_include(self, pattern: str, pattern_types: list[str] | None) -> bool:
        """Check if a pattern type should be included in results."""
        return pattern_types is None or pattern in pattern_types
