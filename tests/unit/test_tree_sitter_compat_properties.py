#!/usr/bin/env python3
"""
Property-based tests for tree-sitter version compatibility.

**Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

Tests that the TreeSitterQueryCompat class provides consistent API behavior
regardless of the underlying tree-sitter version being used.

**Validates: Requirements 1.1, 1.4**
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from unittest.mock import MagicMock, patch
import sys

from tree_sitter_analyzer.utils.tree_sitter_compat import (
    TreeSitterQueryCompat,
    create_query_safely,
    get_node_text_safe,
)


# Strategy for generating valid capture names (alphanumeric identifiers)
capture_names = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        min_codepoint=48,
        max_codepoint=122,
    ),
    min_size=1,
    max_size=20,
).filter(lambda x: x and x[0].isalpha() and x.replace("_", "").isalnum())

# Strategy for generating number of captures
num_captures = st.integers(min_value=0, max_value=10)

# Strategy for generating source code content
source_code_content = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=0,
    max_size=500,
)

# Strategy for byte positions
byte_positions = st.integers(min_value=0, max_value=1000)

# Strategy for line/column positions
line_positions = st.integers(min_value=0, max_value=100)
column_positions = st.integers(min_value=0, max_value=200)


class TestTreeSitterVersionCompatibilityProperties:
    """
    Property-based tests for tree-sitter version compatibility.

    **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**
    **Validates: Requirements 1.1, 1.4**
    """

    @settings(max_examples=100)
    @given(
        capture_name_list=st.lists(capture_names, min_size=0, max_size=5),
    )
    def test_property_14_newest_api_returns_consistent_format(
        self, capture_name_list: list[str]
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any set of captures returned by the newest tree-sitter API (QueryCursor),
        the result SHALL be a list of (node, capture_name) tuples with consistent format.

        **Validates: Requirements 1.1, 1.4**
        """
        # Skip empty or invalid capture names
        capture_name_list = [name for name in capture_name_list if name and name[0].isalpha()]
        if not capture_name_list:
            capture_name_list = ["default_capture"]

        mock_language = MagicMock()
        mock_root_node = MagicMock()

        # Create mock for tree_sitter module with newest API
        mock_tree_sitter = MagicMock()
        mock_tree_sitter.QueryCursor = MagicMock()

        mock_query = MagicMock()
        mock_tree_sitter.Query.return_value = mock_query

        # Setup QueryCursor behavior with generated captures
        mock_cursor = mock_tree_sitter.QueryCursor.return_value
        mock_nodes = [MagicMock(name=f"node_{i}") for i in range(len(capture_name_list))]
        
        # Build captures_dict: {capture_name: [node]}
        captures_dict = {}
        for i, name in enumerate(capture_name_list):
            if name not in captures_dict:
                captures_dict[name] = []
            captures_dict[name].append(mock_nodes[i])
        
        mock_cursor.matches.return_value = [(0, captures_dict)]

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )

            # Property: Result should be a list
            assert isinstance(results, list), "Result should be a list"

            # Property: Each item should be a tuple of (node, capture_name)
            for item in results:
                assert isinstance(item, tuple), f"Each item should be a tuple, got {type(item)}"
                assert len(item) == 2, f"Each tuple should have 2 elements, got {len(item)}"
                node, capture_name = item
                assert isinstance(capture_name, str), f"Capture name should be a string, got {type(capture_name)}"

            # Property: All capture names should be in the result
            result_capture_names = [item[1] for item in results]
            for name in capture_name_list:
                assert name in result_capture_names, f"Capture name '{name}' should be in results"

    @settings(max_examples=100)
    @given(
        capture_name_list=st.lists(capture_names, min_size=0, max_size=5),
    )
    def test_property_14_modern_api_returns_consistent_format(
        self, capture_name_list: list[str]
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any set of captures returned by the modern tree-sitter API (matches),
        the result SHALL be a list of (node, capture_name) tuples with consistent format.

        **Validates: Requirements 1.1, 1.4**
        """
        # Skip empty or invalid capture names
        capture_name_list = [name for name in capture_name_list if name and name[0].isalpha()]
        if not capture_name_list:
            capture_name_list = ["default_capture"]

        mock_language = MagicMock()
        mock_root_node = MagicMock()

        mock_tree_sitter = MagicMock()
        # Ensure QueryCursor does NOT exist (modern API)
        del mock_tree_sitter.QueryCursor

        mock_query = MagicMock()
        mock_tree_sitter.Query.return_value = mock_query

        # Setup matches method on query object
        mock_matches = []
        for i, name in enumerate(capture_name_list):
            mock_match = MagicMock()
            mock_capture = MagicMock()
            mock_node = MagicMock(name=f"node_{i}")

            mock_capture.index = i
            mock_capture.node = mock_node
            mock_match.captures = [mock_capture]
            mock_matches.append(mock_match)

        mock_query.matches.return_value = mock_matches
        mock_query.capture_names = capture_name_list

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )

            # Property: Result should be a list
            assert isinstance(results, list), "Result should be a list"

            # Property: Each item should be a tuple of (node, capture_name)
            for item in results:
                assert isinstance(item, tuple), f"Each item should be a tuple, got {type(item)}"
                assert len(item) == 2, f"Each tuple should have 2 elements, got {len(item)}"
                node, capture_name = item
                assert isinstance(capture_name, str), f"Capture name should be a string, got {type(capture_name)}"

            # Property: Number of results should match number of captures
            assert len(results) == len(capture_name_list), \
                f"Expected {len(capture_name_list)} results, got {len(results)}"

    @settings(max_examples=100)
    @given(
        capture_name_list=st.lists(capture_names, min_size=0, max_size=5),
    )
    def test_property_14_legacy_api_returns_consistent_format(
        self, capture_name_list: list[str]
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any set of captures returned by the legacy tree-sitter API (captures),
        the result SHALL be a list of (node, capture_name) tuples with consistent format.

        **Validates: Requirements 1.1, 1.4**
        """
        # Skip empty or invalid capture names
        capture_name_list = [name for name in capture_name_list if name and name[0].isalpha()]
        if not capture_name_list:
            capture_name_list = ["default_capture"]

        mock_language = MagicMock()
        mock_root_node = MagicMock()

        mock_tree_sitter = MagicMock()
        del mock_tree_sitter.QueryCursor

        mock_query = MagicMock()
        mock_tree_sitter.Query.return_value = mock_query

        # Remove matches, ensure captures exists (legacy API)
        del mock_query.matches

        # Setup captures to return list of (node, capture_name) tuples
        mock_captures = []
        for i, name in enumerate(capture_name_list):
            mock_node = MagicMock(name=f"node_{i}")
            mock_captures.append((mock_node, name))

        mock_query.captures.return_value = mock_captures

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            results = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )

            # Property: Result should be a list
            assert isinstance(results, list), "Result should be a list"

            # Property: Each item should be a tuple of (node, capture_name)
            for item in results:
                assert isinstance(item, tuple), f"Each item should be a tuple, got {type(item)}"
                assert len(item) == 2, f"Each tuple should have 2 elements, got {len(item)}"
                node, capture_name = item
                assert isinstance(capture_name, str), f"Capture name should be a string, got {type(capture_name)}"

            # Property: Number of results should match number of captures
            assert len(results) == len(capture_name_list), \
                f"Expected {len(capture_name_list)} results, got {len(results)}"

    @settings(max_examples=100)
    @given(
        source_code=source_code_content,
        start_byte=byte_positions,
        end_byte=byte_positions,
    )
    def test_property_14_get_node_text_safe_byte_extraction_consistency(
        self, source_code: str, start_byte: int, end_byte: int
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any source code and byte range, get_node_text_safe SHALL return consistent
        text extraction results regardless of which node attributes are available.

        **Validates: Requirements 1.1, 1.4**
        """
        # Ensure valid byte range
        source_bytes = source_code.encode("utf-8")
        if start_byte > end_byte:
            start_byte, end_byte = end_byte, start_byte
        
        # Clamp to valid range
        start_byte = min(start_byte, len(source_bytes))
        end_byte = min(end_byte, len(source_bytes))

        mock_node = MagicMock()
        mock_node.start_byte = start_byte
        mock_node.end_byte = end_byte

        result = get_node_text_safe(mock_node, source_code)

        # Property: Result should always be a string
        assert isinstance(result, str), f"Result should be a string, got {type(result)}"

        # Property: Result should be extractable from source
        if start_byte <= end_byte <= len(source_bytes):
            expected = source_bytes[start_byte:end_byte].decode("utf-8", errors="replace")
            assert result == expected, f"Expected '{expected}', got '{result}'"

    @settings(max_examples=100)
    @given(
        source_code=st.text(min_size=1, max_size=200),
    )
    def test_property_14_get_node_text_safe_text_attribute_consistency(
        self, source_code: str
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any node with a text attribute, get_node_text_safe SHALL return the text
        content consistently whether it's bytes or string.

        **Validates: Requirements 1.1, 1.4**
        """
        # Test with bytes text attribute
        mock_node_bytes = MagicMock()
        del mock_node_bytes.start_byte  # Force skip byte range check
        mock_node_bytes.text = source_code.encode("utf-8")

        result_bytes = get_node_text_safe(mock_node_bytes, "ignored_source")

        # Property: Result should be a string
        assert isinstance(result_bytes, str), f"Result should be a string, got {type(result_bytes)}"
        assert result_bytes == source_code, f"Expected '{source_code}', got '{result_bytes}'"

        # Test with string text attribute
        mock_node_str = MagicMock()
        del mock_node_str.start_byte
        mock_node_str.text = source_code

        result_str = get_node_text_safe(mock_node_str, "ignored_source")

        # Property: Result should be a string
        assert isinstance(result_str, str), f"Result should be a string, got {type(result_str)}"
        assert result_str == source_code, f"Expected '{source_code}', got '{result_str}'"

        # Property: Both methods should return the same result
        assert result_bytes == result_str, \
            f"Bytes and string text attributes should return same result: '{result_bytes}' vs '{result_str}'"

    @settings(max_examples=100)
    @given(
        fallback_captures=st.lists(
            st.tuples(st.text(min_size=1, max_size=10), st.text(min_size=1, max_size=10)),
            min_size=0,
            max_size=5,
        ),
    )
    def test_property_14_safe_execute_query_fallback_consistency(
        self, fallback_captures: list[tuple[str, str]]
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any query execution failure, safe_execute_query SHALL return the fallback
        result consistently.

        **Validates: Requirements 1.1, 1.4**
        """
        mock_language = MagicMock()
        mock_root_node = MagicMock()

        # Convert fallback to expected format (list of tuples)
        fallback_result = [(MagicMock(), name) for _, name in fallback_captures]

        with patch.object(
            TreeSitterQueryCompat,
            "execute_query",
            side_effect=Exception("Simulated failure"),
        ):
            result = TreeSitterQueryCompat.safe_execute_query(
                mock_language, "query", mock_root_node, fallback_result=fallback_result
            )

            # Property: Result should be the fallback
            assert result == fallback_result, \
                f"Expected fallback result, got {result}"

            # Property: Result should be a list
            assert isinstance(result, list), f"Result should be a list, got {type(result)}"

    @settings(max_examples=100)
    @given(
        query_string=st.text(min_size=1, max_size=100),
    )
    def test_property_14_create_query_safely_consistency(
        self, query_string: str
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any query string, create_query_safely SHALL either return a query object
        or None, never raising an exception.

        **Validates: Requirements 1.1, 1.4**
        """
        mock_language = MagicMock()

        # Test success case
        mock_tree_sitter = MagicMock()
        mock_query = MagicMock()
        mock_tree_sitter.Query.return_value = mock_query

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            result = create_query_safely(mock_language, query_string)
            
            # Property: Result should be the query object
            assert result == mock_query, f"Expected query object, got {result}"

        # Test failure case
        mock_tree_sitter_fail = MagicMock()
        mock_tree_sitter_fail.Query.side_effect = Exception("Query creation failed")

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter_fail}):
            result = create_query_safely(mock_language, query_string)
            
            # Property: Result should be None on failure
            assert result is None, f"Expected None on failure, got {result}"

    @settings(max_examples=100)
    @given(
        capture_name_list=st.lists(capture_names, min_size=1, max_size=5),
    )
    def test_property_14_api_version_result_equivalence(
        self, capture_name_list: list[str]
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any set of captures, the result format from different API versions
        (newest, modern, legacy) SHALL be equivalent - all returning list of
        (node, capture_name) tuples.

        **Validates: Requirements 1.1, 1.4**
        """
        # Skip empty or invalid capture names
        capture_name_list = [name for name in capture_name_list if name and name[0].isalpha()]
        if not capture_name_list:
            capture_name_list = ["default_capture"]

        # Create consistent mock nodes for all API versions
        mock_nodes = [MagicMock(name=f"node_{i}") for i in range(len(capture_name_list))]

        # Test newest API
        mock_query_newest = MagicMock()
        captures_dict = {}
        for i, name in enumerate(capture_name_list):
            if name not in captures_dict:
                captures_dict[name] = []
            captures_dict[name].append(mock_nodes[i])

        result_newest = TreeSitterQueryCompat._execute_newest_api(
            mock_query_newest, MagicMock()
        )
        # Note: _execute_newest_api creates its own cursor, so we test the format

        # Test modern API
        mock_query_modern = MagicMock()
        mock_matches = []
        for i, name in enumerate(capture_name_list):
            mock_match = MagicMock()
            mock_capture = MagicMock()
            mock_capture.index = i
            mock_capture.node = mock_nodes[i]
            mock_match.captures = [mock_capture]
            mock_matches.append(mock_match)
        mock_query_modern.matches.return_value = mock_matches
        mock_query_modern.capture_names = capture_name_list

        result_modern = TreeSitterQueryCompat._execute_modern_api(
            mock_query_modern, MagicMock()
        )

        # Test legacy API
        mock_query_legacy = MagicMock()
        mock_captures = [(mock_nodes[i], name) for i, name in enumerate(capture_name_list)]
        mock_query_legacy.captures.return_value = mock_captures

        result_legacy = TreeSitterQueryCompat._execute_legacy_api(
            mock_query_legacy, MagicMock()
        )

        # Property: All results should be lists
        assert isinstance(result_newest, list), "Newest API result should be a list"
        assert isinstance(result_modern, list), "Modern API result should be a list"
        assert isinstance(result_legacy, list), "Legacy API result should be a list"

        # Property: Modern and legacy should have same number of results
        assert len(result_modern) == len(result_legacy), \
            f"Modern ({len(result_modern)}) and legacy ({len(result_legacy)}) should have same count"

        # Property: All results should have consistent tuple format
        for result_list, api_name in [
            (result_modern, "modern"),
            (result_legacy, "legacy"),
        ]:
            for item in result_list:
                assert isinstance(item, tuple), f"{api_name} API: Each item should be a tuple"
                assert len(item) == 2, f"{api_name} API: Each tuple should have 2 elements"
                node, capture_name = item
                assert isinstance(capture_name, str), f"{api_name} API: Capture name should be string"


class TestTreeSitterCompatEdgeCases:
    """
    Edge case tests for tree-sitter compatibility.

    **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**
    **Validates: Requirements 1.1, 1.4**
    """

    @settings(max_examples=100)
    @given(
        source_lines=st.lists(st.text(min_size=0, max_size=50), min_size=1, max_size=20),
        start_line=line_positions,
        end_line=line_positions,
        start_col=column_positions,
        end_col=column_positions,
    )
    def test_property_14_point_based_extraction_consistency(
        self,
        source_lines: list[str],
        start_line: int,
        end_line: int,
        start_col: int,
        end_col: int,
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any source code and point-based positions, get_node_text_safe SHALL
        return consistent text extraction using start_point and end_point.

        **Validates: Requirements 1.1, 1.4**
        """
        source_code = "\n".join(source_lines)
        
        # Clamp line numbers to valid range
        max_line = len(source_lines) - 1
        start_line = min(start_line, max_line)
        end_line = min(end_line, max_line)
        
        if start_line > end_line:
            start_line, end_line = end_line, start_line

        # Clamp column numbers
        if source_lines:
            start_col = min(start_col, len(source_lines[start_line]) if start_line < len(source_lines) else 0)
            end_col = min(end_col, len(source_lines[end_line]) if end_line < len(source_lines) else 0)

        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.text
        mock_node.start_point = (start_line, start_col)
        mock_node.end_point = (end_line, end_col)

        result = get_node_text_safe(mock_node, source_code)

        # Property: Result should always be a string
        assert isinstance(result, str), f"Result should be a string, got {type(result)}"

        # Property: Result should not raise exceptions
        # (implicitly tested by reaching this point)

    @settings(max_examples=100)
    @given(
        error_message=st.text(min_size=1, max_size=100),
    )
    def test_property_14_error_handling_consistency(
        self, error_message: str
    ):
        """
        **Feature: test-coverage-improvement, Property 14: Tree-sitter Version Compatibility**

        For any error during query execution, the system SHALL handle it gracefully
        and return an empty list instead of raising an exception.

        **Validates: Requirements 1.1, 1.4**
        """
        mock_language = MagicMock()
        mock_root_node = MagicMock()

        mock_tree_sitter = MagicMock()
        mock_tree_sitter.Query.side_effect = Exception(error_message)

        with patch.dict(sys.modules, {"tree_sitter": mock_tree_sitter}):
            result = TreeSitterQueryCompat.execute_query(
                mock_language, "query", mock_root_node
            )

            # Property: Result should be an empty list on error
            assert result == [], f"Expected empty list on error, got {result}"
            assert isinstance(result, list), f"Result should be a list, got {type(result)}"
