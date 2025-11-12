#!/usr/bin/env python3
"""
Test coverage helpers and utilities.

This module provides helper functions and fixtures for measuring and
improving test coverage across the tree-sitter-analyzer codebase.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock, AsyncMock


def create_mock_parser(language: str = "python") -> MagicMock:
    """
    Create a mock tree-sitter parser.
    
    Args:
        language: The language for the parser
        
    Returns:
        A configured MagicMock parser
        
    Example:
        >>> parser = create_mock_parser("python")
        >>> tree = parser.parse(b"def foo(): pass")
    """
    parser = MagicMock()
    parser.language = language
    
    # Mock parse method
    mock_tree = MagicMock()
    mock_root = MagicMock()
    mock_tree.root_node = mock_root
    parser.parse.return_value = mock_tree
    
    return parser


def create_mock_node(
    type: str = "function_definition",
    text: str = "def foo():\n    pass",
    start_point: tuple[int, int] = (0, 0),
    end_point: tuple[int, int] = (1, 8),
    children: Optional[List[Any]] = None,
) -> MagicMock:
    """
    Create a mock tree-sitter node.
    
    Args:
        type: Node type
        text: Node text content
        start_point: (row, column) start position
        end_point: (row, column) end position
        children: List of child nodes
        
    Returns:
        A configured MagicMock node
        
    Example:
        >>> node = create_mock_node("function_definition", "def foo(): pass")
        >>> assert node.type == "function_definition"
    """
    node = MagicMock()
    node.type = type
    node.text = text.encode() if isinstance(text, str) else text
    node.start_point = start_point
    node.end_point = end_point
    node.start_byte = 0
    node.end_byte = len(text.encode() if isinstance(text, str) else text)
    node.children = children or []
    node.child_count = len(children) if children else 0
    
    # Mock child_by_field_name
    def child_by_field_name(field_name: str) -> Optional[MagicMock]:
        if children:
            for child in children:
                if hasattr(child, 'field_name') and child.field_name == field_name:
                    return child
        return None
    
    node.child_by_field_name = child_by_field_name
    
    return node


def create_mock_query_result(
    captures: Optional[List[tuple[MagicMock, str]]] = None,
) -> List[tuple[MagicMock, str]]:
    """
    Create mock query results.
    
    Args:
        captures: List of (node, capture_name) tuples
        
    Returns:
        List of query capture tuples
        
    Example:
        >>> results = create_mock_query_result([
        ...     (create_mock_node("function_definition"), "function")
        ... ])
    """
    if captures is None:
        node = create_mock_node()
        captures = [(node, "default")]
    
    return captures


def create_mock_analysis_result(
    file_path: str = "test.py",
    language: str = "python",
    elements: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a mock analysis result.
    
    Args:
        file_path: Path to the analyzed file
        language: Detected language
        elements: Dictionary of extracted elements
        error: Error message if analysis failed
        
    Returns:
        Mock analysis result dictionary
        
    Example:
        >>> result = create_mock_analysis_result(
        ...     file_path="test.py",
        ...     elements={"functions": [{"name": "foo"}]}
        ... )
    """
    if elements is None:
        elements = {
            "functions": [],
            "classes": [],
        }
    
    result: Dict[str, Any] = {
        "file": file_path,
        "language": language,
        "elements": elements,
    }
    
    if error:
        result["error"] = error
        result["success"] = False
    else:
        result["success"] = True
    
    return result


def create_temp_code_file(
    tmp_path: Path,
    filename: str,
    content: str,
    language: str = "python",
) -> Path:
    """
    Create a temporary code file for testing.
    
    Args:
        tmp_path: pytest tmp_path fixture
        filename: Name of the file to create
        content: Code content
        language: Programming language (used for extension if not in filename)
        
    Returns:
        Path to the created file
        
    Example:
        >>> path = create_temp_code_file(tmp_path, "test.py", "def foo(): pass")
        >>> assert path.exists()
    """
    if "." not in filename:
        ext_map = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "java": ".java",
            "html": ".html",
            "css": ".css",
        }
        filename = filename + ext_map.get(language, ".txt")
    
    file_path = tmp_path / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


def create_async_mock_tool(return_value: Any = None) -> AsyncMock:
    """
    Create an async mock MCP tool.
    
    Args:
        return_value: Value to return from execute()
        
    Returns:
        Configured AsyncMock tool
        
    Example:
        >>> tool = create_async_mock_tool({"result": "success"})
        >>> result = await tool.execute({})
        >>> assert result == {"result": "success"}
    """
    tool = AsyncMock()
    tool.execute = AsyncMock(return_value=return_value or {})
    return tool


def assert_coverage_improved(
    before_coverage: float,
    after_coverage: float,
    min_improvement: float = 5.0,
) -> None:
    """
    Assert that coverage has improved by at least the minimum amount.
    
    Args:
        before_coverage: Coverage percentage before changes
        after_coverage: Coverage percentage after changes
        min_improvement: Minimum improvement percentage
        
    Raises:
        AssertionError: If coverage didn't improve enough
        
    Example:
        >>> assert_coverage_improved(60.0, 85.0, min_improvement=20.0)
    """
    improvement = after_coverage - before_coverage
    assert improvement >= min_improvement, (
        f"Coverage improvement of {improvement:.2f}% "
        f"is less than required {min_improvement:.2f}%"
    )


def assert_coverage_threshold(
    coverage: float,
    threshold: float = 80.0,
    module_name: str = "module",
) -> None:
    """
    Assert that coverage meets or exceeds the threshold.
    
    Args:
        coverage: Current coverage percentage
        threshold: Required coverage threshold
        module_name: Name of the module being tested
        
    Raises:
        AssertionError: If coverage is below threshold
        
    Example:
        >>> assert_coverage_threshold(85.0, 80.0, "my_module")
    """
    assert coverage >= threshold, (
        f"Coverage for {module_name} ({coverage:.2f}%) "
        f"is below threshold ({threshold:.2f}%)"
    )


def get_uncovered_lines_info(coverage_data: Dict[str, Any]) -> str:
    """
    Extract and format information about uncovered lines.
    
    Args:
        coverage_data: Coverage data dictionary
        
    Returns:
        Formatted string describing uncovered lines
        
    Example:
        >>> info = get_uncovered_lines_info({"missing_lines": [10, 11, 12]})
    """
    if not coverage_data:
        return "No coverage data available"
    
    missing_lines = coverage_data.get("missing_lines", [])
    if not missing_lines:
        return "All lines covered!"
    
    return f"Uncovered lines: {', '.join(map(str, missing_lines))}"


# Export all helpers
__all__ = [
    "create_mock_parser",
    "create_mock_node",
    "create_mock_query_result",
    "create_mock_analysis_result",
    "create_temp_code_file",
    "create_async_mock_tool",
    "assert_coverage_improved",
    "assert_coverage_threshold",
    "get_uncovered_lines_info",
]
