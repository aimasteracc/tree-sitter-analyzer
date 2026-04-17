"""
Test generation engine for Python functions.

Extracts function information from AST and generates pytest test skeletons.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False



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
        self._language: Any = None
        self._parser: Any = None
        self._ensure_tree_sitter()

    def _ensure_tree_sitter(self) -> None:
        """Ensure tree-sitter is initialized."""
        if not TREE_SITTER_AVAILABLE:
            raise TestGenerationError("tree-sitter is not available")

        if self._language is None:
            try:
                import tree_sitter_python as tspython

                language_capsule = tspython.language()
                self._language = tree_sitter.Language(language_capsule)
            except ImportError as e:
                raise TestGenerationError("tree-sitter-python not available") from e

        if self._parser is None:
            self._parser = tree_sitter.Parser(self._language)

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
        self._ensure_tree_sitter()

        try:
            # Read and parse the file
            with open(file_path, "rb") as f:
                source_bytes = f.read()

            # Parse the source code
            tree = self._parser.parse(source_bytes)

        except Exception as e:
            raise TestGenerationError(f"Failed to parse {file_path}: {e}") from e

        functions: list[FuncInfo] = []

        # Traverse the tree to find function definitions
        def find_functions(node: Any) -> None:
            if node.type == "function_definition":
                # Extract function information
                func_info = self._extract_function_info(node, file_path)
                if func_info:
                    functions.append(func_info)

            # Recursively search children
            for child in node.children:
                find_functions(child)

        find_functions(tree.root_node)

        return functions

    def _extract_function_info(self, func_node: Any, file_path: str) -> FuncInfo | None:
        """Extract function information from a function_definition node."""
        # Check if async
        is_async = False
        for child in func_node.children:
            if child.type == "async":
                is_async = True
                break

        # Skip async functions for MVP
        if is_async:
            func_name = self._find_child_text(func_node, "identifier")
            if func_name:
                print(f"Warning: Skipping async function {func_name} (not supported in MVP)", file=sys.stderr)
            return None

        # Get function name
        func_name = self._find_child_text(func_node, "identifier")
        if not func_name:
            return None

        # Extract parameters
        params_node = None
        for child in func_node.children:
            if child.type == "parameters":
                params_node = child
                break

        parameters = self._extract_parameters(params_node) if params_node else []

        # Extract return type (look for "->" followed by type)
        return_type = None
        for i, child in enumerate(func_node.children):
            if child.type == "->":
                # Next child should be the type
                if i + 1 < len(func_node.children):
                    type_node = func_node.children[i + 1]
                    if type_node.type == "type":
                        type_text = self._find_child_text(type_node, "identifier")
                        if type_text:
                            return_type = type_text
                break

        # Get decorators
        decorators = self._extract_decorators(func_node)

        # Get source location
        line_number = func_node.start_point[0] + 1
        source_location = f"{file_path}:{line_number}"

        # Get body node
        body_node = None
        for child in func_node.children:
            if child.type == "block":
                body_node = child
                break

        # Calculate complexity
        complexity = self._calculate_complexity_from_node(body_node) if body_node else 1

        # Check for exceptions
        has_exceptions = self._has_exceptions_from_node(body_node) if body_node else False

        # Check for branches
        has_branches = self._has_branches_from_node(body_node) if body_node else False

        return FuncInfo(
            name=func_name,
            parameters=parameters,
            return_type=return_type,
            complexity=complexity,
            has_exceptions=has_exceptions,
            has_branches=has_branches,
            decorators=decorators,
            source_location=source_location,
        )

    def _find_child_text(self, node: Any, child_type: str) -> str | None:
        """Find a child node by type and return its text."""
        for child in node.children:
            if child.type == child_type:
                return cast(str, child.text.decode("utf-8"))
        return None

    def _extract_parameters(self, params_node: Any) -> list[ParamInfo]:
        """Extract parameter information from parameters node."""
        parameters: list[ParamInfo] = []

        # Find all parameter entries
        for child in params_node.children:
            if child.type == "identifier":
                # Simple parameter without type hint
                parameters.append(ParamInfo(name=child.text.decode("utf-8"), type_hint=None, has_default=False))
            elif child.type == "typed_parameter":
                # typed_parameter: identifier : type
                name = None
                type_hint = None
                for subchild in child.children:
                    if subchild.type == "identifier" and name is None:
                        name = subchild.text.decode("utf-8")
                    elif subchild.type == "type":
                        # Get the type from the type node
                        type_text = self._find_child_text(subchild, "identifier")
                        if type_text:
                            type_hint = type_text
                if name:
                    parameters.append(ParamInfo(name=name, type_hint=type_hint, has_default=False))
            elif child.type == "default_parameter":
                # default_parameter: parameter = value
                # This could be a typed_parameter or an identifier
                name = None
                type_hint = None
                for subchild in child.children:
                    if subchild.type == "identifier" and name is None:
                        name = subchild.text.decode("utf-8")
                    elif subchild.type == "typed_parameter":
                        # Extract from the typed_parameter child
                        for typed_child in subchild.children:
                            if typed_child.type == "identifier" and name is None:
                                name = typed_child.text.decode("utf-8")
                            elif typed_child.type == "type":
                                type_text = self._find_child_text(typed_child, "identifier")
                                if type_text:
                                    type_hint = type_text
                if name:
                    parameters.append(ParamInfo(name=name, type_hint=type_hint, has_default=True))

        return parameters

    def _extract_decorators(self, func_node: Any) -> list[str]:
        """Extract decorator names from function node."""
        decorators: list[str] = []

        # Check if the function has a decorated_definition parent
        # The decorator is on the decorated_definition, not the function_definition
        parent = func_node.parent
        if parent and parent.type == "decorated_definition":
            # Look for decorator children of the parent
            for child in parent.children:
                if child.type == "decorator":
                    # Get the decorator name (look for identifier child)
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            decorators.append(subchild.text.decode("utf-8"))
                        elif subchild.type == "attribute":
                            # Handle @staticmethod, @classmethod, etc.
                            for attr_child in subchild.children:
                                if attr_child.type == "identifier":
                                    decorators.append(attr_child.text.decode("utf-8"))

        return decorators

    def _calculate_complexity(self, func_item: dict[str, Any] | Any) -> int:
        """
        Calculate cyclomatic complexity for a function.

        Args:
            func_item: Function item from analysis result (dict for test compatibility)

        Returns:
            Cyclomatic complexity score
        """
        # Handle dict format for test compatibility
        if isinstance(func_item, dict):
            complexity = 1  # Base complexity
            complexity += cast(int, func_item.get("if_count", 0))
            complexity += cast(int, func_item.get("elif_count", 0))
            complexity += cast(int, func_item.get("for_count", 0))
            complexity += cast(int, func_item.get("while_count", 0))
            complexity += cast(int, func_item.get("try_count", 0))
            complexity += cast(int, func_item.get("except_count", 0))
            complexity += cast(int, func_item.get("with_count", 0))
            return complexity
        else:
            return self._calculate_complexity_from_node(func_item)

    def _calculate_complexity_from_node(self, node: Any) -> int:
        """Calculate cyclomatic complexity from a node."""
        complexity = 1  # Base complexity

        if not node:
            return complexity

        # Count branching constructs
        for child in node.children:
            if child.type in ("if_statement", "for_statement", "while_statement", "try_statement"):
                complexity += 1
            elif child.type == "elif_clause":
                complexity += 1
            elif child.type == "except_clause":
                complexity += 1
            elif child.type == "with_statement":
                complexity += 1

        return complexity

    def _has_exceptions(self, func_item: dict[str, Any] | Any) -> bool:
        """Check if function raises exceptions (dict format for test compatibility)."""
        if isinstance(func_item, dict):
            return cast(int, func_item.get("raises_count", 0)) > 0
        else:
            return self._has_exceptions_from_node(func_item)

    def _has_branches(self, func_item: dict[str, Any] | Any) -> bool:
        """Check if function has conditional branches (dict format for test compatibility)."""
        if isinstance(func_item, dict):
            return (
                cast(int, func_item.get("if_count", 0)) > 0
                or cast(int, func_item.get("elif_count", 0)) > 0
                or cast(int, func_item.get("try_count", 0)) > 0
            )
        else:
            return self._has_branches_from_node(func_item)

    def _has_exceptions_from_node(self, node: Any) -> bool:
        """Check if function raises exceptions."""
        if not node:
            return False

        # Look for raise statements using tree-sitter traversal
        def has_raise(n: Any) -> bool:
            if n.type == "raise_statement":
                return True
            for child in n.children:
                if has_raise(child):
                    return True
            return False

        return has_raise(node)

    def _has_branches_from_node(self, node: Any) -> bool:
        """Check if function has conditional branches."""
        if not node:
            return False

        # Look for if/try statements using tree-sitter traversal
        def has_branch(n: Any) -> bool:
            if n.type in ("if_statement", "try_statement"):
                return True
            for child in n.children:
                if has_branch(child):
                    return True
            return False

        return has_branch(node)


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
            elif not use_defaults:
                # Use None for edge case / non-default mode
                args.append("None")
            elif param.type_hint and "str" in param.type_hint:
                args.append('"test"')
            elif param.type_hint and "int" in param.type_hint:
                args.append("1")
            elif param.type_hint and "bool" in param.type_hint:
                args.append("True")
            else:
                args.append("None")

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
