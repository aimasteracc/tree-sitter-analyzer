#!/usr/bin/env python3
"""
Custom assertion helpers for testing.

This module provides specialized assertion functions for validating
complex data structures and behaviors in the tree-sitter-analyzer project.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


def assert_has_keys(
    data: Dict[str, Any],
    required_keys: List[str],
    optional_keys: Optional[List[str]] = None,
) -> None:
    """
    Assert that dictionary has required keys and only allowed keys.
    
    Args:
        data: Dictionary to check
        required_keys: Keys that must be present
        optional_keys: Keys that may be present
        
    Raises:
        AssertionError: If required keys are missing or unexpected keys present
        
    Example:
        >>> assert_has_keys({"name": "foo", "type": "function"}, ["name", "type"])
    """
    if optional_keys is None:
        optional_keys = []
    
    # Check required keys
    missing_keys = set(required_keys) - set(data.keys())
    assert not missing_keys, f"Missing required keys: {missing_keys}"
    
    # Check for unexpected keys
    allowed_keys = set(required_keys + optional_keys)
    unexpected_keys = set(data.keys()) - allowed_keys
    assert not unexpected_keys, f"Unexpected keys: {unexpected_keys}"


def assert_dict_structure(
    data: Dict[str, Any],
    expected_structure: Dict[str, type],
) -> None:
    """
    Assert that dictionary has expected structure with correct types.
    
    Args:
        data: Dictionary to check
        expected_structure: Expected keys and their types
        
    Raises:
        AssertionError: If structure doesn't match
        
    Example:
        >>> assert_dict_structure(
        ...     {"name": "foo", "count": 5},
        ...     {"name": str, "count": int}
        ... )
    """
    for key, expected_type in expected_structure.items():
        assert key in data, f"Missing key: {key}"
        assert isinstance(data[key], expected_type), (
            f"Key '{key}' has type {type(data[key]).__name__}, "
            f"expected {expected_type.__name__}"
        )


def assert_analysis_result_valid(
    result: Dict[str, Any],
    expected_language: Optional[str] = None,
    expected_file: Optional[str] = None,
    require_success: bool = True,
) -> None:
    """
    Assert that analysis result has valid structure.
    
    Args:
        result: Analysis result dictionary
        expected_language: Expected language (if known)
        expected_file: Expected file path (if known)
        require_success: Whether to require success=True
        
    Raises:
        AssertionError: If result is invalid
        
    Example:
        >>> assert_analysis_result_valid(
        ...     {"file": "test.py", "language": "python", "elements": {}},
        ...     expected_language="python"
        ... )
    """
    # Check basic structure
    assert_has_keys(result, ["file", "language"], ["elements", "error", "success"])
    
    # Check specific values if provided
    if expected_language:
        assert result["language"] == expected_language, (
            f"Expected language '{expected_language}', "
            f"got '{result['language']}'"
        )
    
    if expected_file:
        assert result["file"] == expected_file, (
            f"Expected file '{expected_file}', "
            f"got '{result['file']}'"
        )
    
    # Check success status
    if require_success:
        assert result.get("success", True) is True, (
            f"Analysis failed: {result.get('error', 'Unknown error')}"
        )


def assert_element_has_required_fields(
    element: Dict[str, Any],
    element_type: str,
) -> None:
    """
    Assert that extracted element has required fields.
    
    Args:
        element: Element dictionary
        element_type: Type of element (function, class, etc.)
        
    Raises:
        AssertionError: If required fields are missing
        
    Example:
        >>> assert_element_has_required_fields(
        ...     {"name": "foo", "line": 1, "type": "function"},
        ...     "function"
        ... )
    """
    common_fields = ["name", "line"]
    
    # Type-specific required fields
    type_fields: Dict[str, List[str]] = {
        "function": ["parameters"],
        "class": ["methods"],
        "method": ["parameters"],
        "import": ["module"],
    }
    
    required_fields = common_fields + type_fields.get(element_type, [])
    
    for field in common_fields:
        assert field in element, f"Element missing required field: {field}"


def assert_list_contains_dicts_with_key(
    items: List[Dict[str, Any]],
    key: str,
    expected_values: Optional[Set[Any]] = None,
) -> None:
    """
    Assert that list contains dictionaries with specified key.
    
    Args:
        items: List of dictionaries
        key: Key that must be present in each dictionary
        expected_values: Optional set of expected values for the key
        
    Raises:
        AssertionError: If key is missing or values don't match
        
    Example:
        >>> assert_list_contains_dicts_with_key(
        ...     [{"name": "foo"}, {"name": "bar"}],
        ...     "name",
        ...     {"foo", "bar"}
        ... )
    """
    assert len(items) > 0, "List is empty"
    
    for i, item in enumerate(items):
        assert isinstance(item, dict), f"Item {i} is not a dictionary"
        assert key in item, f"Item {i} missing key '{key}'"
    
    if expected_values is not None:
        actual_values = {item[key] for item in items}
        assert actual_values == expected_values, (
            f"Values don't match. Expected: {expected_values}, "
            f"Got: {actual_values}"
        )


def assert_query_result_valid(
    result: List[Dict[str, Any]],
    min_matches: int = 0,
    max_matches: Optional[int] = None,
    require_node: bool = True,
    require_text: bool = True,
) -> None:
    """
    Assert that query result has valid structure.
    
    Args:
        result: Query result list
        min_matches: Minimum number of matches required
        max_matches: Maximum number of matches allowed
        require_node: Whether to require 'node' field
        require_text: Whether to require 'text' field
        
    Raises:
        AssertionError: If result is invalid
        
    Example:
        >>> assert_query_result_valid(
        ...     [{"node": mock_node, "text": "foo", "line": 1}],
        ...     min_matches=1
        ... )
    """
    assert isinstance(result, list), "Result must be a list"
    assert len(result) >= min_matches, (
        f"Expected at least {min_matches} matches, got {len(result)}"
    )
    
    if max_matches is not None:
        assert len(result) <= max_matches, (
            f"Expected at most {max_matches} matches, got {len(result)}"
        )
    
    # Check structure of each match
    for i, match in enumerate(result):
        assert isinstance(match, dict), f"Match {i} is not a dictionary"
        
        if require_node:
            assert "node" in match, f"Match {i} missing 'node' field"
        
        if require_text:
            assert "text" in match, f"Match {i} missing 'text' field"


def assert_file_output_valid(
    output: Dict[str, Any],
    expected_format: Optional[str] = None,
) -> None:
    """
    Assert that file output has valid structure.
    
    Args:
        output: File output dictionary
        expected_format: Expected output format
        
    Raises:
        AssertionError: If output is invalid
        
    Example:
        >>> assert_file_output_valid(
        ...     {"format": "json", "content": "{}", "success": True},
        ...     expected_format="json"
        ... )
    """
    assert_has_keys(output, ["format", "content"], ["success", "error", "path"])
    
    if expected_format:
        assert output["format"] == expected_format, (
            f"Expected format '{expected_format}', "
            f"got '{output['format']}'"
        )
    
    # Content should not be empty
    assert output["content"], "Output content is empty"


def assert_no_duplicate_elements(
    elements: List[Dict[str, Any]],
    key: str = "name",
) -> None:
    """
    Assert that list has no duplicate elements based on key.
    
    Args:
        elements: List of element dictionaries
        key: Key to check for duplicates
        
    Raises:
        AssertionError: If duplicates are found
        
    Example:
        >>> assert_no_duplicate_elements(
        ...     [{"name": "foo"}, {"name": "bar"}],
        ...     key="name"
        ... )
    """
    values = [elem[key] for elem in elements if key in elem]
    duplicates = [val for val in set(values) if values.count(val) > 1]
    
    assert not duplicates, f"Found duplicate values for key '{key}': {duplicates}"


def assert_error_message_contains(
    error_msg: str,
    expected_substrings: List[str],
) -> None:
    """
    Assert that error message contains expected substrings.
    
    Args:
        error_msg: Error message to check
        expected_substrings: Substrings that should be present
        
    Raises:
        AssertionError: If any substring is missing
        
    Example:
        >>> assert_error_message_contains(
        ...     "File not found: test.py",
        ...     ["File", "not found", "test.py"]
        ... )
    """
    for substring in expected_substrings:
        assert substring in error_msg, (
            f"Error message missing expected substring '{substring}'. "
            f"Got: {error_msg}"
        )


def assert_performance_acceptable(
    elapsed_time: float,
    max_time: float,
    operation: str = "operation",
) -> None:
    """
    Assert that operation completed within acceptable time.
    
    Args:
        elapsed_time: Time taken in seconds
        max_time: Maximum acceptable time in seconds
        operation: Description of operation
        
    Raises:
        AssertionError: If operation took too long
        
    Example:
        >>> assert_performance_acceptable(0.5, 1.0, "file analysis")
    """
    assert elapsed_time <= max_time, (
        f"{operation} took {elapsed_time:.2f}s, "
        f"expected <= {max_time:.2f}s"
    )


# Export all helpers
__all__ = [
    "assert_has_keys",
    "assert_dict_structure",
    "assert_analysis_result_valid",
    "assert_element_has_required_fields",
    "assert_list_contains_dicts_with_key",
    "assert_query_result_valid",
    "assert_file_output_valid",
    "assert_no_duplicate_elements",
    "assert_error_message_contains",
    "assert_performance_acceptable",
]
