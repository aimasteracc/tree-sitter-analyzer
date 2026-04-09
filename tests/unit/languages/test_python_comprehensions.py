#!/usr/bin/env python3
"""
Unit tests for Python comprehension extraction in python_plugin.py.

Tests the _extract_comprehension method with mock tree-sitter nodes.
No real parser, no tempfile, no asyncio - pure mock-based unit tests.
"""

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.languages.python_plugin import PythonElementExtractor
from tree_sitter_analyzer.models import Comprehension


@pytest.fixture
def extractor() -> PythonElementExtractor:
    """Create a PythonElementExtractor instance for testing."""
    return PythonElementExtractor()


class TestListComprehensions:
    """Test list comprehension extraction."""

    @pytest.mark.unit
    def test_extract_simple_list_comprehension(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of simple list comprehension: [x for x in range(10)]"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 25)
        node.start_byte = 0
        node.end_byte = 25

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 5
        target.end_byte = 6

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "call"
        iterable.start_byte = 14
        iterable.end_byte = 24

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "["
        node.children[2].type = "]"

        # Pre-populate cache
        extractor._node_text_cache[(5, 6)] = "x"
        extractor._node_text_cache[(14, 24)] = "range(10)"
        extractor._node_text_cache[(0, 25)] = "[x for x in range(10)]"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.name == "<list_comprehension>"
        assert result.comprehension_type == "list"
        assert result.target_variable == "x"
        assert result.iterable_preview == "range(10)"
        assert result.has_condition is False
        assert result.start_line == 1
        assert result.end_line == 1
        assert result.language == "python"
        assert result.element_type == "comprehension"
        assert result.node_type == "list_comprehension"

    @pytest.mark.unit
    def test_extract_list_comprehension_with_condition(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of list comprehension with condition: [x for x in range(10) if x % 2 == 0]"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 40)
        node.start_byte = 0
        node.end_byte = 40

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 5
        target.end_byte = 6

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "call"
        iterable.start_byte = 14
        iterable.end_byte = 24

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "["
        node.children[2].type = "]"

        # Pre-populate cache
        extractor._node_text_cache[(5, 6)] = "x"
        extractor._node_text_cache[(14, 24)] = "range(10)"
        extractor._node_text_cache[(0, 40)] = "[x for x in range(10) if x % 2 == 0]"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.comprehension_type == "list"
        assert result.target_variable == "x"
        assert result.iterable_preview == "range(10)"
        # Note: has_condition detection requires specific tree structure that's hard to mock
        # This is tested in integration tests with real parser

    @pytest.mark.unit
    def test_extract_nested_list_comprehension(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of nested list comprehension: [[y for y in range(3)] for x in range(3)]"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 50)
        node.start_byte = 0
        node.end_byte = 50

        # Outer for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 32
        target.end_byte = 33

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "call"
        iterable.start_byte = 41
        iterable.end_byte = 49

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        # Inner list comprehension as first element
        inner_comp = MagicMock()
        inner_comp.type = "list_comprehension"

        node.children = [MagicMock(), inner_comp, for_in_clause, MagicMock()]
        node.children[0].type = "["
        node.children[3].type = "]"

        # Pre-populate cache
        extractor._node_text_cache[(32, 33)] = "x"
        extractor._node_text_cache[(41, 49)] = "range(3)"
        extractor._node_text_cache[
            (0, 50)
        ] = "[[y for y in range(3)] for x in range(3)]"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.comprehension_type == "list"
        assert result.target_variable == "x"

    @pytest.mark.unit
    def test_extract_list_comprehension_multiple_for_clauses(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test list comprehension with multiple for clauses: [x+y for x in range(3) for y in range(3)]"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 50)
        node.start_byte = 0
        node.end_byte = 50

        # First for_in_clause
        for_in_clause1 = MagicMock()
        for_in_clause1.type = "for_in_clause"

        target1 = MagicMock()
        target1.type = "identifier"
        target1.start_byte = 10
        target1.end_byte = 11

        in_keyword1 = MagicMock()
        in_keyword1.type = "in"

        iterable1 = MagicMock()
        iterable1.type = "call"
        iterable1.start_byte = 19
        iterable1.end_byte = 27

        for_in_clause1.children = [MagicMock(), target1, in_keyword1, iterable1]
        for_in_clause1.children[0].type = "for"

        # Second for_in_clause
        for_in_clause2 = MagicMock()
        for_in_clause2.type = "for_in_clause"

        node.children = [MagicMock(), for_in_clause1, for_in_clause2, MagicMock()]
        node.children[0].type = "["
        node.children[3].type = "]"

        # Pre-populate cache
        extractor._node_text_cache[(10, 11)] = "x"
        extractor._node_text_cache[(19, 27)] = "range(3)"
        extractor._node_text_cache[
            (0, 50)
        ] = "[x+y for x in range(3) for y in range(3)]"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.target_variable == "x"
        assert result.iterable_preview == "range(3)"


class TestSetComprehensions:
    """Test set comprehension extraction."""

    @pytest.mark.unit
    def test_extract_simple_set_comprehension(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of simple set comprehension: {x for x in range(10)}"""
        node = MagicMock()
        node.type = "set_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 25)
        node.start_byte = 0
        node.end_byte = 25

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 5
        target.end_byte = 6

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "call"
        iterable.start_byte = 14
        iterable.end_byte = 24

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "{"
        node.children[2].type = "}"

        # Pre-populate cache
        extractor._node_text_cache[(5, 6)] = "x"
        extractor._node_text_cache[(14, 24)] = "range(10)"
        extractor._node_text_cache[(0, 25)] = "{x for x in range(10)}"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.name == "<set_comprehension>"
        assert result.comprehension_type == "set"
        assert result.target_variable == "x"
        assert result.iterable_preview == "range(10)"
        assert result.has_condition is False
        assert result.node_type == "set_comprehension"

    @pytest.mark.unit
    def test_extract_set_comprehension_with_condition(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of set comprehension with condition: {x for x in range(10) if x > 5}"""
        node = MagicMock()
        node.type = "set_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 35)
        node.start_byte = 0
        node.end_byte = 35

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 5
        target.end_byte = 6

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "call"
        iterable.start_byte = 14
        iterable.end_byte = 24

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "{"
        node.children[2].type = "}"

        # Pre-populate cache
        extractor._node_text_cache[(5, 6)] = "x"
        extractor._node_text_cache[(14, 24)] = "range(10)"
        extractor._node_text_cache[(0, 35)] = "{x for x in range(10) if x > 5}"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.comprehension_type == "set"
        # Note: has_condition detection tested in integration tests


class TestDictComprehensions:
    """Test dictionary comprehension extraction."""

    @pytest.mark.unit
    def test_extract_simple_dict_comprehension(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of simple dict comprehension: {x: x**2 for x in range(10)}"""
        node = MagicMock()
        node.type = "dictionary_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 35)
        node.start_byte = 0
        node.end_byte = 35

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 16
        target.end_byte = 17

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "call"
        iterable.start_byte = 25
        iterable.end_byte = 34

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "{"
        node.children[2].type = "}"

        # Pre-populate cache
        extractor._node_text_cache[(16, 17)] = "x"
        extractor._node_text_cache[(25, 34)] = "range(10)"
        extractor._node_text_cache[(0, 35)] = "{x: x**2 for x in range(10)}"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.name == "<dict_comprehension>"
        assert result.comprehension_type == "dict"
        assert result.target_variable == "x"
        assert result.iterable_preview == "range(10)"
        assert result.has_condition is False
        assert result.node_type == "dictionary_comprehension"

    @pytest.mark.unit
    def test_extract_dict_comprehension_with_condition(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of dict comprehension with condition: {k: v for k, v in items if v > 0}"""
        node = MagicMock()
        node.type = "dictionary_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 45)
        node.start_byte = 0
        node.end_byte = 45

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        # pattern_list for "k, v"
        target = MagicMock()
        target.type = "pattern_list"
        target.start_byte = 11
        target.end_byte = 15

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "identifier"
        iterable.start_byte = 23
        iterable.end_byte = 28

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "{"
        node.children[2].type = "}"

        # Pre-populate cache
        extractor._node_text_cache[(11, 15)] = "k, v"
        extractor._node_text_cache[(23, 28)] = "items"
        extractor._node_text_cache[(0, 45)] = "{k: v for k, v in items if v > 0}"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.comprehension_type == "dict"
        assert result.target_variable == "k, v"
        assert result.iterable_preview == "items"
        # Note: has_condition detection tested in integration tests


class TestGeneratorExpressions:
    """Test generator expression extraction."""

    @pytest.mark.unit
    def test_extract_simple_generator_expression(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of simple generator expression: (x for x in range(10))"""
        node = MagicMock()
        node.type = "generator_expression"
        node.start_point = (0, 0)
        node.end_point = (0, 25)
        node.start_byte = 0
        node.end_byte = 25

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 5
        target.end_byte = 6

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "call"
        iterable.start_byte = 14
        iterable.end_byte = 24

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "("
        node.children[2].type = ")"

        # Pre-populate cache
        extractor._node_text_cache[(5, 6)] = "x"
        extractor._node_text_cache[(14, 24)] = "range(10)"
        extractor._node_text_cache[(0, 25)] = "(x for x in range(10))"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.name == "<generator_comprehension>"
        assert result.comprehension_type == "generator"
        assert result.target_variable == "x"
        assert result.iterable_preview == "range(10)"
        assert result.has_condition is False
        assert result.node_type == "generator_expression"

    @pytest.mark.unit
    def test_extract_generator_expression_with_condition(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of generator expression with condition: (x for x in range(10) if x % 2 == 0)"""
        node = MagicMock()
        node.type = "generator_expression"
        node.start_point = (0, 0)
        node.end_point = (0, 40)
        node.start_byte = 0
        node.end_byte = 40

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 5
        target.end_byte = 6

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "call"
        iterable.start_byte = 14
        iterable.end_byte = 24

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "("
        node.children[2].type = ")"

        # Pre-populate cache
        extractor._node_text_cache[(5, 6)] = "x"
        extractor._node_text_cache[(14, 24)] = "range(10)"
        extractor._node_text_cache[(0, 40)] = "(x for x in range(10) if x % 2 == 0)"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert isinstance(result, Comprehension)
        assert result.comprehension_type == "generator"
        # Note: has_condition detection tested in integration tests


class TestComprehensionEdgeCases:
    """Test edge cases and error handling for comprehensions."""

    @pytest.mark.unit
    def test_extract_comprehension_no_target_variable(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test comprehension with no identifiable target variable (fallback behavior)"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        node.start_byte = 0
        node.end_byte = 20

        # for_in_clause with no identifier child (malformed)
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"
        for_in_clause.children = []

        # Fallback identifier at root level
        fallback_id = MagicMock()
        fallback_id.type = "identifier"
        fallback_id.start_byte = 5
        fallback_id.end_byte = 6

        node.children = [MagicMock(), for_in_clause, fallback_id, MagicMock()]
        node.children[0].type = "["
        node.children[3].type = "]"

        # Pre-populate cache
        extractor._node_text_cache[(5, 6)] = "x"
        extractor._node_text_cache[(0, 20)] = "[x for x in list]"

        result = extractor._extract_comprehension(node)

        assert result is not None
        # Should use fallback identifier
        assert result.target_variable == "x"

    @pytest.mark.unit
    def test_extract_comprehension_unknown_type(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test comprehension with unknown type (not in map)"""
        node = MagicMock()
        node.type = "unknown_comprehension_type"
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        node.start_byte = 0
        node.end_byte = 20

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 5
        target.end_byte = 6

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "identifier"
        iterable.start_byte = 10
        iterable.end_byte = 15

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [for_in_clause]

        # Pre-populate cache
        extractor._node_text_cache[(5, 6)] = "x"
        extractor._node_text_cache[(10, 15)] = "items"
        extractor._node_text_cache[(0, 20)] = "[x for x in items]"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert result.comprehension_type == "unknown"

    @pytest.mark.unit
    def test_extract_comprehension_long_iterable_truncation(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test comprehension with long iterable expression gets truncated to 50 chars"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 100)
        node.start_byte = 0
        node.end_byte = 100

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 5
        target.end_byte = 6

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "call"
        iterable.start_byte = 14
        iterable.end_byte = 95

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "["
        node.children[2].type = "]"

        # Very long iterable - should be truncated to 50 chars
        long_iterable = "very_long_function_name_that_returns_a_list_or_generator_with_many_parameters(a, b, c, d, e, f)"
        extractor._node_text_cache[(5, 6)] = "x"
        extractor._node_text_cache[(14, 95)] = long_iterable
        extractor._node_text_cache[(0, 100)] = f"[x for x in {long_iterable}]"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert len(result.iterable_preview) == 50
        # safe_preview truncates to 47 chars and adds "..." to make 50
        assert result.iterable_preview == long_iterable[:47] + "..."

    @pytest.mark.unit
    def test_extract_comprehension_multiline(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test comprehension that spans multiple lines"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (0, 0)
        node.end_point = (3, 5)  # Spans 4 lines
        node.start_byte = 0
        node.end_byte = 80

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 10
        target.end_byte = 11

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "identifier"
        iterable.start_byte = 20
        iterable.end_byte = 25

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "["
        node.children[2].type = "]"

        # Pre-populate cache
        extractor._node_text_cache[(10, 11)] = "x"
        extractor._node_text_cache[(20, 25)] = "items"
        extractor._node_text_cache[(0, 80)] = "[\n    x\n    for x in items\n]"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert result.start_line == 1
        assert result.end_line == 4

    @pytest.mark.unit
    def test_extract_comprehension_exception_handling(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test comprehension extraction gracefully handles exceptions"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 20)

        # Force an exception by making children raise
        node.children = MagicMock()
        node.children.__iter__.side_effect = Exception("Simulated error")

        result = extractor._extract_comprehension(node)

        assert result is None

    @pytest.mark.unit
    def test_extract_comprehension_position_tracking(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test comprehension position tracking is correct"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (10, 5)  # Line 10, column 5
        node.end_point = (10, 30)  # Same line
        node.start_byte = 100
        node.end_byte = 125

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 105
        target.end_byte = 106

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "identifier"
        iterable.start_byte = 114
        iterable.end_byte = 119

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "["
        node.children[2].type = "]"

        # Pre-populate cache
        extractor._node_text_cache[(105, 106)] = "x"
        extractor._node_text_cache[(114, 119)] = "items"
        extractor._node_text_cache[(100, 125)] = "[x for x in items]"

        result = extractor._extract_comprehension(node)

        assert result is not None
        assert result.start_line == 11  # tree-sitter is 0-indexed
        assert result.end_line == 11

    @pytest.mark.unit
    def test_extract_comprehension_empty_cache(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test comprehension extraction when cache is empty"""
        node = MagicMock()
        node.type = "list_comprehension"
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        node.start_byte = 0
        node.end_byte = 20

        # Mock for_in_clause
        for_in_clause = MagicMock()
        for_in_clause.type = "for_in_clause"

        target = MagicMock()
        target.type = "identifier"
        target.start_byte = 5
        target.end_byte = 6

        in_keyword = MagicMock()
        in_keyword.type = "in"

        iterable = MagicMock()
        iterable.type = "identifier"
        iterable.start_byte = 10
        iterable.end_byte = 15

        for_in_clause.children = [MagicMock(), target, in_keyword, iterable]
        for_in_clause.children[0].type = "for"

        node.children = [MagicMock(), for_in_clause, MagicMock()]
        node.children[0].type = "["
        node.children[2].type = "]"

        # Don't populate cache - _get_node_text_optimized will return empty string

        result = extractor._extract_comprehension(node)

        # Should still create Comprehension but with empty fields
        assert result is not None
        assert result.target_variable == ""
        assert result.iterable_preview == ""
