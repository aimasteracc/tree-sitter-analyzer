#!/usr/bin/env python3
"""
Unit tests for Python expression extraction in python_plugin.py.

Tests the _extract_expression method with mock tree-sitter nodes.
No real parser, no tempfile, no asyncio - pure mock-based unit tests.
"""

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.languages.python_plugin import PythonElementExtractor
from tree_sitter_analyzer.models import Expression


@pytest.fixture
def extractor() -> PythonElementExtractor:
    """Create a PythonElementExtractor instance for testing."""
    return PythonElementExtractor()


class TestConditionalExpressions:
    """Test conditional expression extraction."""

    @pytest.mark.unit
    def test_extract_simple_conditional_expression(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of simple conditional expression: x if condition else y"""
        node = MagicMock()
        node.type = "conditional_expression"
        node.start_point = (0, 0)
        node.end_point = (0, 25)
        node.start_byte = 0
        node.end_byte = 25

        # Pre-populate cache
        extractor._node_text_cache[(0, 25)] = "x if condition else y"

        result = extractor._extract_expression(node)

        assert result is not None
        assert isinstance(result, Expression)
        assert result.name == "<conditional>"
        assert result.expression_kind == "conditional"
        assert result.preview == "x if condition else y"
        assert result.start_line == 1
        assert result.end_line == 1
        assert result.language == "python"
        assert result.element_type == "expression"
        assert result.node_type == "conditional_expression"

    @pytest.mark.unit
    def test_extract_nested_conditional_expression(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of nested conditional: a if b else (c if d else e)"""
        node = MagicMock()
        node.type = "conditional_expression"
        node.start_point = (0, 0)
        node.end_point = (0, 35)
        node.start_byte = 0
        node.end_byte = 35

        # Pre-populate cache
        extractor._node_text_cache[(0, 35)] = "a if b else (c if d else e)"

        result = extractor._extract_expression(node)

        assert result is not None
        assert isinstance(result, Expression)
        assert result.expression_kind == "conditional"
        assert result.preview == "a if b else (c if d else e)"

    @pytest.mark.unit
    def test_extract_conditional_in_assignment(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test conditional expression in assignment: result = value if condition else fallback"""
        node = MagicMock()
        node.type = "conditional_expression"
        node.start_point = (0, 9)
        node.end_point = (0, 45)
        node.start_byte = 9
        node.end_byte = 45

        # Pre-populate cache
        extractor._node_text_cache[(9, 45)] = "value if condition else fallback"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.start_line == 1
        assert result.expression_kind == "conditional"

    @pytest.mark.unit
    def test_extract_conditional_complex_condition(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test conditional with complex boolean condition"""
        node = MagicMock()
        node.type = "conditional_expression"
        node.start_point = (0, 0)
        node.end_point = (0, 50)
        node.start_byte = 0
        node.end_byte = 50

        # Pre-populate cache
        extractor._node_text_cache[
            (0, 50)
        ] = "result if x > 0 and y < 10 or z == 5 else default"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.preview == "result if x > 0 and y < 10 or z == 5 else default"


class TestSubscriptExpressions:
    """Test subscript expression extraction."""

    @pytest.mark.unit
    def test_extract_list_indexing(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of list indexing: my_list[0]"""
        node = MagicMock()
        node.type = "subscript"
        node.start_point = (0, 0)
        node.end_point = (0, 11)
        node.start_byte = 0
        node.end_byte = 11

        # Pre-populate cache
        extractor._node_text_cache[(0, 11)] = "my_list[0]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert isinstance(result, Expression)
        assert result.name == "<subscript>"
        assert result.expression_kind == "subscript"
        assert result.preview == "my_list[0]"
        assert result.node_type == "subscript"

    @pytest.mark.unit
    def test_extract_dict_key_access(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of dict key access: my_dict['key']"""
        node = MagicMock()
        node.type = "subscript"
        node.start_point = (0, 0)
        node.end_point = (0, 16)
        node.start_byte = 0
        node.end_byte = 16

        # Pre-populate cache
        extractor._node_text_cache[(0, 16)] = "my_dict['key']"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.expression_kind == "subscript"
        assert result.preview == "my_dict['key']"

    @pytest.mark.unit
    def test_extract_nested_subscript(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of nested subscript: matrix[i][j]"""
        node = MagicMock()
        node.type = "subscript"
        node.start_point = (0, 0)
        node.end_point = (0, 13)
        node.start_byte = 0
        node.end_byte = 13

        # Pre-populate cache
        extractor._node_text_cache[(0, 13)] = "matrix[i][j]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.expression_kind == "subscript"
        assert result.preview == "matrix[i][j]"

    @pytest.mark.unit
    def test_extract_slice_expression(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of slice expression: my_list[1:5]"""
        node = MagicMock()
        node.type = "subscript"
        node.start_point = (0, 0)
        node.end_point = (0, 13)
        node.start_byte = 0
        node.end_byte = 13

        # Pre-populate cache
        extractor._node_text_cache[(0, 13)] = "my_list[1:5]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.expression_kind == "subscript"
        assert result.preview == "my_list[1:5]"

    @pytest.mark.unit
    def test_extract_slice_with_step(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of slice with step: my_list[::2]"""
        node = MagicMock()
        node.type = "subscript"
        node.start_point = (0, 0)
        node.end_point = (0, 13)
        node.start_byte = 0
        node.end_byte = 13

        # Pre-populate cache
        extractor._node_text_cache[(0, 13)] = "my_list[::2]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.expression_kind == "subscript"
        assert result.preview == "my_list[::2]"


class TestListLiterals:
    """Test list literal extraction."""

    @pytest.mark.unit
    def test_extract_empty_list(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of empty list: []"""
        node = MagicMock()
        node.type = "list"
        node.start_point = (0, 0)
        node.end_point = (0, 2)
        node.start_byte = 0
        node.end_byte = 2

        # Pre-populate cache
        extractor._node_text_cache[(0, 2)] = "[]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert isinstance(result, Expression)
        assert result.name == "<list>"
        assert result.expression_kind == "list"
        assert result.preview == "[]"
        assert result.node_type == "list"

    @pytest.mark.unit
    def test_extract_simple_list(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of simple list: [1, 2, 3]"""
        node = MagicMock()
        node.type = "list"
        node.start_point = (0, 0)
        node.end_point = (0, 9)
        node.start_byte = 0
        node.end_byte = 9

        # Pre-populate cache
        extractor._node_text_cache[(0, 9)] = "[1, 2, 3]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.expression_kind == "list"
        assert result.preview == "[1, 2, 3]"

    @pytest.mark.unit
    def test_extract_nested_list(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of nested list: [[1, 2], [3, 4]]"""
        node = MagicMock()
        node.type = "list"
        node.start_point = (0, 0)
        node.end_point = (0, 18)
        node.start_byte = 0
        node.end_byte = 18

        # Pre-populate cache
        extractor._node_text_cache[(0, 18)] = "[[1, 2], [3, 4]]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.expression_kind == "list"
        assert result.preview == "[[1, 2], [3, 4]]"

    @pytest.mark.unit
    def test_extract_mixed_type_list(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of mixed type list: [1, "two", 3.0, True]"""
        node = MagicMock()
        node.type = "list"
        node.start_point = (0, 0)
        node.end_point = (0, 22)
        node.start_byte = 0
        node.end_byte = 22

        # Pre-populate cache
        extractor._node_text_cache[(0, 22)] = '[1, "two", 3.0, True]'

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.expression_kind == "list"
        assert result.preview == '[1, "two", 3.0, True]'

    @pytest.mark.unit
    def test_extract_multiline_list(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of multiline list"""
        node = MagicMock()
        node.type = "list"
        node.start_point = (0, 0)
        node.end_point = (3, 1)
        node.start_byte = 0
        node.end_byte = 30

        # Pre-populate cache
        extractor._node_text_cache[(0, 30)] = "[\n    1,\n    2,\n    3\n]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.start_line == 1
        assert result.end_line == 4


class TestExpressionEdgeCases:
    """Test edge cases and error handling for expressions."""

    @pytest.mark.unit
    def test_extract_expression_long_preview_truncation(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test expression with long text gets truncated to 50 chars"""
        node = MagicMock()
        node.type = "conditional_expression"
        node.start_point = (0, 0)
        node.end_point = (0, 100)
        node.start_byte = 0
        node.end_byte = 100

        # Very long expression - should be truncated to 50 chars
        long_expr = "very_long_variable_name if very_long_condition_that_checks_multiple_things else another_very_long_fallback_value"
        extractor._node_text_cache[(0, 100)] = long_expr

        result = extractor._extract_expression(node)

        assert result is not None
        assert len(result.preview) == 50
        # safe_preview truncates to 47 chars and adds "..." to make 50
        assert result.preview == long_expr[:47] + "..."

    @pytest.mark.unit
    def test_extract_expression_unknown_kind(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test expression with unknown kind (not in map)"""
        node = MagicMock()
        node.type = "unknown_expression_type"
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        node.start_byte = 0
        node.end_byte = 20

        # Pre-populate cache
        extractor._node_text_cache[(0, 20)] = "some_expression"

        result = extractor._extract_expression(node)

        assert result is not None
        # Should use node.type as expression_kind
        assert result.expression_kind == "unknown_expression_type"

    @pytest.mark.unit
    def test_extract_expression_no_text(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test expression extraction fails when text is empty"""
        node = MagicMock()
        node.type = "conditional_expression"
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        node.start_byte = 0
        node.end_byte = 10

        # Don't populate cache - will return empty string

        result = extractor._extract_expression(node)

        assert result is None

    @pytest.mark.unit
    def test_extract_expression_position_tracking(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test expression position tracking is correct"""
        node = MagicMock()
        node.type = "subscript"
        node.start_point = (15, 8)  # Line 15, column 8
        node.end_point = (15, 20)  # Same line
        node.start_byte = 200
        node.end_byte = 212

        # Pre-populate cache
        extractor._node_text_cache[(200, 212)] = "my_list[0]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.start_line == 16  # tree-sitter is 0-indexed
        assert result.end_line == 16

    @pytest.mark.unit
    def test_extract_expression_exception_handling(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test expression extraction gracefully handles exceptions"""
        node = MagicMock()
        node.type = "conditional_expression"
        node.start_point = (0, 0)
        node.end_point = (0, 20)

        # Force an exception by making start_point raise
        node.start_point = property(lambda self: 1 / 0)

        result = extractor._extract_expression(node)

        assert result is None

    @pytest.mark.unit
    def test_extract_expression_multiline_conditional(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test multiline conditional expression"""
        node = MagicMock()
        node.type = "conditional_expression"
        node.start_point = (0, 0)
        node.end_point = (2, 10)
        node.start_byte = 0
        node.end_byte = 60

        # Pre-populate cache
        extractor._node_text_cache[
            (0, 60)
        ] = "very_long_value\n    if complex_condition\n    else fallback"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.start_line == 1
        assert result.end_line == 3

    @pytest.mark.unit
    def test_extract_expression_raw_text_preservation(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test that raw_text preserves original expression text"""
        node = MagicMock()
        node.type = "subscript"
        node.start_point = (0, 0)
        node.end_point = (0, 13)
        node.start_byte = 0
        node.end_byte = 13

        original_text = "matrix[i][j]"
        extractor._node_text_cache[(0, 13)] = original_text

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.raw_text == original_text
        assert result.preview == original_text

    @pytest.mark.unit
    def test_extract_expression_conditional_with_function_calls(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test conditional expression containing function calls"""
        node = MagicMock()
        node.type = "conditional_expression"
        node.start_point = (0, 0)
        node.end_point = (0, 45)
        node.start_byte = 0
        node.end_byte = 45

        # Pre-populate cache
        extractor._node_text_cache[
            (0, 45)
        ] = "func1(x) if is_valid(x) else func2(x)"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.preview == "func1(x) if is_valid(x) else func2(x)"

    @pytest.mark.unit
    def test_extract_expression_subscript_with_expression_key(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test subscript with complex expression as key"""
        node = MagicMock()
        node.type = "subscript"
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        node.start_byte = 0
        node.end_byte = 20

        # Pre-populate cache
        extractor._node_text_cache[(0, 20)] = "my_dict[key1 + key2]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.preview == "my_dict[key1 + key2]"

    @pytest.mark.unit
    def test_extract_expression_list_with_comprehension_element(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test list containing a comprehension as an element"""
        node = MagicMock()
        node.type = "list"
        node.start_point = (0, 0)
        node.end_point = (0, 30)
        node.start_byte = 0
        node.end_byte = 30

        # Pre-populate cache
        extractor._node_text_cache[(0, 30)] = "[1, [x for x in range(3)], 2]"

        result = extractor._extract_expression(node)

        assert result is not None
        assert result.preview == "[1, [x for x in range(3)], 2]"
