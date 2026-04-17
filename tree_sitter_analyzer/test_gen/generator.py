"""
Test generation engine for Python functions.

Extracts function information from AST and generates pytest test skeletons.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
from tree_sitter_analyzer.core.request import AnalysisRequest


@dataclass
class ParamInfo:
    """Function parameter information."""

    name: str
    type_hint: str | None
    has_default: bool


@dataclass
class FuncInfo:
    """Extracted function information from AST."""

    name: str
    parameters: list[ParamInfo]
    return_type: str | None
    complexity: int  # Cyclomatic complexity
    has_exceptions: bool
    has_branches: bool
    decorators: list[str]
    source_location: str  # file:line


@dataclass
class TestCase:
    """Generated test case."""

    test_name: str
    setup: str  # Test setup code
    call: str  # Function call with args
    assertions: list[str]  # Assertion statements
    comment: str  # What this test validates


class TestGenerationError(Exception):
    """Raised when test generation fails."""


class TestGenerationEngine:
    """
    Generates pytest test skeletons from Python functions.

    Features:
    - Extracts function information from AST
    - Calculates cyclomatic complexity
    - Generates test cases (happy path, edge cases, exceptions)
    - Handles decorators (with warnings for non-testable ones)
    """

    def __init__(self, repo_path: str | Path) -> None:
        """
        Initialize test generation engine.

        Args:
            repo_path: Path to the repository (for resolving imports)
        """
        self.repo_path = Path(repo_path).resolve()
        self.analysis_engine = get_analysis_engine(str(self.repo_path))

    def extract_functions(self, file_path: str) -> list[FuncInfo]:
        """
        Extract function information from a Python file.

        Args:
            file_path: Path to the Python file

        Returns:
            List of FuncInfo objects

        Raises:
            TestGenerationError: If parsing fails
        """
        try:
            # Create analysis request
            request = AnalysisRequest(
                file_path=file_path,
                repo_path=str(self.repo_path),
                element_types=["function"],
            )

            # Analyze the file
            result = self.analysis_engine.analyze_file(file_path, request)

        except Exception as e:
            raise TestGenerationError(f"Failed to parse {file_path}: {e}") from e

        functions: list[FuncInfo] = []

        # Extract function definitions from result
        if hasattr(result, "functions"):
            function_list = result.functions
        elif isinstance(result, dict):
            function_list = result.get("functions", [])
        elif isinstance(result, list):
            function_list = result
        else:
            function_list = []

        for item in function_list:
            # Handle both dict and object representations
            if hasattr(item, "__dict__"):
                func_name = getattr(item, "name", "")
                is_async = getattr(item, "is_async", False) or getattr(item, "is_async_def", False)
                line_number = getattr(item, "line_number", getattr(item, "start_line", 0))
                return_type = getattr(item, "return_type", None)
                decorators = getattr(item, "decorators", [])
                params = getattr(item, "parameters", [])
            else:
                func_name = item.get("name", "")
                is_async = item.get("is_async", item.get("is_async_def", False))
                line_number = item.get("line_number", item.get("start_line", 0))
                return_type = item.get("return_type")
                decorators = item.get("decorators", [])
                params = item.get("parameters", [])

            if not func_name:
                continue

            # Skip async functions for MVP
            if is_async:
                print(f"Warning: Skipping async function {func_name} (not supported in MVP)", file=sys.stderr)
                continue

            # Extract parameters
            parameters: list[ParamInfo] = []
            for param in params:
                if hasattr(param, "__dict__"):
                    param_info = ParamInfo(
                        name=getattr(param, "name", ""),
                        type_hint=getattr(param, "type_hint", None),
                        has_default=getattr(param, "has_default", False),
                    )
                else:
                    param_info = ParamInfo(
                        name=param.get("name", ""),
                        type_hint=param.get("type_hint"),
                        has_default=param.get("has_default", False),
                    )
                parameters.append(param_info)

            # Calculate cyclomatic complexity
            complexity = self._calculate_complexity(item)

            # Check for exceptions
            has_exceptions = self._has_exceptions(item)

            # Check for branches
            has_branches = self._has_branches(item)

            # Source location
            source_location = f"{file_path}:{line_number}"

            func_info = FuncInfo(
                name=func_name,
                parameters=parameters,
                return_type=return_type,
                complexity=complexity,
                has_exceptions=has_exceptions,
                has_branches=has_branches,
                decorators=decorators if isinstance(decorators, list) else [],
                source_location=source_location,
            )
            functions.append(func_info)

        return functions

    def _calculate_complexity(self, func_item: dict[str, Any] | Any) -> int:
        """
        Calculate cyclomatic complexity for a function.

        Args:
            func_item: Function item from analysis result

        Returns:
            Cyclomatic complexity score
        """
        complexity = 1  # Base complexity

        # Handle both dict and object representations
        if hasattr(func_item, "__dict__"):
            complexity += getattr(func_item, "if_count", 0)
            complexity += getattr(func_item, "elif_count", 0)
            complexity += getattr(func_item, "for_count", 0)
            complexity += getattr(func_item, "while_count", 0)
            complexity += getattr(func_item, "try_count", 0)
            complexity += getattr(func_item, "except_count", 0)
            complexity += getattr(func_item, "with_count", 0)
        else:
            complexity += func_item.get("if_count", 0)
            complexity += func_item.get("elif_count", 0)
            complexity += func_item.get("for_count", 0)
            complexity += func_item.get("while_count", 0)
            complexity += func_item.get("try_count", 0)
            complexity += func_item.get("except_count", 0)
            complexity += func_item.get("with_count", 0)

        return complexity

    def _has_exceptions(self, func_item: dict[str, Any] | Any) -> bool:
        """Check if function raises exceptions."""
        if hasattr(func_item, "__dict__"):
            return getattr(func_item, "raises_count", 0) > 0
        return func_item.get("raises_count", 0) > 0

    def _has_branches(self, func_item: dict[str, Any] | Any) -> bool:
        """Check if function has conditional branches."""
        if hasattr(func_item, "__dict__"):
            return (
                getattr(func_item, "if_count", 0) > 0
                or getattr(func_item, "elif_count", 0) > 0
                or getattr(func_item, "try_count", 0) > 0
            )
        return (
            func_item.get("if_count", 0) > 0
            or func_item.get("elif_count", 0) > 0
            or func_item.get("try_count", 0) > 0
        )

    def generate_test_cases(self, func_info: FuncInfo) -> list[TestCase]:
        """
        Generate test cases for a function.

        Args:
            func_info: Function information

        Returns:
            List of TestCase objects
        """
        test_cases: list[TestCase] = []

        # 1. Happy path test
        test_cases.append(self._generate_happy_path(func_info))

        # 2. Edge case tests (based on complexity)
        num_edge_cases = min(func_info.complexity, 5)
        for i in range(num_edge_cases):
            test_cases.append(self._generate_edge_case(func_info, i))

        # 3. Exception tests (if function raises exceptions)
        if func_info.has_exceptions:
            test_cases.append(self._generate_exception_test(func_info))

        return test_cases

    def _generate_happy_path(self, func_info: FuncInfo) -> TestCase:
        """Generate happy path test case."""
        test_name = f"test_{func_info.name}_success"
        call = self._generate_function_call(func_info, use_defaults=True)

        # Generate placeholder assertion based on return type
        return_type = func_info.return_type
        if return_type == "bool":
            assertion = "assert isinstance(result, bool)"
        elif return_type in ("int", "float"):
            assertion = "assert isinstance(result, (int, float))"
        elif return_type and return_type != "None":
            assertion = f"assert isinstance(result, {return_type})"
        else:
            assertion = "assert result is not None"

        return TestCase(
            test_name=test_name,
            setup="",
            call=call,
            assertions=[assertion],
            comment=f"Test {func_info.name} with valid inputs",
        )

    def _generate_edge_case(self, func_info: FuncInfo, index: int) -> TestCase:
        """Generate edge case test."""
        edge_type = self._get_edge_case_type(func_info, index)
        test_name = f"test_{func_info.name}_{edge_type['name']}"
        call = self._generate_function_call(func_info, edge_case=edge_type)

        assertion = self._generate_edge_assertion(func_info, edge_type)

        return TestCase(
            test_name=test_name,
            setup="",
            call=call,
            assertions=[assertion],
            comment=f"Test {func_info.name} with {edge_type['description']}",
        )

    def _generate_exception_test(self, func_info: FuncInfo) -> TestCase:
        """Generate exception test case."""
        test_name = f"test_{func_info.name}_raises_exception"

        # Use a value that's likely to raise an exception
        call = self._generate_function_call(func_info, use_defaults=False)

        return TestCase(
            test_name=test_name,
            setup="",
            call=f"with pytest.raises(Exception):\n    {call}",
            assertions=[],
            comment=f"Test {func_info.name} raises exception on invalid input",
        )

    def _generate_function_call(
        self,
        func_info: FuncInfo,
        use_defaults: bool = True,
        edge_case: dict[str, Any] | None = None,
    ) -> str:
        """Generate a function call with arguments."""
        args: list[str] = []

        for param in func_info.parameters:
            if edge_case and edge_case.get("param_name") == param.name:
                args.append(edge_case["value"])
            elif param.has_default and not use_defaults:
                # Use explicit None for edge case
                args.append("None")
            elif param.type_hint and "str" in param.type_hint:
                args.append('""' if edge_case else '"test"')
            elif param.type_hint and "int" in param.type_hint:
                args.append("0" if edge_case else "1")
            elif param.type_hint and "bool" in param.type_hint:
                args.append("False" if edge_case else "True")
            else:
                args.append("None" if edge_case else "None")

        args_str = ", ".join(args)
        return f"result = {func_info.name}({args_str})"

    def _get_edge_case_type(self, func_info: FuncInfo, index: int) -> dict[str, Any]:
        """Get edge case type for a given index."""
        edge_cases = [
            {"name": "none_input", "description": "None input", "value": "None"},
            {"name": "empty_string", "description": "empty string", "value": '""'},
            {"name": "zero_value", "description": "zero value", "value": "0"},
            {"name": "negative_value", "description": "negative value", "value": "-1"},
            {"name": "max_value", "description": "maximum value", "value": "999999"},
        ]

        # Find first applicable edge case
        for i, case in enumerate(edge_cases):
            if i == index:
                # Determine which parameter to apply edge case to
                if func_info.parameters:
                    param = func_info.parameters[0]  # Apply to first param
                    return {"param_name": param.name, **case}

        return edge_cases[0]

    def _generate_edge_assertion(self, func_info: FuncInfo, edge_case: dict[str, Any]) -> str:
        """Generate assertion for edge case."""
        edge_type = edge_case["name"]

        if edge_type == "none_input":
            if func_info.return_type == "bool":
                return "assert isinstance(result, bool)  # TODO: set expected value"
            return "assert result is not None  # TODO: set expected value"
        else:
            return "assert isinstance(result, (int, float, str, bool))  # TODO: set expected value"

    def get_module_path(self, file_path: str) -> str:
        """
        Get module path for import generation.

        Args:
            file_path: Path to the Python file

        Returns:
            Module path (e.g., "src.auth.auth")
        """
        file_path_obj = Path(file_path).resolve()

        try:
            relative_path = file_path_obj.relative_to(self.repo_path)
        except ValueError:
            # File is outside repo_path, use absolute path
            return file_path_obj.stem

        # Remove .py extension and convert to module path
        module_parts = list(relative_path.parts[:-1])  # Remove filename
        if relative_path.stem != "__init__":
            module_parts.append(relative_path.stem)

        return ".".join(module_parts) if module_parts else relative_path.stem
