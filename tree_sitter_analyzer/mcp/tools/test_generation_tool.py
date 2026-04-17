#!/usr/bin/env python3
"""
Test Generation Tool — MCP Tool

Generates pytest test skeletons from Python functions:
- Extracts function information using tree-sitter
- Generates test cases (happy path, edge cases, exceptions)
- Renders pytest-compatible Python code
- Writes test files to disk with syntax validation
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...sdk import Analyzer
from ...test_gen.generator import TestGenerationEngine
from ...test_gen.renderer import render_test_file_to_path
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class TestGenerationTool(BaseMCPTool):
    """
    MCP tool for generating pytest test skeletons.

    Automatically generates test cases for Python functions including
    happy path tests, edge cases based on complexity, and exception tests.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        file_path = arguments.get("file_path")
        if not file_path:
            raise ValueError("file_path is required")

        if not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        return True

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "generate_tests",
            "description": (
                "Generate pytest test skeletons from Python functions. "
                "\n\n"
                "Features:\n"
                "- Extracts function information (name, parameters, return type, decorators)\n"
                "- Calculates cyclomatic complexity\n"
                "- Generates test cases: happy path, edge cases, exceptions\n"
                "- Renders pytest-compatible Python code\n"
                "- Handles decorators (staticmethod, classmethod, property)\n"
                "- Skips async functions (not supported in MVP)\n"
                "\n"
                "WHEN TO USE:\n"
                "- When starting to write tests for existing code\n"
                "- To get a quick test skeleton for refactoring\n"
                "- To ensure test coverage for critical functions\n"
                "- During TDD to scaffold test structure\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For non-Python files (not supported)\n"
                "- For async functions (not supported in MVP)\n"
                "- For integration tests (generates unit tests only)\n"
                "- For complex test scenarios requiring custom setup"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the Python file to generate tests for.",
                    },
                    "module_path": {
                        "type": "string",
                        "description": (
                            "Module path for import generation (e.g., 'src.auth.auth'). "
                            "If not provided, will be inferred from file path."
                        ),
                    },
                    "output_path": {
                        "type": "string",
                        "description": (
                            "Output file path for the generated tests. "
                            "If not provided, will use 'test_<filename>.py' in the same directory."
                        ),
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Project root directory. Default: current directory.",
                    },
                },
                "required": ["file_path"],
            },
        }

    @handle_mcp_errors(operation="test_generation")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the test generation tool."""
        file_path = arguments.get("file_path")
        module_path = arguments.get("module_path")
        output_path = arguments.get("output_path")
        project_root = arguments.get("project_root", ".")

        if not file_path:
            return {
                "success": False,
                "error": "file_path is required",
            }

        # Validate file exists
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path}",
            }

        if not file_path.endswith(".py"):
            return {
                "success": False,
                "error": f"Not a Python file: {file_path}",
            }

        try:
            # Initialize test generation engine
            engine = TestGenerationEngine(project_root)

            # Extract functions
            func_infos = engine.extract_functions(file_path)

            if not func_infos:
                return {
                    "success": False,
                    "error": f"No functions found in {file_path}",
                    "message": "No functions found to generate tests for",
                }

            # Generate test cases
            test_cases: dict[str, list] = {}
            total_tests = 0
            function_summaries: list[dict] = []

            for func_info in func_infos:
                cases = engine.generate_test_cases(func_info)
                test_cases[func_info.name] = cases
                total_tests += len(cases)

                function_summaries.append({
                    "name": func_info.name,
                    "parameters": len(func_info.parameters),
                    "complexity": func_info.complexity,
                    "tests_generated": len(cases),
                    "has_exceptions": func_info.has_exceptions,
                    "decorators": func_info.decorators,
                })

            # Determine output path
            if not output_path:
                output_path = f"test_{file_path_obj.stem}.py"

            # Determine module path
            if not module_path:
                module_path = engine.get_module_path(file_path)

            # Render and write test file
            render_test_file_to_path(func_infos, test_cases, module_path, output_path)

            return {
                "success": True,
                "output_file": output_path,
                "functions_analyzed": len(func_infos),
                "total_tests_generated": total_tests,
                "module_path": module_path,
                "function_summaries": function_summaries,
            }

        except Exception as e:
            logger.error(f"Test generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def get_test_examples(self) -> list[dict[str, Any]]:
        """Get test examples for the tool."""
        return [
            {
                "description": "Generate tests for a Python file",
                "input": {
                    "file_path": "mymodule.py",
                },
                "output": {
                    "success": True,
                    "output_file": "test_mymodule.py",
                    "functions_analyzed": 3,
                    "total_tests_generated": 8,
                },
            },
            {
                "description": "Generate tests with custom output path",
                "input": {
                    "file_path": "src/auth/auth.py",
                    "module_path": "src.auth.auth",
                    "output_path": "tests/test_auth.py",
                },
                "output": {
                    "success": True,
                    "output_file": "tests/test_auth.py",
                },
            },
        ]
